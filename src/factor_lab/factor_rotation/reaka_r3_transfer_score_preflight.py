"""Read-only checkpoint/model replay gate before 2021--2025 transfer scoring."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping
import subprocess
import numpy as np

EXPECTED_TRANSFER_INPUT_GIT_BLOB = "353574896cb478489f7cdcba58697965a48f06e8"
SAMPLE_ROWS = 64


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


def run(spec: Mapping[str, Any], repo_root: Path, factorlab_root: Path) -> dict[str, Any]:
    """Replay 64 archived-score coordinates for every frozen clock/seed/arm.

    No new-period feature store, outcome sidecar, or label file is opened here.
    """
    from factor_lab.factor_rotation import reaka_intraday_k1_preflight_v1 as pf
    from factor_lab.factor_rotation import reaka_intraday_k1_training_v1 as tr
    from factor_lab.factor_rotation import reaka_r3_time_isolated_runner as timeiso_mod
    from factor_lab.factor_rotation import reaka_r3_transfer_evaluation as ev

    if spec.get("schema_id") != "factorlab.r3_transfer_evaluation_run@1.0":
        raise ValueError("wrong transfer evaluation run schema")
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
                receipt = ev.read_json(receipt_path)
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
                indices = np.asarray(archived["indices"][pick], dtype=np.int64)
                replay = timeiso_mod.score_no_labels(model, old_store, normalizer, indices, "cpu")
                if not np.array_equal(replay["rows"], archived["rows"][pick]):
                    raise ValueError(f"archived score rows mismatch: {clock}/{seed}/{arm}")
                error = np.abs(np.asarray(replay["scores"], float) - np.asarray(archived["scores"][pick], float))
                maximum = float(error.max()) if len(error) else 0.0
                if not np.isfinite(error).all() or maximum > 1e-7:
                    raise ValueError(f"archived score numerical mismatch: {clock}/{seed}/{arm}")
                results.append({"clock": clock, "seed": seed, "arm": arm,
                                "rows_replayed": int(len(pick)), "max_abs_error": maximum,
                                "checkpoint_state_digest": manifest["state_digest"]})
    if len(results) != 24:
        raise AssertionError("reference replay budget drift")
    return {"schema_id": "factorlab.r3_transfer_score_preflight@1.0",
            "status": "passed_read_only_checkpoint_score_preflight",
            "reference_pairs_checked": 24, "rows_per_pair_max": SAMPLE_ROWS,
            "checks": results, "new_model_fits": 0, "new_period_score_jobs": 0,
            "outcome_values_read": 0, "fresh_oos": False, "PIT_certified": False}
