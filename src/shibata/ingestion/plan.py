"""Print a single-race acquisition plan without loading or calling JV-Link."""

import argparse
import json

from .contracts import DataError
from .jv_o1 import validate_race_key


def build_plan(race_key: str) -> dict:
    race_key = validate_race_key(race_key)
    return {
        "kind": "dry_run_only", "network_requests": 0, "transport_implemented": False,
        "request": {"method": "JVRTOpen", "dataspec": "0B41", "key": race_key},
        "expected_record": "O1", "scope": "one_race_win_odds_history",
        "requires_before_execution": [
            "JV-Link installation after user is ready to start trial",
            "SDK sample connectivity verification and Python/bitness compatibility check",
            "Official race key confirmation (syntax check does not prove race existence)",
            "Verified raw acquisition adapter with error handling and JVClose",
        ],
        "additional_inputs": ["pre-race entries and start time", "separate official results"],
        "never_infer": ["availability from retrieval date", "pre-race odds from final odds"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--race-key", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build_plan(args.race_key), ensure_ascii=False, indent=2))
    except DataError as exc:
        parser.exit(2, f"FAILED: {exc}\n")


if __name__ == "__main__":
    main()
