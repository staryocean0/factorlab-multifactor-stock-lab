#!/usr/bin/env python3
# pyright: reportAny=false, reportArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false, reportMissingTypeStubs=false
# pyright: reportUnusedCallResult=false, reportIndexIssue=false
"""Execute one explicit REAKA P7 annual portfolio-mapping session."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import (  # noqa: E402
    ANNUAL_YEARS,
    CLOCK_SUFFIX,
    CLOCKS,
    COMMON_ROOT_POLICY_ID,
    CONTRACT_DIGEST,
    SESSION_SCHEMA_ID,
    SLIPPAGE_MULTIPLIERS,
    build_policy_grid,
    canonical_valid,
    file_digest,
    load_contract,
    policy_by_id,
    read_json,
    run_policy_family,
    source_closure_for_module,
    validate_admission,
    validate_market_panel,
    validate_score_panel,
    validate_session_receipt,
    validate_year_request,
    write_json,
)
from factor_lab.governance.canonicalization import canonical_digest  # noqa: E402


def _load_inputs(input_root: Path) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, str]]:
    score_parts: list[pd.DataFrame] = []
    market_parts: list[pd.DataFrame] = []
    digests: dict[str, str] = {}
    for clock in CLOCKS:
        suffix = CLOCK_SUFFIX[clock]
        score_path = input_root / f"bounded_score_panel_{suffix}.parquet"
        market_path = input_root / f"daily_market_panel_{suffix}.parquet"
        manifest_path = input_root / f"input_manifest_{suffix}.json"
        for path in (score_path, market_path, manifest_path):
            if not path.is_file():
                raise FileNotFoundError(f"portfolio_mapping_session_input_missing:{path.name}")
            digests[path.name] = file_digest(path)
        manifest = read_json(manifest_path)
        if not canonical_valid(manifest) or manifest.get("contract_digest") != CONTRACT_DIGEST:
            raise ValueError(f"portfolio_mapping_session_manifest_invalid:{suffix}")
        if manifest.get("panel_digest") != digests[score_path.name]:
            raise ValueError(f"portfolio_mapping_session_score_digest_invalid:{suffix}")
        if manifest.get("market_panel_digest") != digests[market_path.name]:
            raise ValueError(f"portfolio_mapping_session_market_digest_invalid:{suffix}")
        score = pd.read_parquet(score_path)
        market = pd.read_parquet(market_path)
        validate_score_panel(score)
        validate_market_panel(market)
        score_parts.append(score)
        market_parts.append(market)
    scores = pd.concat(score_parts, ignore_index=True).sort_values(
        ["decision_date", "decision_clock", "symbol"], kind="mergesort"
    ).reset_index(drop=True)
    market = pd.concat(market_parts, ignore_index=True).sort_values(
        ["date", "decision_clock", "symbol"], kind="mergesort"
    ).reset_index(drop=True)
    return scores, market, digests


def _write_frame(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix == ".csv":
        frame.to_csv(path, index=False, lineterminator="\n")
    else:
        frame.to_parquet(path, index=False)


def prepare_session(
    *,
    year: int,
    admission: dict[str, object],
    prior_receipt_path: Path | None,
    blind_policy_id: str,
    input_root: Path,
    output_root: Path,
) -> dict[str, object]:
    if year not in ANNUAL_YEARS:
        raise ValueError("portfolio_mapping_year_out_of_range")
    admission_blockers = validate_admission(admission, required_phase="account_execution")
    if admission_blockers:
        raise ValueError("portfolio_mapping_account_admission_invalid:" + ",".join(admission_blockers))
    prior_receipt = read_json(prior_receipt_path) if prior_receipt_path is not None else None
    blockers = validate_year_request(year=year, prior_receipt=prior_receipt)
    if blockers:
        raise ValueError("portfolio_mapping_year_chain_invalid:" + ",".join(blockers))
    if year == 2009 and blind_policy_id != COMMON_ROOT_POLICY_ID:
        raise ValueError("portfolio_mapping_2009_blind_policy_not_common_root")
    if prior_receipt is not None:
        if not canonical_valid(prior_receipt):
            raise ValueError("portfolio_mapping_prior_receipt_digest_invalid")
        if blind_policy_id != prior_receipt.get("selected_policy_id"):
            raise ValueError("portfolio_mapping_blind_policy_not_prior_snapshot")
    _ = policy_by_id(blind_policy_id)
    contract = load_contract(ROOT)
    scores, market, input_digests = _load_inputs(input_root)
    family = run_policy_family(scores=scores, market=market, end_year=year)
    output_root.mkdir(parents=True, exist_ok=True)
    output_files = {
        "metrics.csv": family["metrics"],
        "annual_metrics.csv": family["annual"],
        "quarterly_metrics.csv": family["quarterly"],
        "policy_gates.csv": family["gates"],
        "portfolio_daily.parquet": family["daily"],
        "holdings.parquet": family["holdings"],
        "trades.parquet": family["trades"],
        "events.parquet": family["events"],
    }
    output_digests: dict[str, str] = {}
    for filename, value in output_files.items():
        frame = value if isinstance(value, pd.DataFrame) else pd.DataFrame()
        path = output_root / filename
        _write_frame(path, frame)
        output_digests[filename] = file_digest(path)
    selected_policy_id = str(family["selected_policy_id"])
    selected_policy = policy_by_id(selected_policy_id)
    selected_policy_digest = canonical_digest(
        {
            "policy_id": selected_policy.policy_id,
            "top_n": selected_policy.top_n,
            "weighting": selected_policy.weighting,
            "buy_unavailable": selected_policy.buy_unavailable,
            "size_concentration": selected_policy.size_concentration,
        }
    )
    session_scores = scores.loc[pd.to_datetime(scores["decision_date"]).dt.year.eq(year)]
    result_state = "opportunity_absent" if session_scores.empty else "consumed_history_account_mapping_completed"
    receipt = write_json(
        output_root / "session_receipt.json",
        {
            "schema_id": SESSION_SCHEMA_ID,
            "status": result_state,
            "contract_digest": CONTRACT_DIGEST,
            "admission_digest": admission["canonical_digest"],
            "session_year": year,
            "prior_session_year": None if year == 2009 else year - 1,
            "prior_receipt_digest": None if prior_receipt is None else prior_receipt["canonical_digest"],
            "prior_policy_digest": None if prior_receipt is None else prior_receipt["selected_policy_digest"],
            "blind_prior_policy_id": blind_policy_id,
            "common_root_policy_id": COMMON_ROOT_POLICY_ID,
            "selected_policy_id": selected_policy_id,
            "selected_policy_digest": selected_policy_digest,
            "eligible_policy_ids": list(family["eligible_policy_ids"]),
            "clock_nomination": family["clock_nomination"],
            "policy_count": len(build_policy_grid()),
            "attempt_count": int(family["attempt_count"]),
            "decision_clocks": list(CLOCKS),
            "slippage_multipliers": list(SLIPPAGE_MULTIPLIERS),
            "input_digests": input_digests,
            "output_digests": output_digests,
            "annual_gate": contract["whole_policy_selection"]["annual_gate"],
            "quarterly_gate": contract["whole_policy_selection"]["quarterly_gate"],
            "economics_gate": contract["whole_policy_selection"]["economics_gate_each_clock"],
            "source_digests": source_closure_for_module(),
            "account_mapping_execution_allowed": True,
            "batch_all_year_execution_allowed": False,
            "controller_manual_year_review_required": True,
            "fresh_oos": False,
            "post_2020_rows_read": 0,
            "production_authority": False,
        },
    )
    session_blockers = validate_session_receipt(receipt)
    if session_blockers:
        raise ValueError("portfolio_mapping_session_invalid:" + ",".join(session_blockers))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", required=True, type=int)
    parser.add_argument("--admission", required=True, type=Path)
    parser.add_argument("--prior-receipt", type=Path, default=None)
    parser.add_argument("--blind-policy-id", default=COMMON_ROOT_POLICY_ID)
    parser.add_argument("--input-root", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    args = parser.parse_args()
    if "--years" in sys.argv or "--batch" in sys.argv:
        raise SystemExit("batch_all_year_execution_forbidden")
    admission = read_json(args.admission)
    receipt = prepare_session(
        year=args.year,
        admission=admission,
        prior_receipt_path=args.prior_receipt,
        blind_policy_id=args.blind_policy_id,
        input_root=args.input_root,
        output_root=args.output_root,
    )
    print(json.dumps({"year": args.year, "receipt_digest": receipt["canonical_digest"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
