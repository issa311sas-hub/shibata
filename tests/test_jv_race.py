import copy
import pytest
from shibata.ingestion.contracts import DataError
from shibata.ingestion.jv_race import decode_race_record, audit_mapping


def fixture(kind, number=1):
    b=bytearray(b' ' * ((1272 if kind=='RA' else 555)-2)+b'\r\n')
    b[:27]=(kind+'6202401152024011505010101').encode()
    if kind=='RA':
        b[873:877]=b'1200'
        b[881:885]=b'0202'
    else:
        b[28:30]=f'{number:02}'.encode()
        b[30:40]=f'{number:010}'.encode()
        b[331:332]=b'0'
        b[334:337]=(f'{number:02}'+'0').encode()
    return bytes(b)


def inputs():
    records=[decode_race_record(fixture('RA'))]+[decode_race_record(fixture('SE',n)) for n in (1,2)]
    odds=[dict(race_key=records[0]['race_key'],registered_count=2,
               slots=[dict(horse_number_raw='01'),dict(horse_number_raw='02')])]
    return records,odds


def test_mapping_is_not_availability_proof():
    records,odds=inputs()
    result=audit_mapping(records,odds)
    assert result['complete_normal_result']
    assert result['mapping_consistent']
    assert not result['prediction_ready']
    assert records[1]['horse_id']=='0000000001'
    assert 'result_settlement_timestamp' in result['unresolved']


@pytest.mark.parametrize('damage',['duplicate','missing','revision','race','odds','ranking'])
def test_bad_mapping_rejected(damage):
    r,o=inputs()
    if damage=='duplicate': r[2]=copy.deepcopy(r[1])
    if damage=='missing': r.pop()
    if damage=='revision': r[1]['data_status']='2'
    if damage=='race': o[0]['race_key']='2024011505010102'
    if damage=='odds': o[0]['slots'].pop()
    if damage=='ranking': r[2]['final_rank_raw']='01'
    with pytest.raises(DataError): audit_mapping(r,o)


@pytest.mark.parametrize('field,value',[('abnormal_code_raw','1'),('dead_heat_raw','1'),('final_rank_raw','  ')])
def test_special_results_not_normalized(field,value):
    r,o=inputs()
    r[1][field]=value
    assert not audit_mapping(r,o)['complete_normal_result']


@pytest.mark.parametrize('kind',['RA','SE'])
def test_truncation_and_unsupported_status(kind):
    with pytest.raises(DataError): decode_race_record(fixture(kind)[:-1])
    b=bytearray(fixture(kind)); b[2]=ord('1')
    with pytest.raises(DataError): decode_race_record(bytes(b))
