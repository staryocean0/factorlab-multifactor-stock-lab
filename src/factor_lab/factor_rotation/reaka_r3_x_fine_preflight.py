"""Read-only all-clock preflight for R3 Stage-B fine X decomposition.

This module must complete before any new fine-arm fit starts. It validates both
clocks and all accepted F/E/H seed references, then reconstructs accepted
XCOARSE daily contrasts from existing scores. It performs no training, no model
reload, and no new inference.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from factor_lab.factor_rotation import reaka_r3_x_coarse_runner as coarse
from factor_lab.factor_rotation import reaka_r3_x_fine_runner as fine


def preflight_clock(timeiso_root: Path, xcoarse_root: Path, clock: str) -> dict[str, Any]:
    pf, _, timeiso, _, _ = coarse._rt()
    timeiso_clock = timeiso_root / clock
    xcoarse_clock = xcoarse_root / clock
    experiment = timeiso_clock / "experiment"
    store = pf.IntradayK1InputStore.load(timeiso_clock / "prepared/store")
    accepted: dict[str, list[dict[str, np.ndarray]]] = {"F": [], "E": [], "H": []}
    seed_checks: list[dict[str, Any]] = []

    for seed in fine.SEEDS:
        f_receipt = fine.read_json(experiment / f"models/seed_{seed}/F/fit_receipt.json")
        h_receipt = fine.read_json(experiment / f"models/seed_{seed}/H/fit_receipt.json")
        common = coarse.accepted_pair_common(f_receipt, h_receipt)
        e_receipt = fine.validate_e_reference_files(xcoarse_clock, common, seed, clock)
        paths = fine._reference_paths(timeiso_clock, xcoarse_clock, seed)
        scores = {arm: fine.load_scores(path) for arm, path in paths.items()}
        if not coarse._same_score_coordinates(scores["F"], scores["E"], scores["H"]):
            raise ValueError(f"preflight F/E/H coordinate mismatch: {clock}/{seed}")
        for arm in accepted:
            accepted[arm].append(scores[arm])
        seed_checks.append({
            "seed": seed,
            "pre_dmd_state_digest": common["pre_dmd_state_digest"],
            "E_checkpoint_state_digest": e_receipt["checkpoint_state_digest"],
            "coordinates": int(len(scores["F"]["indices"])),
        })

    ensembles = {arm: timeiso.attach_labels(store, timeiso.ensemble(items)) for arm, items in accepted.items()}
    base = ensembles["F"]
    if not coarse._same_score_coordinates(base, ensembles["E"], ensembles["H"]):
        raise ValueError(f"preflight ensemble support mismatch: {clock}")
    frame = coarse.daily_triplet(
        base["scores"], ensembles["E"]["scores"], ensembles["H"]["scores"],
        base["targets"], base["rows"],
    )
    fine.verify_xcoarse_reconstruction(
        frame[["day_position", "F_minus_E", "E_minus_H", "F_minus_H"]],
        xcoarse_clock / "paired_daily.csv",
    )
    return {
        "clock": clock,
        "seeds": seed_checks,
        "paired_days": int(len(frame)),
        "xcoarse_reconstruction_verified": True,
        "new_fits": 0,
        "new_inference": 0,
    }


def run(timeiso_root: Path, xcoarse_root: Path, repo_root: Path,
        factorlab_root: Path, expected_factorlab_commit: str) -> dict[str, Any]:
    """Validate every accepted reference using repository-root path semantics."""
    source_stack = fine.validate_source_stack(repo_root)
    runtime = coarse.validate_runtime_identity(
        timeiso_root, repo_root, expected_factorlab_commit, factorlab_root,
    )
    xcoarse = fine.validate_xcoarse_reference(xcoarse_root, timeiso_root)
    clocks = {
        clock: preflight_clock(timeiso_root, xcoarse_root, clock)
        for clock in fine.CLOCKS
    }
    return {
        "schema_id": "factorlab.r3_x_fine_preflight@1.0",
        "status": "passed_read_only_reference_preflight",
        "source_stack": source_stack,
        "runtime_identity": runtime,
        "xcoarse_runtime_identity": xcoarse["runtime_identity"],
        "clocks": clocks,
        "reference_seed_pairs_checked": 6,
        "new_fits": 0,
        "new_inference": 0,
        "future_result_peeking": False,
    }
