"""Strict partial RA/SE decoding for audits, never a historical feature exporter.

Layout: official JV-Data 4.9.0.1, RA/SE. Names and other CP932 fields
are intentionally left undecoded. Creation dates are not availability times.
"""
from datetime import datetime
import hashlib

from .contracts import DataError, require
from .jv_o1 import validate_race_key


def decode_race_record(payload: bytes) -> dict:
    kind = payload[:2]
    require(kind in (b"RA", b"SE"), "Expected RA or SE")
    require(len(payload) == (1272 if kind == b"RA" else 555)
            and payload.endswith(b"\r\n"), "Invalid RA/SE length or terminator")

    def field(start, end):
        try:
            return payload[start:end].decode("ascii")
        except UnicodeDecodeError as exc:
            raise DataError("Non-ASCII structural field") from exc

    def number(start, end, low, high):
        raw = field(start, end)
        require(raw.isdigit() and low <= int(raw) <= high, "Invalid numeric field")
        return int(raw)

    status = field(2, 3)
    require(status in "012345679AB", "Unknown RA/SE status")
    try:
        created = datetime.strptime(field(3, 11), "%Y%m%d").date().isoformat()
    except ValueError as exc:
        raise DataError("Invalid creation date") from exc
    record = dict(record_id=kind.decode(), data_status=status,
                  race_key=validate_race_key(field(11, 27)), created_date=created,
                  payload_sha256=hashlib.sha256(payload).hexdigest(),
                  prediction_ready=False)
    # Unassigned entry numbers and deletion/cancellation payloads are not supported.
    require(status in "234567", "Only numbered racecards and result revisions supported")
    if kind == b"RA":
        start = field(873, 877)
        require(start.isdigit() and int(start[:2]) < 24 and int(start[2:]) < 60,
                "Invalid scheduled start time")
        record.update(start_hhmm_raw=start, track_code_raw=field(705, 707), registered_count=number(881, 883, 2, 18),
                      runner_count=number(883, 885, 0, 18))
        require(record["runner_count"] <= record["registered_count"], "Invalid runner count")
    else:
        horse_id = field(30, 40)
        require(horse_id.isdigit() and int(horse_id) > 0, "Invalid horse registration ID")
        record.update(horse_number=number(28, 30, 1, 18), horse_id=horse_id,
                      abnormal_code_raw=field(331, 332),
                      final_rank_raw=field(334, 336), dead_heat_raw=field(336, 337))
    return record


def audit_mapping(records: list[dict], odds: list[dict], *, confirmation_records=None) -> dict:
    """Check a single revision/field. Explicitly exclude this audit from predictions."""
    races = [r for r in records if r["record_id"] == "RA"]
    horses = [r for r in records if r["record_id"] == "SE"]
    require(len(races) == 1, "Expected exactly one RA revision")
    race = races[0]
    require(bool(odds), "No O1 records")
    require(all(r["race_key"] == race["race_key"] for r in horses + odds), "Race mismatch")
    require(all(r["data_status"] == race["data_status"] for r in horses),
            "Inconsistent RA/SE revisions")
    dates_match = all(r["created_date"] == race["created_date"] for r in horses)
    if not dates_match:
        require(confirmation_records is not None and
                sorted(r['payload_sha256'] for r in records) ==
                sorted(r['payload_sha256'] for r in confirmation_records),
                "Different creation dates require an identical independent recapture")
    require(len(horses) == race["registered_count"], "Incomplete horse field")
    numbers = {r["horse_number"] for r in horses}
    require(len(numbers) == len(horses) and len({r["horse_id"] for r in horses}) == len(horses),
            "Duplicate horse number or registration ID")
    for snapshot in odds:
        quoted = {int(s["horse_number_raw"]) for s in snapshot["slots"]
                  if s["horse_number_raw"].strip()}
        require(quoted == numbers and snapshot["registered_count"] == len(horses),
                "O1/SE field mismatch")
    normal_result = (race["data_status"] in "567" and
                     race["runner_count"] == len(horses) and
                     all(r["abnormal_code_raw"] == "0" and r["dead_heat_raw"] == "0"
                         and r["final_rank_raw"].isdigit() for r in horses))
    if normal_result:
        require(sorted(int(r["final_rank_raw"]) for r in horses) == list(range(1, len(horses)+1)),
                "Invalid complete result ranking")
    return dict(race_key=race["race_key"], horse_count=len(horses),
                odds_records_checked=len(odds), mapping_consistent=True,
                creation_dates_match=dates_match,
                complete_normal_result=normal_result, prediction_ready=False,
                unresolved=["pre_race_entry_availability_evidence", "odds_availability_evidence",
                            "result_settlement_timestamp"],
                note="Matching final records cannot prove a historical pre-race field.")


def main():
    """Audit captured folders; preserve raw data and never export model inputs."""
    import argparse
    import json
    from pathlib import Path
    from .jv_o1 import decode_o1
    from .capture import verify_capture
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--race-dir', type=Path, required=True)
    parser.add_argument('--odds-dir', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    race_capture = verify_capture(args.race_dir)
    odds_capture = verify_capture(args.odds_dir)
    require(race_capture['manifest']['dataspec'] in {'0B12', '0B15'}, 'Expected race capture')
    require(odds_capture['manifest']['dataspec'] == '0B41', 'Expected odds capture')
    records, unparsed = [], []
    for captured in race_capture['records']:
        payload = captured['payload']
        if payload[:2] in (b'RA', b'SE'):
            records.append(decode_race_record(payload))
        else:
            unparsed.append({'file': captured['file'], 'sha256': captured['sha256']})
    odds = [decode_o1(r['payload']) for r in odds_capture['records']]
    report = audit_mapping(records, odds)
    report['record_hashes'] = [r['payload_sha256'] for r in records + odds]
    report['unparsed_records'] = unparsed
    report['capture_manifest_verified'] = True
    report['manifest_hashes'] = [race_capture['manifest_sha256'], odds_capture['manifest_sha256']]
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2)
    print(json.dumps({k: v for k, v in report.items() if k != 'record_hashes'}))


if __name__ == '__main__':
    main()
