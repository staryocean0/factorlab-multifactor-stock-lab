#!/usr/bin/env python3
"""Run one clock's result-free K1/r0 compatibility and runtime preflight."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    CLOCK_SUFFIX,
    STORE_FILES,
    IntradayK1InputStore,
    backend_benchmark,
    compatibility_certificate,
    file_digest,
    lr_probe,
    normalizer_from_store,
    parameter_instantiation,
    read_json,
    validate_contract,
    write_json,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "docs/ops/reaka_intraday_K1_preflight@1.0.json"
STORE = ROOT / "output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020"
EVIDENCE = ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/preflight"
GOVERNANCE = ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/parameter_governance"


def main() -> None:
    parser = argparse.ArgumentParser()
    _ = parser.add_argument("--clock", choices=("14:30", "14:45"), required=True)
    args = parser.parse_args()
    clock = cast(str, args.clock)
    contract = read_json(CONTRACT)
    blockers = validate_contract(contract)
    if blockers:
        raise RuntimeError(";".join(blockers))
    suffix = CLOCK_SUFFIX[clock]
    formal = STORE / "formal" / suffix
    isolated = STORE / "isolated" / suffix
    mismatches = [name for name in STORE_FILES if file_digest(formal / name) != file_digest(isolated / name)]
    if mismatches:
        raise RuntimeError(f"reaka_K1_store_replay_mismatch:{mismatches}")
    output = EVIDENCE / suffix
    output.mkdir(parents=True, exist_ok=True)
    store = IntradayK1InputStore.load(formal)
    normalizer = write_json(output / "normalizer.json", normalizer_from_store(store))
    compatibility = write_json(
        output / "compatibility_certificate.json",
        compatibility_certificate(store, decision_clock=clock),
    )
    capacity = cast(list[dict[str, int]], compatibility["capacity_root_candidates"])
    lr = write_json(output / "lr_gradient_receipt.json", lr_probe(store, normalizer, capacity))
    backend = write_json(output / "backend_receipt.json", backend_benchmark(store, normalizer))
    instantiation = write_json(
        output / "run_instantiation.json",
        parameter_instantiation(
            compatibility=compatibility,
            lr_receipt=lr,
            backend_receipt=backend,
            governance_receipts={
                "workflow_gate_digest": str(read_json(GOVERNANCE / "workflow_gate.json")["canonical_digest"]),
                "financial_alignment_gate_digest": str(read_json(GOVERNANCE / "financial_alignment_gate.json")["canonical_digest"]),
                "root_scope_gate_digest": str(read_json(GOVERNANCE / "root_scope_gate.json")["canonical_digest"]),
            },
        ),
    )
    print(
        json.dumps(
            {
                "clock": clock,
                "compatibility_digest": compatibility["canonical_digest"],
                "lr_status": lr["status"],
                "selected_backend": backend["selected_backend"],
                "instantiation_status": instantiation["status"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
