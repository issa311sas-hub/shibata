"""Read-only four-day coverage and pooled scoring; never promotes a phase."""
import argparse
from collections import Counter
import json
from pathlib import Path

import pandas as pd

from . import pilot
from .aggregate_saved import aggregate
from .ingestion.contracts import require, timestamp
from .pilot_policy import DATES, FLAT_TRACKS, load_policy

STATES = {'PLANNED', 'OUT_OF_SCOPE', 'CAPTURING', 'CAPTURED', 'CAPTURE_FAILED',
          'PREDICTING', 'PREDICTED', 'INELIGIBLE', 'MISSED_CUTOFF', 'INTERRUPTED',
          'EVALUATING', 'RESULT_PENDING', 'EVALUATED'}
PENDING = {'PLANNED', 'CAPTURING', 'CAPTURED', 'PREDICTING', 'PREDICTED',
           'EVALUATING', 'RESULT_PENDING'}


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def summarize(manifest_path: Path, output: Path):
    """Manifest maps every approved date to an existing workspace or explicit null."""
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    status = dict(status='RUNNING', phase_promotion=False)
    try:
        manifest = read(manifest_path)
        require(isinstance(manifest, dict) and set(manifest) == set(DATES),
                'Manifest must explicitly list all four approved dates')
        (output/'input-manifest.json').write_bytes(manifest_path.read_bytes())
        days, rows, ledger, paths, policy_hashes = [], [], [], set(), set()
        for date in DATES:
            value = manifest[date]
            if value is None:
                days.append(dict(date=date, status='ROSTER_MISSING', target_races=None))
                continue
            require(isinstance(value, str) and bool(value), 'Workspace must be a path or null')
            workspace = (manifest_path.resolve().parent/value).resolve()
            require(workspace not in paths, 'Duplicate workspace')
            paths.add(workspace)
            roster = read(workspace/'roster.json')
            require(roster['date'] == date, 'Workspace date mismatch')
            _, policy_hash = load_policy(workspace/'policy.json')
            policy_hashes.add(policy_hash)
            require(len(policy_hashes) == 1, 'Different frozen policy versions')
            daily = output/date
            coverage = pilot.report(workspace, daily)
            daily_rows = read(daily/'races.json')
            expected = {r['race_id']: r for r in roster['races']}
            require(len(expected) == len(roster['races']) and
                    len(daily_rows) == len(expected) and
                    {r['race_id'] for r in daily_rows} == set(expected),
                    'Daily database differs from frozen roster population')
            for row in daily_rows:
                original = expected[row['race_id']]
                require(row['state'] in STATES, 'Unknown race state')
                require(timestamp(row['start_at']) == timestamp(original['start_at']) and
                        row['track_code'] == original['track_code'] and
                        timestamp(row['cutoff']) == timestamp(original['start_at']) - pd.Timedelta(minutes=10),
                        'Daily database differs from frozen race definition')
                require((row['state'] == 'OUT_OF_SCOPE') == (row['track_code'] not in FLAT_TRACKS),
                        'Out-of-scope classification differs from frozen roster')
                if row['state'] not in PENDING | {'EVALUATED'}:
                    require(bool(row['reason']), 'Missing exclusion/failure reason')
            for name in ('roster.json', 'policy.json'):
                (daily/name).write_bytes((workspace/name).read_bytes())
                require(pilot.digest(daily/name) == coverage[name.removesuffix('.json')+'_sha256'],
                        'Frozen input changed during report')
            daily_ledger = read(daily/'evaluation-ledger.json')
            # Existing pilot records absolute artifact paths. Refuse ambiguous relative paths.
            require(all(Path(item[key]).is_absolute() for item in daily_ledger
                        for key in ('prediction_dir', 'evaluation_dir')), 'Absolute artifact paths required')
            ledger.extend(daily_ledger)
            rows.extend(dict(date=date, **r) for r in daily_rows)
            days.append(dict(date=date, status='REPORTED', **coverage))
        require(len({r['race_id'] for r in rows}) == len(rows), 'Duplicate race across days')
        write(output/'evaluation-ledger.json', ledger)
        aggregate_status = aggregate(output/'evaluation-ledger.json', output/'metrics') if ledger else None
        evaluated = {r['race_id'] for r in rows if r['state'] == 'EVALUATED'}
        require((set() if aggregate_status is None else
                 {r['race_id'] for r in aggregate_status['runs']}) == evaluated,
                'Aggregate does not match evaluated population')
        missing = [d['date'] for d in days if d['status'] == 'ROSTER_MISSING']
        targets = [r for r in rows if r['state'] != 'OUT_OF_SCOPE']
        summary = dict(days=days, missing_roster_dates=missing,
                       population_basis='frozen rosters; official completeness requires manual review',
                       registered_races=len(rows), known_target_races=len(targets),
                       total_target_races=None if missing else len(targets),
                       evaluated_races=len(evaluated), known_unevaluated_races=len(targets)-len(evaluated),
                       unresolved_races=sum(r['state'] in PENDING for r in targets),
                       states=dict(Counter(r['state'] for r in rows)),
                       reasons=dict(Counter(r['reason'] for r in rows if r['reason'])),
                       metrics_available=bool(ledger), phase_promotion=False,
                       clock_and_official_roster_review='MANUAL_REVIEW_REQUIRED')
        write(output/'coverage.json', summary)
        write(output/'races.json', rows)
        status.update(status='PASS', coverage_complete_against_supplied_rosters=not missing,
                      final_review_ready=not missing and summary['unresolved_races'] == 0 and bool(ledger),
                      note='PASS means report generation succeeded, not Phase 1 acceptance')
        status['output_sha256'] = {p.relative_to(output).as_posix(): pilot.digest(p)
                                   for p in sorted(output.rglob('*')) if p.is_file()}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        status.update(status='FAILED', error=str(exc))
        raise
    finally:
        write(output/'status.json', status)
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(summarize(args.manifest, args.output_dir)))


if __name__ == '__main__':
    main()
