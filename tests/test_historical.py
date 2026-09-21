import hashlib
import json
import pytest
from shibata.ingestion.historical import index_capture
from shibata.ingestion.contracts import DataError
from test_jv_race import fixture


def capture(tmp_path):
    path=tmp_path/'capture.json'; folder=tmp_path/'capture.json.records';folder.mkdir()
    records=[]
    for i,b in enumerate([fixture('RA',1),fixture('SE',1)]):
        name=f'record-{i:04d}.bin';(folder/name).write_bytes(b)
        records.append(dict(file=name,source_file='vendor-file',size=len(b),
                            sha256=hashlib.sha256(b).hexdigest(),retrieved_at='2026-09-21T12:00:01Z'))
    m=dict(dataspec='RACE',option=1,complete=True,init_code=0,open_code=0,close_code=0,
           started_at='2026-09-21T12:00:00Z',finished_at='2026-09-21T12:00:02Z',
           fromtime='20260920000000-20260920235959',records=records)
    path.write_text(json.dumps(m))
    return path,m,folder


def test_index_keeps_no_availability_inference(tmp_path):
    path,m,folder=capture(tmp_path)
    out=tmp_path/'out';summary=index_capture(path,out)
    assert summary['record_count']==2 and summary['decoded_count']==2
    rows=[json.loads(s) for s in (out/'records.jsonl').read_text().splitlines()]
    assert all(r['availability_at'] is None and not r['training_ready'] for r in rows)
    assert summary['latest_revision_selected'] is False
    with pytest.raises(FileExistsError): index_capture(path,out)


@pytest.mark.parametrize('bad',['hash','path','missing','extra','incomplete','clock','boolean_code'])
def test_corrupt_capture_rejected_before_output(tmp_path,bad):
    path,m,folder=capture(tmp_path)
    if bad=='hash': (folder/'record-0000.bin').write_bytes(b'changed')
    if bad=='path': m['records'][0]['file']='../escape.bin'
    if bad=='missing': (folder/'record-0000.bin').unlink()
    if bad=='extra': (folder/'extra.bin').write_bytes(b'irrelevant')
    if bad=='incomplete': m['complete']=False
    if bad=='clock': m['records'][0]['retrieved_at']='2026-09-21T12:01:00Z'
    if bad=='boolean_code': m['open_code']=False
    path.write_text(json.dumps(m))
    with pytest.raises(DataError): index_capture(path,tmp_path/'out')
    assert not (tmp_path/'out').exists()


def test_unsupported_revision_preserved(tmp_path):
    path,m,folder=capture(tmp_path)
    p=folder/'record-0000.bin';b=bytearray(p.read_bytes());b[2]=ord('9');p.write_bytes(b)
    m['records'][0]['sha256']=hashlib.sha256(b).hexdigest();path.write_text(json.dumps(m))
    summary=index_capture(path,tmp_path/'out')
    assert summary['record_count']==2 and summary['decoded_count']==1
    assert summary['status_counts']['RA:9']==1


def test_two_revisions_of_same_race_are_not_collapsed(tmp_path):
    path,m,folder=capture(tmp_path)
    original=bytearray((folder/'record-0000.bin').read_bytes());original[2]=ord('2')
    name='record-0002.bin';(folder/name).write_bytes(original)
    m['records'].append(dict(m['records'][0],file=name,sha256=hashlib.sha256(original).hexdigest()))
    path.write_text(json.dumps(m))
    summary=index_capture(path,tmp_path/'out')
    assert summary['record_count']==3 and summary['race_count']==1
    rows=[json.loads(s) for s in (tmp_path/'out'/'records.jsonl').read_text().splitlines()]
    assert len([r for r in rows if r['record_type']=='RA'])==2
