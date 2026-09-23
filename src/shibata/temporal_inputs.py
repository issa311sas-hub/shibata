"""Synthetic-tested time eligibility gates for future features and snapshots."""
import re

import pandas as pd

from .ingestion.contracts import require, timestamp

TARGET = {'race_id', 'horse_id', 'start_at', 'cutoff_at'}
HISTORY = {'race_id', 'horse_id', 'race_at', 'available_at', 'source_sha256', 'value'}
SNAPSHOTS = {'race_id', 'snapshot_id', 'observed_at', 'available_at', 'source_sha256'}


def _frame(frame, required, key):
    require(isinstance(frame, pd.DataFrame) and set(frame) == required and
            frame.columns.is_unique, 'Unexpected temporal input columns')
    require(not frame.empty and not frame[list(required)].isna().any().any(),
            'Missing temporal input; no zero fill')
    require(not frame.duplicated(key).any(), 'Duplicate temporal input identity')
    out = frame.copy()
    for column in ('race_id', 'horse_id', 'snapshot_id'):
        if column in out:
            require(out[column].map(lambda v: isinstance(v, str) and bool(v.strip())).all(),
                    'Invalid temporal input identity')
    if 'source_sha256' in out:
        require(out.source_sha256.map(lambda v: isinstance(v, str) and
                    re.fullmatch('[0-9a-f]{64}', v) is not None).all(),
                'Missing or invalid source hash')
    for column in ('start_at', 'cutoff_at', 'race_at', 'observed_at', 'available_at'):
        if column in out:
            out[column] = pd.to_datetime([timestamp(v, column) for v in out[column]], utc=True)
    return out


def _targets(frame):
    targets = _frame(frame, TARGET, ['race_id', 'horse_id'])
    require((targets.cutoff_at < targets.start_at).all(), 'Cutoff must precede start')
    require(targets.groupby('race_id').start_at.nunique().eq(1).all() and
            targets.groupby('race_id').cutoff_at.nunique().eq(1).all(),
            'Inconsistent race schedule')
    return targets


def prior_history(target_frame, history_frame):
    """Select only a horse's earlier, already available results; retain exclusions."""
    targets = _targets(target_frame)
    history = _frame(history_frame, HISTORY, ['race_id', 'horse_id'])
    require((history.available_at >= history.race_at).all(),
            'Historical result available before its race')
    joined = targets.merge(history, on='horse_id', how='left', suffixes=('_target', '_history'),
                           validate='many_to_many', indicator=True)
    joined['reason'] = 'ELIGIBLE'
    joined.loc[joined._merge == 'left_only', 'reason'] = 'NO_HISTORY'
    joined.loc[(joined._merge == 'both') &
               (joined.race_id_history == joined.race_id_target), 'reason'] = 'SAME_RACE'
    joined.loc[(joined.reason == 'ELIGIBLE') &
               (joined.race_at >= joined.start_at), 'reason'] = 'NOT_PREVIOUS_RACE'
    joined.loc[(joined.reason == 'ELIGIBLE') &
               (joined.available_at > joined.cutoff_at), 'reason'] = 'NOT_AVAILABLE_AT_CUTOFF'
    audit = joined.drop(columns='_merge')
    eligible = audit.loc[audit.reason == 'ELIGIBLE'].copy()
    return eligible, audit


def cutoff_snapshots(target_frame, snapshot_frame):
    """Reject T-5 observations for a T-10 target without changing the cutoff."""
    targets = _targets(target_frame)[['race_id', 'cutoff_at']].drop_duplicates()
    snapshots = _frame(snapshot_frame, SNAPSHOTS, ['race_id', 'snapshot_id'])
    require((snapshots.available_at >= snapshots.observed_at).all(),
            'Snapshot available before observation')
    joined = snapshots.merge(targets, on='race_id', how='left', validate='many_to_one',
                             indicator=True)
    joined['reason'] = 'ELIGIBLE'
    joined.loc[joined._merge == 'left_only', 'reason'] = 'UNKNOWN_RACE'
    joined.loc[(joined.reason == 'ELIGIBLE') &
               (joined.available_at > joined.cutoff_at), 'reason'] = 'AFTER_CUTOFF'
    audit = joined.drop(columns='_merge')
    eligible = audit.loc[audit.reason == 'ELIGIBLE'].copy()
    return eligible, audit
