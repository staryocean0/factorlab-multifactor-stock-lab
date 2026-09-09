#!/usr/bin/env python3
"""Read bounded recovery-request paths locally; emit metadata, never source data.

This is a transport/readiness inventory, NOT residual arithmetic, PIT, replay
or scientific acceptance. It does not execute historical scripts or recursively
chase an entire DataHub lake. JSON canonical candidates are explicitly unbound
unless the original contract specifies that convention.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def file_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def load_request(text: str) -> dict[str, Any]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate request key: {key}")
            result[key] = value
        return result
    def finite(value):
        raise ValueError(f"nonfinite request value: {value}")
    value = json.loads(text, object_pairs_hook=unique, parse_constant=finite)
    if not isinstance(value, dict):
        raise ValueError("request must be a JSON object")
    return value


def collect(request: dict[str, Any], root: Path) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise ValueError("request must be a JSON object")
    for key in ("required_bounded_upstream", "missing_declared_source_files", "additional_transitive_source_dependencies"):
        value = request.get(key, [])
        if not isinstance(value, list) or any(not isinstance(row, dict) for row in value):
            raise ValueError(f"request {key} must be a list of objects")
    root = Path(root).resolve()
    wanted: dict[str, dict[str, Any]] = {}

    def add(path: str, expected: str | None, convention: str, role: str) -> None:
        if not isinstance(path, str) or not path:
            raise ValueError("nonempty relative path required")
        if path in wanted and (wanted[path]["expected"], wanted[path]["convention"]) != (expected, convention):
            raise ValueError(f"conflicting expectations: {path}")
        wanted[path] = {"path": path, "expected": expected, "convention": convention, "role": role}

    for stage in request.get("required_bounded_upstream", []):
        if stage.get("stage") == "P6.1":
            base = stage["original_root"]
            if not isinstance(stage.get("original_file_digests", {}), dict):
                raise ValueError("P6.1 original_file_digests must be an object")
            for path, expected in stage.get("original_file_digests", {}).items():
                add(f"{base}/{path}", expected, "raw_sha256", "P6.1")
        elif stage.get("stage") == "P6.2":
            if not isinstance(stage.get("original_roots"), list) or any(not isinstance(p, str) for p in stage["original_roots"]):
                raise ValueError("P6.2 original_roots must be a list of paths")
            for base in stage["original_roots"]:
                clock = base.rsplit("/", 1)[-1]
                for ot in ("ot1", "ot2", "ot3"):
                    add(f"{base}/{ot}/manifest.json",
                        stage["manifest_digests_recorded"][f"formal_{clock}_{ot}"],
                        "recover_original_manifest_convention", "P6.2")
                for path in ("ot1/stock_residual_surfaces.npz", "ot1/d5_stock_exposures.parquet",
                             "ot1/d5_stock_industry_exposures.parquet", "ot2/selected_factor_states.parquet"):
                    add(f"{base}/{path}", None, "await_original_manifest_binding", "P6.2")
    for row in request.get("missing_declared_source_files", []):
        add(row["path"], row["expected"], "raw_sha256", "declared_source")
    for row in request.get("additional_transitive_source_dependencies", []):
        add(row["path"], None, "await_original_source_binding", "transitive_source")
    if not wanted:
        raise ValueError("request contains no recognized bounded recovery paths")
    rows = []
    for relative, descriptor in sorted(wanted.items()):
        row = dict(descriptor)
        try:
            path = root / relative
            if (not relative or "\\" in relative or Path(relative).is_absolute()
                    or ".." in Path(relative).parts or not path.resolve().is_relative_to(root)):
                raise ValueError("unsafe requested path")
            before = path.stat()
            row["size_bytes"] = before.st_size
            row["raw_sha256"] = file_digest(path)
            after = path.stat()
            if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                raise ValueError("source changed during byte inventory; rerun on a stable file")
            row["status"] = "present_unbound"
            expected = row["expected"]
            if row["convention"] == "raw_sha256":
                row["status"] = "byte_match" if row["raw_sha256"] == expected else "byte_mismatch"
            elif expected is not None:
                row["raw_matches_recorded"] = row["raw_sha256"] == expected
                try:
                    obj = json.loads(path.read_text(encoding="utf-8"))
                    if isinstance(obj, dict):
                        body = {k: v for k, v in obj.items() if k != "canonical_digest"}
                        candidate = "sha256:" + hashlib.sha256(json.dumps(
                            body, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                            allow_nan=False).encode()).hexdigest()
                        row["canonical_candidate"] = candidate
                        row["canonical_candidate_matches_recorded"] = candidate == expected
                except (OSError, ValueError, TypeError):
                    row["canonical_candidate"] = "not_computable"
        except FileNotFoundError:
            row["status"] = "missing"
        except (OSError, ValueError, TypeError) as exc:
            row.update(status="error", detail=str(exc))
        rows.append(row)
    return {
        "schema_id": "factorlab.reaka_local_source_inventory@1.0",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": "bounded_local_metadata_only", "rows": rows,
        "counts": {key: sum(row["status"] == key for row in rows)
                   for key in ("byte_match", "byte_mismatch", "present_unbound", "missing", "error")},
        "external_pit_verified": False, "historical_reproduction": False,
        "scientific_acceptance": False, "whole_datahub_required": False,
        "raw_data_included": False,
        "account_source_gaps_not_repaired": request.get("unrecovered_account_sources", []),
        "next_step": "inspect the smallest relevant source/clock evidence; receipt is not independent cloud verification",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--input-root", type=Path, required=True)
    args = parser.parse_args()
    try:
        request = load_request(args.request.read_text(encoding="utf-8"))
        report = collect(request, args.input_root)
        report["request_sha256"] = file_digest(args.request)
        report["collector_sha256"] = file_digest(Path(__file__))
        print(json.dumps(report, indent=2, ensure_ascii=False, allow_nan=False))
        if report["counts"]["byte_mismatch"] or report["counts"]["error"]:
            return 1
        return 2 if report["counts"]["missing"] or report["counts"]["present_unbound"] else 0
    except (OSError, ValueError, TypeError, KeyError) as exc:
        print(json.dumps({"status": "invalid_request", "error": str(exc),
                          "scientific_acceptance": False}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
