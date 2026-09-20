"""Verify local JV-Link capture integrity; hashes are not trusted timestamps."""

import hashlib
import json
from pathlib import Path

from .contracts import DataError, require, timestamp
from .jv_o1 import validate_race_key


def verify_capture(folder: Path) -> dict:
    """Read each payload once and return only bytes verified against its manifest."""
    try:
        raw = (folder / "probe.json").read_bytes()
        manifest = json.loads(raw.decode("utf-8-sig"))
        require(isinstance(manifest, dict), "Capture manifest must be an object")
        require(manifest.get("transport") == "JVGets_byte_array", "Unverified capture transport")
        require(manifest.get("complete") is True and not manifest.get("error")
                and not manifest.get("close_error"), "Capture did not complete successfully")
        require(all(type(manifest.get(k)) is int and manifest[k] == 0
                    for k in ("init_code", "open_code", "close_code")), "Capture API failure")
        require(manifest["dataspec"] in {"0B12", "0B15", "0B41"}, "Unsupported dataspec")
        race_key = validate_race_key(manifest["race_key"])
        start = timestamp(manifest["started_at"])
        end = timestamp(manifest["finished_at"])
        require(start <= end, "Capture end precedes start")
        files = manifest["files"]
        require(isinstance(files, list) and type(manifest["records"]) is int
                and 0 < len(files) == manifest["records"] <= 2000, "Invalid capture count")
        expected = {f"record-{i:04d}.bin" for i in range(len(files))}
        require({p.name for p in folder.glob("*.bin")} == expected, "Capture file set mismatch")
        verified = []
        previous = start
        for i, entry in enumerate(files):
            name = f"record-{i:04d}.bin"
            require(entry["file"] == name, "Invalid capture file order/name")
            path = folder / name
            require(not path.is_symlink() and path.resolve().parent == folder.resolve(),
                    "Capture file must remain within its directory")
            payload = path.read_bytes()
            require(type(entry["size"]) is int and len(payload) == entry["size"], "Capture size mismatch")
            digest = hashlib.sha256(payload).hexdigest()
            require(entry["sha256"] == digest, "Capture hash mismatch")
            retrieved = timestamp(entry["retrieved_at"])
            require(previous <= retrieved <= end, "Capture timestamp order mismatch")
            previous = retrieved
            require(len(payload) >= 29 and payload.endswith(b"\r\n"), "Invalid capture record framing")
            require(payload[11:27] == race_key.encode("ascii"), "Capture race key mismatch")
            verified.append(dict(payload=payload, file=name, sha256=digest, retrieved_at=retrieved))
        return dict(manifest=manifest, manifest_sha256=hashlib.sha256(raw).hexdigest(),
                    records=verified, started_at=start, finished_at=end)
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise DataError(f"Invalid capture manifest or files: {exc}") from exc
