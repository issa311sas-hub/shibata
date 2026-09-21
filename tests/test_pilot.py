"""Pilot policy and state-machine tests use fictional data and controlled clocks."""
import hashlib
import json
from pathlib import Path
import subprocess

import pandas as pd
import pytest

from shibata import pilot, observed, score_saved
from shibata.ingestion.contracts import DataError
from shibata.pilot_policy import load_policy, validate_window, validate_save_time
from test_observed import capture
from test_jv_race import fixture
from test_jv_o1 import fixture_record

POLICY=Path(__file__).resolve().parents[1]/'configs'/'market-observed-pilot-v1.json'
KEY='2026092606040801'
START='2026-09-26T12:00:00+09:00'
CUTOFF='2026-09-26T11:50:00+09:00'


def clock(monkeypatch,value):
    for module in (pilot,observed,score_saved):
        monkeypatch.setattr(module,'now_utc',lambda:pd.Timestamp(value).tz_convert('UTC'))


def setup(tmp_path,monkeypatch):
    clock(monkeypatch,'2026-09-25T12:00:00+09:00')
    roster=dict(date='2026-09-26',all_venues_reviewed=True,
                source_url='https://www.jra.go.jp/example-fixture',verified_at='2026-09-25T11:00:00+09:00',
                venue_race_counts={'06':2},races=[
                    dict(race_id=KEY,start_at=START,track_code='21'),
                    dict(race_id='2026092606040802',start_at='2026-09-26T12:30:00+09:00',track_code='51')])
    path=tmp_path/'roster.json';path.write_text(json.dumps(roster))
    workspace=tmp_path/'pilot'
    pilot.initialize(POLICY,path,workspace)
    return workspace,path


def make_capture(folder,spec,payloads,at):
    # Existing fixtures contain an unrelated historical date; rewrite before capture.
    modified=[]
    for source in payloads:
        b=bytearray(source); b[3:11]=b'20260926';b[11:27]=KEY.encode()
        modified.append(bytes(b))
    capture(folder,spec,modified,at=at)
    p=folder/'probe.json';m=json.loads(p.read_text(encoding='utf-8-sig'));m['race_key']=KEY
    p.write_text(json.dumps(m))


def pre_race(tmp_path):
    payloads=[]
    for kind,n in [('RA',1),('SE',1),('SE',2)]:
        b=bytearray(fixture(kind,n));b[2]=ord('2')
        if kind=='RA': b[883:885]=b'00';b[705:707]=b'21'
        else: b[334:336]=b'00'
        payloads.append(bytes(b))
    e,o=tmp_path/'entries',tmp_path/'odds'
    make_capture(e,'0B15',payloads,'2026-09-26T11:48:00+09:00')
    b=fixture_record();b[27:35]=b'09261147'
    make_capture(o,'0B41',[bytes(b)],'2026-09-26T11:49:00+09:00')
    return e,o


@pytest.mark.parametrize('minutes',[0,5])
def test_odds_age_inclusive_bounds(minutes):
    validate_window(START,CUTOFF,[pd.Timestamp(CUTOFF)-pd.Timedelta(minutes=minutes)],'21')


@pytest.mark.parametrize('change',['stale','future','cutoff','date','jump'])
def test_policy_rejects_outside_conditions(change):
    start,cutoff,odds,track=START,CUTOFF,'2026-09-26T11:47:00+09:00','21'
    if change=='stale': odds='2026-09-26T11:44:59+09:00'
    if change=='future': odds='2026-09-26T11:50:01+09:00'
    if change=='cutoff': cutoff='2026-09-26T11:49:59+09:00'
    if change=='date': start='2026-09-22T12:00:00+09:00'
    if change=='jump': track='51'
    with pytest.raises(DataError):validate_window(start,cutoff,[odds],track)


@pytest.mark.parametrize('seconds,success',[(0,True),(60,True),(-1,False),(61,False)])
def test_save_deadline(seconds,success):
    at=pd.Timestamp(CUTOFF)+pd.Timedelta(seconds=seconds)
    if success:validate_save_time(CUTOFF,at)
    else:
        with pytest.raises(DataError):validate_save_time(CUTOFF,at)


@pytest.mark.parametrize('change',['date','missing','duplicate','venue','review','late','track'])
def test_bad_rosters_rejected_before_creation(tmp_path,monkeypatch,change):
    workspace,path=setup(tmp_path,monkeypatch)
    r=json.loads(path.read_text())
    if change=='date': r['date']='2026-09-22'
    if change=='missing': r['races'].pop()
    if change=='duplicate':r['races'][1]=r['races'][0]
    if change=='venue':r['venue_race_counts']={'09':2}
    if change=='review':r['all_venues_reviewed']=False
    if change=='late':clock(monkeypatch,'2026-09-26T12:00:00+09:00')
    if change=='track':r['races'][0]['track_code']='00'
    path.write_text(json.dumps(r))
    with pytest.raises(DataError):pilot.initialize(POLICY,path,tmp_path/'bad')
    assert not (tmp_path/'bad').exists()


def test_complete_pipeline_and_report_preserves_population(tmp_path,monkeypatch):
    workspace,_=setup(tmp_path,monkeypatch);e,o=pre_race(tmp_path)
    clock(monkeypatch,'2026-09-26T11:50:01+09:00')
    result=pilot.predict_race(workspace,KEY,e,o)
    assert result['fixed_cutoff_verified']
    with pytest.raises(DataError):pilot.predict_race(workspace,KEY,e,o)
    pred=Path(pilot.get_race(workspace,KEY)['prediction_dir'])/'predictions.csv'
    before=pred.read_bytes()
    r=tmp_path/'results'
    make_capture(r,'0B12',[fixture('RA'),fixture('SE',1),fixture('SE',2)],'2026-09-26T12:10:00+09:00')
    clock(monkeypatch,'2026-09-26T12:11:00+09:00')
    pilot.evaluate_race(workspace,KEY,r)
    report=pilot.report(workspace,tmp_path/'report')
    assert report['states']=={'EVALUATED':1,'OUT_OF_SCOPE':1}
    assert report['target_races']==1 and report['total_registered']==2
    assert report['fixed_cutoff_verified_for_saved_predictions']
    assert pred.read_bytes()==before
    assert (tmp_path/'report'/'metrics'/'metrics.json').exists()


def test_missed_capture_and_failed_results_are_visible(tmp_path,monkeypatch):
    workspace,_=setup(tmp_path,monkeypatch)
    clock(monkeypatch,'2026-09-26T11:52:00+09:00')
    assert pilot.expire(workspace)==[KEY]
    report=pilot.report(workspace,tmp_path/'report')
    assert report['states']['MISSED_CUTOFF']==1
    assert report['verified_prediction_count']==0
    assert not (tmp_path/'report'/'metrics').exists()


def test_collection_failure_recorded_without_predictions(tmp_path,monkeypatch):
    workspace,_=setup(tmp_path,monkeypatch)
    clock(monkeypatch,'2026-09-26T11:47:00+09:00')
    monkeypatch.setattr(pilot.shutil,'which',lambda _: 'fake-powershell')
    def fail(*args,**kwargs):raise subprocess.CalledProcessError(1,'fixture collector')
    monkeypatch.setattr(pilot.subprocess,'run',fail)
    with pytest.raises(subprocess.CalledProcessError):pilot.collect_race(workspace,KEY)
    row=pilot.get_race(workspace,KEY)
    assert row['state']=='CAPTURE_FAILED' and row['reason']
    assert not (workspace/'runs').exists()


def test_actual_prediction_rejects_stale_odds_and_records_failure(tmp_path,monkeypatch):
    workspace,_=setup(tmp_path,monkeypatch);e,o=pre_race(tmp_path)
    b=fixture_record();b[27:35]=b'09261144'
    bad=tmp_path/'old-odds';make_capture(bad,'0B41',[bytes(b)],'2026-09-26T11:49:00+09:00')
    clock(monkeypatch,'2026-09-26T11:50:01+09:00')
    with pytest.raises(DataError,match='five minutes'):pilot.predict_race(workspace,KEY,e,bad)
    assert pilot.get_race(workspace,KEY)['state']=='INELIGIBLE'


def test_result_failure_keeps_saved_prediction_and_retry_state(tmp_path,monkeypatch):
    workspace,_=setup(tmp_path,monkeypatch);e,o=pre_race(tmp_path)
    clock(monkeypatch,'2026-09-26T11:50:01+09:00');pilot.predict_race(workspace,KEY,e,o)
    clock(monkeypatch,'2026-09-26T12:11:00+09:00')
    with pytest.raises(ValueError):pilot.evaluate_race(workspace,KEY,tmp_path/'missing')
    row=pilot.get_race(workspace,KEY)
    assert row['state']=='RESULT_PENDING' and row['prediction_sha']


def test_frozen_config_tampering_rejected(tmp_path,monkeypatch):
    workspace,_=setup(tmp_path,monkeypatch)
    with (workspace/'policy.json').open('a') as f:f.write(' ')
    with pytest.raises(DataError,match='changed'):pilot.get_race(workspace,KEY)


def test_deadline_exceeded_during_save_is_failed_not_pass(tmp_path,monkeypatch):
    workspace,_=setup(tmp_path,monkeypatch);e,o=pre_race(tmp_path)
    clock(monkeypatch,'2026-09-26T11:50:01+09:00')
    times=iter([pd.Timestamp('2026-09-26T11:50:01+09:00'),
                pd.Timestamp('2026-09-26T11:50:01+09:00'),
                pd.Timestamp('2026-09-26T11:51:01+09:00')])
    monkeypatch.setattr(observed,'now_utc',lambda:next(times))
    with pytest.raises(DataError,match='one minute'):pilot.predict_race(workspace,KEY,e,o)
    assert pilot.get_race(workspace,KEY)['state']=='INELIGIBLE'
    status=json.loads((workspace/'runs'/KEY/'prediction'/'status.json').read_text())
    assert status['status']=='FAILED'


def test_roster_schedule_change_not_silently_adopted(tmp_path,monkeypatch):
    workspace,_=setup(tmp_path,monkeypatch);e,o=pre_race(tmp_path)
    from test_observed import rewrite_record
    rewrite_record(e,0,lambda p:p.__setitem__(slice(873,877),b'1205'))
    clock(monkeypatch,'2026-09-26T11:50:01+09:00')
    with pytest.raises(DataError):pilot.predict_race(workspace,KEY,e,o)
    assert pilot.get_race(workspace,KEY)['state']=='INELIGIBLE'


def test_collect_success_and_predict_uses_registered_paths(tmp_path,monkeypatch):
    workspace,_=setup(tmp_path,monkeypatch)
    clock(monkeypatch,'2026-09-26T11:47:00+09:00')
    monkeypatch.setattr(pilot.shutil,'which',lambda _: 'fake-powershell')
    e,o=pre_race(tmp_path)
    def fake_collector(args,**kwargs):
        import shutil
        target=Path(args[args.index('-OutputDirectory')+1])
        source=o if args[args.index('-DataSpec')+1]=='0B41' else e
        shutil.copytree(source,target)
        if target.name=='confirmation':
            m=json.loads((target/'probe.json').read_text())
            m['started_at']=m['finished_at']='2026-09-26T11:48:10+09:00'
            for item in m['files']:item['retrieved_at']=m['finished_at']
            (target/'probe.json').write_text(json.dumps(m))
    monkeypatch.setattr(pilot.subprocess,'run',fake_collector)
    pilot.collect_race(workspace,KEY)
    assert pilot.get_race(workspace,KEY)['state']=='CAPTURED'
    clock(monkeypatch,'2026-09-26T11:50:01+09:00')
    pilot.predict_race(workspace,KEY)
    assert pilot.get_race(workspace,KEY)['state']=='PREDICTED'
