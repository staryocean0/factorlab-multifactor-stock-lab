#!/usr/bin/env python3
"""Restore GitHub-split REAKA original-byte artifacts and verify sha256."""
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def sha256(path: Path) -> str:
    d = hashlib.sha256()
    with path.open("rb") as h:
        for b in iter(lambda: h.read(1024 * 1024), b""):
            d.update(b)
    return d.hexdigest()

def main() -> int:
    parts_dirs = sorted(ROOT.rglob("*.parts"))
    restored = 0
    for part_dir in parts_dirs:
        if not part_dir.is_dir() or not (part_dir / "manifest.json").is_file():
            continue
        man = json.loads((part_dir / "manifest.json").read_text())
        dest = ROOT / man["original_path"]
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as out:
            for part in man["parts"]:
                out.write((part_dir / part["name"]).read_bytes())
        got = sha256(dest)
        if got != man["original_sha256"] or dest.stat().st_size != man["original_bytes"]:
            raise SystemExit(f"restore digest mismatch: {man['original_path']}")
        restored += 1
        print("restored", man["original_path"], got)
    print("restored_count", restored)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
