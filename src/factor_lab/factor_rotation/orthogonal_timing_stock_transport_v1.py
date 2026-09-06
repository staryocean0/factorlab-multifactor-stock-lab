# pyright: reportAny=false, reportMissingTypeStubs=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false, reportArgumentType=false
# pyright: reportUnknownLambdaType=false
"""OT3 one-state-per-family transport to stock coordinates."""

from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from factor_lab.factor_rotation.orthogonal_index_timing_transport_ot1_v1 import MARKET_FACTOR_ID, SIZE_FACTOR_ID
from factor_lab.governance.canonicalization import canonical_digest

SCHEMA_ID = "factorlab.orthogonal_timing_stock_transport@1.1"
OUTPUT_COLUMNS = (
    "market_timing_transport",
    "size_timing_transport",
    "industry_timing_transport",
)


def build_stock_transport(
    exposures: pd.DataFrame,
    industry_exposures: pd.DataFrame,
    selected_states: pd.DataFrame,
) -> pd.DataFrame:
    required_exposure = {
        "asof_date",
        "effective_date",
        "symbol",
        "symbol_position",
        "crossfit_fold",
        "beta_market",
        "beta_size",
        "reliability",
    }
    if not required_exposure.issubset(exposures.columns):
        raise ValueError("OT3_exposure_schema_mismatch")
    local = exposures.copy()
    local["asof_date"] = pd.to_datetime(local["asof_date"])
    local["effective_date"] = pd.to_datetime(local["effective_date"])
    local["variant_id"] = "crossfit_fold_" + local["crossfit_fold"].astype(str)
    states = selected_states.copy()
    states["decision_date"] = pd.to_datetime(states["decision_date"])

    market = states.loc[
        states["factor_id"].eq(MARKET_FACTOR_ID), ["variant_id", "decision_date", "timing_state", "selected_tool_id"]
    ].rename(
        columns={
            "decision_date": "asof_date",
            "timing_state": "market_timing_state",
            "selected_tool_id": "market_selected_tool_id",
        }
    )
    size = states.loc[states["factor_id"].eq(SIZE_FACTOR_ID), ["variant_id", "decision_date", "timing_state", "selected_tool_id"]].rename(
        columns={
            "decision_date": "asof_date",
            "timing_state": "size_timing_state",
            "selected_tool_id": "size_selected_tool_id",
        }
    )
    local = local.merge(market, on=["variant_id", "asof_date"], how="left", validate="many_to_one")
    local = local.merge(size, on=["variant_id", "asof_date"], how="left", validate="many_to_one")
    local["market_timing_transport"] = local["beta_market"] * local["market_timing_state"] * local["reliability"]
    local["size_timing_transport"] = local["beta_size"] * local["size_timing_state"] * local["reliability"]

    keys = ["asof_date", "symbol", "symbol_position"]
    if len(industry_exposures):
        industry_local = industry_exposures.copy()
        industry_local["asof_date"] = pd.to_datetime(industry_local["asof_date"])
        industry_local["variant_id"] = "crossfit_fold_" + industry_local["crossfit_fold"].astype(str)
        industry_states = states.loc[
            states["economic_family_id"].eq("industry"), ["variant_id", "decision_date", "factor_id", "timing_state", "selected_tool_id"]
        ].rename(
            columns={
                "decision_date": "asof_date",
                "factor_id": "industry_factor_id",
                "timing_state": "industry_timing_state",
                "selected_tool_id": "industry_selected_tool_id",
            }
        )
        industry_local = industry_local.merge(
            industry_states,
            on=["variant_id", "asof_date", "industry_factor_id"],
            how="left",
            validate="many_to_one",
        )
        industry_local["industry_component"] = (
            industry_local["beta_industry"]
            * industry_local["industry_timing_state"]
            * industry_local["reliability"]
            * industry_local["family_vote_weight"]
        )
        industry_aggregate = (
            industry_local.groupby(keys, sort=False, observed=True)
            .agg(
                industry_timing_transport=("industry_component", lambda values: values.sum(min_count=1)),
                industry_state_available_count=("industry_timing_state", "count"),
                industry_factor_count=("industry_factor_id", "nunique"),
                industry_selected_tool_id=("industry_selected_tool_id", "first"),
            )
            .reset_index()
        )
        local = local.merge(industry_aggregate, on=keys, how="left", validate="one_to_one")
    else:
        local["industry_timing_transport"] = np.nan
        local["industry_state_available_count"] = 0
        local["industry_factor_count"] = 0
        local["industry_selected_tool_id"] = pd.NA
    local["market_timing_available"] = local["market_timing_state"].notna()
    local["size_timing_available"] = local["size_timing_state"].notna()
    local["industry_timing_available"] = local["industry_timing_transport"].notna()
    if any(column in local for column in ("combined_score", "total_score", "tool_vote_sum")):
        raise RuntimeError("OT3_pre_sum_column_forbidden")
    return local.sort_values(["asof_date", "symbol"], kind="stable", ignore_index=True)


def build_contract(*, bindings: Mapping[str, str]) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_id": SCHEMA_ID,
        "status": "OT3_family_role_aware_one_state_transport_frozen",
        "issue_ref": "bd://fl-jug4j",
        "input": {
            "OT1_stock_exposures": "accepted_v1_1",
            "OT1_multiindustry_exposures": "accepted_v1_1",
            "OT2_selected_states": "market_industry_participate_or_neutral_size_signed_exact_one_tool_per_family",
        },
        "output_columns": list(OUTPUT_COLUMNS),
        "pre_sum_allowed": False,
        "tool_level_vote_columns_allowed": False,
        "idiosyncratic_transport": "deferred",
        "bindings": dict(sorted(bindings.items())),
        "authority": {
            "OT3_execution_allowed": True,
            "downstream_pretraining_account_simulation_allowed": False,
            "factor_admission_allowed": False,
            "strategy_mutation_allowed": False,
            "model_training_allowed": False,
            "production_authority": False,
        },
        "production_authority": False,
    }
    payload["canonical_digest"] = canonical_digest(payload)
    return payload


def validate_transport(frame: pd.DataFrame) -> list[str]:
    blockers: list[str] = []
    if any(column not in frame for column in OUTPUT_COLUMNS):
        blockers.append("OT3_output_column_missing")
    if any(column in frame for column in ("combined_score", "total_score", "tool_vote_sum")):
        blockers.append("OT3_pre_sum_column_present")
    if frame.duplicated(["asof_date", "symbol"]).any():
        blockers.append("OT3_duplicate_stock_coordinate")
    if pd.to_datetime(frame["effective_date"]).le(pd.to_datetime(frame["asof_date"])).any():
        blockers.append("OT3_not_next_session_effective")
    return blockers


__all__ = ["OUTPUT_COLUMNS", "SCHEMA_ID", "build_contract", "build_stock_transport", "validate_transport"]
