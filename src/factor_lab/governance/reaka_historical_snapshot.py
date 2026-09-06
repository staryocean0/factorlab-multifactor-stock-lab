"""Restore a small frozen source fixture without checking out market data.

No implicit baseline choice, network fetch command, or history rewrite. Git may
hydrate the pinned source blobs of a partial clone. The required commit must
already have been fetched explicitly. Every extracted file is digest checked.
"""
from __future__ import annotations

import atexit
import hashlib
import io
import json
import subprocess
import tarfile
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any

BASELINE = "3a75376e1f7f871bb72e48f886c275919b3c9671"
MANIFEST = "docs/ops/reaka_multifactor_current_manifest@1.3.json"


@lru_cache(maxsize=2)
def historical_root(root: Path) -> Path:
    root = root.resolve()
    show = subprocess.run(["git", "show", f"{BASELINE}:{MANIFEST}"], cwd=root,
                          capture_output=True, timeout=120)
    if show.returncode:
        raise RuntimeError("Historical source fixture unavailable. Run: git fetch --no-tags --depth=1 --filter=blob:none origin " + BASELINE)
    manifest = json.loads(show.stdout)
    digests = {row["path"]: row["file_digest"] for rows in manifest["five_in_one"].values() for row in rows}
    digests[MANIFEST] = "sha256:" + hashlib.sha256(show.stdout).hexdigest()
    for relative in digests:
        if Path(relative).is_absolute() or ".." in Path(relative).parts or "\\" in relative:
            raise ValueError(f"unsafe historical fixture path: {relative}")
    archive = subprocess.run(["git", "archive", BASELINE, "--", *sorted(digests)],
                             cwd=root, capture_output=True, timeout=180)
    if archive.returncode:
        raise RuntimeError("Cannot restore pinned historical source blobs: " + archive.stderr.decode(errors="replace")[:500])
    temporary = tempfile.TemporaryDirectory(prefix="reaka-v13-fixture-")
    atexit.register(temporary.cleanup)
    target = Path(temporary.name)
    found: set[str] = set()
    try:
        with tarfile.open(fileobj=io.BytesIO(archive.stdout)) as tar:
            for member in tar:
                if member.isdir():
                    continue
                if not member.isfile() or member.name not in digests:
                    raise ValueError(f"unexpected historical archive member: {member.name}")
                stream = tar.extractfile(member)
                if stream is None:
                    raise ValueError(f"unreadable historical archive member: {member.name}")
                data = stream.read()
                if "sha256:" + hashlib.sha256(data).hexdigest() != digests[member.name]:
                    raise ValueError(f"historical source digest mismatch: {member.name}")
                destination = target / member.name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(data)
                found.add(member.name)
        if found != set(digests):
            raise ValueError(f"historical source fixture incomplete: {sorted(set(digests) - found)}")
        return target
    except Exception:
        temporary.cleanup()
        raise


def load_historical_contract_tests(namespace: dict[str, Any], root: Path) -> None:
    """Execute original regression tests with their ROOT at original bytes."""
    source = historical_root(root) / "tests/unit/test_reaka_foundation_contract.py"
    old = {"__name__": namespace["__name__"], "__file__": str(source)}
    exec(compile(source.read_bytes(), str(source), "exec"), old)
    namespace.update({key: value for key, value in old.items() if not key.startswith("__")})
