import hashlib
import json
import pytest
from shibata.aggregate_saved import aggregate
from shibata.score_saved import run
from shibata.ingestion.contracts import DataError
from test_score_saved import setup


def prepare(root):
    root.mkdir()
    p,pin,r=setup(root)
    out=root/'evaluation'
    run(p,pin,r,out)
    return dict(prediction_dir=str(p),prediction_status_sha256=pin,evaluation_dir=str(out),
                evaluation_status_sha256=hashlib.sha256((out/'status.json').read_bytes()).hexdigest())


def test_single_run_exact_metrics_and_no_mutation(tmp_path):
    item=prepare(tmp_path/'one')
    ledger=tmp_path/'ledger.json'
    ledger.write_text(json.dumps([item]))
    report=aggregate(ledger,tmp_path/'aggregate')
    assert report['status']=='PASS' and report['omitted_runs']==0
    assert json.loads((tmp_path/'aggregate'/'metrics.json').read_text())==json.loads(
        (tmp_path/'one'/'evaluation'/'metrics.json').read_text())
    with pytest.raises(FileExistsError): aggregate(ledger,tmp_path/'aggregate')


@pytest.mark.parametrize('bad',['duplicate','status_hash','output_hash','empty'])
def test_never_silently_drop_invalid_runs(tmp_path,bad):
    item=prepare(tmp_path/'one')
    rows=[item]
    if bad=='duplicate': rows.append(item.copy())
    if bad=='status_hash': item['evaluation_status_sha256']='0'*64
    if bad=='output_hash': (tmp_path/'one'/'evaluation'/'metrics.json').write_text('{}')
    if bad=='empty': rows=[]
    ledger=tmp_path/'ledger.json'; ledger.write_text(json.dumps(rows))
    with pytest.raises(DataError): aggregate(ledger,tmp_path/'aggregate')
    assert json.loads((tmp_path/'aggregate'/'status.json').read_text())['status']=='FAILED'


def test_two_distinct_races_are_pooled(tmp_path):
    first=prepare(tmp_path/'one')
    root=tmp_path/'two'; root.mkdir()
    p,pin,r=setup(root)
    # Change identifiers only in this synthetic fixture, then pin the new receipt.
    old,new='2024011505010101','2024011505010102'
    s=json.loads((p/'status.json').read_text()); s['race_id']=new
    for name in s['output_sha256']:
        target=p/name
        target.write_text(target.read_text().replace(old,new))
        s['output_sha256'][name]=hashlib.sha256(target.read_bytes()).hexdigest()
    (p/'status.json').write_text(json.dumps(s))
    pin=hashlib.sha256((p/'status.json').read_bytes()).hexdigest()
    m=json.loads((r/'probe.json').read_text(encoding='utf-8-sig')); m['race_key']=new
    for item in m['files']:
        target=r/item['file']; raw=target.read_bytes().replace(old.encode(),new.encode())
        target.write_bytes(raw); item['sha256']=hashlib.sha256(raw).hexdigest()
    (r/'probe.json').write_text(json.dumps(m))
    run(p,pin,r,root/'evaluation')
    second=dict(prediction_dir=str(p),prediction_status_sha256=pin,evaluation_dir=str(root/'evaluation'),
                evaluation_status_sha256=hashlib.sha256((root/'evaluation'/'status.json').read_bytes()).hexdigest())
    ledger=tmp_path/'ledger.json'; ledger.write_text(json.dumps([first,second]))
    report=aggregate(ledger,tmp_path/'aggregate')
    metrics=json.loads((tmp_path/'aggregate'/'metrics.json').read_text())
    assert metrics['rows']==4 and metrics['races']==2 and len(report['runs'])==2
