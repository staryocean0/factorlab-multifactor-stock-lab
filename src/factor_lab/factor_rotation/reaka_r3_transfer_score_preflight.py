"""Read-only checkpoint/model replay gate before 2021--2025 transfer scoring.

Comparison coordinates stay sparse and fixed, but the forward pass is replayed
inside the same contiguous BATCH_SIZE geometry used by the archived scorer.
This avoids treating a different CPU float32 GEMM batch shape as model drift.
The numerical acceptance threshold remains max abs error <= 1e-7.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping
import subprocess
import numpy as np

EXPECTED_TRANSFER_INPUT_GIT_BLOB = "353574896cb478489f7cdcba58697965a48f06e8"
SAMPLE_ROWS = 64
ATOL = 1e-7


def _git_blob(path: Path) -> str:
    proc = subprocess.run(["git", "hash-object", str(path)], capture_output=True, text=True)
    if proc.returncode:
        raise ValueError(f"cannot hash source: {path}: {proc.stderr[-300:]}")
    return proc.stdout.strip()


def reference_paths(timeiso: Path, xfine: Path, clock: str, seed: int, arm: str) -> tuple[Path, Path, Path]:
    if arm == "F":
        root = timeiso / clock / "experiment/models" / f"seed_{seed}" / "F"
    else:
        root = xfine / clock / "models" / f"seed_{seed}" / arm
    return root / "checkpoint", root / "fit_receipt.json", root / "scores.npz"


def sample_positions(n: int, count: int = SAMPLE_ROWS) -> np.ndarray:
    if n <= 0 or count <= 0:
        raise ValueError("positive reference score/sample size required")
    return np.unique(np.linspace(0, n - 1, min(count, n), dtype=np.int64))


def replay_sampled_in_archived_batch_context(
    archived: Mapping[str, np.ndarray],
    pick: np.ndarray,
    *,
    batch_size: int,
    score_batch: Callable[[np.ndarray], Mapping[str, np.ndarray]],
) -> dict[str, Any]:
    """Replay sparse comparison positions inside their original archived batches.

    `pick` indexes the archived score sequence, not model input coordinates. Each
    unique historical batch is replayed in full and only the preselected rows are
    retained for comparison. No labels or new-period arrays are involved.
    """
    idx = np.asarray(archived["indices"], dtype=np.int64)
    rows = np.asarray(archived["rows"], dtype=np.int64)
    p = np.asarray(pick, dtype=np.int64)
    if batch_size <= 0 or p.ndim != 1 or not len(p):
        raise ValueError("invalid archived batch replay request")
    if (p < 0).any() or (p >= len(idx)).any() or len(np.unique(p)) != len(p):
        raise ValueError("comparison positions outside archived score support")
    out_scores = np.empty(len(p), dtype=float)
    out_rows = np.empty_like(rows[p])
    context_rows = 0
    batches = 0
    starts = np.unique((p // batch_size) * batch_size)
    for start in starts:
        stop = min(int(start) + int(batch_size), len(idx))
        context_positions = np.arange(int(start), stop, dtype=np.int64)
        context_indices = idx[context_positions]
        replay = score_batch(context_indices)
        replay_idx = np.asarray(replay["indices"], dtype=np.int64)
        replay_rows = np.asarray(replay["rows"], dtype=np.int64)
        replay_scores = np.asarray(replay["scores"], dtype=float)
        if not np.array_equal(replay_idx, context_indices):
            raise ValueError("archived batch replay index order drift")
        if not np.array_equal(replay_rows, rows[context_positions]):
            raise ValueError("archived batch replay row drift")
        selected = np.flatnonzero((p >= start) & (p < stop))
        local = p[selected] - int(start)
        out_scores[selected] = replay_scores[local]
        out_rows[selected] = replay_rows[local]
        context_rows += len(context_positions)
        batches += 1
    return {
        "scores": out_scores,
        "rows": out_rows,
        "comparison_rows": int(len(p)),
        "context_rows_replayed": int(context_rows),
        "historical_batches_replayed": int(batches),
        "batch_size": int(batch_size),
    }


def _embedded_f_receipt(timeiso: Path, clock: str, seed: int) -> dict[str, Any]:
    """Read accepted TIMEISO F receipt without requiring a materialized file."""
    result = timeiso / clock / "experiment/result.json"
    if not result.exists():
        raise FileNotFoundError(result)
    import json
    body = json.loads(result.read_text(encoding="utf-8"))
    rows = body.get("seed_receipts", {}).get("F", [])
    found = [row for row in rows if row.get("identity", {}).get("clock") == clock
             and row.get("identity", {}).get("seed") == seed
             and row.get("identity", {}).get("arm") == "F"]
    if len(found) != 1:
        raise ValueError(f"accepted embedded F receipt not uniquely identified: {clock}/{seed}")
    return dict(found[0])


def read_reference_receipt(timeiso: Path, receipt_path: Path, clock: str, seed: int, arm: str, reader) -> tuple[dict[str, Any], str]:
    if receipt_path.exists():
        return reader(receipt_path), "materialized_fit_receipt"
    if arm == "F":
        return _embedded_f_receipt(timeiso, clock, seed), "accepted_timeiso_seed_receipts_F"
    raise FileNotFoundError(receipt_path)


def run(spec: Mapping[str, Any], repo_root: Path, factorlab_root: Path) -> dict[str, Any]:
    """Replay <=64 archived comparison coordinates for every frozen pair.

    The comparison rows are sparse, but forward computation preserves archived
    BATCH_SIZE boundaries. No new-period feature store, outcome sidecar, or label
    file is opened here.
    """
    from factor_lab.factor_rotation import reaka_intraday_k1_preflight_v1 as pf
    from factor_lab.factor_rotation import reaka_intraday_k1_training_v1 as tr
    from factor_lab.factor_rotation import reaka_r3_time_isolated_runner as timeiso_mod
    from factor_lab.factor_rotation import reaka_r3_transfer_evaluation as ev

    if spec.get("schema_id") != "factorlab.r3_transfer_evaluation_run@1.0":
        raise ValueError("wrong transfer evaluation run schema")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=factorlab_root,
                          capture_output=True, text=True)
    if head.returncode or head.stdout.strip() != ev.EXPECTED_FACTORLAB_COMMIT:
        raise ValueError("FactorLab commit mismatch")
    timeiso = Path(spec["timeiso_root"]).resolve()
    xfine = Path(spec["xfine_root"]).resolve()
    feature = Path(spec["transfer_feature_root"]).resolve()
    env = Path(spec["accepted_environment"]).resolve()
    ev.validate_job_sources(repo_root, timeiso, feature, env)
    if _git_blob(repo_root / "src/factor_lab/factor_rotation/reaka_r3_transfer_inputs.py") != EXPECTED_TRANSFER_INPUT_GIT_BLOB:
        raise ValueError("accepted transfer-input source drift")

    results = []
    for clock in ev.CLOCKS:
        old_store = pf.IntradayK1InputStore.load(timeiso / clock / "prepared/store")
        normalizer = ev.read_json(timeiso / clock / "experiment/normalizer.json")
        candidate = ev.read_json(timeiso / clock / "experiment/candidate.json")
        for seed in ev.SEEDS:
            for arm in ev.ARMS:
                checkpoint, receipt_path, score_path = reference_paths(timeiso, xfine, clock, seed, arm)
                receipt, receipt_origin = read_reference_receipt(
                    timeiso, receipt_path, clock, seed, arm, ev.read_json
                )
                ev._receipt_identity(receipt, clock, seed, arm)
                manifest = ev.read_json(checkpoint / "manifest.json")
                if manifest.get("state_digest") != receipt.get("checkpoint_state_digest"):
                    raise ValueError(f"checkpoint receipt mismatch: {clock}/{seed}/{arm}")
                model = ev._build_model(candidate, seed, arm)
                tr.load_state_tree(model, checkpoint)
                if tr.state_digest(model) != manifest.get("state_digest"):
                    raise ValueError(f"checkpoint state replay mismatch: {clock}/{seed}/{arm}")
                archived = ev._load_scores(score_path)
                pick = sample_positions(len(archived["indices"]))
                replay = replay_sampled_in_archived_batch_context(
                    archived,
                    pick,
                    batch_size=int(tr.BATCH_SIZE),
                    score_batch=lambda indices: timeiso_mod.score_no_labels(
                        model, old_store, normalizer, indices, "cpu"
                    ),
                )
                if not np.array_equal(replay["rows"], archived["rows"][pick]):
                    raise ValueError(f"archived score rows mismatch: {clock}/{seed}/{arm}")
                error = np.abs(np.asarray(replay["scores"], float) - np.asarray(archived["scores"][pick], float))
                maximum = float(error.max()) if len(error) else 0.0
                if not np.isfinite(error).all() or maximum > ATOL:
                    raise ValueError(f"archived score numerical mismatch: {clock}/{seed}/{arm}")
                results.append({
                    "clock": clock,
                    "seed": seed,
                    "arm": arm,
                    "comparison_rows": int(len(pick)),
                    "context_rows_replayed": replay["context_rows_replayed"],
                    "historical_batches_replayed": replay["historical_batches_replayed"],
                    "batch_size": replay["batch_size"],
                    "max_abs_error": maximum,
                    "atol": ATOL,
                    "checkpoint_state_digest": manifest["state_digest"],
                    "receipt_origin": receipt_origin,
                })
    if len(results) != 24:
        raise AssertionError("reference replay budget drift")
    return {
        "schema_id": "factorlab.r3_transfer_score_preflight@1.1",
        "status": "passed_read_only_checkpoint_score_preflight",
        "reference_pairs_checked": 24,
        "comparison_rows_per_pair_max": SAMPLE_ROWS,
        "archived_batch_geometry_preserved": True,
        "atol": ATOL,
        "checks": results,
        "new_model_fits": 0,
        "new_period_score_jobs": 0,
        "outcome_values_read": 0,
        "fresh_oos": False,
        "PIT_certified": False,
    }
