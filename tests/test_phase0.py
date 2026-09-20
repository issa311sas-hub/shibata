import pandas as pd
import pytest

from shibata.phase0 import exercise_operations, make_example, run


def test_known_history_and_missing_values():
    transformed, summary = exercise_operations(make_example())
    a = transformed.loc[transformed.horse_id == "A"].reset_index(drop=True)
    b = transformed.loc[transformed.horse_id == "B"].reset_index(drop=True)
    assert a.race_id.tolist() == ["001", "002", "003"]
    assert pd.isna(a.previous_win.iloc[0])
    assert pd.isna(a.previous_two_mean.iloc[0])
    assert a.previous_two_mean.iloc[1:].tolist() == [1.0, 1.0]
    assert b.previous_two_mean.iloc[1:].tolist() == [0.0, 0.0]
    assert transformed.runners.tolist() == [2] * 6
    assert summary.wins.tolist() == [2.0, 1.0]


def test_current_and_future_results_do_not_change_past_history():
    rows = make_example()
    before, _ = exercise_operations(rows)
    rows.loc[rows.race_id == "003", "win"] = [0.0, 1.0]
    after, _ = exercise_operations(rows)
    columns = ["race_id", "horse_id", "previous_win", "previous_two_mean"]
    pd.testing.assert_frame_equal(before[columns], after[columns])


def test_same_day_ambiguity_is_rejected():
    rows = make_example()
    rows.loc[rows.race_id == "002", "date"] = "2024-01-01"
    with pytest.raises(ValueError, match="one start"):
        exercise_operations(rows)


def test_io_and_sql_roundtrip(tmp_path):
    report = run(tmp_path)
    assert report["real_data"] is False
    assert report["rows"] == 6
    assert set(report["checks"].values()) == {"PASS"}
    assert (tmp_path / "report.json").exists()
    saved = pd.read_parquet(tmp_path / "exercise.parquet")
    assert set(saved.race_id) == {"001", "002", "003"}
