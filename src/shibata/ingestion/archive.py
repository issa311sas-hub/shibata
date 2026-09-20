"""Copy inputs and record content hashes; never overwrite a previous run."""

import hashlib
import json
import shutil
from pathlib import Path

from .contracts import DataError


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def archive_inputs(source: Path, destination: Path) -> dict:
    """Archive only the specified contract files, not arbitrary nearby files."""
    files = [source / "dataset.json"]
    for name in ("races", "entries", "odds", "results"):
        candidates = [source / f"{name}{suffix}" for suffix in (".csv", ".parquet")]
        found = [path for path in candidates if path.is_file()]
        if len(found) != 1:
            raise DataError(f"{name}: provide exactly one .csv or .parquet file")
        files.extend(found)
    if not files[0].is_file():
        raise DataError("dataset.json is required")
    destination.mkdir(parents=True, exist_ok=False)
    manifest = {}
    for path in files:
        target = destination / path.name
        shutil.copyfile(path, target)
        manifest[path.name] = {"sha256": sha256(target), "bytes": target.stat().st_size}
    (destination / "hashes.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )
    return manifest
