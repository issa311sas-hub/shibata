"""Predict a diagnostic market baseline from verified pre-race local captures.

No results, historical availability overrides, or fixed production cutoff policy.
All availability timestamps are conservative local observation bounds.
"""

import argparse
from datetime import datetime, timedelta
import hashlib
import json
from pathlib import Path

import pandas as pd

from .ingestion.capture import verify_capture
from .ingestion.contracts import DataError, require, timestamp
from .ingestion.jv_o1 import decode_o1
from .ingestion.jv_race import audit_mapping, decode_race_record
from .ingestion.snapshots import select_snapshots
from .models.market import predict_market


def observed_tables(entry_dir: Path, odds_dir: Path, prediction_at: str):
    cutoff = timestamp(prediction_at, "prediction_at")
    entries_capture, odds_capture = verify_capture(entry_dir), verify_capture(odds_dir)
    require(entries_capture["manifest"]["dataspec"] == "0B15", "Entries require 0B15")
    require(odds_capture["manifest"]["dataspec"] == "0B41", "Odds require 0B41")
    require(entries_capture["manifest"]["race_key"] == odds_capture["manifest"]["race_key"],
            "Capture race keys differ")
    require(max(entries_capture["finished_at"], odds_capture["finished_at"]) <= cutoff,
            "Captures finished after prediction cutoff")
    records = [decode_race_record(r["payload"]) for r in entries_capture["records"]]
    require(all(r["data_status"] == "2" for r in records), "Pre-race racecard status 2 required")
    odds_records = [decode_o1(r["payload"]) for r in odds_capture["records"]]
    # Fail closed until other sale/status policies have been explicitly implemented.
    require(all(r["data_status"] == "1" for r in odds_records), "Only intermediate odds supported")
    audit_mapping(records, odds_records)
    race = next(r for r in records if r["record_id"] == "RA")
    horses = [r for r in records if r["record_id"] == "SE"]
    require(race["runner_count"] == len(horses), "Withdrawals or unconfirmed field unsupported")
    require(all(r["abnormal_code_raw"] == "0" and r["final_rank_raw"] in {"00", "  "}
                for r in horses), "Abnormal or result-bearing entry record")
    race_day = datetime.strptime(race["race_key"][:8], "%Y%m%d").date()
    hhmm = race["start_hhmm_raw"]
    scheduled = timestamp(f"{race_day}T{hhmm[:2]}:{hhmm[2:]}:00+09:00")
    require(cutoff < scheduled, "Prediction cutoff must precede scheduled start")
    require(all(timestamp(r["created_date"] + "T00:00:00+09:00") <= entries_capture["finished_at"]
                for r in records), "Entry creation date is in the future")
    entry_evidence = entries_capture["manifest_sha256"]
    # Observation is an upper bound on availability, not the source's publication time.
    entries_at = entries_capture["finished_at"]
    races = pd.DataFrame([dict(race_id=race["race_key"], start_at=scheduled, prediction_at=cutoff,
                              entries_available_at=entries_at, entries_retrieved_at=entries_at,
                              entries_evidence_id=entry_evidence, expected_runners=len(horses))])
    entries = pd.DataFrame([dict(race_id=race["race_key"], horse_id=r["horse_id"],
                                 horse_number=r["horse_number"]) for r in horses])
    horse_ids = {r["horse_number"]: r["horse_id"] for r in horses}
    rows = []
    for record, captured in zip(odds_records, odds_capture["records"], strict=True):
        announced = record["announcement_mmddhhmm_raw"]
        candidates = []
        # Explicitly limited to race day / previous day. This handles New Year without
        # blindly assigning the race year to the provider's yearless timestamp.
        for day in (race_day - timedelta(days=1), race_day):
            if day.strftime("%m%d") == announced[:4]:
                candidates.append(timestamp(f"{day}T{announced[4:6]}:{announced[6:]}:00+09:00"))
        require(len(candidates) == 1, "Announcement date outside supported two-day window")
        announced_at = candidates[0]
        require(announced_at <= captured["retrieved_at"] <= cutoff and announced_at < scheduled,
                "Odds timestamp is after observation or scheduled start")
        require(timestamp(record["created_date"] + "T00:00:00+09:00") <= captured["retrieved_at"],
                "Odds creation date is in the future")
        require(record["runner_count"] == len(horses) and record["win_sale_flag"] == "7",
                "Unsupported runner count or win sale state")
        for slot in record["slots"]:
            if not slot["horse_number_raw"].strip():
                continue
            require(slot["status"] == "quoted" and slot["popularity_raw"].isdigit(),
                    "Missing, cancelled, capped or unquoted odds unsupported")
            rows.append(dict(race_id=race["race_key"], horse_id=horse_ids[slot["slot"]],
                             snapshot_id=captured["file"], odds_at=announced_at,
                             available_at=captured["retrieved_at"], retrieved_at=captured["retrieved_at"],
                             evidence_id=odds_capture["manifest_sha256"], odds_kind="pre_race",
                             win_odds=slot["win_odds"], popularity=slot["popularity_raw"]))
    provenance = dict(entries_manifest_sha256=entry_evidence,
                      odds_manifest_sha256=odds_capture["manifest_sha256"],
                      capture_manifest_verified=True, availability_mode="observed",
                      availability_meaning="local observation upper bound, not publication time",
                      cutoff_policy="explicit diagnostic cutoff; no production policy assigned",
                      scheduled_start_source="captured RA", results_used=False,
                      source_clock_independently_verified=False)
    return races, entries, pd.DataFrame(rows), provenance


def run(entry_dir: Path, odds_dir: Path, output_dir: Path, prediction_at: str) -> dict:
    output_dir.mkdir(parents=True, exist_ok=False)
    status = dict(status="RUNNING", experiment_kind="observed_market_diagnostic")
    status_path = output_dir / "status.json"
    try:
        require(timestamp(prediction_at) <= pd.Timestamp.now(tz="UTC"),
                "Prediction cutoff cannot be in the future at execution")
        races, entries, odds, provenance = observed_tables(entry_dir, odds_dir, prediction_at)
        selected = select_snapshots(races, entries, odds, availability_mode="observed")
        predictions = predict_market(selected)
        for name, table in [("races", races), ("entries", entries), ("odds", odds),
                            ("predictions", predictions)]:
            table.to_csv(output_dir / f"{name}.csv", index=False)
        generated = pd.Timestamp.now(tz="UTC")
        status.update(status="PASS", race_id=races.iloc[0].race_id, horse_count=len(predictions),
                      generated_at=generated.isoformat(),
                      generated_before_scheduled_start=bool(generated < races.iloc[0].start_at),
                      prediction_at=timestamp(prediction_at).isoformat(), **provenance)
        status["output_sha256"] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                                    for p in sorted(output_dir.glob("*.csv"))}
        package = Path(__file__).resolve().parent
        status["code_sha256"] = {str(p.relative_to(package)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in sorted(package.rglob("*.py"))}
    except (DataError, OSError, ValueError) as exc:
        status.update(status="FAILED", error=str(exc))
        raise
    finally:
        status_path.write_text(json.dumps(status, indent=2), encoding="utf-8")
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--entries-dir", type=Path, required=True)
    parser.add_argument("--odds-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--prediction-at", required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.entries_dir, args.odds_dir, args.output_dir, args.prediction_at)))


if __name__ == "__main__":
    main()
