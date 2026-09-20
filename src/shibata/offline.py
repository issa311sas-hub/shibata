"""Local baseline rehearsal. This module never contacts JRA-VAN."""

import argparse
import json
import platform
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from shibata.demo import write_demo
from shibata.evaluation.baseline import evaluate
from shibata.ingestion.archive import archive_inputs, sha256
from shibata.ingestion.contracts import DataError, read_table, require
from shibata.ingestion.snapshots import select_snapshots
from shibata.models.market import predict_market


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                    encoding="utf-8")


def validate_metadata(data: dict) -> dict:
    required = {"schema_version", "dataset_id", "data_kind", "source", "availability_mode",
                "availability_evidence_reviewed"}
    require(isinstance(data, dict) and set(data) == required, "dataset.json: exact metadata keys required")
    require(type(data["schema_version"]) is int and data["schema_version"] == 1,
            "Unsupported schema_version")
    for name in ("dataset_id", "source"):
        require(isinstance(data[name], str) and bool(data[name].strip()), f"Missing {name}")
    require(data["data_kind"] in ("synthetic", "real"), "Unknown data_kind")
    require(data["availability_mode"] in ("observed", "historical"), "Unknown availability_mode")
    require(type(data["availability_evidence_reviewed"]) is bool, "Evidence review must be boolean")
    return data


def code_provenance() -> dict:
    package = Path(__file__).resolve().parent
    root = package.parent.parent
    provenance = {"python": platform.python_version(),
                  "packages": {name: version(name) for name in ("numpy", "pandas", "pyarrow")},
                  "source_sha256": {p.relative_to(package).as_posix(): sha256(p)
                                    for p in sorted(package.rglob("*.py"))}}
    try:
        provenance["git_commit"] = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip()
        provenance["git_dirty"] = bool(subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True, stderr=subprocess.DEVNULL
        ).strip())
    except (OSError, subprocess.CalledProcessError):
        provenance["git_commit"] = None
        provenance["git_dirty"] = None
    lock = root / "requirements-lock.txt"
    if lock.is_file():
        provenance["requirements_sha256"] = sha256(lock)
    return provenance


def run_baseline(source: Path, output: Path) -> dict:
    # Existing runs are immutable to this command, including failed runs.
    output.mkdir(parents=True, exist_ok=False)
    status = output / "status.json"
    write_json(status, {"status": "RUNNING"})
    try:
        hashes = archive_inputs(source, output / "raw")
        raw = output / "raw"
        metadata = validate_metadata(json.loads((raw / "dataset.json").read_text(encoding="utf-8-sig")))

        def table(name: str):
            path = next(raw.glob(f"{name}.*"))
            return read_table(path, name)

        races, entries, odds = table("races"), table("entries"), table("odds")
        selected = select_snapshots(
            races, entries, odds, availability_mode=metadata["availability_mode"],
            evidence_reviewed=metadata["availability_evidence_reviewed"],
        )
        predictions = predict_market(selected)
        predictions.to_parquet(output / "predictions.parquet", index=False)
        predictions.to_csv(output / "predictions.csv", index=False)
        # Open results only AFTER predictions have been generated and saved.
        metrics, tables = evaluate(predictions, table("results"))
        for name, rows in tables.items():
            rows.to_csv(output / f"{name}.csv", index=False)
        report = {
            "run_id": ("DEMO_" if metadata["data_kind"] == "synthetic" else "EXP_") + uuid.uuid4().hex,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": "PASS", "dataset": metadata, "model": "market_inverse_odds_v1",
            "scope": "synthetic_rehearsal" if metadata["data_kind"] == "synthetic" else "local_baseline",
            "phase_completion": "NOT_ASSESSED", "train_validation_test_periods": "NOT_ASSIGNED",
            "input_files": hashes, "provenance": code_provenance(),
            "input_odds_rows": len(odds), "selected_odds_rows": len(selected),
            "metrics": metrics,
        }
        report["artifacts"] = {p.name: sha256(p) for p in sorted(output.iterdir())
                               if p.is_file() and p.name != "status.json"}
        write_json(output / "report.json", report)
        write_json(status, {"status": "PASS", "run_id": report["run_id"]})
        return report
    except Exception as exc:
        write_json(status, {"status": "FAILED", "error_type": type(exc).__name__, "reason": str(exc)})
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Generate fictional data and run all offline checks")
    demo.add_argument("--output-dir", type=Path, required=True)
    run = commands.add_parser("run", help="Use local contract-v1 CSV/Parquet inputs")
    run.add_argument("--input-dir", type=Path, required=True)
    run.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "demo":
            with tempfile.TemporaryDirectory(prefix="shibata_demo_") as temporary:
                source = Path(temporary) / "input"
                write_demo(source)
                report = run_baseline(source, args.output_dir)
        else:
            report = run_baseline(args.input_dir, args.output_dir)
    except (DataError, OSError, ValueError) as exc:
        parser.exit(2, f"FAILED: {exc}\n")
    print(json.dumps({"status": report["status"], "scope": report["scope"],
                      "run_id": report["run_id"], "report": str(args.output_dir / "report.json")},
                     ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
