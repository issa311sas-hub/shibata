"""Metric definitions v1: runner-level binary scores and race diagnostics."""

import numpy as np
import pandas as pd

from shibata.ingestion.contracts import require, validate_table


def evaluate(predictions: pd.DataFrame, results: pd.DataFrame) -> tuple[dict, dict]:
    results = validate_table(results, "results")
    return _score(predictions, results, "settled_at")


def evaluate_observed_results(predictions: pd.DataFrame, results: pd.DataFrame) -> tuple[dict, dict]:
    """Score confirmed labels using observation time, without inventing settlement time."""
    require("result_observed_at" in results and "settled_at" not in results,
            "Observed results require result_observed_at, not settled_at")
    # Reuse label/schema validation only; retain the distinct temporal meaning.
    checked = validate_table(results.rename(columns={"result_observed_at": "settled_at"}), "results")
    checked = checked.rename(columns={"settled_at": "result_observed_at"})
    metrics, tables = _score(predictions, checked, "result_observed_at")
    metrics["result_time_basis"] = "local observation of confirmed result; exact settlement time unknown"
    return metrics, tables


def _score(predictions: pd.DataFrame, results: pd.DataFrame, time_column: str) -> tuple[dict, dict]:
    require(not predictions.empty, "Empty predictions")
    require(not predictions.duplicated(["race_id", "horse_id"]).any(), "Duplicate predictions")
    key = ["race_id", "horse_id"]
    require(set(map(tuple, predictions[key].to_numpy())) ==
            set(map(tuple, results[key].to_numpy())), "Prediction/result keys must match exactly")
    scored = predictions.merge(results, on=key, validate="one_to_one")
    require((scored[time_column] > scored.start_at).all(), "Results settled before race start or observed too early")
    require((scored.groupby("race_id")[time_column].nunique() == 1).all(),
            "Inconsistent result settlement times or observation times")
    p = scored.market_probability.to_numpy(dtype=float)
    y = scored.win.to_numpy(dtype=float)
    require(np.isfinite(p).all() and ((p > 0) & (p < 1)).all(),
            "Probabilities must be finite and strictly between 0 and 1")
    require(np.allclose(scored.groupby("race_id").market_probability.sum(), 1, atol=1e-12),
            "Race probabilities must sum to one")
    scored["binary_log_loss"] = -(y * np.log(p) + (1 - y) * np.log1p(-p))
    scored["binary_brier"] = (p - y) ** 2
    metrics = {
        "definition_version": "v1",
        "rows": len(scored),
        "races": int(scored.race_id.nunique()),
        "binary_log_loss_per_runner": float(scored.binary_log_loss.mean()),
        "binary_brier_per_runner": float(scored.binary_brier.mean()),
        "winner_log_loss_per_race": float(-np.log(scored.loc[scored.win == 1,
                                                                  "market_probability"]).mean()),
        "multiclass_brier_per_race": float(scored.groupby("race_id").binary_brier.sum().mean()),
        "roi": None,
        "roi_status": "NOT_COMPUTED: staking policy and official payouts not yet defined",
    }
    scored["year"] = scored.start_at.dt.tz_convert("Asia/Tokyo").dt.year
    scored["odds_band"] = pd.cut(scored.win_odds, [1, 2, 5, 10, 20, 50, np.inf],
                                right=False, labels=["1-2", "2-5", "5-10", "10-20", "20-50", "50+"])
    tables = {}
    for name in ("year", "popularity", "odds_rank", "odds_band"):
        tables[name] = scored.groupby(name, observed=True).agg(
            runners=("win", "size"), wins=("win", "sum"),
            observed_win_rate=("win", "mean"), mean_probability=("market_probability", "mean"),
            binary_log_loss=("binary_log_loss", "mean"), binary_brier=("binary_brier", "mean")
        ).reset_index()
    scored["bin"] = np.minimum((p * 10).astype(int), 9)
    calibration = scored.groupby("bin").agg(
        runners=("win", "size"), wins=("win", "sum"),
        mean_probability=("market_probability", "mean"), observed_win_rate=("win", "mean")
    ).reindex(range(10))
    # Empty-bin counts are zero; empty-bin probabilities remain missing.
    calibration[["runners", "wins"]] = calibration[["runners", "wins"]].fillna(0).astype(int)
    calibration["lower"] = np.arange(10) / 10
    calibration["upper"] = np.arange(1, 11) / 10
    tables["calibration"] = calibration.reset_index()
    return metrics, tables
