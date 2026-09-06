#!/usr/bin/env python3
# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false, reportMissingImports=false
# pyright: reportMissingTypeStubs=false, reportOperatorIssue=false
# pyright: reportOptionalMemberAccess=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnknownVariableType=false
# pyright: reportUnusedCallResult=false, reportAny=false
"""Rebuild REAKA P7 market inputs while preserving frozen score bytes."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
for value in (ROOT, ROOT / "src"):
    if str(value) not in sys.path:
        sys.path.insert(0, str(value))

from scripts.factor_rotation.build_reaka_intraday_portfolio_mapping_inputs_v1 import (  # noqa: E402
    _attach_hfq_accounting,
    _materialize_raw_market_panel,
)
from scripts.factor_rotation.materialize_reaka_stage6_portfolio_inputs import (  # noqa: E402
    _load_rules,
)

from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import (  # noqa: E402
    CLOCK_SUFFIX,
    CLOCKS,
    CONTRACT_DIGEST,
    canonical_valid,
    file_digest,
    validate_market_panel,
    validate_score_panel,
    write_json,
)
from factor_lab.factor_rotation.reaka_stage6_portfolio_execution import (  # noqa: E402
    eligibility_from_row,
    map_risk_warning_for_rules,
)

CONTRACT_SCHEMA_ID = "factorlab.reaka_intraday_portfolio_mapping_market_rebuild@1.0"
CONTRACT_SCHEMA_IDS = {
    CONTRACT_SCHEMA_ID,
    "factorlab.reaka_intraday_portfolio_mapping_market_rebuild@1.1",
    "factorlab.reaka_intraday_portfolio_mapping_market_rebuild@1.2",
    "factorlab.reaka_intraday_portfolio_mapping_market_rebuild@1.3",
    "factorlab.reaka_intraday_portfolio_mapping_market_rebuild@1.4",
}
VALIDATION_SCHEMA_ID = "factorlab.reaka_intraday_portfolio_mapping_market_rebuild_validation@1.0"
DEFAULT_CONTRACT = ROOT / "docs/ops/reaka_intraday_portfolio_mapping_market_rebuild@1.4.json"
DATAHUB_ROOT = Path("/home/starryocean/桌面/量化/unified_datahub")
REPAIR_SYMBOL = "000638"
MINIMUM_YEAR = 2011
MAXIMUM_YEAR = 2020


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"market_rebuild_json_object_required:{path}")
    return payload


def _resolve(raw: str | Path) -> Path:
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def _verify_file(path: Path, expected_digest: str) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = _sha256_file(path)
    if actual != str(expected_digest):
        raise ValueError(f"market_rebuild_source_drift:{path}:{actual}:{expected_digest}")
    return {"sha256": actual, "bytes": int(path.stat().st_size)}


def _deep_merge(base: Mapping[str, Any], overrides: Mapping[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in overrides.items():
        current = merged.get(key)
        if isinstance(current, Mapping) and isinstance(value, Mapping):
            merged[key] = _deep_merge(current, value)
        else:
            merged[key] = value
    return merged


def load_rebuild_contract(path: Path) -> dict[str, Any]:
    payload = _read_json(path)
    schema_id = str(payload.get("schema_id") or "")
    if schema_id not in CONTRACT_SCHEMA_IDS:
        raise ValueError("market_rebuild_contract_schema_invalid")
    if not canonical_valid(payload):
        raise ValueError("market_rebuild_contract_digest_invalid")
    if schema_id != CONTRACT_SCHEMA_ID:
        binding = payload.get("base_contract") or {}
        base_path = _resolve(str(binding.get("path") or ""))
        _verify_file(base_path, str(binding.get("sha256") or ""))
        base = load_rebuild_contract(base_path)
        current = payload
        payload = _deep_merge(base, current.get("overrides") or {})
        payload.update(
            {
                "schema_id": schema_id,
                "status": current["status"],
                "canonical_digest": current["canonical_digest"],
                "base_contract": binding,
                "pre_result_incident": current.get("pre_result_incident"),
            }
        )
    if payload.get("status") != "result_free_DataHub_repair_bound_market_rebuild_authorized":
        raise ValueError("market_rebuild_contract_not_authorized")
    if payload.get("account_mapping_execution_allowed") is not False:
        raise ValueError("market_rebuild_contract_account_boundary_invalid")
    if payload.get("post_2020_read_allowed") is not False:
        raise ValueError("market_rebuild_contract_future_boundary_invalid")
    return payload


def _tree_root(contract: Mapping[str, Any], key: str, tree: str) -> Path:
    roots = contract["inputs"][key]
    if not isinstance(roots, Mapping) or tree not in roots:
        raise ValueError(f"market_rebuild_tree_root_missing:{key}:{tree}")
    return _resolve(str(roots[tree]))


def verify_contract_inputs(
    contract: Mapping[str, Any], *, tree: str
) -> dict[str, Any]:
    inputs = contract["inputs"]
    verified: dict[str, Any] = {}
    score_root = _tree_root(contract, "score_roots", tree)
    target_fill_root = _tree_root(contract, "target_fill_roots", tree)
    for clock in CLOCKS:
        suffix = CLOCK_SUFFIX[clock]
        for prefix, name in (
            ("score_panel", f"bounded_score_panel_{suffix}.parquet"),
            ("old_input_manifest", f"input_manifest_{suffix}.json"),
            ("old_source_closure", f"source_closure_{suffix}.json"),
        ):
            expected = inputs[f"{prefix}_digests"][clock]
            verified[f"{prefix}_{suffix}"] = _verify_file(score_root / name, expected)
    for name, expected in inputs["target_fill_digests"].items():
        verified[f"target_fill_{name}"] = _verify_file(target_fill_root / name, expected)
    for position, item in enumerate(inputs["daily_panels"]):
        verified[f"daily_panel_{position:02d}"] = _verify_file(
            _resolve(str(item["path"])), str(item["sha256"])
        )
    for key in (
        "datahub_repair_payload",
        "datahub_repair_bundle_manifest",
        "datahub_repair_validation",
        "raw_daily_bars",
        "market_cap",
        "adjustment_factors",
        "xdxr_events",
        "price_limit_rules",
    ):
        item = inputs[key]
        verified[key] = _verify_file(_resolve(str(item["path"])), str(item["sha256"]))
    for position, item in enumerate(contract["source_closure"]):
        verified[f"source_file_{position:02d}"] = _verify_file(
            _resolve(str(item["path"])), str(item["sha256"])
        )
    return verified


def _repair_tradeability_panel(
    *,
    metadata_path: Path,
    raw_bars_path: Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    metadata = pd.read_parquet(metadata_path)
    metadata["trading_day"] = pd.to_datetime(metadata["trading_day"], errors="raise").dt.normalize()
    metadata["symbol"] = metadata["symbol"].astype(str)
    if set(metadata["symbol"].unique()) != {REPAIR_SYMBOL}:
        raise ValueError("market_rebuild_metadata_symbol_scope_invalid")
    if metadata["trading_day"].dt.year.min() != MINIMUM_YEAR or metadata["trading_day"].dt.year.max() != MAXIMUM_YEAR:
        raise ValueError("market_rebuild_metadata_year_scope_invalid")
    bars = pd.read_parquet(
        raw_bars_path,
        columns=["trading_day", "symbol", "open", "close", "volume", "amount"],
        filters=[("symbol", "=", REPAIR_SYMBOL)],
    )
    bars["trading_day"] = pd.to_datetime(bars["trading_day"], errors="raise").dt.normalize()
    bars["symbol"] = bars["symbol"].astype(str)
    for column in ("open", "close", "volume", "amount"):
        bars[column] = pd.to_numeric(bars[column], errors="raise")
    bars = bars.loc[
        np.isfinite(bars["open"])
        & np.isfinite(bars["close"])
        & bars["open"].gt(0.0)
        & bars["close"].gt(0.0)
        & bars["volume"].gt(0.0)
        & bars["amount"].gt(0.0)
    ].sort_values(["symbol", "trading_day"], kind="mergesort")
    if bars.duplicated(["symbol", "trading_day"]).any():
        raise ValueError("market_rebuild_raw_bar_duplicate")
    bars["previous_tradable_close"] = bars.groupby("symbol", sort=False)["close"].shift(1)
    bars = bars.loc[
        bars["trading_day"].dt.year.between(MINIMUM_YEAR, MAXIMUM_YEAR, inclusive="both")
    ].copy()
    merged = metadata.merge(
        bars.loc[:, ["trading_day", "symbol", "open", "close", "previous_tradable_close"]],
        on=["trading_day", "symbol"],
        how="inner",
        validate="one_to_one",
    ).sort_values(["trading_day", "symbol"], kind="mergesort")
    if merged.empty:
        raise ValueError("market_rebuild_repair_panel_empty")
    if merged["suspension_status"].astype(str).eq("full_day").any():
        raise ValueError("market_rebuild_positive_bar_marked_full_day")
    merged["risk_for_rules"] = merged["risk_warning_state"].map(
        map_risk_warning_for_rules
    )
    profile, rule_query, resolve_rule, rule_profile_path = _load_rules()
    cache: dict[tuple[object, ...], dict[str, object]] = {}
    rows: list[dict[str, object]] = []
    for row in merged.itertuples(index=False):
        day = pd.Timestamp(row.trading_day)
        key = (
            day.date(),
            str(row.exchange),
            str(row.board),
            str(row.risk_for_rules),
            str(row.listing_phase),
        )
        if key not in cache:
            query = rule_query(
                family="price_limit",
                on_date=date(day.year, day.month, day.day),
                exchange=str(row.exchange),
                instrument_type="stock",
                board=str(row.board),
                risk_warning_state=(
                    None if str(row.risk_for_rules) == "unknown" else str(row.risk_for_rules)
                ),
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
        previous_close = float(row.previous_tradable_close)
        if not np.isfinite(previous_close) or previous_close <= 0.0:
            raise ValueError(f"market_rebuild_previous_close_invalid:{day.date()}")
        gate = eligibility_from_row(
            {"suspension_status": row.suspension_status},
            previous_tradable_close=previous_close,
            open_price=float(row.open),
            resolved=cache[key],
        )
        rows.append(
            {
                "trading_day": day,
                "symbol": REPAIR_SYMBOL,
                "exchange": str(row.exchange),
                "board": str(row.board),
                "listing_phase": str(row.listing_phase),
                "risk_warning_state": str(row.risk_warning_state),
                "historical_name": str(row.historical_name),
                "suspension_status": str(row.suspension_status),
                "open": float(row.open),
                "close": float(row.close),
                "previous_tradable_close": previous_close,
                "buy_ok": bool(gate.buy_ok),
                "sell_ok": bool(gate.sell_ok),
                "paused": bool(gate.paused),
                "limit_up": gate.limit_up_price,
                "limit_down": gate.limit_down_price,
                "is_limit_up": bool(gate.is_limit_up),
                "is_limit_down": bool(gate.is_limit_down),
                "rule_status": str(gate.rule_status),
                "rule_id": str(gate.rule_id),
                "eligibility_reason": str(gate.reason),
            }
        )
    panel = pd.DataFrame(rows).sort_values(
        ["trading_day", "symbol"], kind="mergesort"
    ).reset_index(drop=True)
    if panel.duplicated(["trading_day", "symbol"]).any():
        raise ValueError("market_rebuild_repair_panel_duplicate")
    report = {
        "row_count": int(len(panel)),
        "first_day": pd.Timestamp(panel["trading_day"].min()).date().isoformat(),
        "last_day": pd.Timestamp(panel["trading_day"].max()).date().isoformat(),
        "status_counts": {
            str(key): int(value)
            for key, value in panel["suspension_status"].value_counts().sort_index().items()
        },
        "paused_rows": int(panel["paused"].sum()),
        "unresolved_rule_rows": int(panel["rule_status"].ne("resolved").sum()),
        "rule_profile_digest": _sha256_file(rule_profile_path),
    }
    return panel, report


def _score_market_join_report(
    score: pd.DataFrame, market: pd.DataFrame, *, clock: str
) -> dict[str, Any]:
    left = score.loc[:, ["decision_date", "decision_clock", "symbol"]].copy()
    left["date"] = pd.to_datetime(left["decision_date"], errors="raise").dt.normalize()
    left["symbol"] = left["symbol"].astype(str)
    right = market.loc[:, ["date", "decision_clock", "symbol"]].copy()
    right["date"] = pd.to_datetime(right["date"], errors="raise").dt.normalize()
    right["symbol"] = right["symbol"].astype(str)
    if right.duplicated(["date", "decision_clock", "symbol"]).any():
        raise ValueError("market_rebuild_market_key_duplicate")
    joined = left.merge(
        right.assign(_market_present=True),
        on=["date", "decision_clock", "symbol"],
        how="left",
        validate="one_to_one",
    )
    missing = int(joined["_market_present"].isna().sum())
    target = joined.loc[joined["symbol"].eq(REPAIR_SYMBOL)]
    target_missing = int(target["_market_present"].isna().sum())
    if missing or len(target) != 143 or target_missing:
        raise ValueError(
            f"market_rebuild_score_market_join_invalid:{clock}:{missing}:{len(target)}:{target_missing}"
        )
    return {
        "score_row_count": int(len(score)),
        "joined_score_row_count": int(len(joined) - missing),
        "missing_score_market_coordinates": missing,
        "target_symbol": REPAIR_SYMBOL,
        "target_score_coordinate_count": int(len(target)),
        "target_joined_coordinate_count": int(len(target) - target_missing),
        "target_missing_coordinate_count": target_missing,
    }


def _attach_repair_symbol_hfq(
    raw_market: pd.DataFrame,
    *,
    adjustment_factors_path: Path,
    xdxr_events_path: Path,
    expected_category1_events: int,
    factor_source_label: str,
) -> pd.DataFrame:
    market = raw_market.copy()
    market["date"] = pd.to_datetime(market["date"], errors="raise").dt.normalize()
    market["symbol"] = market["symbol"].astype(str)
    if set(market["symbol"].unique()) != {REPAIR_SYMBOL}:
        raise ValueError("market_rebuild_target_hfq_symbol_scope_invalid")
    primary = pd.read_parquet(
        adjustment_factors_path,
        columns=["symbol", "instrument_type", "factor_type"],
        filters=[("symbol", "=", REPAIR_SYMBOL)],
    )
    if not primary.empty:
        raise ValueError("market_rebuild_target_hfq_primary_product_not_empty")
    events = pd.read_parquet(
        xdxr_events_path,
        columns=[
            "date",
            "code",
            "category",
            "fenhong",
            "peigujia",
            "songzhuangu",
            "peigu",
            "suogu",
        ],
        filters=[("code", "=", REPAIR_SYMBOL), ("category", "=", 1)],
    )
    events["date"] = pd.to_datetime(events["date"], errors="raise").dt.normalize()
    events = events.loc[
        events["date"].between(market["date"].min(), market["date"].max(), inclusive="both")
    ].sort_values("date", kind="mergesort")
    if len(events) != expected_category1_events:
        raise ValueError(
            f"market_rebuild_target_hfq_event_count_invalid:{len(events)}:{expected_category1_events}"
        )
    if events.duplicated(["date", "code"]).any():
        raise ValueError("market_rebuild_target_hfq_event_duplicate")
    if (pd.to_numeric(events["peigu"], errors="raise") != 0.0).any():
        raise ValueError("market_rebuild_target_hfq_peigu_not_preregistered")
    if (pd.to_numeric(events["suogu"], errors="raise") != 0.0).any():
        raise ValueError("market_rebuild_target_hfq_suogu_not_preregistered")
    market = market.sort_values("date", kind="mergesort").reset_index(drop=True)
    dates = market["date"].to_numpy(dtype="datetime64[ns]")
    factors = np.ones(len(market), dtype=np.float64)
    for event in events.itertuples(index=False):
        event_date = pd.Timestamp(event.date)
        event_rows = market.loc[market["date"].eq(event_date)]
        if event_rows.empty:
            event_rows = market.loc[market["date"].ge(event_date)].head(1)
        if len(event_rows) != 1:
            raise ValueError(
                f"market_rebuild_target_hfq_event_or_successor_row_missing:{event_date.date()}"
            )
        previous_close = float(event_rows.iloc[0]["previous_tradable_close"])
        if not np.isfinite(previous_close) or previous_close <= 0.0:
            raise ValueError(
                f"market_rebuild_target_hfq_previous_close_invalid:{event_date.date()}"
            )
        numerator = previous_close * (
            10.0 + float(event.songzhuangu) + float(event.peigu)
        )
        denominator = (
            10.0 * previous_close
            - float(event.fenhong)
            + float(event.peigu) * float(event.peigujia)
        )
        if denominator <= 0.0:
            raise ValueError(
                f"market_rebuild_target_hfq_theoretical_price_invalid:{event_date.date()}"
            )
        step = numerator / denominator
        if not np.isfinite(step) or step <= 0.0:
            raise ValueError(f"market_rebuild_target_hfq_step_invalid:{event_date.date()}")
        factors[dates >= event_date.to_datetime64()] *= step
    market["hfq_price_multiplier"] = factors
    market["hfq_factor_source"] = factor_source_label
    market["accounting_execution_price"] = (
        pd.to_numeric(market["raw_execution_price"], errors="coerce") * factors
    )
    market["accounting_close_price"] = (
        pd.to_numeric(market["raw_close_price"], errors="coerce") * factors
    )
    return market


def _attach_hfq_with_target_repair(
    raw_market: pd.DataFrame,
    *,
    adjustment_factors_path: Path,
    xdxr_events_path: Path,
    expected_category1_events: int,
    factor_source_label: str,
) -> pd.DataFrame:
    symbol = raw_market["symbol"].astype(str)
    ordinary_raw = raw_market.loc[~symbol.eq(REPAIR_SYMBOL)].copy()
    target_raw = raw_market.loc[symbol.eq(REPAIR_SYMBOL)].copy()
    if target_raw.empty:
        raise ValueError("market_rebuild_target_hfq_raw_market_empty")
    ordinary = _attach_hfq_accounting(
        ordinary_raw,
        adjustment_factors_path=adjustment_factors_path,
        xdxr_events_path=xdxr_events_path,
    )
    target = _attach_repair_symbol_hfq(
        target_raw,
        adjustment_factors_path=adjustment_factors_path,
        xdxr_events_path=xdxr_events_path,
        expected_category1_events=expected_category1_events,
        factor_source_label=factor_source_label,
    )
    return pd.concat([ordinary, target], ignore_index=True).sort_values(
        ["date", "symbol"], kind="mergesort"
    ).reset_index(drop=True)


def _source_digest_map(contract: Mapping[str, Any]) -> dict[str, str]:
    return {
        str(item["path"]): str(item["sha256"])
        for item in contract["source_closure"]
    }


def build_tree(
    *,
    contract_path: Path,
    tree: str,
    output_root: Path,
) -> dict[str, Any]:
    if output_root.exists():
        raise FileExistsError(f"market_rebuild_output_must_start_empty:{output_root}")
    contract = load_rebuild_contract(contract_path)
    verified = verify_contract_inputs(contract, tree=tree)
    inputs = contract["inputs"]
    score_root = _tree_root(contract, "score_roots", tree)
    target_fill_root = _tree_root(contract, "target_fill_roots", tree)
    daily_panel_paths = [_resolve(str(item["path"])) for item in inputs["daily_panels"]]
    metadata_path = _resolve(str(inputs["datahub_repair_payload"]["path"]))
    raw_bars_path = _resolve(str(inputs["raw_daily_bars"]["path"]))
    market_cap_path = _resolve(str(inputs["market_cap"]["path"]))
    adjustment_path = _resolve(str(inputs["adjustment_factors"]["path"]))
    xdxr_path = _resolve(str(inputs["xdxr_events"]["path"]))
    staging = output_root.parent / f".{output_root.name}.{uuid4().hex}.staging"
    staging.mkdir(parents=True, exist_ok=False)
    try:
        repair_panel, repair_report = _repair_tradeability_panel(
            metadata_path=metadata_path,
            raw_bars_path=raw_bars_path,
        )
        repair_panel_path = staging / "security_metadata_repair_tradeability_panel.parquet"
        repair_panel.to_parquet(repair_panel_path, index=False)
        clock_reports: dict[str, Any] = {}
        for clock in CLOCKS:
            suffix = CLOCK_SUFFIX[clock]
            source_score = score_root / f"bounded_score_panel_{suffix}.parquet"
            score_path = staging / source_score.name
            shutil.copyfile(source_score, score_path)
            if _sha256_file(score_path) != _sha256_file(source_score):
                raise ValueError(f"market_rebuild_score_copy_changed:{clock}")
            score = pd.read_parquet(score_path)
            validate_score_panel(score)
            raw_market = _materialize_raw_market_panel(
                score,
                clock=clock,
                target_fill_root=target_fill_root,
                daily_panel_paths=[*daily_panel_paths, repair_panel_path],
                market_cap_path=market_cap_path,
            )
            market = _attach_hfq_with_target_repair(
                raw_market,
                adjustment_factors_path=adjustment_path,
                xdxr_events_path=xdxr_path,
                expected_category1_events=int(
                    contract["target_hfq_repair"]["expected_category1_events_2011_2020"]
                ),
                factor_source_label=str(
                    contract["target_hfq_repair"]["factor_source_label"]
                ),
            )
            market = market.loc[
                market["decision_clock"].astype(str).eq(clock)
                & pd.to_datetime(market["date"], errors="raise").dt.year.le(MAXIMUM_YEAR)
            ].sort_values(["date", "symbol"], kind="mergesort").reset_index(drop=True)
            validate_market_panel(market)
            if pd.to_datetime(market["date"], errors="raise").dt.year.gt(MAXIMUM_YEAR).any():
                raise ValueError("market_rebuild_post_2020_market_row")
            join_report = _score_market_join_report(score, market, clock=clock)
            market_path = staging / f"daily_market_panel_{suffix}.parquet"
            market.to_parquet(market_path, index=False)
            old_manifest = _read_json(score_root / f"input_manifest_{suffix}.json")
            old_manifest.pop("canonical_digest", None)
            old_manifest.update(
                {
                    "panel_digest": file_digest(score_path),
                    "market_panel_digest": file_digest(market_path),
                    "market_rebuild_contract_digest": contract["canonical_digest"],
                    "score_panel_reused_byte_identical": True,
                    "datahub_repair_payload_digest": file_digest(metadata_path),
                    "datahub_repair_validation_digest": file_digest(
                        _resolve(str(inputs["datahub_repair_validation"]["path"]))
                    ),
                    "repair_tradeability_panel_digest": file_digest(repair_panel_path),
                    "hfq_factor_source_counts": {
                        str(key): int(value)
                        for key, value in market["hfq_factor_source"]
                        .value_counts(dropna=False)
                        .sort_index()
                        .items()
                    },
                    "raw_market_source_digests": {
                        "target_fill_manifest": file_digest(target_fill_root / "manifest.json"),
                        "daily_panels": {
                            f"{path.name}#{position}": file_digest(path)
                            for position, path in enumerate(daily_panel_paths)
                        },
                        "security_metadata_repair_tradeability_panel": file_digest(
                            repair_panel_path
                        ),
                        "market_cap": file_digest(market_cap_path),
                    },
                    "market_rebuild_source_digests": _source_digest_map(contract),
                    "score_market_join": join_report,
                    "account_mapping_execution_allowed": False,
                    "annual_session_execution_allowed": False,
                    "production_authority": False,
                }
            )
            manifest = write_json(staging / f"input_manifest_{suffix}.json", old_manifest)
            closure = write_json(
                staging / f"source_closure_{suffix}.json",
                {
                    "schema_id": (
                        "factorlab.reaka_intraday_portfolio_mapping_market_rebuild_source_closure@1.0"
                    ),
                    "contract_digest": CONTRACT_DIGEST,
                    "market_rebuild_contract_digest": contract["canonical_digest"],
                    "tree_neutral": True,
                    "decision_clock": clock,
                    "source_digests": _source_digest_map(contract),
                    "verified_input_count": len(verified),
                    "input_manifest_digest": manifest["canonical_digest"],
                    "account_mapping_execution_allowed": False,
                    "production_authority": False,
                },
            )
            clock_reports[clock] = {
                "score_panel_digest": file_digest(score_path),
                "market_panel_digest": file_digest(market_path),
                "input_manifest_digest": manifest["canonical_digest"],
                "source_closure_digest": closure["canonical_digest"],
                "market_row_count": int(len(market)),
                "target_market_row_count": int(market["symbol"].astype(str).eq(REPAIR_SYMBOL).sum()),
                "score_market_join": join_report,
                "accounting_identity_max_abs_error": float(
                    np.nanmax(
                        np.abs(
                            pd.to_numeric(market["accounting_execution_price"], errors="raise")
                            - pd.to_numeric(market["raw_execution_price"], errors="raise")
                            * pd.to_numeric(market["hfq_price_multiplier"], errors="raise")
                        )
                    )
                ),
            }
        validation = write_json(
            staging / "validation_report.json",
            {
                "schema_id": VALIDATION_SCHEMA_ID,
                "status": "market_rebuild_passed_account_execution_closed",
                "contract_digest": contract["canonical_digest"],
                "repair_panel": repair_report,
                "clock_reports": clock_reports,
                "formal_isolated_byte_identity_pending": True,
                "score_training_or_checkpoint_read": False,
                "score_panel_bytes_changed": False,
                "post_2020_rows": 0,
                "account_mapping_execution_allowed": False,
                "annual_session_execution_allowed": False,
                "production_authority": False,
            },
        )
        write_json(
            staging / "tree_manifest.json",
            {
                "schema_id": "factorlab.reaka_intraday_portfolio_mapping_market_rebuild_tree@1.0",
                "contract_digest": contract["canonical_digest"],
                "tree_neutral": True,
                "files": {
                    path.name: file_digest(path)
                    for path in sorted(staging.iterdir())
                    if path.is_file()
                },
                "validation_digest": validation["canonical_digest"],
                "account_mapping_execution_allowed": False,
                "production_authority": False,
            },
        )
        output_root.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, output_root)
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return _read_json(output_root / "validation_report.json")


def compare_trees(formal: Path, isolated: Path) -> dict[str, Any]:
    formal_files = {
        path.name: path.read_bytes() for path in sorted(formal.iterdir()) if path.is_file()
    }
    isolated_files = {
        path.name: path.read_bytes() for path in sorted(isolated.iterdir()) if path.is_file()
    }
    changed = sorted(
        name
        for name in set(formal_files) | set(isolated_files)
        if formal_files.get(name) != isolated_files.get(name)
    )
    if changed:
        raise ValueError("market_rebuild_formal_isolated_drift:" + ",".join(changed))
    return {
        "status": "passed",
        "byte_identical": True,
        "file_count": len(formal_files),
        "file_digests": {
            name: "sha256:" + hashlib.sha256(payload).hexdigest()
            for name, payload in formal_files.items()
        },
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--tree", choices=("formal", "isolated"), required=True)
    build.add_argument("--output-root", type=Path, required=True)
    verify = sub.add_parser("verify")
    verify.add_argument("--formal", type=Path, required=True)
    verify.add_argument("--isolated", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "build":
        result = build_tree(
            contract_path=args.contract,
            tree=args.tree,
            output_root=args.output_root,
        )
    elif args.command == "verify":
        result = compare_trees(args.formal, args.isolated)
    else:  # pragma: no cover
        raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
