import hashlib
import json
import pytest
from shibata.observed_features import build,FEATURES
from shibata.ingestion.contracts import DataError
from test_observed import inputs


def prepared(tmp_path):
    e,o=inputs(tmp_path)
    p=e/'probe.json';m=json.loads(p.read_text(encoding='utf-8-sig'))
    for item in m['files']:
        f=e/item['file'];b=bytearray(f.read_bytes())
        if b[:2]==b'RA': b[697:701]=b'1600';b[705:707]=b'17'
        else: b[27:28]=b'1';b[78:79]=b'1';b[82:84]=b'03';b[288:291]=b'550'
        f.write_bytes(b);item['sha256']=hashlib.sha256(b).hexdigest()
    p.write_text(json.dumps(m))
    return e,o


def test_verified_inputs_have_no_result_columns(tmp_path):
    e,o=prepared(tmp_path)
    frame,_=build(e,o,'2024-01-15T11:50:00+09:00')
    assert set(frame)==set(FEATURES)|{'race_id','horse_id','prediction_at'}
    assert frame.runner_count.tolist()==[2,2]
    assert frame.carried_weight.tolist()==[55,55]


def test_late_capture_rejected(tmp_path):
    e,o=prepared(tmp_path)
    with pytest.raises(DataError):build(e,o,'2024-01-15T11:44:00+09:00')


def test_missing_feature_not_imputed(tmp_path):
    e,o=prepared(tmp_path)
    p=e/'probe.json';m=json.loads(p.read_text());item=m['files'][1]
    f=e/item['file'];b=bytearray(f.read_bytes());b[82:84]=b'00';f.write_bytes(b)
    item['sha256']=hashlib.sha256(b).hexdigest();p.write_text(json.dumps(m))
    with pytest.raises(DataError,match='Missing approved feature'):build(e,o,'2024-01-15T11:50:00+09:00')


def test_manifest_changed_between_validation_and_assembly(tmp_path,monkeypatch):
    from shibata import observed_features
    e,o=prepared(tmp_path)
    original=observed_features.verify_capture
    def changed(path):
        result=original(path);result['manifest_sha256']='changed';return result
    monkeypatch.setattr(observed_features,'verify_capture',changed)
    with pytest.raises(DataError,match='Entries changed'):
        build(e,o,'2024-01-15T11:50:00+09:00')
