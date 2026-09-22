import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from shibata.ingestion.contracts import DataError
from shibata.models.logistic import FEATURES
from shibata.retrospective import assemble, reconstruct_race, run
from test_jv_o1 import fixture_record
from test_jv_race import fixture


def race(day='20251004'):
    result = []
    for kind, number in [('RA', 1), ('SE', 1), ('SE', 2)]:
        b = bytearray(fixture(kind, number))
        b[2:11] = ('7' + day).encode()
        b[11:27] = (day + '05010101').encode()
        if kind == 'RA':
            b[697:701] = b'1600'; b[705:707] = b'11'
        else:
            b[27:28] = str(number).encode(); b[78:79] = b'1'
            b[82:84] = f'{number + 2:02}'.encode(); b[288:291] = b'550'
        result.append(bytes(b))
    o = fixture_record(); o[2:11] = ('5' + day).encode()
    o[11:27] = (day + '05010101').encode()
    return result + [bytes(o)]


def capture(tmp_path, payloads):
    path = tmp_path/'capture.json'; folder = Path(str(path)+'.records'); folder.mkdir()
    records = []
    for i, b in enumerate(payloads):
        name = f'record-{i:04d}.bin'; (folder/name).write_bytes(b)
        records.append(dict(file=name, source_file='fixture', size=len(b), sha256=hashlib.sha256(b).hexdigest(),
                            retrieved_at='2026-09-22T09:00:01Z'))
    manifest = dict(dataspec='RACE', option=1, complete=True, init_code=0, open_code=0, close_code=0,
                    started_at='2026-09-22T09:00:00Z', finished_at='2026-09-22T09:00:02Z',
                    fromtime='synthetic', records=records)
    path.write_text(json.dumps(manifest))
    return path


def config():
    return json.loads(Path('configs/logistic-retrospective-v1.json').read_text(encoding='utf-8'))


def test_features_separate_from_labels_and_odds():
    f, r, m = reconstruct_race(race(), '2026-09-22T09:00:02Z')
    assert list(f) == ['race_id', 'horse_id'] + FEATURES
    assert f.runner_count.tolist() == [2, 2] and r.win.tolist() == [1, 0]
    assert m.market_probability.tolist() == pytest.approx([2/3, 1/3])
    changed = race()
    for index, rank in [(1, b'02'), (2, b'01')]:
        b = bytearray(changed[index]); b[334:336] = rank; changed[index] = bytes(b)
    other, _, _ = reconstruct_race(changed, '2026-09-22T09:00:02Z')
    pd.testing.assert_frame_equal(f, other)


@pytest.mark.parametrize('index,start,value,reason', [
    (1, 331, b'3', 'Non-normal'), (2, 336, b'1', 'Non-normal'),
    (0, 701, b'1800', 'Distance'), (1, 291, b'540', 'Carried-weight'),
    (1, 82, b'00', 'Missing'), (3, 45, b'9999', 'capped'),
    (0, 705, b'51', 'flat-race'),
])
def test_whole_race_exclusions(index, start, value, reason):
    payloads = race(); b = bytearray(payloads[index]); b[start:start+len(value)] = value
    payloads[index] = bytes(b)
    with pytest.raises(DataError, match=reason): reconstruct_race(payloads, '2026-09-22T09:00:02Z')


def test_revisions_not_chosen_by_outcome():
    payloads = race(); b = bytearray(payloads[1]); b[288:291] = b'560'
    with pytest.raises(DataError): reconstruct_race(payloads + [bytes(b)], '2026-09-22T09:00:02Z')
    f, _, _ = reconstruct_race(payloads + payloads, '2026-09-22T09:00:02Z')
    assert len(f) == 2


def test_test_period_rejected(tmp_path):
    path = capture(tmp_path, race('20260912'))
    with pytest.raises(DataError, match='Test/outside'): assemble([path], config())


def test_reference_run_and_audit(tmp_path):
    excluded = race('20251005'); b = bytearray(excluded[1]); b[331:332] = b'4'; excluded[1] = bytes(b)
    path = capture(tmp_path, race() + excluded + race('20260725'))
    out = tmp_path/'out'
    status = run(Path('configs/logistic-retrospective-v1.json'), [path], out)
    assert status['status'] == 'COMPLETED_REFERENCE_ONLY'
    assert status['excluded_races'] == 1 and status['included_races'] == 2
    assert status['coverage']['train']['rows'] == 2 and status['coverage']['validation']['rows'] == 2
    assert status['included_months']['train']['202510'] == dict(races=1, rows=2)
    assert status['validation_unknown_categories']['venue'] == 0
    assert status['test_evaluated'] is False and status['pre_race_availability_verified'] is False
    assert len(json.loads((out/'race-audit.json').read_text())) == 3
    with pytest.raises(FileExistsError): run(Path('configs/logistic-retrospective-v1.json'), [path], out)


def test_strict_config_cannot_enable_reference(tmp_path):
    with pytest.raises(DataError, match='Explicit approved'):
        run(Path('configs/logistic-initial-v1.json'), [], tmp_path/'out')
    assert not (tmp_path/'out').exists()
