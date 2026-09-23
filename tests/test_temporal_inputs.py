import pandas as pd
import pytest

from shibata.ingestion.contracts import DataError
from shibata.temporal_inputs import prior_history, cutoff_snapshots

HASH = 'a'*64
START = '2026-09-26T12:00:00+09:00'
CUTOFF = '2026-09-26T11:50:00+09:00'


def targets():
    return pd.DataFrame([dict(race_id='target', horse_id='horse1',
                              start_at=START, cutoff_at=CUTOFF)])


def history():
    return pd.DataFrame([
        dict(race_id='old', horse_id='horse1', race_at='2026-09-01T12:00:00+09:00',
             available_at='2026-09-01T13:00:00+09:00', source_sha256=HASH, value=2),
        dict(race_id='late_result', horse_id='horse1', race_at='2026-09-25T12:00:00+09:00',
             available_at='2026-09-26T11:50:01+09:00', source_sha256='b'*64, value=1),
        dict(race_id='target', horse_id='horse1', race_at=START,
             available_at='2026-09-26T13:00:00+09:00', source_sha256='c'*64, value=1),
        dict(race_id='future', horse_id='horse1', race_at='2026-09-27T12:00:00+09:00',
             available_at='2026-09-27T13:00:00+09:00', source_sha256='d'*64, value=9),
    ])


def test_past_only_and_future_outcome_changes_do_not_change_selected_history():
    selected, audit = prior_history(targets(), history())
    assert selected.race_id_history.tolist() == ['old']
    assert set(audit.reason) == {'ELIGIBLE', 'NOT_AVAILABLE_AT_CUTOFF',
                                 'SAME_RACE', 'NOT_PREVIOUS_RACE'}
    changed = history(); changed.loc[changed.race_id == 'future', 'value'] = 999
    changed.loc[changed.race_id == 'target', 'value'] = 888
    after, _ = prior_history(targets(), changed)
    assert after[['race_id_history', 'value']].equals(selected[['race_id_history', 'value']])


def test_exact_cutoff_is_included_and_missing_history_is_not_filled():
    old = history().iloc[[0]].copy()
    old['available_at'] = CUTOFF
    selected, _ = prior_history(targets(), old)
    assert len(selected) == 1
    old['horse_id'] = 'other'
    selected, audit = prior_history(targets(), old)
    assert selected.empty and audit.reason.tolist() == ['NO_HISTORY']
    assert pd.isna(audit.value.iloc[0])


@pytest.mark.parametrize('damage', ['missing', 'duplicate', 'naive_time', 'bad_hash', 'before_race'])
def test_bad_history_provenance_is_rejected(damage):
    old = history().iloc[[0]].copy()
    if damage == 'missing': old['value'] = None
    if damage == 'duplicate': old = pd.concat([old, old], ignore_index=True)
    if damage == 'naive_time': old['available_at'] = '2026-09-01T13:00:00'
    if damage == 'bad_hash': old['source_sha256'] = ''
    if damage == 'before_race': old['available_at'] = '2026-09-01T11:00:00+09:00'
    with pytest.raises(DataError):
        prior_history(targets(), old)


def test_t_minus_five_odds_cannot_enter_t_minus_ten_model():
    snapshots = pd.DataFrame([
        dict(race_id='target', snapshot_id='t10', observed_at=CUTOFF,
             available_at=CUTOFF, source_sha256=HASH),
        dict(race_id='target', snapshot_id='t5',
             observed_at='2026-09-26T11:55:00+09:00',
             available_at='2026-09-26T11:55:01+09:00', source_sha256='b'*64),
    ])
    selected, audit = cutoff_snapshots(targets(), snapshots)
    assert selected.snapshot_id.tolist() == ['t10']
    assert audit.reason.tolist() == ['ELIGIBLE', 'AFTER_CUTOFF']
    changed = snapshots.copy(); changed.loc[1, 'source_sha256'] = 'c'*64
    after, _ = cutoff_snapshots(targets(), changed)
    assert after.snapshot_id.tolist() == selected.snapshot_id.tolist()


def test_unknown_race_snapshot_is_visible_but_not_selected():
    snapshot = pd.DataFrame([dict(race_id='other', snapshot_id='one',
                                  observed_at=CUTOFF, available_at=CUTOFF,
                                  source_sha256=HASH)])
    selected, audit = cutoff_snapshots(targets(), snapshot)
    assert selected.empty and audit.reason.tolist() == ['UNKNOWN_RACE']
