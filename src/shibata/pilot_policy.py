"""The user-approved pilot policy. It is separate from training/test periods."""
import hashlib
import json
from pathlib import Path
import pandas as pd
from .ingestion.contracts import require, timestamp

DATES = ['2026-09-26', '2026-09-27', '2026-10-03', '2026-10-04']
# JV-Data code table 2009: 10..29 flat, 51..59 steeplechase.
FLAT_TRACKS = {str(i) for i in range(10, 30)}


def load_policy(path: Path):
    raw = path.read_bytes()
    policy = json.loads(raw.decode('utf-8-sig'))
    required = dict(experiment_id='market-observed-pilot-v1', status='ADOPTED',
                    timezone='Asia/Tokyo', observation_dates=DATES,
                    cutoff_minutes_before_scheduled_start=10, max_odds_age_minutes_at_cutoff=5,
                    prediction_save_deadline_minutes_after_cutoff=1,
                    model='normalized_inverse_win_odds', metric_definition_version='v1')
    require(all(policy.get(k) == v for k, v in required.items()), 'Policy differs from approved v1')
    require(policy.get('execution_enabled') is True and policy.get('roi_enabled') is False,
            'Policy is not enabled for this pilot')
    require(all(policy.get(k) is None for k in ('train_period', 'validation_period', 'test_period')),
            'Pilot must not assign training/test periods')
    return policy, hashlib.sha256(raw).hexdigest()


def validate_window(start_at, cutoff, odds_at, track_code):
    start, cutoff = timestamp(start_at), timestamp(cutoff)
    require(start.tz_convert('Asia/Tokyo').date().isoformat() in DATES, 'Race outside approved dates')
    require(track_code in FLAT_TRACKS, 'Pilot accepts only flat races')
    require(cutoff == start - pd.Timedelta(minutes=10), 'Cutoff must be exactly 10 minutes before start')
    ages = [cutoff - timestamp(t) for t in odds_at]
    require(bool(ages) and all(pd.Timedelta(0) <= age <= pd.Timedelta(minutes=5) for age in ages),
            'Odds must be no more than five minutes old at cutoff')


def validate_save_time(cutoff, generated_at):
    cutoff, generated = timestamp(cutoff), timestamp(generated_at)
    require(cutoff <= generated <= cutoff + pd.Timedelta(minutes=1),
            'Prediction must be saved within one minute after cutoff')
