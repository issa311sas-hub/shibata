"""Deterministic fictional records, never historical JRA observations."""

import json
from pathlib import Path

import pandas as pd


def write_demo(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    races, entries, odds, results = [], [], [], []
    for index, year in enumerate((2024, 2025, 2026), start=1):
        race_id = f"SYNTH_{index:03d}"
        day = f"{year}-01-15"
        races.append({
            "race_id": race_id, "start_at": f"{day}T12:00:00+09:00",
            "prediction_at": f"{day}T11:50:00+09:00",
            "entries_available_at": f"{day}T09:00:00+09:00",
            "entries_retrieved_at": f"{day}T09:01:00+09:00",
            "entries_evidence_id": f"synthetic_entries_{index}", "expected_runners": 2,
        })
        for horse_number in (1, 2):
            horse_id = f"{horse_number:03d}"
            entries.append({"race_id": race_id, "horse_id": horse_id, "horse_number": horse_number})
            for snapshot_id, clock, kind in (("early", "11:40", "pre_race"),
                                             ("late", "11:55", "pre_race"),
                                             ("final", "12:10", "final")):
                value = (2.0 if horse_number == 1 else 4.0) if snapshot_id == "early" else (
                    5.0 if horse_number == 1 else 1.5
                )
                if index == 2 and snapshot_id == "early":
                    value = 2.0
                odds.append({
                    "race_id": race_id, "horse_id": horse_id, "snapshot_id": snapshot_id,
                    "odds_at": f"{day}T{clock}:00+09:00",
                    "available_at": f"{day}T{clock}:00+09:00",
                    "retrieved_at": f"{day}T{clock}:05+09:00",
                    "evidence_id": f"synthetic_{index}_{snapshot_id}", "odds_kind": kind,
                    "win_odds": value, "popularity": horse_number if snapshot_id == "early" else 3-horse_number,
                })
            results.append({"race_id": race_id, "horse_id": horse_id,
                            "win": int(horse_number == (2 if index == 3 else 1)),
                            "result_status": "official", "settled_at": f"{day}T12:15:00+09:00"})
    for name, records in (("races", races), ("entries", entries), ("odds", odds), ("results", results)):
        pd.DataFrame(records).to_csv(destination / f"{name}.csv", index=False)
    (destination / "dataset.json").write_text(json.dumps({
        "schema_version": 1, "dataset_id": "SYNTHETIC_BASELINE_V1",
        "data_kind": "synthetic", "source": "generated_by_shibata.demo",
        "availability_mode": "observed", "availability_evidence_reviewed": False,
    }, indent=2) + "\n", encoding="utf-8")
