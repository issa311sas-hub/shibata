"""Frozen daily pilot roster, transactional state transitions and coverage reports.

No background scheduling. Capture files are supplied by the JV-Link collector.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import shutil
from urllib.parse import urlparse
import uuid

import pandas as pd
from .ingestion.contracts import require, timestamp
from .ingestion.jv_o1 import validate_race_key
from .pilot_policy import load_policy, FLAT_TRACKS, validate_window, validate_save_time
from .observed import run as predict
from .score_saved import run as score, load_saved
from .aggregate_saved import aggregate


def now_utc():
    return pd.Timestamp.now(tz='UTC')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def connect(workspace):
    require((workspace / 'pilot.sqlite').is_file(), 'Pilot workspace not initialized')
    con = sqlite3.connect(workspace / 'pilot.sqlite', timeout=10)
    con.row_factory = sqlite3.Row
    try:
        meta = dict(con.execute('SELECT key,value FROM meta').fetchall())
        require(digest(workspace / 'policy.json') == meta['policy_sha256'] and
                digest(workspace / 'roster.json') == meta['roster_sha256'], 'Frozen policy/roster changed')
        load_policy(workspace / 'policy.json')
    except Exception:
        con.close()
        raise
    return con


def initialize(policy_path, roster_path, workspace):
    policy, policy_hash = load_policy(policy_path)
    raw = roster_path.read_bytes()
    roster = json.loads(raw.decode('utf-8-sig'))
    require(roster['date'] in policy['observation_dates'], 'Roster outside approved dates')
    require(roster['all_venues_reviewed'] is True, 'All venues must be reviewed before freezing roster')
    require(urlparse(roster['source_url']).hostname in {'jra.go.jp', 'www.jra.go.jp', 'jra.jp', 'www.jra.jp'},
            'Roster needs an official JRA source URL')
    now = now_utc()
    require(timestamp(roster['verified_at']) <= now, 'Roster review is in the future')
    counts, races = roster['venue_race_counts'], roster['races']
    require(isinstance(counts, dict) and bool(counts) and bool(races), 'Empty roster')
    require(all(isinstance(k, str) and k in {f'{i:02d}' for i in range(1,11)} and
                type(v) is int and 1 <= v <= 12 for k,v in counts.items()), 'Invalid venue counts')
    seen, numbers = set(), {k:set() for k in counts}
    normalized = []
    for race in races:
        key = validate_race_key(race['race_id'])
        require(key not in seen and key[8:10] in counts, 'Duplicate race or unknown venue')
        seen.add(key)
        require(key[:8] == roster['date'].replace('-',''), 'Race/roster date mismatch')
        start = timestamp(race['start_at'])
        require(start.tz_convert('Asia/Tokyo').date().isoformat() == roster['date'], 'Start date mismatch')
        cutoff = start - pd.Timedelta(minutes=10)
        require(timestamp(roster['verified_at']) <= now < cutoff, 'Roster must be frozen before all cutoffs')
        track = race['track_code']
        require(track in FLAT_TRACKS | {str(i) for i in range(51,60)}, 'Unknown track code')
        require(int(key[14:]) not in numbers[key[8:10]], 'Duplicate venue/race number')
        numbers[key[8:10]].add(int(key[14:]))
        normalized.append((key,start.isoformat(),cutoff.isoformat(),track,
                           'PLANNED' if track in FLAT_TRACKS else 'OUT_OF_SCOPE'))
    require(all(numbers[k] == set(range(1,v+1)) for k,v in counts.items()), 'Missing races in declared venue')
    workspace.mkdir(parents=True, exist_ok=False)
    (workspace/'policy.json').write_bytes(policy_path.read_bytes())
    (workspace/'roster.json').write_bytes(raw)
    con = sqlite3.connect(workspace/'pilot.sqlite')
    try:
        with con:
            con.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)')
            con.executemany('INSERT INTO meta VALUES (?,?)', [('policy_sha256',policy_hash),
                ('roster_sha256',hashlib.sha256(raw).hexdigest())])
            con.execute('''CREATE TABLE races(race_id TEXT PRIMARY KEY,start_at TEXT,cutoff TEXT,
                track_code TEXT,state TEXT,reason TEXT,prediction_dir TEXT,prediction_sha TEXT,
                evaluation_dir TEXT,evaluation_sha TEXT,entries_dir TEXT,odds_dir TEXT,confirmation_dir TEXT)''')
            con.execute('CREATE TABLE events(sequence INTEGER PRIMARY KEY, race_id TEXT, at TEXT, state TEXT, detail TEXT)')
            for key,start,cutoff,track,state in normalized:
                con.execute('INSERT INTO races(race_id,start_at,cutoff,track_code,state,reason) VALUES (?,?,?,?,?,?)',
                            (key,start,cutoff,track,state,'non-flat' if state=='OUT_OF_SCOPE' else ''))
                con.execute('INSERT INTO events(race_id,at,state,detail) VALUES (?,?,?,?)',
                            (key,now.isoformat(),state,'Frozen roster'))
    finally:
        con.close()
    return dict(races=len(races), target_races=sum(r[-1]=='PLANNED' for r in normalized), policy_sha256=policy_hash)


def transition(workspace, race_id, allowed, new_state, reason='', **artifacts):
    con=connect(workspace)
    try:
        con.execute('BEGIN IMMEDIATE')
        row=con.execute('SELECT * FROM races WHERE race_id=?',(race_id,)).fetchone()
        require(row is not None and row['state'] in allowed, 'Invalid or duplicate state transition')
        fields={'state':new_state,'reason':reason,**artifacts}
        require(set(fields) <= {'state','reason','prediction_dir','prediction_sha','evaluation_dir','evaluation_sha','entries_dir','odds_dir','confirmation_dir'},
                'Invalid artifact fields')
        con.execute('UPDATE races SET '+','.join(k+'=?' for k in fields)+' WHERE race_id=?',
                    (*fields.values(),race_id))
        con.execute('INSERT INTO events(race_id,at,state,detail) VALUES (?,?,?,?)',
                    (race_id,now_utc().isoformat(),new_state,reason))
        con.commit()
        return dict(row)
    finally:
        con.close()


def get_race(workspace, race_id):
    con=connect(workspace)
    try:
        row=con.execute('SELECT * FROM races WHERE race_id=?',(race_id,)).fetchone()
        require(row is not None, 'Race not in roster')
        return dict(row)
    finally:
        con.close()


def collect_race(workspace,race_id):
    row=get_race(workspace,race_id)
    cutoff=timestamp(row['cutoff'])
    require(cutoff-pd.Timedelta(minutes=3) <= now_utc() < cutoff,
            'Collect only during the three minutes preceding cutoff')
    shell=shutil.which('pwsh') or shutil.which('powershell')
    require(shell is not None,'PowerShell is unavailable')
    transition(workspace,race_id,{'PLANNED'},'CAPTURING')
    script=Path(__file__).resolve().parents[2]/'scripts'/'collect-jvlink.ps1'
    root=workspace/'raw'/race_id
    paths={name:root/name for name in ('entries','confirmation','odds')}
    try:
        for name,spec in [('entries','0B15'),('confirmation','0B15'),('odds','0B41')]:
            require(now_utc()<cutoff,'Capture cutoff reached')
            subprocess.run([shell,'-NoProfile','-NonInteractive','-File',str(script),
                            '-DataSpec',spec,'-RaceKey',race_id,'-OutputDirectory',str(paths[name].resolve())],
                           check=True,timeout=60,capture_output=True,text=True)
        require(now_utc()<=cutoff,'Capture completed after cutoff')
        transition(workspace,race_id,{'CAPTURING'},'CAPTURED',
                   **{name+'_dir':str(path.resolve()) for name,path in paths.items()})
        return {name:str(path) for name,path in paths.items()}
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        transition(workspace,race_id,{'CAPTURING'},'CAPTURE_FAILED',str(exc))
        raise


def predict_race(workspace, race_id, entries=None, odds=None, confirmation=None):
    row=get_race(workspace,race_id)
    cutoff=timestamp(row['cutoff'])
    validate_save_time(cutoff,now_utc())
    row=transition(workspace,race_id,{'PLANNED','CAPTURED'},'PREDICTING')
    out=workspace/'runs'/race_id/'prediction'
    try:
        entries=entries or (Path(row['entries_dir']) if row['entries_dir'] else None)
        odds=odds or (Path(row['odds_dir']) if row['odds_dir'] else None)
        confirmation=confirmation or (Path(row['confirmation_dir']) if row['confirmation_dir'] else None)
        require(entries is not None and odds is not None,'Capture paths required')
        result=predict(entries,odds,out,cutoff.isoformat(),confirmation,workspace/'policy.json',row)
        transition(workspace,race_id,{'PREDICTING'},'PREDICTED',prediction_dir=str(out.resolve()),
                   prediction_sha=digest(out/'status.json'))
        return result
    except (ValueError,OSError,KeyError,TypeError) as exc:
        transition(workspace,race_id,{'PREDICTING'},'INELIGIBLE',str(exc))
        raise


def evaluate_race(workspace,race_id,result_dir):
    row=transition(workspace,race_id,{'PREDICTED','RESULT_PENDING'},'EVALUATING')
    out=workspace/'runs'/race_id/('evaluation-'+uuid.uuid4().hex[:12])
    try:
        result=score(Path(row['prediction_dir']),row['prediction_sha'],result_dir,out)
        transition(workspace,race_id,{'EVALUATING'},'EVALUATED',evaluation_dir=str(out.resolve()),
                   evaluation_sha=digest(out/'status.json'))
        return result
    except (ValueError,OSError,KeyError,TypeError) as exc:
        transition(workspace,race_id,{'EVALUATING'},'RESULT_PENDING',str(exc))
        raise


def record_failure(workspace,race_id,reason):
    require(isinstance(reason,str) and bool(reason.strip()), 'Failure reason required')
    return transition(workspace,race_id,{'PLANNED'},'CAPTURE_FAILED',reason)


def expire(workspace):
    con=connect(workspace)
    try:
        rows=[dict(r) for r in con.execute("SELECT * FROM races WHERE state IN ('PLANNED','CAPTURED','CAPTURING','PREDICTING')")]
    finally:
        con.close()
    expired=[]
    for row in rows:
        if now_utc() > timestamp(row['cutoff'])+pd.Timedelta(minutes=1):
            state='MISSED_CUTOFF' if row['state'] in {'PLANNED','CAPTURED'} else 'INTERRUPTED'
            transition(workspace,row['race_id'],{row['state']},state,'No completed prediction by deadline')
            expired.append(row['race_id'])
    return expired


def report(workspace, output):
    con=connect(workspace)
    try:
        con.execute('BEGIN')
        rows=[dict(r) for r in con.execute('SELECT * FROM races ORDER BY race_id')]
        events=[dict(r) for r in con.execute('SELECT * FROM events ORDER BY sequence')]
    finally:
        con.close()
    ledger=[]
    policy_hash=digest(workspace/'policy.json')
    for row in rows:
        if row['state'] in {'PREDICTED','RESULT_PENDING','EVALUATING','EVALUATED'}:
            saved,predictions=load_saved(Path(row['prediction_dir']),row['prediction_sha'])
            require(saved.get('pilot_policy_sha256')==policy_hash,'Prediction policy mismatch')
            require(saved['race_id']==row['race_id'] and
                    (predictions.start_at==timestamp(row['start_at'])).all(), 'Prediction roster mismatch')
            validate_window(row['start_at'],saved['prediction_at'],predictions.odds_at,row['track_code'])
            validate_save_time(saved['prediction_at'],saved['generated_at'])
        if row['state']=='EVALUATED':
            ledger.append(dict(prediction_dir=row['prediction_dir'],prediction_status_sha256=row['prediction_sha'],
                               evaluation_dir=row['evaluation_dir'],evaluation_status_sha256=row['evaluation_sha']))
    output.mkdir(parents=True,exist_ok=False)
    summary=dict(total_registered=len(rows),target_races=sum(r['state']!='OUT_OF_SCOPE' for r in rows),
                 states=dict(Counter(r['state'] for r in rows)),
                 reasons=dict(Counter(r['reason'] for r in rows if r['reason'])),
                 policy_sha256=policy_hash,roster_sha256=digest(workspace/'roster.json'),
                 population_basis='all venues declared reviewed in frozen daily roster; not independently certified',
                 verified_prediction_count=sum(r['state'] in {'PREDICTED','RESULT_PENDING','EVALUATING','EVALUATED'} for r in rows),
                 fixed_cutoff_verified_for_saved_predictions=any(r['state'] in {'PREDICTED','RESULT_PENDING','EVALUATING','EVALUATED'} for r in rows),phase_promotion=False)
    (output/'coverage.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (output/'races.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    (output/'events.json').write_text(json.dumps(events,indent=2),encoding='utf-8')
    (output/'evaluation-ledger.json').write_text(json.dumps(ledger,indent=2),encoding='utf-8')
    if ledger:
        aggregate(output/'evaluation-ledger.json',output/'metrics')
    return summary


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init'); init.add_argument('--policy',type=Path,required=True)
    init.add_argument('--roster',type=Path,required=True)
    for name in ['collect','predict','evaluate','failure','expire','report']:
        cmd=sub.add_parser(name)
        if name in {'collect','predict','evaluate','failure'}: cmd.add_argument('--race-id',required=True)
        if name=='predict':
            cmd.add_argument('--entries',type=Path); cmd.add_argument('--odds',type=Path)
            cmd.add_argument('--confirmation',type=Path)
        if name=='evaluate': cmd.add_argument('--results',type=Path,required=True)
        if name=='failure': cmd.add_argument('--reason',required=True)
        if name=='report': cmd.add_argument('--output',type=Path,required=True)
    for cmd in sub.choices.values(): cmd.add_argument('--workspace',type=Path,required=True)
    a=parser.parse_args()
    if a.command=='init': result=initialize(a.policy,a.roster,a.workspace)
    elif a.command=='collect': result=collect_race(a.workspace,a.race_id)
    elif a.command=='predict': result=predict_race(a.workspace,a.race_id,a.entries,a.odds,a.confirmation)
    elif a.command=='evaluate': result=evaluate_race(a.workspace,a.race_id,a.results)
    elif a.command=='failure': result=record_failure(a.workspace,a.race_id,a.reason)
    elif a.command=='expire': result=expire(a.workspace)
    else: result=report(a.workspace,a.output)
    print(json.dumps(result))


if __name__=='__main__': main()
