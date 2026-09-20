"""Normalized inverse-odds baseline defined by the development plan."""

import numpy as np
import pandas as pd

from shibata.ingestion.contracts import require


def predict_market(selected: pd.DataFrame) -> pd.DataFrame:
    require(not selected.empty, "Empty prediction input")
    require("win" not in selected.columns, "Results must not enter the predictor")
    require(not selected.duplicated(["race_id", "horse_id"]).any(), "Duplicate prediction key")
    require(np.isfinite(selected.win_odds).all() and (selected.win_odds >= 1).all(),
            "Invalid odds")
    grouped = selected.groupby("race_id")
    require((grouped.runner_count.nunique() == 1).all(), "Inconsistent runner_count")
    require((grouped.size() == grouped.runner_count.first()).all(), "Incomplete prediction field")
    output = selected.copy()
    inverse = 1.0 / output.win_odds
    output["market_probability"] = inverse / inverse.groupby(output.race_id).transform("sum")
    # Ties share the minimum rank; this is not the provider's popularity field.
    output["odds_rank"] = grouped.win_odds.rank(method="min").astype(int)
    return output
