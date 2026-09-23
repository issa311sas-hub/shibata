"""Three-model synthetic comparison; no real-data training or phase promotion."""
import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .chronological import partition
from .evaluation.compare import compare
from .models import logistic, logistic_artifact, tree_rehearsal
from .observed_features import FEATURES
from .ingestion.contracts import require


def synthetic_raw():
    """Fictional records; counts are derived per race during feature assembly."""
    return [dict(race_id=day+'05010101', horse_id=f'{day}{h}', age=2+h,
                 sex='1', bracket_number=h, horse_number=h, distance=1600,
                 surface='turf', venue='05', carried_weight=55., win=int(h == 1))
            for day in ('20260101', '20260201', '20260701') for h in range(1, 5)]


def feature_frame(raw):
    frame = pd.DataFrame(raw)
    require('runner_count' not in frame and set(frame) ==
            set(FEATURES)-{'runner_count'} | {'race_id', 'horse_id', 'win'},
            'Unexpected synthetic raw columns')
    frame['runner_count'] = frame.groupby('race_id').horse_id.transform('size')
    return frame[['race_id', 'horse_id', *FEATURES, 'win']]


def synthetic_market(validation):
    market = validation[['race_id', 'horse_id']].copy()
    market['start_at'] = pd.Timestamp('2026-07-01T12:00:00+09:00')
    market['win_odds'] = [2., 4., 6., 8.]
    market['popularity'] = [1, 2, 3, 4]
    market['odds_rank'] = [1, 2, 3, 4]
    inverse = 1/market.win_odds
    market['market_probability'] = inverse/inverse.sum()
    return market


def run(config_path: Path, output: Path):
    raw_config = config_path.read_bytes()
    config = json.loads(raw_config.decode('utf-8-sig'))
    require(config['features'] == FEATURES and config['model'] == 'logistic_regression' and
            config['status'] == 'APPROVED_PREPARATION' and
            config['training_enabled'] is False and config['phase_promotion'] is False,
            'Only the fixed synthetic preparation scope is accepted')
    output.mkdir(parents=True, exist_ok=False)
    status = dict(status='RUNNING', experiment_kind='phase2_synthetic_three_model_rehearsal',
                  real_data_used=False, test_evaluated=False, phase_promotion=False)
    try:
        raw = synthetic_raw()
        (output/'synthetic-raw.json').write_text(json.dumps(raw, indent=2), encoding='utf-8')
        dataset = feature_frame(raw)
        dataset.to_csv(output/'synthetic-features.csv', index=False)
        parts, coverage = partition(dataset, config)
        require(coverage['train']['races'] == 2 and coverage['validation']['races'] == 1 and
                coverage['test']['rows'] == coverage['outside']['rows'] == 0,
                'Unexpected rehearsal partition')
        train, validation = parts['train'], parts['validation']
        market = synthetic_market(validation)
        results = validation[['race_id', 'horse_id', 'win']].copy()
        results['result_status'] = 'official'
        results['result_observed_at'] = '2026-07-01T13:00:00+09:00'
        config_sha = hashlib.sha256(raw_config).hexdigest()
        dataset_sha = hashlib.sha256((output/'synthetic-features.csv').read_bytes()).hexdigest()
        scores = {}
        for name in ('logistic_regression', *tree_rehearsal.MODELS):
            if name == 'logistic_regression':
                model = logistic.fit_training(train, config)
                model_sha = logistic_artifact.save(model, output/'logistic-model.json',
                                                   config_sha256=config_sha, dataset_sha256=dataset_sha)
                pred = logistic_artifact.predict_saved(
                    logistic_artifact.load(output/'logistic-model.json', model_sha), validation)
                direct = logistic.predict(model, validation)
            else:
                model, prep = tree_rehearsal.fit_synthetic(train, config, name)
                model_sha = tree_rehearsal.save(model, prep, output/name, name,
                                                config_sha=config_sha, dataset_sha=dataset_sha)
                loaded, meta = tree_rehearsal.load(output/name, model_sha, name)
                pred = tree_rehearsal.predict(loaded, validation, meta=meta, name=name)
                direct = tree_rehearsal.predict(model, validation, prep=prep, name=name)
            np.testing.assert_allclose(pred.probability, direct.probability, rtol=1e-12, atol=1e-12)
            metrics, tables = compare(pred, market, results)
            pred.to_csv(output/f'{name}-predictions.csv', index=False)
            (output/f'{name}-metrics.json').write_text(json.dumps(metrics, indent=2), encoding='utf-8')
            for scope, group in tables.items():
                for table_name, table in group.items():
                    table.to_csv(output/f'{name}-{scope}-{table_name}.csv', index=False)
            scores[name] = dict(model=metrics['model'], market=metrics['market'],
                                model_minus_market=metrics['model_minus_market'], model_sha256=model_sha)
        (output/'comparison.json').write_text(json.dumps(scores, indent=2), encoding='utf-8')
        status.update(status='PASS', coverage=coverage, feature_names=FEATURES,
                      model_names=list(scores), config_sha256=config_sha, dataset_sha256=dataset_sha,
                      output_sha256={p.relative_to(output).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                                     for p in sorted(output.rglob('*')) if p.is_file()})
    except Exception as exc:
        status.update(status='FAILED', error=str(exc))
        raise
    finally:
        (output/'status.json').write_text(json.dumps(status, indent=2), encoding='utf-8')
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('configs/logistic-initial-v1.json'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.config, args.output)))


if __name__ == '__main__':
    main()
