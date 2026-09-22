import json
import sqlite3

import pytest

from shibata import pilot
from shibata.ingestion.contracts import DataError
from shibata.pilot_policy import DATES
from shibata.pilot_summary import summarize
from test_pilot import setup, clock, pre_race, make_capture, fixture, KEY


def manifest(tmp_path, workspace=None):
    values = dict.fromkeys(DATES)
    if workspace is not None:
        values[DATES[0]] = str(workspace)
    path = tmp_path/'manifest.json'
    path.write_text(json.dumps(values))
    return path


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def test_all_missing_is_unknown_not_zero_or_phase_pass(tmp_path):
    out = tmp_path/'summary'
    result = summarize(manifest(tmp_path), out)
    coverage = read(out/'coverage.json')
    assert coverage['total_target_races'] is None
    assert coverage['missing_roster_dates'] == DATES
    assert not coverage['metrics_available'] and not (out/'metrics').exists()
    assert not result['final_review_ready'] and not result['phase_promotion']


def test_missed_race_and_obstacle_preserved_without_source_changes(tmp_path, monkeypatch):
    workspace, _ = setup(tmp_path, monkeypatch)
    clock(monkeypatch, '2026-09-26T12:11:00+09:00')
    pilot.expire(workspace)
    before = {p.name: p.read_bytes() for p in workspace.iterdir() if p.is_file()}
    summarize(manifest(tmp_path, workspace), tmp_path/'summary')
    c = read(tmp_path/'summary'/'coverage.json')
    assert c['states'] == {'MISSED_CUTOFF': 1, 'OUT_OF_SCOPE': 1}
    assert c['known_target_races'] == c['known_unevaluated_races'] == 1
    assert c['evaluated_races'] == 0 and c['reasons']
    assert before == {p.name: p.read_bytes() for p in workspace.iterdir() if p.is_file()}


def test_evaluated_pipeline_matches_frozen_metrics_and_reproduces(tmp_path, monkeypatch):
    workspace, _ = setup(tmp_path, monkeypatch)
    e, o = pre_race(tmp_path)
    clock(monkeypatch, '2026-09-26T11:50:01+09:00')
    pilot.predict_race(workspace, KEY, e, o)
    results = tmp_path/'results'
    make_capture(results, '0B12', [fixture('RA'), fixture('SE', 1), fixture('SE', 2)],
                 '2026-09-26T12:10:00+09:00')
    clock(monkeypatch, '2026-09-26T12:11:00+09:00')
    pilot.evaluate_race(workspace, KEY, results)
    path = manifest(tmp_path, workspace)
    first = summarize(path, tmp_path/'one')
    second = summarize(path, tmp_path/'two')
    assert not first['final_review_ready']  # Three dates still explicitly absent.
    assert read(tmp_path/'one'/'coverage.json')['evaluated_races'] == 1
    expected = read(tmp_path/'one'/DATES[0]/'metrics'/'metrics.json')
    assert read(tmp_path/'one'/'metrics'/'metrics.json') == expected
    for name in ('coverage.json', 'races.json', 'metrics/metrics.json', 'metrics/calibration.csv'):
        assert first['output_sha256'][name] == second['output_sha256'][name]
    with pytest.raises(FileExistsError):
        summarize(path, tmp_path/'one')


@pytest.mark.parametrize('bad', ['missing_date', 'duplicate_workspace', 'wrong_date', 'missing_path'])
def test_manifest_errors_never_silently_omit_a_day(tmp_path, monkeypatch, bad):
    workspace, _ = setup(tmp_path, monkeypatch)
    path = manifest(tmp_path, workspace)
    values = read(path)
    if bad == 'missing_date': del values[DATES[-1]]
    if bad == 'duplicate_workspace': values[DATES[1]] = str(workspace)
    if bad == 'wrong_date': values[DATES[0]], values[DATES[1]] = None, str(workspace)
    if bad == 'missing_path': values[DATES[0]] = 'nonexistent'
    path.write_text(json.dumps(values))
    with pytest.raises((DataError, OSError)):
        summarize(path, tmp_path/'bad')
    assert read(tmp_path/'bad'/'status.json')['status'] == 'FAILED'


@pytest.mark.parametrize('sql', [
    'DELETE FROM races WHERE track_code="21"',
    'UPDATE races SET state="OUT_OF_SCOPE" WHERE track_code="21"',
    'UPDATE races SET cutoff="2026-09-26T11:51:00+09:00" WHERE track_code="21"',
])
def test_database_cannot_silently_change_frozen_population(tmp_path, monkeypatch, sql):
    workspace, _ = setup(tmp_path, monkeypatch)
    with sqlite3.connect(workspace/'pilot.sqlite') as con:
        con.execute(sql)
    with pytest.raises(DataError):
        summarize(manifest(tmp_path, workspace), tmp_path/'bad')


def test_four_days_all_missing_predictions_are_accounted_but_no_performance(tmp_path, monkeypatch):
    workspace, source = setup(tmp_path, monkeypatch)
    roster = read(source)
    values = {DATES[0]: str(workspace)}
    for date in DATES[1:]:
        rewritten = json.dumps(roster).replace('2026-09-26', date).replace('20260926', date.replace('-', ''))
        p = tmp_path/(date+'.json'); p.write_text(rewritten)
        w = tmp_path/date
        pilot.initialize(workspace/'policy.json', p, w)
        values[date] = str(w)
    clock(monkeypatch, '2026-10-05T00:00:00+09:00')
    from pathlib import Path
    for w in values.values(): pilot.expire(Path(w))
    path = tmp_path/'all.json'; path.write_text(json.dumps(values))
    status = summarize(path, tmp_path/'all')
    c = read(tmp_path/'all'/'coverage.json')
    assert c['total_target_races'] == 4 and c['registered_races'] == 8
    assert c['states'] == {'MISSED_CUTOFF': 4, 'OUT_OF_SCOPE': 4}
    assert status['coverage_complete_against_supplied_rosters']
    assert not status['final_review_ready'] and not status['phase_promotion']
