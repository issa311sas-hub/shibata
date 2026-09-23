"""Fictional JV-format captures for an offline integration rehearsal."""
import hashlib
import json
from pathlib import Path

import pandas as pd

from .ingestion.contracts import require
from .observed import observed_tables
from .observed_features import FEATURES, build

DAYS = ('20260101', '20260201', '20260701')


def _race_record(kind, key, number=1):
    size = 1272 if kind == 'RA' else 555
    raw = bytearray(b' '*(size-2)+b'\r\n')
    raw[:27] = (kind+'2'+key[:8]+key).encode('ascii')
    if kind == 'RA':
        raw[697:701] = b'1600'
        raw[705:707] = b'17'  # Turf, flat.
        raw[873:877] = b'1200'
        raw[881:885] = b'0400'  # Four registered; actual starter count still empty.
    else:
        raw[27:28] = str(number).encode('ascii')
        raw[28:30] = f'{number:02d}'.encode('ascii')
        raw[30:40] = f'{number:010d}'.encode('ascii')
        raw[78:79] = b'1'
        raw[82:84] = f'{2+number:02d}'.encode('ascii')
        raw[288:291] = b'550'
        raw[331:332] = b'0'
        raw[334:337] = b'000'
    return bytes(raw)


def _odds_record(key):
    raw = bytearray(b' '*960+b'\r\n')
    raw[:27] = ('O11'+key[:8]+key).encode('ascii')
    raw[27:35] = (key[4:8]+'1147').encode('ascii')
    raw[35:43] = b'04047770'
    for number in range(1, 5):
        start = 43+(number-1)*8
        raw[start:start+8] = f'{number:02d}{number*20:04d}{number:02d}'.encode('ascii')
    return bytes(raw)


def _capture(folder: Path, spec, key, records, observed_at):
    folder.mkdir(parents=True, exist_ok=False)
    files = []
    for i, payload in enumerate(records):
        name = f'record-{i:04d}.bin'
        (folder/name).write_bytes(payload)
        files.append(dict(file=name, size=len(payload), retrieved_at=observed_at,
                          sha256=hashlib.sha256(payload).hexdigest()))
    manifest = dict(transport='JVGets_byte_array', dataspec=spec, race_key=key,
                    started_at=observed_at, finished_at=observed_at, complete=True,
                    records=len(records), init_code=0, open_code=0, close_code=0, files=files,
                    synthetic_fixture=True)
    (folder/'probe.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')


def assemble(root: Path):
    """Return decoded features, separate fictional labels and validation market."""
    root.mkdir(parents=True, exist_ok=False)
    features, labels, market = [], [], None
    for day in DAYS:
        key = day+'05010101'
        folder = root/key
        before = f'{day[:4]}-{day[4:6]}-{day[6:]}T11:48:00+09:00'
        cutoff = f'{day[:4]}-{day[4:6]}-{day[6:]}T11:50:00+09:00'
        entries, odds = folder/'entries', folder/'odds'
        _capture(entries, '0B15', key,
                 [_race_record('RA', key), *[_race_record('SE', key, n) for n in range(1, 5)]],
                 before)
        _capture(odds, '0B41', key, [_odds_record(key)],
                 f'{day[:4]}-{day[4:6]}-{day[6:]}T11:49:00+09:00')
        frame, _ = build(entries, odds, cutoff)
        require(set(frame) == set(FEATURES)|{'race_id', 'horse_id', 'prediction_at'} and
                len(frame) == 4 and frame.race_id.eq(key).all(),
                'Unexpected decoded synthetic feature population')
        features.append(frame.drop(columns='prediction_at'))
        labels.extend(dict(race_id=key, horse_id=f'{n:010d}', win=int(n == 1))
                      for n in range(1, 5))
        if day == DAYS[-1]:
            races, _, quotes, _ = observed_tables(entries, odds, cutoff)
            market = quotes[['race_id', 'horse_id', 'win_odds', 'popularity']].copy()
            market['start_at'] = races.iloc[0].start_at
            market['odds_rank'] = market.win_odds.rank(method='min').astype(int)
            inverse = 1/market.win_odds
            market['market_probability'] = inverse/inverse.sum()
    features = pd.concat(features, ignore_index=True)
    labels = pd.DataFrame(labels)
    require(not labels.duplicated(['race_id', 'horse_id']).any() and
            set(map(tuple, features[['race_id', 'horse_id']].to_numpy())) ==
            set(map(tuple, labels[['race_id', 'horse_id']].to_numpy())),
            'Synthetic feature/label identity mismatch')
    dataset = features.merge(labels, on=['race_id', 'horse_id'], validate='one_to_one')
    return dataset, labels, market
