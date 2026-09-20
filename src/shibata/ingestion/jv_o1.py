"""Inspect one O1 record offline; never infer historical availability.

Reference: JV-Data 4.9.0.1, format 7 (PDF page 15), linked in docs/acquisition.md.
This deliberately decodes only the header and win-odds area. It does not decode
place/frame odds or turn a vendor record into a prediction-ready input.
"""

import argparse
import hashlib
import json
from datetime import datetime
from pathlib import Path

from .contracts import DataError, require


def validate_race_key(value: str) -> str:
    require(isinstance(value, str) and len(value) == 16 and value.isascii() and value.isdigit(),
            "race_key must be 16 ASCII digits: YYYYMMDDJJKKHHRR")
    try:
        datetime.strptime(value[:8], "%Y%m%d")
    except ValueError as exc:
        raise DataError("race_key contains an invalid date") from exc
    require(1 <= int(value[8:10]) <= 10, "Only JRA course codes 01..10 are supported")
    require(int(value[10:12]) > 0 and int(value[12:14]) > 0 and 1 <= int(value[14:]) <= 12,
            "Invalid meeting/day/race number")
    return value


def decode_o1(payload: bytes) -> dict:
    require(len(payload) == 962 and payload.endswith(b"\r\n"),
            "O1 must be exactly 962 bytes including CRLF")
    try:
        header = payload[:267].decode("ascii")
    except UnicodeDecodeError as exc:
        raise DataError("O1 header/win area must be ASCII") from exc
    require(header[:2] == "O1", "Expected O1 record")
    record_kind = {"0": "deletion", "1": "intermediate", "2": "previous_day_final",
                   "3": "final", "4": "confirmed", "5": "monday_confirmed", "9": "cancelled"}
    require(header[2] in record_kind, "Unknown O1 data status")
    race_key = validate_race_key(header[11:27])
    try:
        created_date = datetime.strptime(header[3:11], "%Y%m%d").date().isoformat()
    except ValueError as exc:
        raise DataError("Invalid O1 creation date") from exc
    announced = header[27:35]
    if header[2] == "1":
        require(announced.isdigit(), "Intermediate O1 announcement time is required")
        # Month/day has no year. Use a leap year for syntax checking only.
        try:
            datetime.strptime("2000" + announced, "%Y%m%d%H%M")
        except ValueError as exc:
            raise DataError("Invalid O1 announcement month/day/time") from exc
    for part in (header[35:37], header[37:39]):
        require(part.isdigit() and 0 <= int(part) <= 28, "Invalid O1 runner counts")
    require(int(header[37:39]) <= int(header[35:37]), "O1 runners exceed registrations")
    require(header[39] in "0137", "Unknown win sale flag")
    slots = []
    special = {"    ": "not_registered", "0000": "no_votes",
               "----": "cancelled_before_sale", "****": "cancelled_after_sale"}
    for slot in range(28):
        block = header[43 + slot * 8:51 + slot * 8]
        number, quote, popularity = block[:2], block[2:6], block[6:8]
        require(number == "  " or (number.isdigit() and int(number) == slot + 1),
                "O1 horse slots must be in ascending slot order")
        if quote in special:
            state, value = special[quote], None
        else:
            require(quote.isdigit() and int(quote) >= 10, "Invalid O1 win quote")
            state = "capped" if quote == "9999" else "quoted"
            value = int(quote) / 10
        require(number != "  " or state == "not_registered", "Quote without horse number")
        require(popularity in ("  ", "--", "**") or
                (popularity.isdigit() and 1 <= int(popularity) <= 28), "Invalid O1 popularity")
        slots.append({"slot": slot + 1, "horse_number_raw": number,
                      "odds_raw": quote, "popularity_raw": popularity,
                      "status": state, "win_odds": value})
    return {
        "record_id": "O1", "data_status": header[2], "record_kind": record_kind[header[2]],
        "race_key": race_key, "created_date": created_date,
        "announcement_mmddhhmm_raw": announced, "registered_count": int(header[35:37]),
        "runner_count": int(header[37:39]), "win_sale_flag": header[39],
        "slots": slots, "payload_sha256": hashlib.sha256(payload).hexdigest(),
        "prediction_ready": False,
        "unresolved": ["announcement_year_and_timezone", "public_availability_evidence",
                       "local_retrieval_timestamp", "horse_id_mapping", "field_and_status_review"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        decoded = decode_o1(args.input.read_bytes())
        # Exclusive creation: preserve earlier inspection results.
        with args.output.open("x", encoding="utf-8") as stream:
            json.dump(decoded, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
    except (DataError, OSError) as exc:
        parser.exit(2, f"FAILED: {exc}\n")
    print(f"Inspection saved: {args.output} (prediction_ready=false)")


if __name__ == "__main__":
    main()
