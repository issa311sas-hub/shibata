"""Version 1 of the internal input contract, not a JV-Data decoder."""

from pathlib import Path

import numpy as np
import pandas as pd


class DataError(ValueError):
    """The input cannot safely be used under the declared contract."""


SCHEMAS = {
    "races": ["race_id", "start_at", "prediction_at", "entries_available_at",
              "entries_retrieved_at", "entries_evidence_id", "expected_runners"],
    "entries": ["race_id", "horse_id", "horse_number"],
    "odds": ["race_id", "horse_id", "snapshot_id", "odds_at", "available_at",
             "retrieved_at", "evidence_id", "odds_kind", "win_odds", "popularity"],
    "results": ["race_id", "horse_id", "win", "result_status", "settled_at"],
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise DataError(message)


def timestamp(value: str | pd.Timestamp, name: str = "timestamp") -> pd.Timestamp:
    require(isinstance(value, pd.Timestamp) or
            (isinstance(value, str) and bool(value.strip())), f"{name}: timestamp missing")
    try:
        parsed = pd.Timestamp(value)
    except (ValueError, TypeError) as exc:
        raise DataError(f"{name}: invalid timestamp") from exc
    require(not pd.isna(parsed) and parsed.tzinfo is not None,
            f"{name}: explicit timezone required")
    return parsed.tz_convert("UTC")


def read_table(path: Path, name: str) -> pd.DataFrame:
    if path.suffix == ".csv":
        rows = pd.read_csv(path, dtype="string", keep_default_na=False)
    elif path.suffix == ".parquet":
        rows = pd.read_parquet(path)
    else:
        raise DataError("Only .csv or .parquet inputs are supported")
    return validate_table(rows, name)


def validate_table(rows: pd.DataFrame, name: str) -> pd.DataFrame:
    require(name in SCHEMAS, "Unknown table")
    require(set(rows.columns) == set(SCHEMAS[name]) and rows.columns.is_unique,
            f"{name}: columns must exactly match schema v1; no columns are silently dropped")
    require(not rows.empty, f"{name}: empty table")
    data = rows.copy()
    for column in data.columns:
        values = data[column]
        require(not values.isna().any(), f"{name}.{column}: missing values")
        if column.endswith("_at"):
            data[column] = pd.to_datetime(
                [timestamp(v, f"{name}.{column}") for v in values], utc=True
            )
        elif column in {"win_odds", "win", "expected_runners", "horse_number", "popularity"}:
            require(not values.map(lambda v: isinstance(v, (bool, np.bool_))).any(),
                    f"{name}.{column}: boolean is not numeric data")
            numbers = pd.to_numeric(values, errors="coerce").astype(float)
            require(bool(np.isfinite(numbers).all()), f"{name}.{column}: finite numbers required")
            if column != "win_odds":
                require(bool((numbers % 1 == 0).all()), f"{name}.{column}: integer required")
                numbers = numbers.astype("int64")
            data[column] = numbers
        else:
            require(values.map(lambda v: isinstance(v, str) and bool(v.strip())
                               and v == v.strip()).all(),
                    f"{name}.{column}: nonblank strings required; IDs must not be numeric")
    keys = {"races": ["race_id"], "entries": ["race_id", "horse_id"],
            "odds": ["race_id", "snapshot_id", "horse_id"],
            "results": ["race_id", "horse_id"]}[name]
    require(not data.duplicated(keys).any(), f"{name}: duplicate key {keys}")
    if name == "odds":
        require(data.odds_kind.isin(["pre_race", "final"]).all(), "odds: unsupported odds_kind")
        require((data.win_odds >= 1).all(), "odds: win_odds must be >= 1")
        require(data.popularity.between(1, 18).all(), "odds: popularity outside 1..18")
        require((data.odds_at <= data.available_at).all(), "odds: odds_at after available_at")
        require((data.available_at <= data.retrieved_at).all(), "odds: available_at after retrieval")
    if name == "entries":
        require(data.horse_number.between(1, 18).all(), "entries: horse_number outside 1..18")
        require(not data.duplicated(["race_id", "horse_number"]).any(),
                "entries: duplicate horse_number")
    if name == "results":
        require(data.win.isin([0, 1]).all(), "results: win must be 0 or 1")
        require((data.result_status == "official").all(),
                "results: unresolved/cancelled races need a separate policy")
        require((data.groupby("race_id").win.sum() == 1).all(),
                "results: exactly one winner required; dead heats need a separate policy")
    return data
