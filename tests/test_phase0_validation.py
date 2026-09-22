import pytest
from shibata.phase0_validation import check_later_period, later_example


def test_later_period_oracle_and_causality():
    frame, report = check_later_period()
    assert report['status'] == 'PASS' and report['causal_boundary_checks'] == 4
    assert frame.previous_win.isna().sum() == 3


def test_oracle_detects_wrong_label():
    rows = later_example()
    rows.loc[(rows.horse_id == 'X') & (rows.race_id == '101'), 'win'] = 1.
    with pytest.raises(AssertionError): check_later_period(rows)
