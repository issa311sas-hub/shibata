"""Aggregate explicitly listed, hash-pinned evaluations without selecting by outcome."""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from .evaluation.baseline import evaluate_observed_results
from .ingestion.contracts import require, timestamp
from .score_saved import load_saved


def aggregate(ledger_path: Path, output: Path):
    output.mkdir(parents=True, exist_ok=False)
    status = dict(status='RUNNING', purpose='descriptive_aggregation_not_model_selection')
    try:
        ledger_bytes = ledger_path.read_bytes()
        ledger = json.loads(ledger_bytes)
        require(isinstance(ledger, list) and bool(ledger), 'Nonempty explicit run list required')
        predictions, results, seen, runs = [], [], set(), []
        for item in ledger:
            require(set(item) == {'prediction_dir', 'prediction_status_sha256', 'evaluation_dir',
                                  'evaluation_status_sha256'}, 'Invalid ledger keys')
            # Paths are relative to the ledger file, never to an implicit process cwd.
            pdir = ledger_path.parent / item['prediction_dir']
            edir = ledger_path.parent / item['evaluation_dir']
            raw = (edir / 'status.json').read_bytes()
            require(hashlib.sha256(raw).hexdigest() == item['evaluation_status_sha256'],
                    'Evaluation status hash mismatch')
            report = json.loads(raw)
            require(report['status'] == 'PASS' and report['prediction_recomputed'] is False,
                    'Only completed saved-prediction evaluations accepted')
            require(report['prediction_status_sha256'] == item['prediction_status_sha256'],
                    'Evaluation references a different prediction')
            expected_files = {'observed_results.csv', 'metrics.json', 'year.csv', 'popularity.csv',
                              'odds_rank.csv', 'odds_band.csv', 'calibration.csv'}
            require(set(report['output_sha256']) == expected_files, 'Unexpected evaluation output set')
            verified = {}
            for name, digest in report['output_sha256'].items():
                payload = (edir / name).read_bytes()
                require(hashlib.sha256(payload).hexdigest() == digest, 'Evaluation output hash mismatch')
                verified[name] = payload
            saved, prediction = load_saved(pdir, item['prediction_status_sha256'])
            require(report['prediction_sha256'] == saved['output_sha256']['predictions.csv'],
                    'Prediction hash does not match evaluation')
            race_id = saved['race_id']
            require(report['race_id'] == race_id and race_id not in seen, 'Duplicate or mismatched race')
            seen.add(race_id)
            from io import BytesIO
            labels = pd.read_csv(BytesIO(verified['observed_results.csv']), dtype='string', keep_default_na=False)
            # Recompute metrics from frozen predictions and labels, never average race means.
            metrics, _ = evaluate_observed_results(prediction, labels)
            original = json.loads(verified['metrics.json'])
            require(metrics == original, 'Evaluation metrics do not reproduce from saved inputs')
            predictions.append(prediction)
            results.append(labels)
            lead = (prediction.start_at.iloc[0] - timestamp(saved['prediction_at'])).total_seconds() / 60
            runs.append(dict(race_id=race_id, runners=len(prediction), cutoff_minutes_before_start=lead,
                             prediction_status_sha256=item['prediction_status_sha256'],
                             evaluation_status_sha256=item['evaluation_status_sha256']))
        metrics, tables = evaluate_observed_results(pd.concat(predictions, ignore_index=True),
                                                   pd.concat(results, ignore_index=True))
        (output / 'metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
        for name, table in tables.items():
            table.to_csv(output / f'{name}.csv', index=False)
        status.update(status='PASS', runs=runs, ledger_sha256=hashlib.sha256(ledger_bytes).hexdigest(),
                      omitted_runs=0, population_coverage='unknown; only explicitly listed runs',
                      fixed_cutoff_verified=False, phase_promotion=False)
        status['output_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(output.iterdir())}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        status.update(status='FAILED', error=str(exc))
        raise
    finally:
        (output / 'status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--ledger', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(aggregate(args.ledger, args.output_dir)))


if __name__ == '__main__':
    main()
