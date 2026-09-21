"""Score an immutable saved pre-race prediction against a separate result capture."""

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .evaluation.baseline import evaluate_observed_results
from .ingestion.capture import verify_capture
from .ingestion.contracts import DataError, require, timestamp, validate_table
from .ingestion.jv_race import decode_race_record


def now_utc():
    return pd.Timestamp.now(tz='UTC')


def load_saved(folder: Path, expected_status_sha256: str):
    """Pin status to a previously recorded hash and verify bytes before parsing."""
    raw = (folder / 'status.json').read_bytes()
    require(hashlib.sha256(raw).hexdigest() == expected_status_sha256, 'Saved status hash mismatch')
    status = json.loads(raw)
    require(status['status'] == 'PASS' and status['results_used'] is False
            and status['generated_before_scheduled_start'] is True,
            'Only successful predictions generated before the start may be scored')
    require(status['availability_mode'] == 'observed' and status['capture_manifest_verified'] is True,
            'Saved prediction must use verified observed inputs')
    require(set(status['output_sha256']) == {'races.csv', 'entries.csv', 'odds.csv', 'predictions.csv'},
            'Unexpected saved output set')
    tables = {}
    for name, digest in status['output_sha256'].items():
        payload = (folder / name).read_bytes()
        require(hashlib.sha256(payload).hexdigest() == digest, f'Saved output hash mismatch: {name}')
        tables[name] = pd.read_csv(BytesIO(payload), dtype='string', keep_default_na=False)
    races = validate_table(tables['races.csv'], 'races')
    entries = validate_table(tables['entries.csv'], 'entries')
    validate_table(tables['odds.csv'], 'odds')
    require(len(races) == 1 and races.iloc[0].race_id == status['race_id'], 'Expected one saved race')
    race = races.iloc[0]
    require(timestamp(status['prediction_at']) == race.prediction_at and
            race.prediction_at <= timestamp(status['generated_at']) < race.start_at,
            'Saved generation time must be between cutoff and start')
    predictions = tables['predictions.csv']
    require('win' not in predictions and 'final_rank_raw' not in predictions, 'Saved prediction contains results')
    for name in ('start_at', 'prediction_at'):
        predictions[name] = pd.to_datetime([timestamp(x) for x in predictions[name]], utc=True)
        require((predictions[name] == race[name]).all(), 'Prediction/race timestamp mismatch')
    for name in ('horse_number', 'runner_count', 'win_odds', 'popularity', 'odds_rank', 'market_probability'):
        predictions[name] = pd.to_numeric(predictions[name], errors='raise')
        require(np.isfinite(predictions[name]).all(), 'Invalid saved numeric value')
    keys = ['race_id', 'horse_id', 'horse_number']
    require(not predictions.duplicated(['race_id', 'horse_id']).any() and
            set(map(tuple, predictions[keys].to_numpy())) == set(map(tuple, entries[keys].to_numpy())),
            'Saved prediction/entry identity mismatch')
    require(len(predictions) == race.expected_runners == status['horse_count'] and
            (predictions.runner_count == len(predictions)).all(), 'Saved field size mismatch')
    return status, predictions


def result_labels(result_dir: Path, predictions: pd.DataFrame):
    captured = verify_capture(result_dir)
    require(captured['manifest']['dataspec'] == '0B12', 'Results require a separate 0B12 capture')
    require(captured['started_at'] > predictions.start_at.max(), 'Result capture began before race start')
    require(captured['finished_at'] <= now_utc(), 'Result capture is in the future')
    parsed = []
    unparsed = []
    for record in captured['records']:
        if record['payload'][:2] in (b'RA', b'SE'):
            parsed.append(decode_race_record(record['payload']))
        else:
            unparsed.append(dict(file=record['file'], sha256=record['sha256']))
    races = [r for r in parsed if r['record_id'] == 'RA']
    horses = [r for r in parsed if r['record_id'] == 'SE']
    require(len(races) == 1, 'Expected one result RA')
    race = races[0]
    # v1 deliberately waits for a full result with actual runner count (status 6/7).
    require(race['data_status'] in {'6', '7'} and all(
        r['data_status'] == race['data_status'] and r['created_date'] == race['created_date']
        for r in horses), 'Full consistent result status 6/7 required')
    require(timestamp(race['created_date'] + 'T00:00:00+09:00') <= captured['finished_at'],
            'Result creation date is in the future')
    require(race['race_key'] == predictions.race_id.iloc[0] and
            race['registered_count'] == race['runner_count'] == len(horses) == len(predictions),
            'Result race or field changed')
    numbers = {(r['race_key'], r['horse_id'], r['horse_number']) for r in horses}
    require(len(numbers) == len(horses) and numbers == set(map(tuple, predictions[
        ['race_id', 'horse_id', 'horse_number']].to_numpy())), 'Result horse identities changed')
    require(all(r['abnormal_code_raw'] == '0' and r['dead_heat_raw'] == '0'
                and r['final_rank_raw'].isdigit() for r in horses), 'Abnormal, tied or missing result unsupported')
    require(sorted(int(r['final_rank_raw']) for r in horses) == list(range(1, len(horses) + 1)),
            'Invalid complete result ranking')
    local_start = predictions.start_at.iloc[0].tz_convert('Asia/Tokyo')
    require(race['start_hhmm_raw'] == local_start.strftime('%H%M'),
            'Start time changed; explicit review required')
    results = pd.DataFrame([dict(race_id=r['race_key'], horse_id=r['horse_id'],
                                 win=int(r['final_rank_raw'] == '01'), result_status='official',
                                 result_observed_at=captured['finished_at']) for r in horses])
    evidence = dict(result_manifest_sha256=captured['manifest_sha256'],
                    result_observed_at=captured['finished_at'].isoformat(),
                    exact_settlement_time=None, unparsed_records=unparsed)
    return results, evidence


def run(prediction_dir: Path, expected_status_sha256: str, result_dir: Path, output_dir: Path):
    output_dir.mkdir(parents=True, exist_ok=False)
    status = dict(status='RUNNING', prediction_status_sha256=expected_status_sha256,
                  prediction_recomputed=False, experiment_kind='saved_observed_market_evaluation')
    try:
        saved, predictions = load_saved(prediction_dir, expected_status_sha256)
        # Result files are accessed only after the prediction's identity/integrity checks.
        results, evidence = result_labels(result_dir, predictions)
        metrics, tables = evaluate_observed_results(predictions, results)
        results.to_csv(output_dir / 'observed_results.csv', index=False)
        (output_dir / 'metrics.json').write_text(json.dumps(metrics, indent=2, allow_nan=False), encoding='utf-8')
        for name, table in tables.items():
            table.to_csv(output_dir / f'{name}.csv', index=False)
        status.update(status='PASS', race_id=saved['race_id'], **evidence,
                      prediction_sha256=saved['output_sha256']['predictions.csv'],
                      evaluated_at=now_utc().isoformat(),
                      scope='single-race diagnostic; no model selection or phase promotion')
        status['output_sha256'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in sorted(output_dir.iterdir())}
        package = Path(__file__).resolve().parent
        status['code_sha256'] = {p.relative_to(package).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(package.rglob('*.py'))}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        status.update(status='FAILED', error=str(exc))
        raise
    finally:
        (output_dir / 'status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prediction-dir', type=Path, required=True)
    parser.add_argument('--prediction-status-sha256', required=True)
    parser.add_argument('--result-dir', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.prediction_dir, args.prediction_status_sha256, args.result_dir, args.output_dir)))


if __name__ == '__main__':
    main()
