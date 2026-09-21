import subprocess
import pytest
from shibata import pilot, pilot_finish as finish
from test_pilot import setup, clock, KEY


def ready(tmp_path,monkeypatch,state='PREDICTED'):
    workspace,_=setup(tmp_path,monkeypatch)
    pilot.transition(workspace,KEY,{'PLANNED'},state)
    clock(monkeypatch,'2026-09-26T17:00:00+09:00')
    monkeypatch.setattr(finish.shutil,'which',lambda _: 'powershell')
    monkeypatch.setattr(pilot,'report',lambda w,o:{'states':{r['state']:1 for r in finish.rows(w)}})
    return workspace


def test_refuses_pending_prediction_window(tmp_path,monkeypatch):
    workspace=ready(tmp_path,monkeypatch,'PLANNED')
    with pytest.raises(ValueError,match='Finish acquisition'): finish.finish(workspace)


def test_refuses_early_result_batch(tmp_path,monkeypatch):
    workspace=ready(tmp_path,monkeypatch)
    clock(monkeypatch,'2026-09-26T11:55:00+09:00')
    with pytest.raises(ValueError,match='every scheduled'): finish.finish(workspace)


def test_capture_failure_is_retained_and_retry_uses_fresh_folder(tmp_path,monkeypatch):
    workspace=ready(tmp_path,monkeypatch)
    paths=[]
    def failed(args,**kwargs):
        paths.append(args[-1])
        raise subprocess.TimeoutExpired(args,60)
    monkeypatch.setattr(finish.subprocess,'run',failed)
    finish.finish(workspace);finish.finish(workspace)
    assert len(set(paths))==2
    assert pilot.get_race(workspace,KEY)['state']=='RESULT_PENDING'


def test_success_not_evaluated_twice(tmp_path,monkeypatch):
    workspace=ready(tmp_path,monkeypatch)
    calls=[]
    monkeypatch.setattr(finish.subprocess,'run',lambda *a,**k:None)
    def score(w,key,path):
        calls.append(key)
        pilot.transition(w,key,{'PREDICTED'},'EVALUATED')
    monkeypatch.setattr(pilot,'evaluate_race',score)
    finish.finish(workspace);finish.finish(workspace)
    assert calls==[KEY]


def test_interrupted_evaluation_retried_as_pending(tmp_path,monkeypatch):
    workspace=ready(tmp_path,monkeypatch,'EVALUATING')
    monkeypatch.setattr(finish.subprocess,'run',lambda *a,**k:None)
    def score(w,key,path):
        assert pilot.get_race(w,key)['state']=='RESULT_PENDING'
        raise ValueError('Not final')
    monkeypatch.setattr(pilot,'evaluate_race',score)
    finish.finish(workspace)
    assert pilot.get_race(workspace,KEY)['state']=='RESULT_PENDING'
