"""Read-only acceptance of the delivered R1 bytes, never financial acceptance.

Historical files are inspected as data. No historical launcher is imported.
Split originals are restored into a separate scratch directory, never resealed.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

STORE = "output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020/formal"
FIT = "output/factor-rotation/reaka_intraday_K1_fit_prefix_successor_v1_2011_2017/formal"
MAPPING = "output/factor-rotation/reaka_intraday_portfolio_mapping_inputs_v2_2011_2020/formal"
PREFLIGHT = "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/preflight"


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return "sha256:" + h.hexdigest()


def historical_digest(data: dict) -> str:
    body = {k: v for k, v in data.items() if k != "canonical_digest"}
    return "sha256:" + hashlib.sha256(json.dumps(
        body, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode()).hexdigest()


def contained(root: Path, relative: str) -> Path:
    p = Path(relative)
    if p.is_absolute() or ".." in p.parts or not relative:
        raise ValueError(f"unsafe relative path: {relative}")
    result = (root / p).resolve()
    if not result.is_relative_to(root.resolve()):
        raise ValueError(f"path escapes root: {relative}")
    return result


class ArtifactReader:
    def __init__(self, root: Path, restored: Path):
        self.root = root.resolve()
        self.restored = restored.resolve()
        if self.restored.is_relative_to(self.root) or self.root.is_relative_to(self.restored):
            raise ValueError("restoration and input trees must be separate")
        self.verified: dict[str, str] = {}
        self.restoration_receipts: list[dict] = []

    def file(self, relative: str, expected: str | None = None) -> Path:
        source = contained(self.root, relative)
        path = source
        if not path.is_file():
            path = contained(self.restored, relative)
            if not path.is_file():
                manifest_path = Path(str(source) + ".parts") / "manifest.json"
                if not manifest_path.is_file():
                    raise FileNotFoundError(relative)
                m = json.loads(manifest_path.read_text())
                if m["original_path"] != relative:
                    raise ValueError(f"split destination mismatch: {relative}")
                names = [p["name"] for p in m["parts"]]
                if not names or len(names) != len(set(names)):
                    raise ValueError(f"duplicate/empty parts: {relative}")
                path.parent.mkdir(parents=True, exist_ok=True)
                temporary = path.with_name(path.name + ".verifying")
                try:
                    with temporary.open("xb") as out:
                        for part in m["parts"]:
                            chunk = contained(manifest_path.parent, part["name"])
                            if chunk.stat().st_size != part["bytes"] or digest(chunk) != "sha256:" + part["sha256"]:
                                raise ValueError(f"split part mismatch: {relative}/{part['name']}")
                            with chunk.open("rb") as f:
                                for block in iter(lambda: f.read(1024 * 1024), b""):
                                    out.write(block)
                    if temporary.stat().st_size != m["original_bytes"] or digest(temporary) != "sha256:" + m["original_sha256"]:
                        raise ValueError(f"restored original mismatch: {relative}")
                    temporary.rename(path)
                finally:
                    if temporary.exists():
                        temporary.unlink()
                self.restoration_receipts.append({"path": relative, "parts": len(names), "bytes": m["original_bytes"], "digest": "sha256:" + m["original_sha256"]})
        actual = self.verified.get(relative)
        if actual is None:
            actual = digest(path)
            self.verified[relative] = actual
        if expected is not None and actual != expected:
            raise ValueError(f"file digest mismatch: {relative}: {actual} != {expected}")
        return path

    def json(self, relative: str, expected: str | None = None) -> dict:
        data = json.loads(self.file(relative, expected).read_text())
        if "canonical_digest" in data and historical_digest(data) != data["canonical_digest"]:
            raise ValueError(f"canonical digest mismatch: {relative}")
        return data


def checkpoint_state(reader: ArtifactReader, root: str, manifest: dict) -> dict:
    import numpy as np

    rows = manifest["tensors"]
    names = [row["name"] for row in rows]
    if len(rows) != manifest["tensor_count"] or names != sorted(set(names)):
        raise ValueError("checkpoint tensor inventory mismatch")
    if [row["position"] for row in rows] != list(range(len(rows))):
        raise ValueError("checkpoint tensor positions mismatch")
    h = hashlib.sha256()
    shapes = {}
    for row in rows:
        a = np.load(reader.file(f"{root}/{row['filename']}", row["digest"]), allow_pickle=False)
        if a.dtype.hasobject or not np.isfinite(a).all():
            raise ValueError("invalid checkpoint tensor")
        h.update(row["name"].encode())
        h.update(str(a.dtype).encode("ascii"))
        h.update(str(a.shape).encode("ascii"))
        h.update(a.tobytes(order="C"))
        shapes[row["name"]] = list(a.shape)
    state = "sha256:" + h.hexdigest()
    if state != manifest["state_digest"]:
        raise ValueError("checkpoint state digest mismatch")
    if shapes.get("operators") != [1, 8, 8] or shapes.get("feature_encoder.weight_ih_l0") != [32, 71]:
        raise ValueError("checkpoint is not the declared d8/71-feature/K1 incumbent")
    return {"state_digest": state, "tensor_count": len(rows), "operator_shape": shapes["operators"]}


def inspect_clock(reader: ArtifactReader, suffix: str) -> dict:
    import numpy as np
    import pandas as pd
    import pyarrow.parquet as pq

    clock = suffix[:2] + ":" + suffix[2:]
    m = reader.json(f"{MAPPING}/input_manifest_{suffix}.json")
    store = reader.json(f"{STORE}/{suffix}/manifest.json", m["store_manifest_digest"])
    if m["decision_clock"] != clock or store["decision_clock"] != clock:
        raise ValueError("clock binding mismatch")
    arrays = {}
    for name, expected in store["artifact_digests"].items():
        path = reader.file(f"{STORE}/{suffix}/{name}", expected)
        if name.endswith(".npy"):
            arrays[name] = np.load(path, allow_pickle=False, mmap_mode="r")
    calendar, symbols, rows = (arrays[n] for n in ("calendar.npy", "symbols.npy", "inference_rows.npy"))
    labels = arrays["labelled_row_indices.npy"]
    if len(calendar) != store["calendar_days"] or len(symbols) != store["symbol_count"] or rows.shape != (store["inference_row_count"], 4):
        raise ValueError("store dimensions mismatch")
    if np.isnat(calendar).any() or not np.all(np.diff(calendar) > np.timedelta64(0, "ns")) or calendar[-1] > np.datetime64("2020-12-31T23:59:59"):
        raise ValueError("invalid/out-of-bound input calendar")
    if rows[:, 0].min() < 180 or rows[:, 0].max() >= len(calendar) or rows[:, 1].min() < 0 or rows[:, 1].max() >= len(symbols):
        raise ValueError("invalid inference coordinates")
    if len(np.unique(rows[:, :2], axis=0)) != len(rows):
        raise ValueError("duplicate inference coordinates")
    years = calendar[rows[:, 0]].astype("datetime64[Y]").astype(int) + 1970
    if not np.array_equal(years, rows[:, 2]):
        raise ValueError("inference year mismatch")
    expected_labels = np.flatnonzero(np.isfinite(arrays["epsilon_future.npy"][rows[:, 0], rows[:, 1]]))
    if not np.array_equal(labels, expected_labels) or len(labels) != store["labelled_row_count"]:
        raise ValueError("label availability index mismatch")
    for start in range(0, len(rows), 16384):
        b = rows[start:start + 16384]
        if not np.isfinite(arrays["epsilon_history.npy"][b[:, 0, None] + np.arange(-180, 1, 20), b[:, 1, None]]).all():
            raise ValueError("nonfinite inference history")
    normalizer = reader.json(f"{PREFLIGHT}/{suffix}/normalizer.json", m["normalizer_digest"])
    if normalizer["fit_end_year"] != 2016 or normalizer["target_used"] is not False:
        raise ValueError("normalizer fit boundary mismatch")
    for prefix in ("return", "beta", "reliability"):
        if not np.isfinite([normalizer[prefix + "_mean"], normalizer[prefix + "_scale"]]).all() or normalizer[prefix + "_scale"] <= 0:
            raise ValueError("invalid normalizer")
    fit = reader.json(f"{FIT}/{suffix}/formal.json")
    fit_contract = reader.json("docs/ops/reaka_intraday_K1_fit_prefix_successor@1.0.json")
    if fit["contract_digest"] != fit_contract["canonical_digest"] or fit["config"] != fit_contract["fixed_config"] or fit["clock"] != clock:
        raise ValueError("fit contract/config mismatch")
    seeds = {}
    if [r["seed"] for r in fit["seed_results"]] != [11, 29, 47]:
        raise ValueError("fit seed inventory mismatch")
    for seed in fit["seed_results"]:
        key = str(seed["seed"])
        root = f"{FIT}/{suffix}/{seed['checkpoint_relative']}"
        checkpoint = reader.json(f"{root}/manifest.json", m["checkpoint_manifest_digests"][key])
        result = checkpoint_state(reader, root, checkpoint)
        if result["state_digest"] != seed["state_digest"]:
            raise ValueError("checkpoint/formal state binding mismatch")
        selected = min(seed["cycles"], key=lambda r: r["canonical_train_loss"])
        if seed["selected_cycle"] != selected["cycle"] or seed["selected_canonical_loss"] != selected["canonical_train_loss"] or seed["2017_used_for_checkpoint_selection"] is not False:
            raise ValueError("fit-prefix selection receipt mismatch")
        review = np.load(reader.file(f"{FIT}/{suffix}/review_scores_seed_{key}.npy", seed["review_score_digest"]), allow_pickle=False)
        if not np.isfinite(review).all() or len(review) != int(np.sum(years[labels] == 2017)):
            raise ValueError("review score support mismatch")
        seeds[key] = {**result, "selected_cycle": seed["selected_cycle"], "review_score_count": len(review)}
    score_path = reader.file(f"{MAPPING}/bounded_score_panel_{suffix}.parquet", m["panel_digest"])
    market_path = reader.file(f"{MAPPING}/daily_market_panel_{suffix}.parquet", m["market_panel_digest"])
    score = pd.read_parquet(score_path)
    market = pd.read_parquet(market_path, columns=["date", "decision_clock", "symbol"])
    for frame, date in ((score, "decision_date"), (market, "date")):
        if frame[[date, "symbol", "decision_clock"]].isna().any().any() or frame.duplicated([date, "symbol", "decision_clock"]).any():
            raise ValueError("null/duplicate panel coordinates")
        if not frame["decision_clock"].eq(clock).all() or pd.to_datetime(frame[date]).max() > pd.Timestamp("2020-12-31"):
            raise ValueError("panel clock/date boundary mismatch")
    if len(score) != len(rows) or not np.isfinite(score["score"]).all():
        raise ValueError("score support/value mismatch")
    expected_support = pd.MultiIndex.from_arrays([pd.to_datetime(calendar[rows[:, 0]]), symbols[rows[:, 1]].astype(str)])
    actual_support = pd.MultiIndex.from_frame(score[["decision_date", "symbol"]])
    market_support = pd.MultiIndex.from_frame(market[["date", "symbol"]])
    if len(expected_support.difference(actual_support)) or len(actual_support.difference(expected_support)) or len(actual_support.difference(market_support)):
        raise ValueError("inference/score/market support mismatch")
    return {"clock": clock, "store_artifacts": len(store["artifact_digests"]), "inference_rows": len(rows), "labelled_rows": len(labels), "unlabelled_inference_rows": len(rows) - len(labels), "calendar_start": str(calendar[0]), "calendar_end": str(calendar[-1]), "normalizer_file_digest": m["normalizer_digest"], "checkpoint_bindings": seeds, "score_rows": len(score), "market_rows": len(market), "score_columns": list(score.columns), "market_columns": pq.ParquetFile(market_path).schema_arrow.names, "score_content_recomputed": False, "external_pit_proven": False}


def audit_sources(reader: ArtifactReader, manifests: list[str]) -> list[dict]:
    snapshots = reader.json("docs/ops/evidence/r1_original_source_snapshots/manifest.json")
    copies = reader.json("docs/ops/evidence/r1_datahub_history_copies/path_map.json")
    alternatives = {(r["original_path"], r["digest"]): r["snapshot_path"] for r in snapshots["files"]}
    alternatives.update({(r["original_absolute_path"], r["digest"]): r["package_path"] for r in copies["files"]})
    results = []
    for manifest_path in manifests:
        manifest = reader.json(manifest_path)
        for field in ("source_closure", "source_digests", "market_rebuild_source_digests"):
            for path, expected in manifest.get(field, {}).items():
                actual_path = alternatives.get((path, expected), path)
                row = {"manifest": manifest_path, "field": field, "path": path, "resolved_path": actual_path, "expected": expected}
                try:
                    reader.file(actual_path, expected)
                    row["status"] = "matched_archived_original" if actual_path != path else "matched"
                except FileNotFoundError:
                    row["status"] = "missing"
                except ValueError as exc:
                    row["status"] = "mismatch"
                    row["detail"] = str(exc)
                results.append(row)
    return results


def audit_daily_uploads(reader: ArtifactReader) -> list[dict]:
    import pandas as pd
    import pyarrow.parquet as pq

    manifest = reader.json("data/manifest.json")
    products = {r["path"]: r for r in manifest["products"]}
    result = []
    for year in (2023, 2024):
        for month in range(1, 13):
            relative = f"data/development/cn_a_qfq_daily/year={year}/{month:02d}.parquet"
            path = reader.file(relative, "sha256:" + products[relative]["sha256"])
            parquet = pq.ParquetFile(path)
            date = next((n for n in ("trading_day", "date") if n in parquet.schema_arrow.names), None)
            if date is None:
                raise ValueError(f"daily date column missing: {relative}")
            days = pd.to_datetime(pd.read_parquet(path, columns=[date])[date], errors="raise")
            if days.empty or days.isna().any() or not (days.dt.year.eq(year) & days.dt.month.eq(month)).all():
                raise ValueError(f"daily partition date mismatch: {relative}")
            result.append({"path": relative, "digest": reader.verified[relative], "rows": len(days), "date_min": str(days.min()), "date_max": str(days.max())})
    return result


def audit_uploads(reader: ArtifactReader, previous: dict, tree: dict) -> dict:
    report = {"schema_id": "factorlab.reaka_first_round_upload_audit@1.0", "fresh_oos": False, "scientific_acceptance": "not_established", "model_training_run": False, "score_generation_run": False, "account_run": False, "production_authority": False, "errors": [], "initial_inputs": [], "clocks": []}
    for row in previous["required_initial_input_inventory"]:
        try:
            reader.file(row["path"], row["expected_file_digest"])
            report["initial_inputs"].append({"path": row["path"], "digest": row["expected_file_digest"], "status": "matched_original_bytes"})
        except (OSError, ValueError) as exc:
            report["errors"].append(str(exc))
    try:
        required = previous["required_ledger_contract"]
        ledger = reader.json(required["path"])
        if ledger["canonical_digest"] != required["expected_canonical_digest"]:
            raise ValueError("old ledger contract binding mismatch")
        report["ledger_contract"] = {"path": required["path"], "canonical_digest": ledger["canonical_digest"], "matched": True}
        for suffix in ("1430", "1445"):
            report["clocks"].append(inspect_clock(reader, suffix))
        report["source_closure"] = audit_sources(reader, [required["path"], "docs/ops/reaka_intraday_K1_preflight@1.0.json", "docs/ops/reaka_intraday_K1_fit_prefix_successor@1.0.json", *[f"{MAPPING}/input_manifest_{c}.json" for c in ("1430", "1445")]])
        report["daily_2023_2024"] = audit_daily_uploads(reader)
    except (OSError, ValueError, KeyError, IndexError) as exc:
        report["errors"].append(str(exc))
    entries = {e["path"] for e in tree["tree"] if e["type"] == "blob"}
    if tree.get("truncated") is not False:
        report["errors"].append("remote tree is not complete")
    upstream = ["ot1/stock_residual_surfaces.npz", "ot1/d5_stock_exposures.parquet", "ot1/d5_stock_industry_exposures.parquet", "ot2/selected_factor_states.parquet", "entry_open_1430.npy", "entry_open_1445.npy"]
    report["upstream_inventory"] = [{"suffix": suffix, "matches": sorted(p for p in entries if p.endswith("/" + suffix))} for suffix in upstream]
    report["declared_upstream_manifest_digests"] = reader.json("docs/ops/reaka_intraday_K1_preflight@1.0.json")["inputs"]
    report["restorations"] = reader.restoration_receipts
    report["verified_file_digests"] = dict(sorted(reader.verified.items()))
    report["delivered_byte_acceptance"] = "passed" if not report["errors"] and len(report["clocks"]) == 2 else "failed"
    unresolved = [r for r in report.get("source_closure", []) if r["status"] in ("missing", "mismatch")]
    report["source_closure_unresolved"] = unresolved
    report["next_step"] = "R2_external_PIT_and_residual_construction_source_review"
    report["next_step_status"] = "blocked_missing_upstream_sources" if any(not r["matches"] for r in report["upstream_inventory"]) else "requires_upstream_manifest_review"
    report["historical_reproducibility_complete"] = False
    return report
