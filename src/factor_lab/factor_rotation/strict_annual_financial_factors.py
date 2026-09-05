# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false, reportReturnType=false
# pyright: reportAny=false, reportImplicitStringConcatenation=false
# pyright: reportMissingTypeStubs=false, reportUnusedCallResult=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Strict annual first-release financial factors for single-stock research.

The module is the FactorLab side of the annual-large-cap DataHub contract.  It
does not select a DataHub version and it never falls back to a latest or
revised statement.  Callers bind to a fixed DataHub-certified product and
pass its annual first-release rows plus a causally materialized monthly
market-cap panel here.  DataHub certification is the upstream authority;
FactorLab does not repeat PDF extraction or locator replay.

Quarter-dependent legacy identities remain registered, but they are not
silently redefined from annual observations.  The two historical cash-flow
quality names are one economic formula and therefore contribute one model
column only.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final, cast

import numpy as np
import pandas as pd

from factor_lab.governance.canonicalization import canonical_digest

ANNUAL_COMPATIBLE_FINANCIAL_FACTOR_IDS: Final[tuple[str, ...]] = (
    "accruals_lag1",
    "asset_turnover_lag1",
    "assets_growth_yoy",
    "book_to_price_lag1",
    "cash_flow_roe_lag1",
    "cash_flow_to_assets_lag1",
    "cash_flow_yield_lag1",
    "cashflow_to_debt_lag1",
    "debt_to_equity_lag1",
    "earnings_quality_lag1",
    "earnings_yield_lag1",
    "equity_growth_yoy",
    "equity_turnover_lag1",
    "fundamental_quality_lag1",
    "net_profit_growth_yoy",
    "net_profit_to_debt_lag1",
    "operating_margin_lag1",
    "profit_margin_lag1",
    "roa_lag1",
    "roic_lag1",
    "sales_to_price_lag1",
)

ANNUAL_INCOMPATIBLE_FINANCIAL_FACTOR_IDS: Final[tuple[str, ...]] = (
    "asset_turnover_stability_lag1",
    "earnings_consistency_lag1",
    "margin_acceleration_lag1",
    "revenue_trend_3q_lag1",
    "roe_improvement_count_lag1",
)

ANNUAL_FINANCIAL_ALIAS_TO_CANONICAL: Final[dict[str, str]] = {
    "cash_flow_quality_lag1": "earnings_quality_lag1",
}

REQUIRED_ANNUAL_LINE_ITEM_IDS: Final[tuple[str, ...]] = (
    "net_profit",
    "operating_cashflow_net",
    "operating_profit",
    "revenue",
    "total_assets",
    "total_equity",
    "total_liabilities",
)

NORMALIZED_ANNUAL_VALUE_COLUMN: Final[str] = "derived_amount_cny_decimal"
ANNUAL_STALENESS_POLICY: Final[str] = (
    "latest_visible_report_must_be_at_least_previous_calendar_year_after_april_30_else_previous_two_calendar_years"
)

_VALUE_FACTOR_IDS: Final[frozenset[str]] = frozenset(
    {
        "book_to_price_lag1",
        "cash_flow_yield_lag1",
        "earnings_yield_lag1",
        "sales_to_price_lag1",
    }
)

_GROWTH_FACTOR_IDS: Final[frozenset[str]] = frozenset(
    {
        "assets_growth_yoy",
        "equity_growth_yoy",
        "net_profit_growth_yoy",
    }
)


def build_annual_financial_factor_disposition_contract() -> dict[str, object]:
    """Return the frozen annual/deferred/alias census for the 27 identities."""

    formulas = _formula_contract()
    rows: list[dict[str, object]] = []
    for factor_id in ANNUAL_COMPATIBLE_FINANCIAL_FACTOR_IDS:
        if factor_id == "roic_lag1":
            reason = "strict_annual_semantic_correction_to_pre_tax_operating_roic_proxy_distinct_from_net_profit_roe"
            semantic_status = "strict_annual_semantic_correction"
            historical_formula_transferable = False
            historical_prior_inheritance_allowed = False
        elif factor_id == "operating_margin_lag1":
            reason = "legacy_cash_flow_operating_margin_proxy_retained_for_frozen_input_continuity"
            semantic_status = "legacy_cash_flow_proxy_retained"
            historical_formula_transferable = True
            historical_prior_inheritance_allowed = True
        else:
            reason = "formula_is_well_defined_on_consecutive_annual_first_release_facts"
            semantic_status = "historical_formula_retained"
            historical_formula_transferable = True
            historical_prior_inheritance_allowed = True
        rows.append(
            {
                "factor_id": factor_id,
                "disposition": "executable_annual_first_release",
                "model_column_id": factor_id,
                "formula": formulas[factor_id],
                "reason": reason,
                "semantic_status": semantic_status,
                "historical_formula_transferable": historical_formula_transferable,
                "historical_prior_inheritance_allowed": (historical_prior_inheritance_allowed),
            }
        )
    for alias, canonical in sorted(ANNUAL_FINANCIAL_ALIAS_TO_CANONICAL.items()):
        rows.append(
            {
                "factor_id": alias,
                "disposition": "alias_deduplicated",
                "model_column_id": canonical,
                "reason": "same_operating_cashflow_over_net_profit_formula_one_vote_only",
            }
        )
    for factor_id in ANNUAL_INCOMPATIBLE_FINANCIAL_FACTOR_IDS:
        rows.append(
            {
                "factor_id": factor_id,
                "disposition": "deferred_quarterly_cadence_required",
                "model_column_id": None,
                "reason": "annual_only_input_would_change_the_registered_quarterly_formula",
            }
        )
    rows.sort(key=lambda row: str(row["factor_id"]))
    payload: dict[str, object] = {
        "schema_id": "factorlab.strict_annual_financial_factor_disposition.v1",
        "registered_financial_identity_count": len(rows),
        "executable_unique_model_column_count": len(ANNUAL_COMPATIBLE_FINANCIAL_FACTOR_IDS),
        "executable_unique_formula_count": len(set(formulas.values())),
        "strict_annual_semantic_correction_count": 1,
        "strict_annual_semantic_correction_factor_ids": ["roic_lag1"],
        "alias_deduplicated_count": len(ANNUAL_FINANCIAL_ALIAS_TO_CANONICAL),
        "quarterly_cadence_deferred_count": len(ANNUAL_INCOMPATIBLE_FINANCIAL_FACTOR_IDS),
        "rows": rows,
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    validate_annual_financial_factor_disposition_contract(payload)
    return payload


def annual_financial_formula_contract_digest() -> str:
    """Return the canonical digest of the active strict-annual formulas."""

    return canonical_digest(_formula_contract())


def annual_financial_materialization_contract_digest() -> str:
    """Bind formulas to consumer semantics without re-auditing DataHub truth."""

    return canonical_digest(
        {
            "schema_id": "factorlab.strict_annual_financial_materialization_contract.v2",
            "formula_contract_digest": annual_financial_formula_contract_digest(),
            "observation_value_field": NORMALIZED_ANNUAL_VALUE_COLUMN,
            "observation_value_semantics": "datahub_governed_amount_in_cny",
            "first_release_authority": "datahub_product_certification",
            "annual_staleness_policy": ANNUAL_STALENESS_POLICY,
        }
    )


def validate_annual_financial_factor_disposition_contract(
    payload: Mapping[str, object],
) -> None:
    """Reject identity loss, cadence redefinition, or duplicate model votes."""

    rows = payload.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, Mapping) for row in rows):
        raise ValueError("annual_financial_disposition_rows_required")
    typed_rows = cast(list[Mapping[str, object]], rows)
    if len(typed_rows) != 27 or payload.get("registered_financial_identity_count") != 27:
        raise ValueError("annual_financial_disposition_requires_27_identities")
    ids = [str(row.get("factor_id", "")) for row in typed_rows]
    if "" in ids or len(ids) != len(set(ids)):
        raise ValueError("annual_financial_disposition_ids_must_be_unique")
    expected_ids = set(ANNUAL_COMPATIBLE_FINANCIAL_FACTOR_IDS)
    expected_ids.update(ANNUAL_INCOMPATIBLE_FINANCIAL_FACTOR_IDS)
    expected_ids.update(ANNUAL_FINANCIAL_ALIAS_TO_CANONICAL)
    if set(ids) != expected_ids:
        raise ValueError("annual_financial_disposition_identity_set_changed")
    executable_columns = [
        str(row.get("model_column_id", "")) for row in typed_rows if row.get("disposition") == "executable_annual_first_release"
    ]
    if set(executable_columns) != set(ANNUAL_COMPATIBLE_FINANCIAL_FACTOR_IDS):
        raise ValueError("annual_financial_executable_columns_changed")
    if len(executable_columns) != len(set(executable_columns)):
        raise ValueError("annual_financial_duplicate_model_vote")
    formula_contract = _formula_contract()
    executable_formulas = {
        str(row.get("model_column_id", "")): str(row.get("formula", ""))
        for row in typed_rows
        if row.get("disposition") == "executable_annual_first_release"
    }
    if executable_formulas != formula_contract:
        raise ValueError("annual_financial_executable_formula_contract_changed")
    if len(set(executable_formulas.values())) != len(ANNUAL_COMPATIBLE_FINANCIAL_FACTOR_IDS) or payload.get(
        "executable_unique_formula_count"
    ) != len(ANNUAL_COMPATIBLE_FINANCIAL_FACTOR_IDS):
        raise ValueError("annual_financial_duplicate_executable_formula")
    semantic_corrections = [
        str(row.get("factor_id", "")) for row in typed_rows if row.get("semantic_status") == "strict_annual_semantic_correction"
    ]
    if (
        semantic_corrections != ["roic_lag1"]
        or payload.get("strict_annual_semantic_correction_count") != 1
        or payload.get("strict_annual_semantic_correction_factor_ids") != ["roic_lag1"]
    ):
        raise ValueError("annual_financial_semantic_correction_census_changed")
    roic_rows = [row for row in typed_rows if row.get("factor_id") == "roic_lag1"]
    if (
        len(roic_rows) != 1
        or roic_rows[0].get("historical_formula_transferable") is not False
        or roic_rows[0].get("historical_prior_inheritance_allowed") is not False
    ):
        raise ValueError("annual_financial_roic_historical_prior_must_not_transfer")
    if payload.get("production_authority") is not False:
        raise ValueError("annual_financial_disposition_cannot_grant_authority")
    expected_digest = canonical_digest({key: value for key, value in payload.items() if key != "canonical_digest"})
    if payload.get("canonical_digest") != expected_digest:
        raise ValueError("annual_financial_disposition_digest_mismatch")


def materialize_strict_annual_financial_factors(
    *,
    observations: pd.DataFrame,
    monthly_market_cap: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Materialize 21 unique annual factors at governed monthly decisions.

    ``monthly_market_cap`` defines the admitted stock/date surface.  Missing
    share or price evidence therefore remains an honest exclusion upstream;
    this function never invents a row.  All joins use ``available_at <
    decision_as_of`` and all ratios preserve non-finite values as missing.
    """

    statement_events, statement_audit = _statement_factor_events(observations)
    decisions = _validated_monthly_market_cap(monthly_market_cap)
    merged_parts: list[pd.DataFrame] = []
    symbol_intersection_found = False
    for symbol, decision_group in decisions.groupby("symbol", sort=True):
        event_group = statement_events.loc[statement_events["symbol"].eq(symbol)]
        if event_group.empty:
            continue
        symbol_intersection_found = True
        merged = _latest_visible_statement_rows(
            decisions=decision_group,
            statement_events=event_group,
        )
        if not merged.empty:
            merged_parts.append(merged)
    if not merged_parts:
        if symbol_intersection_found:
            raise ValueError("strict_annual_financial_no_visible_statement_rows")
        raise ValueError("strict_annual_financial_no_statement_decision_intersection")
    merged = pd.concat(merged_parts, ignore_index=True)
    merged = merged.dropna(subset=["statement_available_at", "report_period_end"])
    if merged.empty:
        raise ValueError("strict_annual_financial_no_visible_statement_rows")

    factor_values = _decision_factor_values(merged)
    rows: list[pd.DataFrame] = []
    for factor_id in ANNUAL_COMPATIBLE_FINANCIAL_FACTOR_IDS:
        values = factor_values[factor_id].replace([np.inf, -np.inf], np.nan)
        if factor_id in _VALUE_FACTOR_IDS:
            available_at = merged[["statement_available_at", "market_cap_available_at"]].max(axis=1)
        elif factor_id in _GROWTH_FACTOR_IDS:
            available_at = merged[["statement_available_at", "previous_statement_available_at"]].max(axis=1)
        else:
            available_at = merged["statement_available_at"]
        valid = values.notna() & available_at.notna() & available_at.lt(merged["decision_as_of"])
        if not bool(valid.any()):
            continue
        rows.append(
            pd.DataFrame(
                {
                    "date": merged.loc[valid, "date"].to_numpy(),
                    "decision_as_of": merged.loc[valid, "decision_as_of"].to_numpy(),
                    "symbol": merged.loc[valid, "symbol"].to_numpy(),
                    "factor_id": factor_id,
                    "factor_value": values.loc[valid].astype("float64").to_numpy(),
                    "available_at": available_at.loc[valid].to_numpy(),
                    "report_period": merged.loc[valid, "report_period_end"].to_numpy(),
                }
            )
        )
    if not rows:
        raise ValueError("strict_annual_financial_all_factor_values_missing")
    result = pd.concat(rows, ignore_index=True).sort_values(["date", "symbol", "factor_id"], kind="stable")
    result = result.reset_index(drop=True)
    if result.duplicated(["date", "symbol", "factor_id"]).any():
        raise ValueError("strict_annual_financial_duplicate_output_key")
    if not bool(result["available_at"].lt(result["decision_as_of"]).all()):
        raise ValueError("strict_annual_financial_visibility_violation")
    materialized_ids = sorted(result["factor_id"].unique().tolist())
    receipt: dict[str, object] = {
        "schema_id": "factorlab.strict_annual_financial_factor_materialization.v2",
        "formula_contract_digest": annual_financial_formula_contract_digest(),
        "materialization_contract_digest": (annual_financial_materialization_contract_digest()),
        "required_line_item_ids": list(REQUIRED_ANNUAL_LINE_ITEM_IDS),
        "observation_value_field": NORMALIZED_ANNUAL_VALUE_COLUMN,
        "observation_value_semantics": "datahub_governed_amount_in_cny",
        "input_observation_row_count": int(len(observations)),
        "admitted_monthly_market_cap_row_count": int(len(decisions)),
        "statement_event_count": int(len(statement_events)),
        "output_row_count": int(len(result)),
        "materialized_factor_ids": materialized_ids,
        "materialized_factor_count": len(materialized_ids),
        "missing_factor_ids": sorted(set(ANNUAL_COMPATIBLE_FINANCIAL_FACTOR_IDS) - set(materialized_ids)),
        "statement_audit": statement_audit,
        "join_predicate": "statement_available_at < decision_as_of",
        "growth_join_predicate": ("max(statement_available_at,previous_statement_available_at) < decision_as_of"),
        "annual_staleness_policy": ANNUAL_STALENESS_POLICY,
        "market_cap_join_predicate": "market_cap_available_at < decision_as_of",
        "winsorization": "none_cross_sectional_rank_is_applied_downstream",
        "latest_fallback_allowed": False,
        "revision_fallback_allowed": False,
        "strict_annual_semantic_correction_factor_ids": ["roic_lag1"],
        "historical_formula_transferable": {"roic_lag1": False},
        "historical_prior_inheritance_allowed": {"roic_lag1": False},
        "production_authority": False,
    }
    receipt["canonical_digest"] = canonical_digest(receipt)
    return result, receipt


def _statement_factor_events(
    observations: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, object]]:
    required = {
        "available_at",
        NORMALIZED_ANNUAL_VALUE_COLUMN,
        "line_item_id",
        "report_form",
        "report_period_end",
        "symbol",
    }
    missing = sorted(required - set(observations.columns))
    if missing:
        raise ValueError("strict_annual_financial_observation_columns_missing:" + ",".join(missing))
    frame = observations.loc[:, sorted(required)].copy()
    frame = frame.loc[frame["report_form"].eq("annual")]
    frame = frame.loc[frame["line_item_id"].isin(REQUIRED_ANNUAL_LINE_ITEM_IDS)]
    frame["symbol"] = frame["symbol"].astype(str).str.extract(r"(\d{6})", expand=False)
    frame["report_period_end"] = pd.to_datetime(frame["report_period_end"], errors="coerce")
    frame["available_at"] = pd.to_datetime(frame["available_at"], errors="coerce", utc=True).astype("datetime64[ns, UTC]")
    frame["value_cny"] = pd.to_numeric(frame[NORMALIZED_ANNUAL_VALUE_COLUMN], errors="coerce")
    frame = frame.dropna(
        subset=[
            "available_at",
            "line_item_id",
            "report_period_end",
            "symbol",
            "value_cny",
        ]
    )
    if frame.empty:
        raise ValueError("strict_annual_financial_observations_empty")
    keys = ["symbol", "report_period_end", "line_item_id"]
    grouped = frame.groupby(keys, observed=True, sort=False)
    conflict = grouped.agg(
        value_count=("value_cny", "nunique"),
        available_at_count=("available_at", "nunique"),
    )
    conflicting = conflict.loc[conflict["value_count"].gt(1) | conflict["available_at_count"].gt(1)]
    if not conflicting.empty:
        raise ValueError(f"strict_annual_financial_conflicting_first_release_rows:{len(conflicting)}")
    duplicate_row_count = int(frame.duplicated(keys, keep="first").sum())
    frame = frame.drop_duplicates(keys, keep="first")
    values = frame.pivot(
        index=["symbol", "report_period_end"],
        columns="line_item_id",
        values="value_cny",
    )
    missing_line_items = sorted(set(REQUIRED_ANNUAL_LINE_ITEM_IDS) - set(values.columns))
    if missing_line_items:
        raise ValueError("strict_annual_financial_required_line_items_missing:" + ",".join(missing_line_items))
    availability = frame.groupby(["symbol", "report_period_end"], observed=True, sort=False)["available_at"].max()
    statements = values.join(availability.rename("statement_available_at")).reset_index()
    statements = statements.sort_values(["symbol", "report_period_end"], kind="stable").reset_index(drop=True)

    previous_period = statements.groupby("symbol", sort=False)["report_period_end"].shift(1)
    statements["previous_statement_available_at"] = statements.groupby("symbol", sort=False)["statement_available_at"].shift(1)
    consecutive = (
        statements["report_period_end"].dt.year.sub(previous_period.dt.year).eq(1)
        & statements["report_period_end"].dt.month.eq(previous_period.dt.month)
        & statements["report_period_end"].dt.day.eq(previous_period.dt.day)
    )
    previous_profit = statements.groupby("symbol", sort=False)["net_profit"].shift(1)
    previous_assets = statements.groupby("symbol", sort=False)["total_assets"].shift(1)
    previous_equity = statements.groupby("symbol", sort=False)["total_equity"].shift(1)

    def divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
        return numerator.astype(float).div(denominator.astype(float).replace(0.0, np.nan))

    net_profit = statements["net_profit"].astype(float)
    operating_cashflow = statements["operating_cashflow_net"].astype(float)
    operating_profit = statements["operating_profit"].astype(float)
    revenue = statements["revenue"].astype(float)
    assets = statements["total_assets"].astype(float)
    equity = statements["total_equity"].astype(float)
    liabilities = statements["total_liabilities"].astype(float)
    invested_capital = assets - liabilities
    statements["accruals_lag1"] = -divide(net_profit - operating_cashflow, assets)
    statements["asset_turnover_lag1"] = divide(revenue, assets)
    statements["assets_growth_yoy"] = divide(assets, previous_assets).sub(1.0).where(consecutive)
    statements["cash_flow_roe_lag1"] = divide(operating_cashflow, equity)
    statements["cash_flow_to_assets_lag1"] = divide(operating_cashflow, assets)
    statements["cashflow_to_debt_lag1"] = divide(operating_cashflow, liabilities)
    statements["debt_to_equity_lag1"] = -divide(liabilities, equity)
    statements["earnings_quality_lag1"] = divide(operating_cashflow, net_profit)
    statements["equity_growth_yoy"] = divide(equity, previous_equity).sub(1.0).where(consecutive)
    statements["equity_turnover_lag1"] = divide(revenue, equity)
    statements["fundamental_quality_lag1"] = divide(net_profit, equity)
    statements["net_profit_growth_yoy"] = divide(net_profit, previous_profit).sub(1.0).where(consecutive)
    statements["net_profit_to_debt_lag1"] = divide(net_profit, liabilities)
    statements["operating_margin_lag1"] = divide(operating_cashflow, revenue)
    statements["profit_margin_lag1"] = divide(net_profit, revenue)
    statements["roa_lag1"] = divide(net_profit, assets)
    statements["roic_lag1"] = divide(operating_profit, invested_capital)
    audit: dict[str, object] = {
        "annual_input_row_count": int(len(frame)),
        "statement_event_count": int(len(statements)),
        "exact_duplicate_row_count_collapsed": duplicate_row_count,
        "conflicting_first_release_key_count": 0,
        "first_release_authority": "datahub_product_certification",
        "consecutive_annual_growth_required": True,
        "growth_requires_both_statement_availabilities": True,
        "latest_visible_statement_policy": ("greatest_report_period_among_statement_available_at_before_decision"),
    }
    return statements, audit


def _latest_visible_statement_rows(
    *,
    decisions: pd.DataFrame,
    statement_events: pd.DataFrame,
) -> pd.DataFrame:
    """Select the newest report period from statements visible at each decision.

    Availability order and report-period order are normally aligned, but that
    is not assumed.  A delayed older filing must neither displace an already
    visible newer annual statement nor make a two-period growth value visible
    before both source statements are available.
    """

    ordered_decisions = decisions.sort_values("decision_as_of", kind="stable")
    ordered_events = statement_events.sort_values(["statement_available_at", "report_period_end"], kind="stable").reset_index(drop=True)
    event_times = ordered_events["statement_available_at"].astype("int64").to_numpy()
    event_periods = ordered_events["report_period_end"].astype("int64").to_numpy()
    decision_times = ordered_decisions["decision_as_of"].astype("int64").to_numpy()
    cursor = 0
    best_event_index: int | None = None
    best_report_period: int | None = None
    decision_positions: list[int] = []
    event_positions: list[int] = []
    for decision_position, decision_time in enumerate(decision_times):
        while cursor < len(ordered_events) and event_times[cursor] < decision_time:
            report_period = int(event_periods[cursor])
            if best_report_period is None or report_period > best_report_period:
                best_report_period = report_period
                best_event_index = cursor
            cursor += 1
        if best_event_index is not None:
            decision_positions.append(decision_position)
            event_positions.append(best_event_index)
    if not decision_positions:
        return pd.DataFrame()
    visible_decisions = ordered_decisions.iloc[decision_positions].reset_index(drop=True)
    visible_events = ordered_events.iloc[event_positions].reset_index(drop=True)
    visible_events = visible_events.drop(columns=["symbol"], errors="ignore")
    visible = pd.concat([visible_decisions, visible_events], axis=1)
    decision_local = visible["decision_as_of"].dt.tz_convert("Asia/Shanghai")
    latest_required_year = decision_local.dt.year - np.where(decision_local.dt.month.le(4), 2, 1)
    report_year = visible["report_period_end"].dt.year
    return visible.loc[report_year.ge(latest_required_year)].reset_index(drop=True)


def _validated_monthly_market_cap(frame: pd.DataFrame) -> pd.DataFrame:
    required = {
        "available_at",
        "date",
        "decision_as_of",
        "symbol",
        "total_market_cap",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("strict_annual_market_cap_columns_missing:" + ",".join(missing))
    result = frame.loc[:, sorted(required)].copy()
    result = result.rename(columns={"available_at": "market_cap_available_at"})
    result["symbol"] = result["symbol"].astype(str).str.extract(r"(\d{6})", expand=False)
    result["date"] = pd.to_datetime(result["date"], errors="coerce")
    result["decision_as_of"] = pd.to_datetime(result["decision_as_of"], errors="coerce", utc=True).astype("datetime64[ns, UTC]")
    result["market_cap_available_at"] = pd.to_datetime(result["market_cap_available_at"], errors="coerce", utc=True).astype(
        "datetime64[ns, UTC]"
    )
    result["total_market_cap"] = pd.to_numeric(result["total_market_cap"], errors="coerce")
    result = result.dropna(subset=list(result.columns))
    result = result.loc[result["total_market_cap"].gt(0.0)]
    if result.empty:
        raise ValueError("strict_annual_monthly_market_cap_empty")
    if result.duplicated(["date", "symbol"]).any():
        raise ValueError("strict_annual_monthly_market_cap_duplicate_key")
    if not bool(result["market_cap_available_at"].lt(result["decision_as_of"]).all()):
        raise ValueError("strict_annual_monthly_market_cap_visibility_violation")
    return result.sort_values(["symbol", "decision_as_of"], kind="stable")


def _decision_factor_values(frame: pd.DataFrame) -> dict[str, pd.Series]:
    market_cap = frame["total_market_cap"].astype(float)
    result = {
        factor_id: frame[factor_id].astype(float)
        for factor_id in ANNUAL_COMPATIBLE_FINANCIAL_FACTOR_IDS
        if factor_id not in _VALUE_FACTOR_IDS
    }
    result.update(
        {
            "book_to_price_lag1": frame["total_equity"].astype(float).div(market_cap.replace(0.0, np.nan)),
            "cash_flow_yield_lag1": frame["operating_cashflow_net"].astype(float).div(market_cap.replace(0.0, np.nan)),
            "earnings_yield_lag1": frame["net_profit"].astype(float).div(market_cap.replace(0.0, np.nan)),
            "sales_to_price_lag1": frame["revenue"].astype(float).div(market_cap.replace(0.0, np.nan)),
        }
    )
    return result


def _formula_contract() -> dict[str, str]:
    return {
        "accruals_lag1": "-(net_profit-operating_cashflow_net)/total_assets",
        "asset_turnover_lag1": "revenue/total_assets",
        "assets_growth_yoy": "total_assets/previous_consecutive_annual_total_assets-1",
        "book_to_price_lag1": "total_equity/current_pit_total_market_cap",
        "cash_flow_roe_lag1": "operating_cashflow_net/total_equity",
        "cash_flow_to_assets_lag1": "operating_cashflow_net/total_assets",
        "cash_flow_yield_lag1": "operating_cashflow_net/current_pit_total_market_cap",
        "cashflow_to_debt_lag1": "operating_cashflow_net/total_liabilities",
        "debt_to_equity_lag1": "-total_liabilities/total_equity",
        "earnings_quality_lag1": "operating_cashflow_net/net_profit",
        "earnings_yield_lag1": "net_profit/current_pit_total_market_cap",
        "equity_growth_yoy": "total_equity/previous_consecutive_annual_total_equity-1",
        "equity_turnover_lag1": "revenue/total_equity",
        "fundamental_quality_lag1": "net_profit/total_equity",
        "net_profit_growth_yoy": "net_profit/previous_consecutive_annual_net_profit-1",
        "net_profit_to_debt_lag1": "net_profit/total_liabilities",
        "operating_margin_lag1": "operating_cashflow_net/revenue",
        "profit_margin_lag1": "net_profit/revenue",
        "roa_lag1": "net_profit/total_assets",
        "roic_lag1": ("operating_profit/(total_assets-total_liabilities)"),
        "sales_to_price_lag1": "revenue/current_pit_total_market_cap",
    }
