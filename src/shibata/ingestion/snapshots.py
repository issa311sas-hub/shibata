"""Select a complete pre-race snapshot without looking at race results."""

import pandas as pd

from .contracts import require, validate_table


def select_snapshots(
    races: pd.DataFrame,
    entries: pd.DataFrame,
    odds: pd.DataFrame,
    *,
    availability_mode: str = "observed",
    evidence_reviewed: bool = False,
) -> pd.DataFrame:
    require(availability_mode in {"observed", "historical"}, "Unknown availability_mode")
    require(availability_mode != "historical" or evidence_reviewed is True,
            "historical mode requires an explicit availability evidence review")
    races = validate_table(races, "races")
    entries = validate_table(entries, "entries")
    odds = validate_table(odds, "odds")
    race_ids = set(races.race_id)
    require(set(entries.race_id) == race_ids, "entries: race IDs must match races")
    require(set(odds.race_id) == race_ids, "odds: race IDs must match races")
    require((races.prediction_at < races.start_at).all(), "prediction_at must precede start_at")
    require(races.expected_runners.between(2, 18).all(), "expected_runners outside 2..18")
    require((races.entries_available_at <= races.entries_retrieved_at).all(),
            "entries availability after retrieval")
    known_entries_at = (races.entries_retrieved_at if availability_mode == "observed"
                        else races.entries_available_at)
    require((known_entries_at <= races.prediction_at).all(),
            "entries were unavailable at prediction time")
    parts = []
    for race in races.itertuples(index=False):
        runners = entries.loc[entries.race_id == race.race_id]
        require(len(runners) == race.expected_runners, f"{race.race_id}: incomplete entry list")
        snapshots = odds.loc[odds.race_id == race.race_id].copy()
        require(set(snapshots.horse_id) <= set(runners.horse_id),
                f"{race.race_id}: odds contain an unknown horse")
        uniform = ["odds_at", "available_at", "retrieved_at", "odds_kind", "evidence_id"]
        require((snapshots.groupby("snapshot_id")[uniform].nunique() == 1).all().all(),
                f"{race.race_id}: inconsistent metadata within snapshot")
        clock = "retrieved_at" if availability_mode == "observed" else "available_at"
        eligible = snapshots.loc[(snapshots[clock] <= race.prediction_at)
                                 & (snapshots.odds_kind == "pre_race")]
        require(not eligible.empty, f"{race.race_id}: no eligible pre-race odds")
        # Never combine per-horse updates from different snapshots.
        newest = eligible.loc[eligible.odds_at == eligible.odds_at.max()]
        require(newest.snapshot_id.nunique() == 1,
                f"{race.race_id}: ambiguous revisions at the same odds timestamp")
        require(set(newest.horse_id) == set(runners.horse_id),
                f"{race.race_id}: newest eligible snapshot is incomplete")
        joined = runners.merge(newest, on=["race_id", "horse_id"], validate="one_to_one")
        joined["start_at"] = race.start_at
        joined["prediction_at"] = race.prediction_at
        joined["runner_count"] = race.expected_runners
        joined["availability_mode"] = availability_mode
        parts.append(joined)
    return pd.concat(parts, ignore_index=True).sort_values(["start_at", "race_id", "horse_number"])
