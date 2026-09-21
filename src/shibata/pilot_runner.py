"""Foreground pilot acquisition runner; no operating-system schedule is installed."""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
import time

import pandas as pd
from . import pilot
from .ingestion.contracts import require, timestamp

ACTIVE = {'PLANNED', 'CAPTURED', 'CAPTURING', 'PREDICTING'}


def rows(workspace):
    con = pilot.connect(workspace)
    try:
        return [dict(r) for r in con.execute('SELECT * FROM races ORDER BY cutoff,race_id')]
    finally:
        con.close()


def schedule(workspace):
    targets = [r for r in rows(workspace) if r['state'] != 'OUT_OF_SCOPE']
    events = []
    previous_end = None
    for row in targets:
        cutoff = timestamp(row['cutoff'])
        begin = cutoff - pd.Timedelta(minutes=3)
        # One COM collector at a time; reserve the full collection/save window.
        require(previous_end is None or begin > previous_end,
                'Overlapping acquisition windows: unattended execution unavailable')
        previous_end = cutoff + pd.Timedelta(minutes=1)
        events.append(dict(race_id=row['race_id'], collect_at=begin.isoformat(),
                           predict_at=cutoff.isoformat(), deadline=previous_end.isoformat(),
                           state=row['state']))
    return events


@contextmanager
def runner_lock(workspace):
    # A separate SQLite transaction is released by the OS even after process death.
    # Never unlink this file: doing so would permit a second inode/lock on Unix.
    con = sqlite3.connect(workspace / 'runner-lock.sqlite', timeout=0)
    try:
        try:
            con.execute('BEGIN EXCLUSIVE')
        except sqlite3.OperationalError as exc:
            raise ValueError('Another pilot runner holds this workspace') from exc
        yield
    finally:
        con.close()


def log(workspace, kind, **details):
    with (workspace / 'runner.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(dict(at=pilot.now_utc().isoformat(), kind=kind, **details)) + '\n')


def run(workspace, sleep=time.sleep):
    workspace = workspace.resolve()
    schedule(workspace)  # Validate frozen files and conflicting windows before starting.
    with runner_lock(workspace):
        log(workspace, 'START')
        try:
            while True:
                pilot.expire(workspace)
                active = [r for r in rows(workspace) if r['state'] in ACTIVE]
                if not active:
                    break
                row = active[0]
                key, state = row['race_id'], row['state']
                now, cutoff = pilot.now_utc(), timestamp(row['cutoff'])
                # Interrupted work is never automatically re-collected/re-predicted.
                if state in {'CAPTURING', 'PREDICTING'}:
                    pilot.transition(workspace, key, {state}, 'INTERRUPTED',
                                     'Previous process stopped during an operation; no retry')
                    continue
                if state == 'PLANNED' and now >= cutoff:
                    pilot.record_failure(workspace, key, 'Runner started after acquisition cutoff')
                    continue
                action = None
                if state == 'PLANNED' and now >= cutoff - pd.Timedelta(minutes=3):
                    action = pilot.collect_race
                elif state == 'CAPTURED' and now >= cutoff:
                    action = pilot.predict_race
                if action is None:
                    sleep(0.5)
                    continue
                log(workspace, 'ACTION', race_id=key, action=action.__name__)
                try:
                    action(workspace, key)
                except Exception as exc:
                    log(workspace, 'ERROR', race_id=key, error=type(exc).__name__, detail=str(exc))
                    # Expected acquisition/validation failures have terminal states.
                    # Unexpected errors with unchanged state must stop, not busy-loop.
                    if pilot.get_race(workspace, key)['state'] in ACTIVE:
                        raise
            log(workspace, 'FINISH', states={r['race_id']: r['state'] for r in rows(workspace)})
        except BaseException as exc:
            log(workspace, 'STOP', error=type(exc).__name__, detail=str(exc))
            raise
    return {'acquisition_finished': True, 'results_evaluated_automatically': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--run', action='store_true', help='Remain running until all prediction windows finish')
    args = parser.parse_args()
    result = run(args.workspace) if args.run else schedule(args.workspace)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
