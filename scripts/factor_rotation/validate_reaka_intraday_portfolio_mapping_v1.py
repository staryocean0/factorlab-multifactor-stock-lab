#!/usr/bin/env python3
# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportGeneralTypeIssues=false, reportOptionalMemberAccess=false
# pyright: reportUnusedCallResult=false, reportAny=false
"""Validate REAKA P7 portfolio-mapping infrastructure without opening account results."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import cast

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import (  # noqa: E402
    COMMON_ROOT_POLICY_ID,
    CONTRACT_DIGEST,
    VALIDATION_SCHEMA_ID,
    build_policy_grid,
    canonical_valid,
    compare_tree_bytes,
    contract_path,
    read_json,
    source_closure_for_module,
    validate_admission,
    validate_contract_payload,
    validate_input_manifest,
    validate_session_receipt,
    write_json,
)
from factor_lab.governance.canonicalization import canonical_digest  # noqa: E402


def _validate_canonical(path: Path, blockers: list[str]) -> dict[str, object]:
    payload = read_json(path)
    if not canonical_valid(payload):
        blockers.append(f"canonical_digest_mismatch:{path.relative_to(ROOT)}")
    return payload


def validate_package(
    *,
    admission_path: Path | None,
    formal_root: Path | None,
    isolated_root: Path | None,
    session_receipts: Sequence[Path],
    report_path: Path | None = None,
) -> dict[str, object]:
    blockers: list[str] = []
    contract = _validate_canonical(contract_path(ROOT), blockers)
    blockers.extend(validate_contract_payload(contract))
    if contract.get("canonical_digest") != CONTRACT_DIGEST:
        blockers.append("contract_digest_mismatch")
    policies = [policy.policy_id for policy in build_policy_grid()]
    if len(policies) != 24:
        blockers.append("policy_grid_count_invalid")
    if COMMON_ROOT_POLICY_ID not in policies:
        blockers.append("common_root_missing")
    current_closure = source_closure_for_module()
    if admission_path is not None:
        admission = _validate_canonical(admission_path, blockers)
        blockers.extend(validate_admission(admission))
        recorded = cast(Mapping[str, str], admission.get("source_digests", {}))
        if recorded != current_closure:
            blockers.append("admission_source_closure_drift")
        if int(admission.get("source_closure_file_count", -1)) != len(current_closure):
            blockers.append("admission_source_closure_count_invalid")
    if formal_root is not None and formal_root.exists():
        manifest_paths = sorted(formal_root.glob("input_manifest_*.json"))
        if len(manifest_paths) != 2:
            blockers.append("formal_input_manifest_count_invalid")
        for manifest_path in manifest_paths:
            formal_manifest = _validate_canonical(manifest_path, blockers)
            blockers.extend(validate_input_manifest(formal_manifest))
            closure_path = manifest_path.with_name(manifest_path.name.replace("input_manifest", "source_closure"))
            if closure_path.exists():
                closure = _validate_canonical(closure_path, blockers)
                recorded = cast(Mapping[str, str], closure.get("source_digests", {}))
                if recorded != current_closure:
                    blockers.append("formal_source_closure_drift")
    if isolated_root is not None and isolated_root.exists():
        manifest_paths = sorted(isolated_root.glob("input_manifest_*.json"))
        if len(manifest_paths) != 2:
            blockers.append("isolated_input_manifest_count_invalid")
        for manifest_path in manifest_paths:
            isolated_manifest = _validate_canonical(manifest_path, blockers)
            blockers.extend(validate_input_manifest(isolated_manifest))
            closure_path = manifest_path.with_name(manifest_path.name.replace("input_manifest", "source_closure"))
            if closure_path.exists():
                closure = _validate_canonical(closure_path, blockers)
                recorded = cast(Mapping[str, str], closure.get("source_digests", {}))
                if recorded != current_closure:
                    blockers.append("isolated_source_closure_drift")
    byte_identical = False
    mismatches: list[str] = []
    if formal_root is not None and isolated_root is not None and formal_root.exists() and isolated_root.exists():
        byte_identical, mismatches = compare_tree_bytes(formal_root, isolated_root)
        if not byte_identical:
            blockers.append(f"formal_isolated_not_byte_identical:{','.join(mismatches[:5])}")
    for receipt_path in session_receipts:
        receipt = _validate_canonical(receipt_path, blockers)
        blockers.extend(validate_session_receipt(receipt))
        if receipt.get("account_mapping_execution_allowed") is not True:
            blockers.append("session_account_execution_not_admitted")
    permissions = cast(Mapping[str, object], contract.get("current_permissions", {}))
    if permissions.get("account_mapping_execution_allowed") is not False:
        blockers.append("contract_account_execution_open")
    report = {
            "schema_id": VALIDATION_SCHEMA_ID,
            "status": "passed" if not blockers else "failed",
            "package_blockers": blockers,
            "contract_digest": CONTRACT_DIGEST,
            "policy_count": len(policies),
            "policy_ids": policies,
            "common_root_policy_id": COMMON_ROOT_POLICY_ID,
            "source_closure_file_count": len(current_closure),
            "formal_isolated_byte_identical": byte_identical,
            "formal_isolated_mismatches": mismatches[:20],
            "score_extension_execution_allowed": permissions.get("score_extension_execution_allowed"),
            "account_mapping_execution_allowed": permissions.get("account_mapping_execution_allowed"),
            "post_2020_read_allowed": permissions.get("post_2020_read_allowed"),
            "production_authority": permissions.get("production_authority"),
            "controller_acceptance_created": False,
            "next_legal_action": "controller_infrastructure_acceptance_only",
        }
    if report_path is not None:
        return write_json(report_path, report)
    report["canonical_digest"] = canonical_digest(report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admission", type=Path, default=None)
    parser.add_argument("--formal-root", type=Path, default=None)
    parser.add_argument("--isolated-root", type=Path, default=None)
    parser.add_argument("--session-receipt", action="append", default=[])
    parser.add_argument("--report-path", type=Path, default=None)
    args = parser.parse_args()
    report = validate_package(
        admission_path=args.admission,
        formal_root=args.formal_root,
        isolated_root=args.isolated_root,
        session_receipts=[Path(value) for value in args.session_receipt],
        report_path=args.report_path,
    )
    print(json.dumps({"status": report["status"], "blockers": report["package_blockers"]}, ensure_ascii=False, indent=2))
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
