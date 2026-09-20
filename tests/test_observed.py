import hashlib
import json

import pandas as pd
import pytest

from shibata.ingestion.capture import verify_capture
from shibata.ingestion.contracts import DataError
from shibata.observed import observed_tables, run
from test_jv_o1 import fixture_record
from test_jv_race import fixture


def capture(folder, spec, payloads, at='2024-01-15T11:45:00+09:00'):
    folder.mkdir()
    manifest = dict(transport='JVGets_byte_array', dataspec=spec, race_key='2024011505010101',
                    started_at=at, finished_at=at, complete=True, records=len(payloads),
                    init_code=0, open_code=0, close_code=0, files=[])
    for i, payload in enumerate(payloads):
        name = f'record-{i:04d}.bin'
        (folder / name).write_bytes(payload)
        manifest['files'].append(dict(file=name, size=len(payload), retrieved_at=at,
                                      sha256=hashlib.sha256(payload).hexdigest()))
    save_manifest(folder, manifest)
    return manifest


def save_manifest(folder, manifest):
    (folder / 'probe.json').write_text(json.dumps(manifest), encoding='utf-8-sig')


def inputs(tmp_path, *, entry_status=b'2', quote=b'0020', announcement=b'01151140'):
    entries = []
    for kind, number in [('RA', 1), ('SE', 1), ('SE', 2)]:
        payload = bytearray(fixture(kind, number))
        payload[2:3] = entry_status
        if kind == 'SE':
            payload[334:336] = b'00'
        entries.append(bytes(payload))
    o1 = fixture_record()
    o1[45:49] = quote
    o1[27:35] = announcement
    e, o = tmp_path / 'entries', tmp_path / 'odds'
    capture(e, '0B15', entries)
    capture(o, '0B41', [bytes(o1)])
    return e, o


def test_observed_baseline_and_reproducibility(tmp_path):
    e, o = inputs(tmp_path)
    for folder in ['first', 'second']:
        report = run(e, o, tmp_path / folder, '2024-01-15T11:50:00+09:00')
        assert report['capture_manifest_verified'] and not report['results_used']
        assert not report['generated_before_scheduled_start']  # replay, not live prediction
    a, b = tmp_path / 'first', tmp_path / 'second'
    assert (a / 'predictions.csv').read_bytes() == (b / 'predictions.csv').read_bytes()
    prediction = pd.read_csv(a / 'predictions.csv', dtype={'horse_id': str})
    assert prediction.market_probability.tolist() == pytest.approx([2/3, 1/3])
    assert prediction.horse_id.tolist() == ['0000000001', '0000000002']
    assert 'final_rank_raw' not in prediction and 'win' not in prediction
    with pytest.raises(FileExistsError):
        run(e, o, a, '2024-01-15T11:50:00+09:00')


@pytest.mark.parametrize('damage', ['hash', 'size', 'missing', 'extra', 'duplicate', 'traversal',
                                  'incomplete', 'api', 'boolean_api', 'count', 'naive',
                                  'backwards', 'outside', 'wrong_race', 'old_transport'])
def test_corrupt_capture_rejected(tmp_path, damage):
    e, _ = inputs(tmp_path)
    m = json.loads((e / 'probe.json').read_text(encoding='utf-8-sig'))
    if damage == 'hash': m['files'][0]['sha256'] = '0' * 64
    if damage == 'size': m['files'][0]['size'] += 1
    if damage == 'missing': (e / 'record-0000.bin').unlink()
    if damage == 'extra': (e / 'record-0003.bin').write_bytes(b'wrong')
    if damage == 'duplicate': m['files'][1]['file'] = m['files'][0]['file']
    if damage == 'traversal': m['files'][0]['file'] = '../record-0000.bin'
    if damage == 'incomplete': m['complete'] = False
    if damage == 'api': m['close_code'] = -1
    if damage == 'boolean_api': m['open_code'] = False
    if damage == 'count': m['records'] = 2
    if damage == 'naive': m['started_at'] = '2024-01-15T11:45:00'
    if damage == 'backwards': m['started_at'] = '2024-01-15T11:46:00+09:00'
    if damage == 'outside': m['files'][0]['retrieved_at'] = '2024-01-15T11:46:00+09:00'
    if damage == 'wrong_race': m['race_key'] = '2024011505010102'
    if damage == 'old_transport': m.pop('transport')
    save_manifest(e, m)
    with pytest.raises(DataError): verify_capture(e)


@pytest.mark.parametrize('cutoff', ['2024-01-15T11:44:00+09:00', '2024-01-15T12:00:00+09:00'])
def test_cutoff_violations_leave_failed_status(tmp_path, cutoff):
    e, o = inputs(tmp_path)
    out = tmp_path / 'output'
    with pytest.raises(DataError): run(e, o, out, cutoff)
    assert json.loads((out / 'status.json').read_text())['status'] == 'FAILED'
    assert not (out / 'predictions.csv').exists()


@pytest.mark.parametrize('status', [b'3', b'6', b'9'])
def test_post_race_or_cancelled_entry_not_accepted(tmp_path, status):
    e, o = inputs(tmp_path, entry_status=status)
    with pytest.raises(DataError): observed_tables(e, o, '2024-01-15T11:50:00+09:00')


@pytest.mark.parametrize('quote', [b'0000', b'----', b'****', b'9999'])
def test_unsupported_quotes_not_imputed(tmp_path, quote):
    e, o = inputs(tmp_path, quote=quote)
    with pytest.raises(DataError): observed_tables(e, o, '2024-01-15T11:50:00+09:00')


@pytest.mark.parametrize('announcement', [b'01151146', b'01131200'])
def test_future_or_unresolvable_announcement_rejected(tmp_path, announcement):
    e, o = inputs(tmp_path, announcement=announcement)
    with pytest.raises(DataError): observed_tables(e, o, '2024-01-15T11:50:00+09:00')


def test_final_odds_rejected_even_with_valid_hash(tmp_path):
    e, o = inputs(tmp_path)
    payload = bytearray((o / 'record-0000.bin').read_bytes())
    payload[2] = ord('3')
    new = tmp_path / 'final'
    capture(new, '0B41', [bytes(payload)])
    with pytest.raises(DataError, match='intermediate'):
        observed_tables(e, new, '2024-01-15T11:50:00+09:00')


def test_future_execution_cutoff_rejected(tmp_path):
    e, o = inputs(tmp_path)
    with pytest.raises(DataError, match='future at execution'):
        run(e, o, tmp_path / 'future', '2100-01-15T11:50:00+09:00')


def test_ambiguous_odds_revisions_fail_instead_of_choosing(tmp_path):
    e, o = inputs(tmp_path)
    first = (o / 'record-0000.bin').read_bytes()
    second = bytearray(first)
    second[45:49] = b'0030'
    revised = tmp_path / 'revised'
    capture(revised, '0B41', [first, bytes(second)])
    with pytest.raises(DataError, match='ambiguous'):
        run(e, revised, tmp_path / 'ambiguous', '2024-01-15T11:50:00+09:00')


def test_new_year_announcement_uses_previous_year(tmp_path):
    e, o = inputs(tmp_path)
    for folder in (e, o):
        m = json.loads((folder / 'probe.json').read_text(encoding='utf-8-sig'))
        m['race_key'] = '2025010105010101'
        m['started_at'] = m['finished_at'] = '2025-01-01T10:00:00+09:00'
        for item in m['files']:
            payload = bytearray((folder / item['file']).read_bytes())
            payload[3:11] = b'20241231'
            payload[11:27] = m['race_key'].encode()
            if payload[:2] == b'O1': payload[27:35] = b'12312000'
            (folder / item['file']).write_bytes(payload)
            item['sha256'] = hashlib.sha256(payload).hexdigest()
            item['retrieved_at'] = m['finished_at']
        save_manifest(folder, m)
    _, _, odds, _ = observed_tables(e, o, '2025-01-01T10:01:00+09:00')
    assert odds.iloc[0].odds_at == pd.Timestamp('2024-12-31T20:00:00+09:00')
