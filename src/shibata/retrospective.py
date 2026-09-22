"""Approved reference experiment from final records, never a pre-race backtest."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .chronological import partition
from .evaluation.compare import compare
from .ingestion.contracts import DataError, require
from .ingestion.historical import verify
from .ingestion.jv_o1 import decode_o1, validate_race_key
from .ingestion.jv_race import audit_mapping, decode_race_record
from .ingestion.model_fields import decode_model_fields
from .models.logistic import CATEGORICAL, FEATURES, fit_training, predict, validate
from .models.logistic_artifact import load, predict_saved, save

KEY = ['race_id', 'horse_id']


def reconstruct_race(payloads, observed_at):
    """Conservative complete-normal-result sample; exclusions depend on outcomes."""
    payloads = list(dict.fromkeys(payloads))  # Only byte-identical repetitions collapse.
    records = [decode_race_record(p) for p in payloads if p[:2] in (b'RA', b'SE')]
    odds = [decode_o1(p) for p in payloads if p[:2] == b'O1']
    require(records and all(r['data_status'] == '7' for r in records), 'Final RA/SE status 7 required')
    require(len(odds) == 1 and odds[0]['data_status'] == '5', 'Unique final O1 status 5 required')
    audit = audit_mapping(records, odds)
    require(audit['complete_normal_result'], 'Non-normal result, nonstarter, or dead heat')
    race = next(r for r in records if r['record_id'] == 'RA')
    ra = next(p for p in payloads if p[:2] == b'RA')
    fields = decode_model_fields(ra)['raw_fields']
    require(fields['surface'] is not None, 'Outside flat-race scope')
    # Nonzero old values indicate changes. Blank/zero does NOT prove T-10 availability.
    for old in (ra[701:705], ra[707:709]):
        require(old.strip() in (b'', b'0', b'00', b'0000'), 'Distance or track change recorded')
    snapshot = odds[0]
    require(snapshot['runner_count'] == race['registered_count'], 'Final odds runner count mismatch')
    require(snapshot['win_sale_flag'] in {'1', '3', '7'}, 'Win betting not offered')
    quotes = {int(s['horse_number_raw']): s for s in snapshot['slots'] if s['horse_number_raw'].strip()}
    require(all(s['status'] == 'quoted' and s['popularity_raw'].isdigit() for s in quotes.values()),
            'Missing, cancelled, or capped final odds')
    start = pd.Timestamp(datetime.strptime(race['race_key'][:8] + race['start_hhmm_raw'], '%Y%m%d%H%M'),
                         tz='Asia/Tokyo')
    rows, labels, market = [], [], []
    for payload in sorted((p for p in payloads if p[:2] == b'SE'), key=lambda p: p[28:30]):
        horse = decode_race_record(payload)
        require(payload[291:294].strip() in (b'', b'000'), 'Carried-weight change recorded')
        inputs = decode_model_fields(payload)['raw_fields']
        identity = dict(race_id=race['race_key'], horse_id=horse['horse_id'])
        rows.append(dict(identity, **inputs, runner_count=race['registered_count'],
                         distance=fields['distance'], surface=fields['surface'], venue=fields['venue']))
        labels.append(dict(identity, win=int(horse['final_rank_raw'] == '01'), result_status='official',
                           result_observed_at=observed_at))
        quote = quotes[horse['horse_number']]
        market.append(dict(identity, start_at=start, win_odds=quote['win_odds'],
                           popularity=int(quote['popularity_raw'])))
    features = pd.DataFrame(rows)[KEY + FEATURES]
    validate(features)
    market = pd.DataFrame(market)
    inverse = 1 / market.win_odds
    market['market_probability'] = inverse / inverse.sum()
    market['odds_rank'] = market.win_odds.rank(method='min').astype(int)
    return features, pd.DataFrame(labels), market


def assemble(manifests, config):
    """Explicit captures only. Reject Test/outside dates before reading result values."""
    grouped, ledger = defaultdict(list), []
    observed = defaultdict(list)
    for path in manifests:
        manifest, digest, records = verify(path)
        ledger.append(dict(path=str(path), sha256=digest, fromtime=manifest['fromtime'],
                           records=len(records), finished_at=manifest['finished_at']))
        for item, payload in records:
            if payload[:2] not in (b'RA', b'SE', b'O1'):
                continue
            key = validate_race_key(payload[11:27].decode('ascii'))
            day = datetime.strptime(key[:8], '%Y%m%d').date().isoformat()
            require(any(config[name]['start'] <= day <= config[name]['end_inclusive']
                        for name in ('train', 'validation')), 'Test/outside records forbidden in reference development')
            grouped[key].append(payload)
            observed[key].append(manifest['finished_at'])
    features, results, markets, audit = [], [], [], []
    for key, payloads in sorted(grouped.items()):
        row = dict(race_id=key, source_hashes=sorted({hashlib.sha256(p).hexdigest() for p in payloads}))
        try:
            at = max(observed[key], key=pd.Timestamp)
            f, r, m = reconstruct_race(payloads, at)
        except DataError as exc:
            audit.append(dict(row, included=False, reason=str(exc)))
            continue
        features.append(f); results.append(r); markets.append(m)
        audit.append(dict(row, included=True, reason=None, runners=len(f)))
    require(features, 'No eligible reference races')
    return (pd.concat(features, ignore_index=True), pd.concat(results, ignore_index=True),
            pd.concat(markets, ignore_index=True), audit, ledger)


def run(config_path, manifests, output):
    raw_config = config_path.read_bytes()
    config = json.loads(raw_config.decode('utf-8-sig'))
    require(config.get('experiment_kind') == 'retrospective_reference' and
            config.get('reference_training_enabled') is True and config.get('phase_promotion') is False,
            'Explicit approved reference configuration required')
    output.mkdir(parents=True, exist_ok=False)
    status = dict(status='RUNNING', experiment_id=config['experiment_id'],
                  experiment_kind='retrospective_reference', pre_race_availability_verified=False,
                  benchmark_timing='final_confirmed_odds_after_race_not_T_minus_10',
                  test_evaluated=False, phase_promotion=False, full_period_coverage_verified=False,
                  selection_bias='Only complete normal finishes without recorded input changes and with uncapped odds; outcome-dependent exclusions')
    try:
        features, results, market, audit, ledger = assemble(manifests, config)
        (output/'race-audit.json').write_text(json.dumps(audit, indent=2), encoding='utf-8')
        (output/'sources.json').write_text(json.dumps(ledger, indent=2), encoding='utf-8')
        (output/'config.json').write_bytes(raw_config)
        features.to_csv(output/'features.csv', index=False)
        results.to_csv(output/'results.csv', index=False)
        market.to_csv(output/'final-market.csv', index=False)
        parts, coverage = partition(features, config)
        require(parts['test'].empty and parts['outside'].empty, 'Test/outside rows forbidden')
        require(not parts['train'].empty and not parts['validation'].empty, 'Train and Validation samples required')
        train = parts['train'].merge(results[KEY + ['win']], on=KEY, validate='one_to_one')
        # Hash the complete fitted dataset (including labels), separately retain provenance hashes.
        train.to_csv(output/'train.csv', index=False)
        model = fit_training(train, config)
        digest = save(model, output/'model.json', config_sha256=hashlib.sha256(raw_config).hexdigest(),
                      dataset_sha256=hashlib.sha256((output/'train.csv').read_bytes()).hexdigest())
        validation = parts['validation']
        predictions = predict_saved(load(output/'model.json', digest), validation)
        np.testing.assert_allclose(predictions.probability, predict(model, validation).probability, rtol=1e-12)
        val_keys = validation[KEY]
        val_market = val_keys.merge(market, on=KEY, validate='one_to_one')
        val_results = val_keys.merge(results, on=KEY, validate='one_to_one')
        metrics, tables = compare(predictions, val_market, val_results)
        metrics['performance_claim'] = 'Retrospective reference only; outcome-selected sample and final-odds benchmark; no live predictive-performance claim'
        predictions.to_csv(output/'validation-predictions.csv', index=False)
        (output/'metrics.json').write_text(json.dumps(metrics, indent=2, allow_nan=False), encoding='utf-8')
        for model_name, group in tables.items():
            for name, table in group.items():
                table.to_csv(output/f'{model_name}-{name}.csv', index=False)
        status.update(status='COMPLETED_REFERENCE_ONLY', coverage=coverage,
                      included_months={name: {month: dict(races=int(group.race_id.nunique()), rows=len(group))
                                               for month, group in frame.groupby(frame.race_id.str[:6])}
                                       for name, frame in parts.items()},
                      validation_unknown_categories={column: int((~validation[column].astype(str).isin(
                          train[column].astype(str).unique())).sum()) for column in CATEGORICAL},
                      observed_race_dates=sorted({r['race_id'][:8] for r in audit}),
                      included_races=sum(r['included'] for r in audit),
                      excluded_races=sum(not r['included'] for r in audit),
                      exclusion_reasons=dict(Counter(r['reason'] for r in audit if not r['included'])),
                      model_sha256=digest,
                      artifact_hashes={p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                       for p in output.iterdir() if p.is_file()})
    except Exception as exc:
        status.update(status='FAILED', error=str(exc))
        raise
    finally:
        (output/'status.json').write_text(json.dumps(status, indent=2, allow_nan=False), encoding='utf-8')
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('configs/logistic-retrospective-v1.json'))
    parser.add_argument('--manifest', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.config, args.manifest, args.output), indent=2))


if __name__ == '__main__':
    main()
