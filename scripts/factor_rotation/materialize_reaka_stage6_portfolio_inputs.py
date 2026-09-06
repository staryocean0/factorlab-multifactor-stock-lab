#!/usr/bin/env python3
"""Materialize the 2009-only Stage 6 price and tradeability panel."""

# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportGeneralTypeIssues=false, reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false, reportMissingTypeArgument=false
# pyright: reportReturnType=false, reportIndexIssue=false
# pyright: reportOperatorIssue=false, reportCallIssue=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnusedCallResult=false
# pyright: reportPossiblyUnboundVariable=false, reportUnusedExpression=false
# pyright: reportImplicitRelativeImport=false
# pyright: reportAny=false, reportExplicitAny=false, reportMissingTypeStubs=false, reportMissingImports=false

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from factor_lab.factor_rotation.reaka_stage6_paper_faithful_freeze import (  # noqa: E402
    canonical_digest,
)
from factor_lab.factor_rotation.reaka_stage6_portfolio_execution import (  # noqa: E402
    CADENCE_INTERVALS,
    PORTFOLIO_SIZES,
    SLIPPAGE_MULTIPLIERS,
    eligibility_from_row,
    map_risk_warning_for_rules,
)

DATAHUB = Path("/home/starryocean/桌面/量化/unified_datahub")
DEFAULT_OUTPUT = ROOT / "output/factor-rotation/reaka_stage6_portfolio_inputs_v1_20260818"
DEFAULT_HANDOFF = (
    ROOT / "docs/ops/evidence/reaka_stage6_year2009_portfolio_external_handoff_20260818"
)
EXECUTION_CONTRACT = ROOT / "docs/ops/reaka_stage6_portfolio_execution@1.0.json"
EXPOSURE_LINEAGE = (
    ROOT / "output/factor-rotation/reaka_daily_exposures_full_a_v1_20260816/lineage_audit.json"
)
SCORE_PATH = (
    ROOT
    / "output/factor-rotation/reaka_stage6_annual_materials_v1_20260818/2009/transparent_scores.parquet"
)
OPEN_PATH = ROOT / "output/factor-rotation/reaka_daily_exposures_full_a_v1_20260816/daily/open.parquet"
CLOSE_PATH = ROOT / "output/factor-rotation/reaka_daily_exposures_full_a_v1_20260816/daily/close.parquet"
CALENDAR_PATH = (
    ROOT
    / "output/factor-rotation/reaka_product_driven_multiscale_stage12_v2_1_r1_20260816/prep/market_calendar.parquet"
)
METADATA_VERSION = "security_day_metadata_cn_a_stock_2009_official_final_v1_20260821"
EXECUTION_METADATA_VERSION = "security_day_metadata_cn_a_stock_2010_pool_assembled_v1_20260821"
_METADATA_CANDIDATES = (
    DATAHUB
    / "runtime/live/lake/security_day_metadata"
    / f"dataset_version={METADATA_VERSION}"
    / "security_day_metadata.parquet",
    DATAHUB
    / ".runtime/live/lake/security_day_metadata"
    / f"dataset_version={METADATA_VERSION}"
    / "security_day_metadata.parquet",
)
METADATA_PATH = next((path for path in _METADATA_CANDIDATES if path.exists()), _METADATA_CANDIDATES[-1])
METADATA_MANIFEST_PATH = METADATA_PATH.parent / "manifest.json"
EXECUTION_METADATA_PATH = (
    DATAHUB
    / ".runtime/live/lake/security_day_metadata"
    / f"dataset_version={EXECUTION_METADATA_VERSION}"
    / "security_day_metadata.parquet"
)
EXECUTION_METADATA_MANIFEST_PATH = EXECUTION_METADATA_PATH.parent / "manifest.json"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_rules() -> tuple[object, object, object, Path]:
    sys.path.insert(0, str(DATAHUB / "src"))
    from datahub.core.services.market_standards.cn_a_stock_rules import (  # type: ignore[import-not-found]
        RuleQuery,
        default_cn_a_stock_rule_profile_path,
        load_cn_a_stock_rule_profile,
        resolve_rule,
    )

    profile_path = default_cn_a_stock_rule_profile_path(DATAHUB)
    profile = load_cn_a_stock_rule_profile(profile_path)
    return profile, RuleQuery, resolve_rule, profile_path


def _source_record(*, repo: str, root: Path, path: Path, purpose: str) -> dict[str, object]:
    resolved = path.resolve()
    return {
        "repo": repo,
        "path": str(resolved.relative_to(root.resolve())),
        "sha256": _sha256_file(resolved),
        "bytes": int(resolved.stat().st_size),
        "purpose": purpose,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--handoff-root", type=Path, default=DEFAULT_HANDOFF)
    args = parser.parse_args(argv)
    output = args.output_root
    output.mkdir(parents=True, exist_ok=True)

    calendar = pd.to_datetime(
        pd.read_parquet(CALENDAR_PATH)["trading_day"]
    ).sort_values()
    calendar = calendar[(calendar >= "2008-12-01") & (calendar <= "2010-01-04")]
    open_px = pd.read_parquet(OPEN_PATH)
    close_px = pd.read_parquet(CLOSE_PATH)
    open_px.index = pd.to_datetime(open_px.index)
    close_px.index = pd.to_datetime(close_px.index)
    open_px = open_px.loc[open_px.index.isin(calendar)]
    close_px = close_px.loc[close_px.index.isin(calendar)]
    if (open_px.index >= "2010-01-05").any() or (close_px.index >= "2011-01-01").any():
        raise RuntimeError("stage6_portfolio_inputs_read_beyond_execution_window")

    metadata = pd.read_parquet(METADATA_PATH)
    metadata["trading_day"] = pd.to_datetime(metadata["trading_day"])
    metadata["symbol"] = metadata["symbol"].astype(str)
    metadata_2009 = metadata[
        (metadata["trading_day"] >= "2009-01-01")
        & (metadata["trading_day"] <= "2009-12-31")
    ]
    execution_metadata = pd.read_parquet(EXECUTION_METADATA_PATH)
    execution_metadata["trading_day"] = pd.to_datetime(execution_metadata["trading_day"])
    execution_metadata["symbol"] = execution_metadata["symbol"].astype(str)
    execution_metadata = execution_metadata.loc[
        execution_metadata["trading_day"] == pd.Timestamp("2010-01-04")
    ]
    if execution_metadata.empty:
        raise RuntimeError("stage6_portfolio_2010_01_04_execution_metadata_empty")
    # 2008-12 prices are used only to seed previous_tradable_close; they are not
    # research rows and are not 2010 scores.
    warmup_days = calendar[(calendar >= "2008-12-01") & (calendar < "2009-01-01")]
    metadata = pd.concat([metadata_2009, execution_metadata], ignore_index=True)

    profile, rule_query, resolve_rule, rule_profile_path = _load_rules()
    cache: dict[tuple[object, ...], dict[str, object]] = {}
    metadata = metadata.copy()
    metadata["risk_for_rules"] = metadata["risk_warning_state"].map(map_risk_warning_for_rules)
    unique_keys = metadata[["trading_day", "exchange", "board", "risk_for_rules", "listing_phase"]].drop_duplicates()
    for row in unique_keys.itertuples(index=False):
        day_ts = pd.Timestamp(row.trading_day)
        risk = str(row.risk_for_rules)
        key = (day_ts.date(), str(row.exchange), str(row.board), risk, str(row.listing_phase))
        query = rule_query(
            family="price_limit",
            on_date=date(day_ts.year, day_ts.month, day_ts.day),
            exchange=str(row.exchange),
            instrument_type="stock",
            board=str(row.board),
            risk_warning_state=None if risk == "unknown" else risk,
            listing_phase=str(row.listing_phase),
        )
        resolved = resolve_rule(profile, query)
        cache[key] = {
            "status": resolved.status,
            "rule_id": resolved.rule_id,
            "gap_id": resolved.gap_id,
            "params": dict(resolved.params),
            "detail": resolved.detail,
        }

    open_long = (
        open_px.stack(future_stack=True)
        .rename("open")
        .rename_axis(["trading_day", "symbol"])
        .reset_index()
    )
    close_long = (
        close_px.stack(future_stack=True)
        .rename("close")
        .rename_axis(["trading_day", "symbol"])
        .reset_index()
    )
    prices = open_long.merge(close_long, on=["trading_day", "symbol"], how="inner")
    prices["symbol"] = prices["symbol"].astype(str)
    prices["trading_day"] = pd.to_datetime(prices["trading_day"])
    prices = prices.sort_values(["symbol", "trading_day"], kind="mergesort")
    merged = prices.merge(
        metadata,
        on=["trading_day", "symbol"],
        how="inner",
    )
    merged = merged.sort_values(["symbol", "trading_day"], kind="mergesort")
    warmup_close = (
        close_px.loc[close_px.index.isin(warmup_days)]
        .replace([np.inf, -np.inf], np.nan)
    )
    seed = warmup_close.ffill().iloc[-1] if not warmup_close.empty else pd.Series(dtype=float)
    tradable_close = merged["close"].where(
        (merged["suspension_status"] == "not_suspended")
        & np.isfinite(merged["close"])
        & (merged["close"] > 0)
    )
    last_tradable = tradable_close.groupby(merged["symbol"]).ffill()
    shifted = last_tradable.groupby(merged["symbol"]).shift(1)
    seeded = merged["symbol"].map(seed)
    merged["previous_tradable_close"] = shifted.fillna(seeded)

    rows: list[dict[str, object]] = []
    for row in merged.itertuples(index=False):
        day_ts = pd.Timestamp(row.trading_day)
        risk = str(row.risk_for_rules)
        key = (day_ts.date(), str(row.exchange), str(row.board), risk, str(row.listing_phase))
        prev = None if pd.isna(row.previous_tradable_close) else float(row.previous_tradable_close)
        open_price = float(row.open)
        gate = eligibility_from_row(
            {"suspension_status": row.suspension_status},
            previous_tradable_close=prev,
            open_price=open_price if np.isfinite(open_price) else None,
            resolved=cache[key],
        )
        rows.append(
            {
                "trading_day": day_ts,
                "symbol": str(row.symbol),
                "exchange": row.exchange,
                "board": row.board,
                "listing_phase": row.listing_phase,
                "risk_warning_state": row.risk_warning_state,
                "historical_name": row.historical_name,
                "suspension_status": row.suspension_status,
                "open": open_price,
                "close": float(row.close),
                "previous_tradable_close": prev,
                "buy_ok": gate.buy_ok,
                "sell_ok": gate.sell_ok,
                "paused": gate.paused,
                "limit_up": gate.limit_up_price,
                "limit_down": gate.limit_down_price,
                "is_limit_up": gate.is_limit_up,
                "is_limit_down": gate.is_limit_down,
                "rule_status": gate.rule_status,
                "rule_id": gate.rule_id,
                "eligibility_reason": gate.reason,
            }
        )
    panel = pd.DataFrame(rows)
    panel_path = output / "price_tradeability_panel_2009.parquet"
    panel.to_parquet(panel_path, index=False)

    scores = pd.read_parquet(SCORE_PATH)
    score_years = set(pd.to_datetime(scores["decision_date"]).dt.year.unique().tolist())
    if score_years != {2009}:
        raise RuntimeError(f"stage6_score_years_not_only_2009:{sorted(score_years)}")

    exposure_lineage = json.loads(EXPOSURE_LINEAGE.read_text(encoding="utf-8"))
    raw_parent = dict(exposure_lineage.get("bar_parent") or {})
    if "raw_canonical" not in str(raw_parent.get("path") or ""):
        raise RuntimeError("stage6_portfolio_fill_parent_not_raw_canonical")
    metadata_manifest = json.loads(METADATA_MANIFEST_PATH.read_text(encoding="utf-8"))
    if metadata_manifest.get("dataset_version") != METADATA_VERSION:
        raise RuntimeError("stage6_portfolio_metadata_manifest_version_mismatch")
    if int(metadata_manifest.get("record_count") or 0) != int(len(metadata_2009)):
        raise RuntimeError("stage6_portfolio_metadata_manifest_row_count_mismatch")
    execution_metadata_manifest = json.loads(
        EXECUTION_METADATA_MANIFEST_PATH.read_text(encoding="utf-8")
    )
    if execution_metadata_manifest.get("dataset_version") != EXECUTION_METADATA_VERSION:
        raise RuntimeError("stage6_portfolio_execution_metadata_manifest_version_mismatch")

    source_records = [
        _source_record(
            repo="factor_lab",
            root=ROOT,
            path=EXECUTION_CONTRACT,
            purpose="frozen_portfolio_execution_contract",
        ),
        _source_record(
            repo="factor_lab",
            root=ROOT,
            path=Path(__file__),
            purpose="portfolio_input_materializer",
        ),
        _source_record(
            repo="factor_lab",
            root=ROOT,
            path=ROOT / "src/factor_lab/factor_rotation/reaka_stage6_portfolio_execution.py",
            purpose="portfolio_execution_engine",
        ),
        _source_record(
            repo="factor_lab",
            root=ROOT,
            path=ROOT / "scripts/factor_rotation/build_reaka_stage6_year2009_portfolio_materials.py",
            purpose="portfolio_material_builder",
        ),
        _source_record(
            repo="factor_lab",
            root=ROOT,
            path=ROOT / "scripts/factor_rotation/validate_reaka_stage6_portfolio_materials.py",
            purpose="portfolio_material_validator",
        ),
        _source_record(
            repo="factor_lab",
            root=ROOT,
            path=EXPOSURE_LINEAGE,
            purpose="raw_fill_lineage",
        ),
        _source_record(
            repo="unified_datahub",
            root=DATAHUB,
            path=METADATA_MANIFEST_PATH,
            purpose="official_2009_security_day_metadata_manifest",
        ),
        _source_record(
            repo="unified_datahub",
            root=DATAHUB,
            path=METADATA_PATH,
            purpose="official_2009_security_day_metadata",
        ),
        _source_record(
            repo="unified_datahub",
            root=DATAHUB,
            path=EXECUTION_METADATA_MANIFEST_PATH,
            purpose="2010_01_04_execution_only_security_day_metadata_manifest",
        ),
        _source_record(
            repo="unified_datahub",
            root=DATAHUB,
            path=EXECUTION_METADATA_PATH,
            purpose="2010_01_04_execution_only_security_day_metadata",
        ),
        _source_record(
            repo="unified_datahub",
            root=DATAHUB,
            path=rule_profile_path,
            purpose="effective_dated_cn_a_price_limit_rules",
        ),
    ]
    source_manifest = {
        "schema_id": "factorlab.reaka_stage6_portfolio_source_digest_manifest@2.0",
        "sources": source_records,
        "fill_price_view": "raw_canonical",
        "opened_research_years": [2009],
        "production_authority": False,
    }
    source_manifest["canonical_digest"] = canonical_digest(source_manifest)
    source_manifest_path = output / "source_digest_manifest.json"
    _write_json(source_manifest_path, source_manifest)

    usage = {
        "schema_id": "factorlab.reaka_stage6_portfolio_inputs_data_usage@1.0",
        "opened_year": 2009,
        "execution_calendar_window": "2008-12-01/2010-01-04",
        "score_years": [2009],
        "later_research_years_opened": [],
        "closed_2021_2026_rows_read": 0,
        "fresh_oos": False,
        "production_authority": False,
    }
    usage["canonical_digest"] = canonical_digest(usage)
    identity = {
        "schema_id": "factorlab.reaka_stage6_portfolio_input_identity@1.0",
        "score_path": str(SCORE_PATH),
        "score_sha256": _sha256_file(SCORE_PATH),
        "open_path": str(OPEN_PATH),
        "close_path": str(CLOSE_PATH),
        "open_sha256": _sha256_file(OPEN_PATH),
        "close_sha256": _sha256_file(CLOSE_PATH),
        "metadata_version": METADATA_VERSION,
        "metadata_manifest_sha256": _sha256_file(METADATA_MANIFEST_PATH),
        "metadata_sha256": _sha256_file(METADATA_PATH),
        "execution_metadata_version": EXECUTION_METADATA_VERSION,
        "execution_metadata_manifest_sha256": _sha256_file(
            EXECUTION_METADATA_MANIFEST_PATH
        ),
        "execution_metadata_sha256": _sha256_file(EXECUTION_METADATA_PATH),
        "execution_metadata_rows_2010_01_04": int(len(execution_metadata)),
        "fill_price_view": "raw_canonical",
        "raw_fill_parent_path": str(raw_parent.get("path") or ""),
        "raw_fill_parent_sha256": str(raw_parent.get("sha256") or ""),
        "execution_contract_path": str(EXECUTION_CONTRACT),
        "execution_contract_sha256": _sha256_file(EXECUTION_CONTRACT),
        "source_digest_manifest_sha256": _sha256_file(source_manifest_path),
        "panel_sha256": _sha256_file(panel_path),
        "panel_rows": int(len(panel)),
        "panel_symbols": int(panel["symbol"].nunique()) if not panel.empty else 0,
        "buy_ok_true": int(panel["buy_ok"].sum()) if not panel.empty else 0,
        "sell_ok_true": int(panel["sell_ok"].sum()) if not panel.empty else 0,
        "paused_true": int(panel["paused"].sum()) if not panel.empty else 0,
        "attempt_denominator": {
            "tasks": 12,
            "sizes": list(PORTFOLIO_SIZES),
            "slippage_multipliers": list(SLIPPAGE_MULTIPLIERS),
            "cadence_intervals": CADENCE_INTERVALS,
            "task_sequence_units": 36,
            "total_attempts": 324,
        },
        "stopping_rule": "all_324_parallel_attempts_then_stop_without_selection",
        "production_authority": False,
    }
    identity["canonical_digest"] = canonical_digest(identity)
    _write_json(output / "data_usage_declaration.json", usage)
    _write_json(output / "input_identity.json", identity)
    current_audit = {
        "schema_id": "factorlab.reaka_stage6_tradeability_source_audit@2.0",
        "audit_status": "resolved_official_metadata_rules_raw_prices",
        "year_in_scope": 2009,
        "metadata_version": METADATA_VERSION,
        "metadata_manifest_sha256": _sha256_file(METADATA_MANIFEST_PATH),
        "execution_metadata_version": EXECUTION_METADATA_VERSION,
        "execution_metadata_manifest_sha256": _sha256_file(
            EXECUTION_METADATA_MANIFEST_PATH
        ),
        "execution_metadata_rows_2010_01_04": int(len(execution_metadata)),
        "raw_fill_parent_path": str(raw_parent.get("path") or ""),
        "raw_fill_parent_sha256": str(raw_parent.get("sha256") or ""),
        "rule_profile_path": str(rule_profile_path),
        "rule_profile_sha256": _sha256_file(rule_profile_path),
        "derivation": (
            "buy_ok/sell_ok derive from 2009 official-final plus 2010-01-04 "
            "execution-only metadata, effective-dated price-limit rules, and raw "
            "previous-tradable-close/open prices"
        ),
        "panel_sha256": _sha256_file(panel_path),
        "later_research_years_opened": [],
        "closed_2021_2026_rows_read": 0,
        "portfolio_economics_permitted": True,
        "fresh_oos": False,
        "production_authority": False,
    }
    current_audit["canonical_digest"] = canonical_digest(current_audit)
    for target in (output, args.handoff_root):
        _write_json(target / "source_digest_manifest.json", source_manifest)
        _write_json(target / "data_usage_declaration.json", usage)
        _write_json(target / "input_identity.json", identity)
        _write_json(target / "tradeability_source_audit.json", current_audit)
    print(json.dumps({"panel_rows": int(len(panel)), "output": str(output)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
