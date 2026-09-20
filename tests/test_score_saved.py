"""Synthetic captures and receipts only; never rewrite a real saved prediction."""
import hashlib
import json
import math

import pandas as pd
import pytest

from shibata.ingestion.contracts import DataError
from shibata.score_saved import load_saved, result_labels, run
from shibata.observed import run as predict
from test_observed import inputs, capture, rewrite_record, save_manifest
from test_jv_race import fixture


def setup(tmp_path):
    e, o = inputs(tmp_path)
    p = tmp_path / 'prediction'
    predict(e, o, p, '2024-01-15T11:50:00+09:00')
    # Fixture models an earlier live run; the production pipeline cannot rewrite this.
    status = json.loads((p / 'status.json').read_text())
    status['generated_at'] = '2024-01-15T11:50:01+09:00'
    status['generated_before_scheduled_start'] = True
    (p / 'status.json').write_text(json.dumps(status), encoding='utf-8')
    pin = hashlib.sha256((p / 'status.json').read_bytes()).hexdigest()
    r = tmp_path / 'result'
    capture(r, '0B12', [fixture('RA'), fixture('SE', 1), fixture('SE', 2)],
            at='2024-01-15T12:10:00+09:00')
    return p, pin, r


def test_score_saved_without_recomputing_or_mutating(tmp_path):
    p, pin, r = setup(tmp_path)
    before = {x.name:x.read_bytes() for x in p.iterdir()}
    report = run(p, pin, r, tmp_path / 'score')
    assert report['status'] == 'PASS' and report['prediction_recomputed'] is False
    assert before == {x.name:x.read_bytes() for x in p.iterdir()}
    metrics = json.loads((tmp_path / 'score' / 'metrics.json').read_text())
    assert metrics['binary_log_loss_per_runner'] == pytest.approx(-math.log(2/3))
    assert metrics['binary_brier_per_runner'] == pytest.approx(1/9)
    assert metrics['winner_log_loss_per_race'] == pytest.approx(-math.log(2/3))
    assert metrics['multiclass_brier_per_race'] == pytest.approx(2/9)
    assert metrics['roi'] is None
    assert report['exact_settlement_time'] is None
    labels = pd.read_csv(tmp_path / 'score' / 'observed_results.csv')
    assert 'result_observed_at' in labels and 'settled_at' not in labels
    with pytest.raises(FileExistsError): run(p, pin, r, tmp_path / 'score')


@pytest.mark.parametrize('target', ['status.json', 'predictions.csv', 'entries.csv', 'odds.csv', 'races.csv'])
def test_saved_artifact_tampering_rejected_before_results(tmp_path, target):
    p, pin, _ = setup(tmp_path)
    with (p / target).open('ab') as f: f.write(b' ')
    with pytest.raises(DataError, match='hash mismatch'):
        run(p, pin, tmp_path / 'nonexistent-result', tmp_path / 'failed')
    status = json.loads((tmp_path / 'failed' / 'status.json').read_text())
    assert status['status'] == 'FAILED'
    assert not (tmp_path / 'failed' / 'metrics.json').exists()


@pytest.mark.parametrize('bad', ['late', 'flag', 'cutoff'])
def test_replay_or_invalid_generation_time_rejected(tmp_path, bad):
    p, _, _ = setup(tmp_path)
    s = json.loads((p / 'status.json').read_text())
    if bad == 'late': s['generated_at'] = '2024-01-15T12:01:00+09:00'
    if bad == 'flag': s['generated_before_scheduled_start'] = False
    if bad == 'cutoff': s['generated_at'] = '2024-01-15T11:49:00+09:00'
    (p / 'status.json').write_text(json.dumps(s))
    pin = hashlib.sha256((p / 'status.json').read_bytes()).hexdigest()
    with pytest.raises(DataError): load_saved(p, pin)


@pytest.mark.parametrize('bad', ['partial', 'dead_heat', 'abnormal', 'rank', 'horse', 'number',
                                'count', 'start', 'date', 'early', 'wrong_spec', 'missing'])
def test_result_edge_cases_fail_closed(tmp_path, bad):
    p, pin, r = setup(tmp_path)
    _, predictions = load_saved(p, pin)
    if bad == 'partial': rewrite_record(r, 0, lambda b:b.__setitem__(2,ord('3')))
    if bad == 'dead_heat': rewrite_record(r, 1, lambda b:b.__setitem__(336,ord('1')))
    if bad == 'abnormal': rewrite_record(r, 1, lambda b:b.__setitem__(331,ord('1')))
    if bad == 'rank': rewrite_record(r, 2, lambda b:b.__setitem__(slice(334,336),b'01'))
    if bad == 'horse': rewrite_record(r, 1, lambda b:b.__setitem__(slice(30,40),b'0000000009'))
    if bad == 'number': rewrite_record(r, 1, lambda b:b.__setitem__(slice(28,30),b'03'))
    if bad == 'count': rewrite_record(r, 0, lambda b:b.__setitem__(slice(883,885),b'01'))
    if bad == 'start': rewrite_record(r, 0, lambda b:b.__setitem__(slice(873,877),b'1205'))
    if bad == 'date': rewrite_record(r, 1, lambda b:b.__setitem__(slice(3,11),b'20240114'))
    if bad == 'missing': (r / 'record-0002.bin').unlink()
    if bad in ('early','wrong_spec'):
        m=json.loads((r/'probe.json').read_text(encoding='utf-8-sig'))
        if bad=='wrong_spec': m['dataspec']='0B15'
        else:
            m['started_at']=m['finished_at']='2024-01-15T11:59:00+09:00'
            for item in m['files']: item['retrieved_at']=m['finished_at']
        save_manifest(r,m)
    with pytest.raises(DataError): result_labels(r,predictions)


def test_different_winner_only_changes_scores_not_predictions(tmp_path):
    p,pin,r=setup(tmp_path)
    before=(p/'predictions.csv').read_bytes()
    run(p,pin,r,tmp_path/'score1')
    rewrite_record(r,1,lambda b:b.__setitem__(slice(334,336),b'02'))
    rewrite_record(r,2,lambda b:b.__setitem__(slice(334,336),b'01'))
    run(p,pin,r,tmp_path/'score2')
    a=json.loads((tmp_path/'score1'/'metrics.json').read_text())
    b=json.loads((tmp_path/'score2'/'metrics.json').read_text())
    assert a['binary_log_loss_per_runner'] != b['binary_log_loss_per_runner']
    assert (p/'predictions.csv').read_bytes()==before
