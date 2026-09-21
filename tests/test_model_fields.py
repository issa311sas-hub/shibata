import pytest
from shibata.ingestion.model_fields import decode_model_fields
from shibata.ingestion.contracts import DataError
from test_jv_race import fixture


def test_horse_units_and_missing():
    b=bytearray(fixture('SE',1));b[27:28]=b'4';b[78:79]=b'2';b[82:84]=b'03';b[288:291]=b'555'
    r=decode_model_fields(bytes(b))
    assert r['raw_fields']==dict(age=3,sex='2',bracket_number=4,horse_number=1,carried_weight=55.5)
    assert r['training_ready'] is False and r['availability_at'] is None
    b[82:84]=b'00';b[288:291]=b'000';b[78:79]=b'0'
    r=decode_model_fields(bytes(b))['raw_fields']
    assert r['age'] is None and r['carried_weight'] is None and r['sex'] is None


@pytest.mark.parametrize('track,surface',[('10','turf'),('22','turf'),('23','dirt'),('29','dirt'),('27','sand'),('28','sand'),('51',None)])
def test_race_fields(track,surface):
    b=bytearray(fixture('RA',1));b[697:701]=b'1600';b[705:707]=track.encode()
    r=decode_model_fields(bytes(b))
    assert r['raw_fields']['distance']==1600 and r['raw_fields']['surface']==surface
    assert 'runner_count' not in r['raw_fields']


def test_invalid_weight_rejected():
    b=bytearray(fixture('SE',1));b[78:79]=b'1';b[288:291]=b'5X0'
    with pytest.raises(DataError): decode_model_fields(bytes(b))

