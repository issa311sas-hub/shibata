import pandas as pd
import pytest
from shibata import pilot, pilot_runner as runner
from test_pilot import setup, clock, KEY, CUTOFF


def test_schedule_only_and_lock_release(tmp_path, monkeypatch):
    workspace, _ = setup(tmp_path, monkeypatch)
    events = runner.schedule(workspace)
    assert len(events) == 1
    assert pd.Timestamp(events[0]['collect_at']) == pd.Timestamp(CUTOFF)-pd.Timedelta(minutes=3)
    assert pilot.get_race(workspace, KEY)['state'] == 'PLANNED'
    with runner.runner_lock(workspace):
        with pytest.raises(ValueError, match='Another pilot runner'):
            with runner.runner_lock(workspace):
                pass
    with runner.runner_lock(workspace):
        pass


def test_runner_waits_collects_predicts_once(tmp_path, monkeypatch):
    workspace, _ = setup(tmp_path, monkeypatch)
    current = [pd.Timestamp(CUTOFF)-pd.Timedelta(minutes=4)]
    monkeypatch.setattr(pilot, 'now_utc', lambda:current[0])
    calls = []
    def collect(w, key):
        calls.append(('collect', current[0]))
        pilot.transition(w,key,{'PLANNED'},'CAPTURED')
    def predict(w, key):
        calls.append(('predict', current[0]))
        pilot.transition(w,key,{'CAPTURED'},'PREDICTED')
    monkeypatch.setattr(pilot,'collect_race',collect)
    monkeypatch.setattr(pilot,'predict_race',predict)
    def sleep(seconds):
        current[0] += pd.Timedelta(seconds=seconds)
    runner.run(workspace,sleep)
    runner.run(workspace,sleep)
    assert calls == [('collect', pd.Timestamp(CUTOFF)-pd.Timedelta(minutes=3)),
                     ('predict', pd.Timestamp(CUTOFF))]


@pytest.mark.parametrize('state,expected', [('PLANNED','CAPTURE_FAILED'),
    ('CAPTURING','INTERRUPTED'), ('PREDICTING','INTERRUPTED'), ('CAPTURED','MISSED_CUTOFF')])
def test_restart_does_not_retry_or_use_late_data(tmp_path,monkeypatch,state,expected):
    workspace,_=setup(tmp_path,monkeypatch)
    if state!='PLANNED': pilot.transition(workspace,KEY,{'PLANNED'},state)
    clock(monkeypatch,'2026-09-26T11:50:30+09:00' if state!='CAPTURED' else '2026-09-26T11:51:01+09:00')
    runner.run(workspace,lambda seconds:pytest.fail('Unexpected wait'))
    assert pilot.get_race(workspace,KEY)['state']==expected


def test_collection_failure_finishes_with_record(tmp_path,monkeypatch):
    workspace,_=setup(tmp_path,monkeypatch)
    clock(monkeypatch,'2026-09-26T11:47:00+09:00')
    def fail(w,key):
        pilot.record_failure(w,key,'COM unavailable')
        raise OSError('COM unavailable')
    monkeypatch.setattr(pilot,'collect_race',fail)
    runner.run(workspace)
    assert 'COM unavailable' in (workspace/'runner.jsonl').read_text()


def test_unexpected_error_stops_and_releases_lock(tmp_path,monkeypatch):
    workspace,_=setup(tmp_path,monkeypatch)
    clock(monkeypatch,'2026-09-26T11:47:00+09:00')
    def fail(w,key): raise RuntimeError('unexpected')
    monkeypatch.setattr(pilot,'collect_race',fail)
    with pytest.raises(RuntimeError): runner.run(workspace)
    with runner.runner_lock(workspace): pass


def test_overlapping_windows_refused(tmp_path,monkeypatch):
    workspace,_=setup(tmp_path,monkeypatch)
    con=pilot.connect(workspace)
    with con:
        con.execute("UPDATE races SET state='PLANNED',track_code='21',cutoff=? WHERE race_id != ?",
                    ((pd.Timestamp(CUTOFF)+pd.Timedelta(minutes=2)).isoformat(),KEY))
    con.close()
    with pytest.raises(ValueError,match='Overlapping'): runner.schedule(workspace)
