"""Independent later-period synthetic checks of the unchanged Phase 0 operations."""
import numpy as np
import pandas as pd
from .phase0 import exercise_operations


def later_example():
    days = ['2025-04-01', '2025-04-08', '2025-05-04', '2025-06-02']
    winners = ['Y', 'X', 'Z', 'Y']
    rows = [(f'{i+101:03}', h, day, float(h == winners[i]))
            for i, day in enumerate(days) for h in ['X', 'Y', 'Z']]
    return pd.DataFrame(rows[::-1], columns=['race_id', 'horse_id', 'date', 'win']).astype(
        {'race_id': 'string', 'horse_id': 'string', 'date': 'string'})


def check_later_period(rows=None):
    rows = later_example() if rows is None else rows
    actual, summary = exercise_operations(rows)
    previous = {'X': [np.nan, 0., 1., 0.], 'Y': [np.nan, 1., 0., 0.], 'Z': [np.nan, 0., 0., 1.]}
    rolling = {'X': [np.nan, 0., .5, .5], 'Y': [np.nan, 1., .5, 0.], 'Z': [np.nan, 0., 0., .5]}
    for horse in ['X', 'Y', 'Z']:
        group = actual.loc[actual.horse_id == horse]
        assert group.race_id.tolist() == ['101', '102', '103', '104']
        np.testing.assert_allclose(group.previous_win, previous[horse], equal_nan=True)
        np.testing.assert_allclose(group.previous_two_mean, rolling[horse], equal_nan=True)
    assert actual.runners.tolist() == [3] * 12
    assert summary.wins.tolist() == [1., 2., 1.]
    columns = ['race_id', 'horse_id', 'previous_win', 'previous_two_mean']
    for day in sorted(rows.date.unique()):
        changed = rows.copy()
        changed.loc[changed.date >= day, 'win'] = 1 - changed.loc[changed.date >= day, 'win']
        after, _ = exercise_operations(changed)
        pd.testing.assert_frame_equal(actual.loc[actual.date <= day, columns],
                                      after.loc[after.date <= day, columns])
    return actual, dict(status='PASS', real_data=False, rows=12, races=4,
                        period='2025-04-01..2025-06-02', development_period='2024-01-01..2024-03-01',
                        independent_expected_values=True, causal_boundary_checks=4,
                        prediction_performance_claim=False)
