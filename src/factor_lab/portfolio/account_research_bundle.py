# pyright: reportAny=false
# pyright: reportArgumentType=false
# pyright: reportAttributeAccessIssue=false
# pyright: reportCallIssue=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportIndexIssue=false
# pyright: reportMissingTypeStubs=false
# pyright: reportOperatorIssue=false
# pyright: reportReturnType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Project-level reusable account snapshots, ledgers, and derived reports.

Strategy adapters own score generation, market data, execution semantics, and
factor definitions.  This module owns the immutable boundary after an account
has been replayed: deterministic snapshot files, generic ledger schemas,
conservation checks, cache identity, and report-only derivation.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Final

import numpy as np
import pandas as pd

from factor_lab.governance.canonicalization import canonical_digest
from factor_lab.portfolio.relative_performance import compute_relative_performance

SCHEMA_ID: Final = "factorlab.post_training_account_research_bundle@1.0"
IDENTITY_COLUMNS: Final[tuple[str, ...]] = (
    "account_id",
    "variant_id",
    "policy_id",
    "cost_scenario_id",
)
DAILY_CORE_COLUMNS: Final[tuple[str, ...]] = (
    "date",
    *IDENTITY_COLUMNS,
    "nav",
    "daily_return",
    "cash",
    "cash_weight",
    "holding_count",
    "is_rebalance",
)
HOLDING_CORE_COLUMNS: Final[tuple[str, ...]] = (
    "date",
    *IDENTITY_COLUMNS,
    "asset_id",
    "quantity",
    "mark_price",
    "market_value",
)
TRADE_CORE_COLUMNS: Final[tuple[str, ...]] = (
    "date",
    *IDENTITY_COLUMNS,
    "asset_id",
    "direction",
    "quantity",
    "execution_price",
    "trade_value",
    "transaction_cost",
)
EVENT_CORE_COLUMNS: Final[tuple[str, ...]] = (
    "date",
    *IDENTITY_COLUMNS,
    "asset_id",
    "event_type",
    "reason",
)
SELECTION_OPPORTUNITY_COLUMNS: Final[tuple[str, ...]] = (
    "decision_id",
    "decision_time",
    "variant_id",
    "policy_id",
    "asset_id",
    "score",
    "score_available_at",
    "eligible",
    "selected",
    "selection_rank",
    "label_start_time",
    "label_end_time",
    "realized_forward_return",
    "opportunity_rank",
    "opportunity_bucket",
)
REALIZED_PNL_COLUMNS: Final[tuple[str, ...]] = (
    "date",
    *IDENTITY_COLUMNS,
    "asset_id",
    "trade_episode_id",
    "segment_id",
    "component_id",
    "simple_contribution",
    "linked_log_contribution",
)
FACTOR_RETURN_SURFACE_COLUMNS: Final[tuple[str, ...]] = (
    "variant_id",
    "segment_id",
    "segment_start_time",
    "segment_end_time",
    "exposure_available_at",
    "factor_id",
    "factor_return",
    "observation_count",
    "design_rank",
    "condition_number",
)
SNAPSHOT_FILENAMES: Final[dict[str, str]] = {
    "daily": "portfolio_daily.parquet",
    "holdings": "holdings.parquet",
    "trades": "trades.parquet",
    "events": "events.parquet",
}
REPORT_FILENAMES: Final[dict[str, str]] = {
    "annual": "annual_relative_performance.csv",
    "quarterly": "quarterly_relative_performance.csv",
    "monthly": "monthly_relative_performance.csv",
}


@dataclass(frozen=True, slots=True)
class AccountSnapshotIdentity:
    """All immutable inputs that determine an account snapshot cache key."""

    strategy_id: str
    model_or_score_digest: str
    account_policy_family_digest: str
    market_data_digest: str
    adapter_digest: str
    data_usage_digest: str
    tree: str
    execution_semantics: str

    def __post_init__(self) -> None:
        if not self.strategy_id.strip() or not self.execution_semantics.strip():
            raise ValueError("account_snapshot_identity_text_missing")
        if self.tree not in {"formal", "isolated"}:
            raise ValueError("account_snapshot_tree_invalid")
        for name in (
            "model_or_score_digest",
            "account_policy_family_digest",
            "market_data_digest",
            "adapter_digest",
            "data_usage_digest",
        ):
            if not str(getattr(self, name)).startswith("sha256:"):
                raise ValueError(f"account_snapshot_digest_invalid:{name}")

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    @property
    def cache_key(self) -> str:
        return canonical_digest(self.to_dict())


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    root: Path
    manifest: dict[str, object]
    daily: pd.DataFrame
    holdings: pd.DataFrame
    trades: pd.DataFrame
    events: pd.DataFrame


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical_valid(payload: Mapping[str, object]) -> bool:
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    return stored == canonical_digest(body)


def _write_json(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    output = dict(payload)
    output.pop("canonical_digest", None)
    output["canonical_digest"] = canonical_digest(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output


def _require_columns(frame: pd.DataFrame, required: tuple[str, ...], code: str) -> None:
    missing = set(required) - set(frame.columns)
    if missing:
        raise ValueError(code + ":" + ",".join(sorted(missing)))


def _normalize_date(frame: pd.DataFrame, column: str = "date") -> pd.DataFrame:
    output = frame.copy()
    output[column] = pd.to_datetime(output[column], errors="raise").dt.tz_localize(None).dt.normalize()
    return output


def validate_account_daily(
    frame: pd.DataFrame,
    *,
    initial_nav: float | None = None,
    tolerance: float = 1.0e-10,
) -> dict[str, object]:
    """Validate one or more complete account paths and NAV conservation."""

    _require_columns(frame, DAILY_CORE_COLUMNS, "account_snapshot_daily_columns_missing")
    daily = _normalize_date(frame)
    key = [*IDENTITY_COLUMNS, "date"]
    if daily.duplicated(key).any():
        raise ValueError("account_snapshot_daily_key_duplicate")
    numeric_columns = ("nav", "daily_return", "cash", "cash_weight", "holding_count")
    numeric = {
        column: pd.to_numeric(daily[column], errors="raise").to_numpy(np.float64)
        for column in numeric_columns
    }
    if any(not np.isfinite(values).all() for values in numeric.values()):
        raise ValueError("account_snapshot_daily_nonfinite")
    if (numeric["nav"] <= 0.0).any() or (numeric["daily_return"] <= -1.0).any():
        raise ValueError("account_snapshot_daily_economic_domain_invalid")
    if (numeric["holding_count"] < 0.0).any():
        raise ValueError("account_snapshot_holding_count_negative")
    if not np.allclose(
        numeric["holding_count"],
        np.rint(numeric["holding_count"]),
        rtol=0.0,
        atol=0.0,
    ):
        raise ValueError("account_snapshot_holding_count_not_integer")
    maximum_error = 0.0
    account_count = 0
    for _, local in daily.groupby(list(IDENTITY_COLUMNS), sort=True, dropna=False):
        account_count += 1
        ordered = local.sort_values("date", kind="mergesort")
        nav = pd.to_numeric(ordered["nav"], errors="raise").to_numpy(np.float64)
        returns = pd.to_numeric(ordered["daily_return"], errors="raise").to_numpy(np.float64)
        if len(nav) > 1:
            error = np.abs(nav[1:] / nav[:-1] - 1.0 - returns[1:])
            maximum_error = max(maximum_error, float(error.max(initial=0.0)))
        if initial_nav is not None:
            if not np.isfinite(initial_nav) or initial_nav <= 0.0:
                raise ValueError("account_snapshot_initial_nav_invalid")
            maximum_error = max(maximum_error, abs(nav[0] / initial_nav - 1.0 - returns[0]))
    if maximum_error > tolerance:
        raise ValueError(f"account_snapshot_nav_return_identity_failed:{maximum_error}")
    return {
        "account_count": account_count,
        "daily_row_count": len(daily),
        "maximum_nav_return_identity_error": maximum_error,
    }


def validate_holdings(frame: pd.DataFrame) -> None:
    _require_columns(frame, HOLDING_CORE_COLUMNS, "account_snapshot_holding_columns_missing")
    holdings = _normalize_date(frame)
    key = [*IDENTITY_COLUMNS, "date", "asset_id"]
    if holdings.duplicated(key).any():
        raise ValueError("account_snapshot_holding_key_duplicate")
    quantity = pd.to_numeric(holdings["quantity"], errors="raise").to_numpy(np.float64)
    mark_price = pd.to_numeric(holdings["mark_price"], errors="raise").to_numpy(np.float64)
    market_value = pd.to_numeric(holdings["market_value"], errors="raise").to_numpy(np.float64)
    if not all(np.isfinite(values).all() for values in (quantity, mark_price, market_value)):
        raise ValueError("account_snapshot_holding_nonfinite")
    if (mark_price <= 0.0).any():
        raise ValueError("account_snapshot_holding_mark_price_invalid")
    if not np.allclose(market_value, quantity * mark_price, rtol=1.0e-12, atol=1.0e-10):
        raise ValueError("account_snapshot_holding_market_value_identity_failed")


def validate_trades(frame: pd.DataFrame) -> None:
    _require_columns(frame, TRADE_CORE_COLUMNS, "account_snapshot_trade_columns_missing")
    trades = _normalize_date(frame)
    if not set(trades["direction"].astype(str)).issubset({"buy", "sell"}):
        raise ValueError("account_snapshot_trade_direction_invalid")
    quantity = pd.to_numeric(trades["quantity"], errors="raise").to_numpy(np.float64)
    execution = pd.to_numeric(trades["execution_price"], errors="raise").to_numpy(np.float64)
    trade_value = pd.to_numeric(trades["trade_value"], errors="raise").to_numpy(np.float64)
    transaction_cost = pd.to_numeric(trades["transaction_cost"], errors="raise").to_numpy(np.float64)
    if any(
        not np.isfinite(values).all() or (values < 0.0).any()
        for values in (quantity, execution, trade_value, transaction_cost)
    ):
        raise ValueError("account_snapshot_trade_value_invalid")
    if not np.allclose(trade_value, quantity * execution, rtol=1.0e-12, atol=1.0e-10):
        raise ValueError("account_snapshot_trade_value_identity_failed")


def validate_events(frame: pd.DataFrame) -> None:
    _require_columns(frame, EVENT_CORE_COLUMNS, "account_snapshot_event_columns_missing")
    _ = _normalize_date(frame)


def validate_selection_opportunity_ledger(frame: pd.DataFrame) -> dict[str, object]:
    """Validate the hindsight opportunity/selection ledger boundary."""

    _require_columns(
        frame,
        SELECTION_OPPORTUNITY_COLUMNS,
        "selection_opportunity_ledger_columns_missing",
    )
    key = ["decision_id", "variant_id", "policy_id", "asset_id"]
    if frame.duplicated(key).any():
        raise ValueError("selection_opportunity_ledger_key_duplicate")
    decision = pd.to_datetime(frame["decision_time"], errors="raise")
    score_available = pd.to_datetime(frame["score_available_at"], errors="raise")
    label_start = pd.to_datetime(frame["label_start_time"], errors="raise")
    label_end = pd.to_datetime(frame["label_end_time"], errors="raise")
    if score_available.gt(decision).any():
        raise ValueError("selection_opportunity_score_available_after_decision")
    if label_start.lt(decision).any() or label_end.lt(label_start).any():
        raise ValueError("selection_opportunity_hindsight_label_time_invalid")
    eligible = frame["eligible"].astype(bool).to_numpy()
    selected = frame["selected"].astype(bool).to_numpy()
    if (selected & ~eligible).any():
        raise ValueError("selection_opportunity_selected_ineligible_asset")
    score = pd.to_numeric(frame["score"], errors="coerce").to_numpy(np.float64)
    realized = pd.to_numeric(frame["realized_forward_return"], errors="coerce").to_numpy(np.float64)
    if not np.isfinite(score[selected]).all() or not np.isfinite(realized[eligible]).all():
        raise ValueError("selection_opportunity_required_value_nonfinite")
    selection_rank = pd.to_numeric(frame["selection_rank"], errors="coerce").to_numpy(np.float64)
    opportunity_rank = pd.to_numeric(frame["opportunity_rank"], errors="coerce").to_numpy(np.float64)
    if (selection_rank[selected] < 1.0).any() or (opportunity_rank[eligible] < 1.0).any():
        raise ValueError("selection_opportunity_rank_invalid")
    return {
        "row_count": len(frame),
        "decision_count": int(frame["decision_id"].nunique()),
        "selected_row_count": int(selected.sum()),
        "hindsight_label_is_runtime_input": False,
    }


def validate_selection_opportunity_ledger_v2(
    frame: pd.DataFrame,
) -> dict[str, object]:
    """Validate score selections plus explicit untradable forced carries."""

    _require_columns(
        frame,
        (*SELECTION_OPPORTUNITY_COLUMNS, "selection_reason"),
        "selection_opportunity_ledger_v2_columns_missing",
    )
    key = ["decision_id", "variant_id", "policy_id", "asset_id"]
    if frame.duplicated(key).any():
        raise ValueError("selection_opportunity_ledger_v2_key_duplicate")
    decision = pd.to_datetime(frame["decision_time"], errors="raise")
    score_available = pd.to_datetime(frame["score_available_at"], errors="raise")
    label_start = pd.to_datetime(frame["label_start_time"], errors="coerce")
    label_end = pd.to_datetime(frame["label_end_time"], errors="coerce")
    if score_available.isna().any() or score_available.gt(decision).any():
        raise ValueError("selection_opportunity_v2_score_availability_invalid")
    reason = frame["selection_reason"].astype(str)
    if not set(reason).issubset({"score_selected", "not_selected", "forced_carry"}):
        raise ValueError("selection_opportunity_v2_reason_invalid")
    eligible = frame["eligible"].astype(bool).to_numpy()
    selected = frame["selected"].astype(bool).to_numpy()
    forced = reason.eq("forced_carry").to_numpy()
    score_selected = reason.eq("score_selected").to_numpy()
    not_selected = reason.eq("not_selected").to_numpy()
    if (
        (forced & (~selected | eligible)).any()
        or (score_selected & (~selected | ~eligible)).any()
        or (not_selected & selected).any()
        or (selected & ~(forced | score_selected)).any()
    ):
        raise ValueError("selection_opportunity_v2_role_identity_invalid")
    score = pd.to_numeric(frame["score"], errors="coerce").to_numpy(np.float64)
    realized = pd.to_numeric(
        frame["realized_forward_return"],
        errors="coerce",
    ).to_numpy(np.float64)
    selection_rank = pd.to_numeric(
        frame["selection_rank"],
        errors="coerce",
    ).to_numpy(np.float64)
    opportunity_rank = pd.to_numeric(
        frame["opportunity_rank"],
        errors="coerce",
    ).to_numpy(np.float64)
    if (
        not np.isfinite(score[selected]).all()
        or (selection_rank[selected] < 1.0).any()
        or not np.isfinite(realized[eligible]).all()
        or (opportunity_rank[eligible] < 1.0).any()
    ):
        raise ValueError("selection_opportunity_v2_required_value_invalid")
    eligible_series = pd.Series(eligible, index=frame.index)
    if (
        label_start.loc[eligible_series].isna().any()
        or label_end.loc[eligible_series].isna().any()
        or label_start.loc[eligible_series].lt(decision.loc[eligible_series]).any()
        or label_end.loc[eligible_series].lt(label_start.loc[eligible_series]).any()
    ):
        raise ValueError("selection_opportunity_v2_label_time_invalid")
    if (
        np.isfinite(realized[forced]).any()
        or np.isfinite(opportunity_rank[forced]).any()
        or label_start.loc[pd.Series(forced, index=frame.index)].notna().any()
        or label_end.loc[pd.Series(forced, index=frame.index)].notna().any()
        or not frame.loc[forced, "opportunity_bucket"].astype(str).eq("unavailable").all()
    ):
        raise ValueError("selection_opportunity_v2_forced_carry_payload_invalid")
    return {
        "schema_id": "factorlab.selection_opportunity_ledger@2.0",
        "row_count": len(frame),
        "decision_count": int(frame["decision_id"].nunique()),
        "selected_row_count": int(selected.sum()),
        "forced_carry_row_count": int(forced.sum()),
        "hindsight_label_is_runtime_input": False,
    }


def validate_factor_return_surface(frame: pd.DataFrame) -> dict[str, object]:
    """Validate policy-independent realised factor returns cached once per segment."""

    _require_columns(
        frame,
        FACTOR_RETURN_SURFACE_COLUMNS,
        "factor_return_surface_columns_missing",
    )
    key = ["variant_id", "segment_id", "factor_id"]
    if frame.duplicated(key).any():
        raise ValueError("factor_return_surface_key_duplicate")
    start = pd.to_datetime(frame["segment_start_time"], errors="raise")
    end = pd.to_datetime(frame["segment_end_time"], errors="raise")
    available = pd.to_datetime(frame["exposure_available_at"], errors="raise")
    if end.lt(start).any() or available.gt(start).any():
        raise ValueError("factor_return_surface_temporal_invalid")
    factor_return = pd.to_numeric(frame["factor_return"], errors="raise").to_numpy(np.float64)
    condition = pd.to_numeric(frame["condition_number"], errors="raise").to_numpy(np.float64)
    if not np.isfinite(factor_return).all() or not np.isfinite(condition).all() or (condition < 0.0).any():
        raise ValueError("factor_return_surface_numeric_invalid")
    return {
        "row_count": len(frame),
        "segment_count": int(frame["segment_id"].nunique()),
        "factor_count": int(frame["factor_id"].nunique()),
    }


def validate_realized_pnl_ledger(
    frame: pd.DataFrame,
    *,
    account_daily: pd.DataFrame,
    tolerance: float = 1.0e-10,
) -> dict[str, object]:
    """Require stock/trade/component contributions to conserve account P&L."""

    _require_columns(frame, REALIZED_PNL_COLUMNS, "realized_pnl_ledger_columns_missing")
    validate_account_daily(account_daily, tolerance=tolerance)
    ledger = _normalize_date(frame)
    daily = _normalize_date(account_daily)
    key = ["date", *IDENTITY_COLUMNS]
    simple = (
        ledger.groupby(key, sort=True, dropna=False)["simple_contribution"]
        .sum()
        .rename("attributed_simple")
        .reset_index()
    )
    linked = (
        ledger.groupby(key, sort=True, dropna=False)["linked_log_contribution"]
        .sum()
        .rename("attributed_log")
        .reset_index()
    )
    if len(simple) != len(daily) or len(linked) != len(daily):
        raise ValueError("realized_pnl_ledger_daily_coverage_mismatch")
    comparison = daily[key + ["daily_return"]].merge(
        simple.merge(linked, on=key, validate="one_to_one"),
        on=key,
        validate="one_to_one",
    )
    if len(comparison) != len(daily):
        raise ValueError("realized_pnl_ledger_daily_coverage_missing")
    daily_return = pd.to_numeric(comparison["daily_return"], errors="raise").to_numpy(np.float64)
    simple_error = np.abs(
        pd.to_numeric(comparison["attributed_simple"], errors="raise").to_numpy(np.float64)
        - daily_return
    )
    log_error = np.abs(
        pd.to_numeric(comparison["attributed_log"], errors="raise").to_numpy(np.float64)
        - np.log1p(daily_return)
    )
    maximum_simple = float(simple_error.max(initial=0.0))
    maximum_log = float(log_error.max(initial=0.0))
    if max(maximum_simple, maximum_log) > tolerance:
        raise ValueError("realized_pnl_ledger_account_identity_failed")
    return {
        "row_count": len(ledger),
        "account_day_count": len(comparison),
        "maximum_simple_identity_error": maximum_simple,
        "maximum_linked_log_identity_error": maximum_log,
        "component_count": int(ledger["component_id"].nunique()),
    }


def _sort_frame(name: str, frame: pd.DataFrame) -> pd.DataFrame:
    columns = {
        "daily": [*IDENTITY_COLUMNS, "date"],
        "holdings": [*IDENTITY_COLUMNS, "date", "asset_id"],
        "trades": [*IDENTITY_COLUMNS, "date", "asset_id", "direction"],
        "events": [*IDENTITY_COLUMNS, "date", "asset_id", "event_type"],
    }[name]
    return _normalize_date(frame).sort_values(columns, kind="mergesort", ignore_index=True)


def materialize_account_snapshot(
    *,
    output_root: Path,
    identity: AccountSnapshotIdentity,
    daily: pd.DataFrame,
    holdings: pd.DataFrame,
    trades: pd.DataFrame,
    events: pd.DataFrame,
    snapshot_profile: str = "complete_account",
    initial_nav: float | None = None,
    source_closure: Mapping[str, str] | None = None,
) -> dict[str, object]:
    """Write one immutable account replay snapshot for all downstream reports."""

    if snapshot_profile not in {"complete_account", "account_daily_only"}:
        raise ValueError("account_snapshot_profile_invalid")
    if output_root.exists():
        raise FileExistsError(output_root)
    diagnostics = validate_account_daily(daily, initial_nav=initial_nav)
    validate_holdings(holdings)
    validate_trades(trades)
    validate_events(events)
    if snapshot_profile == "complete_account":
        daily_holding_count = pd.to_numeric(daily["holding_count"], errors="raise")
        if (daily_holding_count > 0).any() and holdings.empty:
            raise ValueError("complete_account_snapshot_holdings_missing")
        active_days = _normalize_date(daily.loc[daily_holding_count > 0, ["date", *IDENTITY_COLUMNS]])
        holding_days = _normalize_date(holdings.loc[:, ["date", *IDENTITY_COLUMNS]])
        active_keys = set(active_days.itertuples(index=False, name=None))
        holding_keys = set(holding_days.itertuples(index=False, name=None))
        if not active_keys.issubset(holding_keys):
            raise ValueError("complete_account_snapshot_holding_day_coverage_missing")
    output_root.mkdir(parents=True)
    frames = {
        "daily": _sort_frame("daily", daily),
        "holdings": _sort_frame("holdings", holdings),
        "trades": _sort_frame("trades", trades),
        "events": _sort_frame("events", events),
    }
    artifact_digests: dict[str, str] = {}
    for name, filename in SNAPSHOT_FILENAMES.items():
        path = output_root / filename
        frames[name].to_parquet(
            path,
            index=False,
            compression="zstd",
            use_dictionary=False,
        )
        artifact_digests[filename] = file_digest(path)
    return _write_json(
        output_root / "snapshot_manifest.json",
        {
            "schema_id": SCHEMA_ID,
            "status": "materialized_immutable_account_snapshot",
            "identity": identity.to_dict(),
            "cache_key": identity.cache_key,
            "snapshot_profile": snapshot_profile,
            "initial_nav": initial_nav,
            "artifact_digests": artifact_digests,
            "source_closure": dict(sorted((source_closure or {}).items())),
            "diagnostics": diagnostics,
            "downstream_model_or_score_rebuild_required": False,
            "account_parameter_selection_performed": False,
            "fresh_oos": False,
            "production_authority": False,
        },
    )


def load_account_snapshot(
    root: Path,
    *,
    expected_cache_key: str | None = None,
) -> AccountSnapshot:
    manifest_path = root / "snapshot_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or not _canonical_valid(manifest):
        raise ValueError("account_snapshot_manifest_invalid")
    if expected_cache_key is not None and manifest.get("cache_key") != expected_cache_key:
        raise ValueError("account_snapshot_cache_key_mismatch")
    artifact_digests = manifest.get("artifact_digests")
    if not isinstance(artifact_digests, Mapping):
        raise ValueError("account_snapshot_artifact_digests_missing")
    frames: dict[str, pd.DataFrame] = {}
    for name, filename in SNAPSHOT_FILENAMES.items():
        path = root / filename
        if artifact_digests.get(filename) != file_digest(path):
            raise ValueError(f"account_snapshot_artifact_drift:{filename}")
        frames[name] = pd.read_parquet(path)
    initial_nav_raw = manifest.get("initial_nav")
    initial_nav = float(initial_nav_raw) if initial_nav_raw is not None else None
    validate_account_daily(frames["daily"], initial_nav=initial_nav)
    validate_holdings(frames["holdings"])
    validate_trades(frames["trades"])
    validate_events(frames["events"])
    if manifest.get("snapshot_profile") not in {"complete_account", "account_daily_only"}:
        raise ValueError("account_snapshot_profile_invalid")
    return AccountSnapshot(
        root=root,
        manifest=manifest,
        daily=frames["daily"],
        holdings=frames["holdings"],
        trades=frames["trades"],
        events=frames["events"],
    )


def derive_relative_reports(
    account_daily: pd.DataFrame,
    benchmark_returns: pd.Series,
    *,
    benchmark_id: str,
) -> dict[str, pd.DataFrame]:
    """Derive every period report without model, score, market, or account replay."""

    validate_account_daily(account_daily)
    daily = _normalize_date(account_daily)
    output: dict[str, list[pd.DataFrame]] = {key: [] for key in REPORT_FILENAMES}
    for identity_values, local in daily.groupby(list(IDENTITY_COLUMNS), sort=True, dropna=False):
        identity = dict(zip(IDENTITY_COLUMNS, identity_values, strict=True))
        ordered = local.sort_values("date", kind="mergesort")
        series = pd.Series(
            pd.to_numeric(ordered["daily_return"], errors="raise").to_numpy(np.float64),
            index=pd.DatetimeIndex(ordered["date"]),
        )
        result = compute_relative_performance(
            series,
            benchmark_returns,
            strategy_id=str(identity["account_id"]),
            benchmark_id=benchmark_id,
        )
        for name, frame in (
            ("annual", result.annual),
            ("quarterly", result.quarterly),
            ("monthly", result.monthly),
        ):
            annotated = frame.copy()
            for position, column in enumerate(IDENTITY_COLUMNS):
                annotated.insert(position, column, identity[column])
            output[name].append(annotated)
    return {
        name: pd.concat(parts, ignore_index=True).sort_values(
            ["period", *IDENTITY_COLUMNS], kind="mergesort", ignore_index=True
        )
        for name, parts in output.items()
    }


def materialize_relative_reports_from_snapshot(
    *,
    snapshot_root: Path,
    output_root: Path,
    benchmark_returns: pd.Series,
    benchmark_id: str,
    benchmark_digest: str,
) -> dict[str, object]:
    """Fast cache-hit path: read only account daily and benchmark returns."""

    started = time.perf_counter()
    if output_root.exists():
        raise FileExistsError(output_root)
    snapshot = load_account_snapshot(snapshot_root)
    reports = derive_relative_reports(
        snapshot.daily,
        benchmark_returns,
        benchmark_id=benchmark_id,
    )
    output_root.mkdir(parents=True)
    digests: dict[str, str] = {}
    for name, filename in REPORT_FILENAMES.items():
        path = output_root / filename
        reports[name].to_csv(path, index=False, lineterminator="\n", float_format="%.17g")
        digests[filename] = file_digest(path)
    return _write_json(
        output_root / "report_receipt.json",
        {
            "schema_id": "factorlab.post_training_account_derived_report@1.0",
            "status": "completed_from_immutable_account_snapshot",
            "snapshot_manifest_digest": snapshot.manifest["canonical_digest"],
            "snapshot_cache_key": snapshot.manifest["cache_key"],
            "benchmark_id": benchmark_id,
            "benchmark_digest": benchmark_digest,
            "artifact_digests": digests,
            "model_read_count": 0,
            "score_generation_count": 0,
            "market_replay_count": 0,
            "account_replay_count": 0,
            "elapsed_seconds": time.perf_counter() - started,
            "parameter_selection_performed": False,
            "fresh_oos": False,
            "production_authority": False,
        },
    )


__all__ = [
    "AccountSnapshot",
    "AccountSnapshotIdentity",
    "DAILY_CORE_COLUMNS",
    "EVENT_CORE_COLUMNS",
    "FACTOR_RETURN_SURFACE_COLUMNS",
    "HOLDING_CORE_COLUMNS",
    "IDENTITY_COLUMNS",
    "REALIZED_PNL_COLUMNS",
    "REPORT_FILENAMES",
    "SCHEMA_ID",
    "SELECTION_OPPORTUNITY_COLUMNS",
    "SNAPSHOT_FILENAMES",
    "TRADE_CORE_COLUMNS",
    "derive_relative_reports",
    "file_digest",
    "load_account_snapshot",
    "materialize_account_snapshot",
    "materialize_relative_reports_from_snapshot",
    "validate_account_daily",
    "validate_events",
    "validate_factor_return_surface",
    "validate_holdings",
    "validate_realized_pnl_ledger",
    "validate_selection_opportunity_ledger",
    "validate_selection_opportunity_ledger_v2",
    "validate_trades",
]
