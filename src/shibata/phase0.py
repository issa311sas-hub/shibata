"""Synthetic-data exercises only; these are not prediction features."""

import argparse
import json
import platform
import sqlite3
from importlib.metadata import version
from pathlib import Path

import pandas as pd


def make_example() -> pd.DataFrame:
    """Deliberately unsorted synthetic rows, with leading-zero IDs."""
    return pd.DataFrame(
        [
            ("003", "B", "2024-03-01", 1.0),
            ("001", "A", "2024-01-01", 1.0),
            ("002", "B", "2024-02-01", 0.0),
            ("003", "A", "2024-03-01", 0.0),
            ("001", "B", "2024-01-01", 0.0),
            ("002", "A", "2024-02-01", 1.0),
        ],
        columns=["race_id", "horse_id", "date", "win"],
    ).astype({"race_id": "string", "horse_id": "string", "date": "string"})


def exercise_operations(rows: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Practice sort/groupby/merge/shift/rolling, preserving missing history.

    Date ordering suffices ONLY for this one-start-per-horse-per-day fixture.
    Production history must also filter on actual information availability.
    """
    ordered = rows.sort_values(["horse_id", "date", "race_id"]).copy()
    if ordered.duplicated(["horse_id", "date"]).any():
        raise ValueError("Exercise requires one start per horse per day")
    grouped = ordered.groupby("horse_id", sort=False)["win"]
    ordered["previous_win"] = grouped.shift(1)
    ordered["previous_two_mean"] = grouped.transform(
        lambda values: values.shift(1).rolling(2, min_periods=1).mean()
    )
    counts = ordered.groupby("race_id", as_index=False).agg(
        runners=("horse_id", "size")
    )
    ordered = ordered.merge(counts, on="race_id", validate="many_to_one")
    # Whole-period aggregation is descriptive ONLY, never a pre-race feature.
    summary = ordered.groupby("horse_id", as_index=False).agg(
        starts=("win", "size"), wins=("win", "sum")
    )
    return ordered, summary


def run(output_dir: Path) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    example = make_example()
    csv_path = output_dir / "synthetic.csv"
    parquet_path = output_dir / "synthetic.parquet"
    example.to_csv(csv_path, index=False)
    example.to_parquet(parquet_path, index=False)
    csv_rows = pd.read_csv(csv_path, dtype=example.dtypes.to_dict())
    parquet_rows = pd.read_parquet(parquet_path)
    pd.testing.assert_frame_equal(example, csv_rows)
    pd.testing.assert_frame_equal(example, parquet_rows)
    transformed, summary = exercise_operations(csv_rows)
    with sqlite3.connect(":memory:") as connection:
        example.to_sql("starts", connection, index=False)
        sql_summary = pd.read_sql_query(
            "SELECT horse_id, COUNT(*) AS starts, SUM(win) AS wins "
            "FROM starts GROUP BY horse_id ORDER BY horse_id", connection
        )
    pd.testing.assert_frame_equal(summary, sql_summary, check_dtype=False)
    transformed.to_parquet(output_dir / "exercise.parquet", index=False)
    report = {
        "kind": "synthetic_environment_check",
        "real_data": False,
        "python": platform.python_version(),
        "packages": {name: version(name) for name in ("numpy", "pandas", "pyarrow")},
        "rows": len(example),
        "races": int(example.race_id.nunique()),
        "checks": {name: "PASS" for name in (
            "csv_roundtrip", "parquet_roundtrip", "sql_matches_groupby"
        )},
        "model_validation": "NOT_RUN",
    }
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/phase0"))
    args = parser.parse_args()
    print(json.dumps(run(args.output_dir), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
