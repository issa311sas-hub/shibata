import json
import math

import numpy as np
import pandas as pd
import pytest

from shibata.demo import write_demo
from shibata.evaluation.baseline import evaluate
from shibata.ingestion.archive import sha256
from shibata.ingestion.contracts import DataError, read_table, validate_table
from shibata.ingestion.snapshots import select_snapshots
from shibata.models.market import predict_market
from shibata.offline import run_baseline, validate_metadata


@pytest.fixture
def dataset(tmp_path):
    source = tmp_path / "input"
    write_demo(source)
    return source


@pytest.fixture
def frames(dataset):
    return {name: read_table(dataset / f"{name}.csv", name)
            for name in ("races", "entries", "odds", "results")}


def select(frames, **kwargs):
    return select_snapshots(frames["races"], frames["entries"], frames["odds"], **kwargs)


def test_cutoff_whole_snapshot_and_tied_odds(frames):
    predictions = predict_market(select(frames))
    assert set(predictions.snapshot_id) == {"early"}
    assert set(predictions.horse_id) == {"001", "002"}
    assert predictions.market_probability.tolist() == pytest.approx([2/3, 1/3, .5, .5, 2/3, 1/3])
    assert predictions.odds_rank.tolist() == [1, 2, 1, 1, 1, 2]
    assert predictions.groupby("race_id").market_probability.sum().tolist() == pytest.approx([1]*3)


@pytest.mark.parametrize("value", [0, -2, .5, np.nan, np.inf, "unknown", ""])
def test_invalid_odds_rejected(frames, value):
    frames["odds"]["win_odds"] = frames["odds"].win_odds.astype(object)
    frames["odds"].loc[0, "win_odds"] = value
    with pytest.raises(DataError):
        select(frames)


def test_result_columns_cannot_enter_inputs(frames):
    frames["odds"]["win"] = 1
    with pytest.raises(DataError, match="columns"):
        select(frames)


def test_numeric_id_is_not_silently_converted(frames):
    frames["entries"]["horse_id"] = frames["entries"].horse_id.astype(int)
    with pytest.raises(DataError, match="strings"):
        select(frames)


@pytest.mark.parametrize("table", ["races", "entries", "odds", "results"])
def test_duplicate_keys_rejected(frames, table):
    data = pd.concat([frames[table], frames[table].iloc[[0]]], ignore_index=True)
    with pytest.raises(DataError, match="duplicate"):
        validate_table(data, table)


def test_missing_horse_is_not_renormalized(frames):
    mask = (frames["odds"].race_id == "SYNTH_001") & (frames["odds"].horse_id == "002")
    frames["odds"] = frames["odds"].loc[~mask]
    with pytest.raises(DataError, match="incomplete"):
        select(frames)


def test_incomplete_newest_snapshot_does_not_fall_back(frames):
    old = frames["odds"].loc[frames["odds"].snapshot_id == "early"].copy()
    old["snapshot_id"] = "older"
    for column in ("odds_at", "available_at", "retrieved_at"):
        old[column] -= pd.Timedelta(minutes=5)
    mask = (frames["odds"].race_id == "SYNTH_001") & (frames["odds"].horse_id == "002")
    mask &= frames["odds"].snapshot_id == "early"
    frames["odds"] = pd.concat([frames["odds"].loc[~mask], old], ignore_index=True)
    with pytest.raises(DataError, match="newest eligible snapshot is incomplete"):
        select(frames)


def test_final_odds_rejected_even_with_early_timestamp(frames):
    frames["odds"]["odds_kind"] = "final"
    with pytest.raises(DataError, match="no eligible"):
        select(frames)


def test_conflicting_revisions_rejected(frames):
    revision = frames["odds"].loc[frames["odds"].snapshot_id == "early"].copy()
    revision["snapshot_id"] = "revision"
    frames["odds"] = pd.concat([frames["odds"], revision], ignore_index=True)
    with pytest.raises(DataError, match="ambiguous revisions"):
        select(frames)


@pytest.mark.parametrize("table,column", [("odds", "available_at"), ("races", "prediction_at")])
def test_timezone_required(frames, table, column):
    frames[table][column] = frames[table][column].dt.tz_localize(None).astype(str)
    with pytest.raises(DataError, match="timezone"):
        select(frames)


def test_after_race_cutoff_rejected(frames):
    frames["races"]["prediction_at"] = frames["races"].start_at
    with pytest.raises(DataError, match="precede"):
        select(frames)


def test_backfill_requires_explicit_review(frames):
    frames["odds"]["retrieved_at"] += pd.Timedelta(days=100)
    frames["races"]["entries_retrieved_at"] += pd.Timedelta(days=100)
    with pytest.raises(DataError, match="unavailable"):
        select(frames)
    with pytest.raises(DataError, match="evidence review"):
        select(frames, availability_mode="historical")
    result = select(frames, availability_mode="historical", evidence_reviewed=True)
    assert set(result.snapshot_id) == {"early"}


def test_source_publication_after_cutoff_is_not_usable(frames):
    frames["odds"]["available_at"] += pd.Timedelta(days=1)
    frames["odds"]["retrieved_at"] += pd.Timedelta(days=2)
    with pytest.raises(DataError, match="no eligible"):
        select(frames, availability_mode="historical", evidence_reviewed=True)


def test_future_odds_and_results_cannot_change_predictions(frames):
    before = predict_market(select(frames))
    before_metrics, _ = evaluate(before, frames["results"])
    frames["odds"].loc[frames["odds"].snapshot_id != "early", "win_odds"] = 99
    change = frames["results"].race_id == "SYNTH_001"
    frames["results"].loc[change, "win"] = 1 - frames["results"].loc[change, "win"]
    after = predict_market(select(frames))
    pd.testing.assert_frame_equal(before, after)
    after_metrics, _ = evaluate(after, frames["results"])
    assert before_metrics["binary_log_loss_per_runner"] != after_metrics["binary_log_loss_per_runner"]


def test_metric_values_are_hand_calculable(frames):
    metrics, tables = evaluate(predict_market(select(frames)), frames["results"])
    assert metrics["binary_log_loss_per_runner"] == pytest.approx(math.log(9)/3)
    assert metrics["binary_brier_per_runner"] == pytest.approx(29/108)
    assert metrics["multiclass_brier_per_race"] == pytest.approx(29/54)
    assert metrics["roi"] is None
    assert tables["calibration"].runners.sum() == 6
    assert tables["calibration"].loc[tables["calibration"].runners == 0, "mean_probability"].isna().all()
    assert tables["year"].year.tolist() == [2024, 2025, 2026]


def test_binary_and_race_metrics_have_distinct_definitions():
    start = pd.Timestamp("2024-01-01T12:00:00+09:00")
    predictions = pd.DataFrame({"race_id": ["r"]*3, "horse_id": ["a", "b", "c"],
                                "market_probability": [.5, .25, .25], "start_at": [start]*3,
                                "win_odds": [2., 4., 4.], "odds_rank": [1, 2, 2], "popularity": [1, 2, 3]})
    results = pd.DataFrame({"race_id": ["r"]*3, "horse_id": ["a", "b", "c"],
                           "win": [1, 0, 0], "result_status": ["official"]*3,
                           "settled_at": ["2024-01-01T12:10:00+09:00"]*3})
    metrics, _ = evaluate(predictions, results)
    assert metrics["binary_log_loss_per_runner"] == pytest.approx((math.log(2)-2*math.log(.75))/3)
    assert metrics["winner_log_loss_per_race"] == pytest.approx(math.log(2))
    assert metrics["binary_brier_per_runner"] == pytest.approx(.125)


@pytest.mark.parametrize("bad", ["dead_heat", "missing", "cancelled", "early_settlement"])
def test_unsupported_results_fail_instead_of_dropping(frames, bad):
    results = frames["results"].copy()
    if bad == "dead_heat":
        results.loc[results.race_id == "SYNTH_001", "win"] = 1
    elif bad == "missing":
        results = results.iloc[1:]
    elif bad == "cancelled":
        results.loc[0, "result_status"] = "cancelled"
    else:
        results["settled_at"] -= pd.Timedelta(hours=1)
    with pytest.raises(DataError):
        evaluate(predict_market(select(frames)), results)


def test_end_to_end_archive_and_rerun(dataset, tmp_path):
    output = tmp_path / "run1"
    report = run_baseline(dataset, output)
    assert report["scope"] == "synthetic_rehearsal"
    assert report["phase_completion"] == "NOT_ASSESSED"
    assert report["input_odds_rows"] == 18
    assert report["selected_odds_rows"] == 6
    for name, info in report["input_files"].items():
        assert info["sha256"] == sha256(dataset / name) == sha256(output / "raw" / name)
    for name, digest in report["artifacts"].items():
        assert digest == sha256(output / name)
    with pytest.raises(FileExistsError):
        run_baseline(dataset, output)
    second = tmp_path / "run2"
    other = run_baseline(dataset, second)
    assert report["metrics"] == other["metrics"]
    pd.testing.assert_frame_equal(pd.read_parquet(output / "predictions.parquet"),
                                  pd.read_parquet(second / "predictions.parquet"))


def test_parquet_input_is_equivalent(dataset, tmp_path):
    first = run_baseline(dataset, tmp_path / "csv")
    for name in ("races", "entries", "odds", "results"):
        path = dataset / f"{name}.csv"
        rows = pd.read_csv(path, dtype="string", keep_default_na=False)
        rows.to_parquet(path.with_suffix(".parquet"), index=False)
        path.unlink()
    second = run_baseline(dataset, tmp_path / "parquet")
    assert first["metrics"] == second["metrics"]


def test_failed_run_keeps_inputs_and_failure_status(dataset, tmp_path):
    rows = pd.read_csv(dataset / "results.csv", dtype="string")
    rows["win"] = "0"
    rows.to_csv(dataset / "results.csv", index=False)
    output = tmp_path / "failed"
    with pytest.raises(DataError):
        run_baseline(dataset, output)
    assert json.loads((output / "status.json").read_text())["status"] == "FAILED"
    assert (output / "raw" / "results.csv").exists()
    assert (output / "predictions.parquet").exists()
    assert not (output / "report.json").exists()


def test_metadata_rejects_truthy_strings(dataset):
    metadata = json.loads((dataset / "dataset.json").read_text())
    metadata["availability_evidence_reviewed"] = "false"
    with pytest.raises(DataError, match="boolean"):
        validate_metadata(metadata)
