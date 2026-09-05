# pyright: reportAny=false
"""K1_only CloudRidge index-regime atlas: frozen weekly/monthly/quarterly family."""

from __future__ import annotations

from pathlib import Path
from typing import Final, cast

import numpy as np
import pandas as pd

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import canonical_valid, file_digest, read_json, write_json
from factor_lab.portfolio.post_training_strategy_science_acceptance import assert_no_scientific_wall_clock

ROOT: Final = Path(__file__).resolve().parents[3]
CONTRACT: Final = ROOT / "docs/ops/reaka_k1_only_index_regime_atlas@1.0.json"
ATLAS_ROOT: Final = ROOT / "output/factor-rotation/reaka_k1_only_four_group_atlas_v1_2011_2025"
BLACKBOX_ROOT: Final = ROOT / "output/factor-rotation/reaka_k1_only_blackbox_ledgers_v1_2018_2025"
CLOUDRIDGE_TEMPLATE: Final = (
    "output/factor-rotation/reaka_residual_only_post2020_extension_v1_2009_2026/"
    "{tree}/cloudridge/cloudridge_beta_weekly_2008_2026.levels.csv"
)
GROUPS: Final = ("index", "size", "industry", "other")
GRAINS: Final = ("weekly", "monthly", "quarterly")
CLOCKS: Final = ("14:30", "14:45")
TRENDS: Final = ("up", "sideways", "down")
VOLS: Final = ("high", "low")
COMBINED: Final = (
    "up_high",
    "up_low",
    "sideways_high",
    "sideways_low",
    "down_high",
    "down_low",
)
LABEL: Final[dict[str, str]] = {
    "index": "指数",
    "size": "规模",
    "industry": "行业",
    "other": "个股残差",
    "up": "上涨",
    "sideways": "横盘",
    "down": "下跌",
    "high": "高波",
    "low": "低波",
    "up_high": "上涨高波",
    "up_low": "上涨低波",
    "sideways_high": "横盘高波",
    "sideways_low": "横盘低波",
    "down_high": "下跌高波",
    "down_low": "下跌低波",
    "weekly": "周",
    "monthly": "月",
    "quarterly": "季",
}
FROZEN_Z: Final = 1.0
SIGMA_MIN_PERIODS: Final = 60
VOL_MEDIAN_MIN_PERIODS: Final = 12
MIN_TREND_PERIODS: Final = 4
SKELETON_BAR: Final = 0.5
SELECTION_YEAR_MIN: Final = 2011
SELECTION_YEAR_MAX: Final = 2016
HARD_END: Final = pd.Timestamp("2025-12-31")
WARMUP_START: Final = pd.Timestamp("2008-01-07")
GRAIN_COARSENESS: Final[dict[str, int]] = {"weekly": 0, "monthly": 1, "quarterly": 2}
SOURCE_FILES: Final[tuple[str, ...]] = (
    "docs/ops/reaka_k1_only_four_group_atlas@1.0.json",
    "docs/ops/reaka_k1_only_principal_contradiction@2.0.json",
    "docs/ops/state_factor_research_state_machine@1.0.json",
    "docs/ops/reaka_k1_only_index_regime_atlas_whitepaper.md",
    "docs/user/reaka_k1_only_index_regime_atlas_workflow.md",
    "src/factor_lab/factor_rotation/reaka_k1_only_index_regime_atlas_v1.py",
    "scripts/factor_rotation/run_reaka_k1_only_index_regime_atlas_v1.py",
    "scripts/factor_rotation/validate_reaka_k1_only_index_regime_atlas_v1.py",
    "tests/unit/test_reaka_k1_only_index_regime_atlas_v1.py",
)


def source_closure() -> dict[str, str]:
    return {relative: file_digest(ROOT / relative) for relative in SOURCE_FILES}


def load_contract() -> dict[str, object]:
    payload = read_json(CONTRACT)
    if not canonical_valid(payload):
        raise PermissionError("k1_only_index_regime_digest_invalid")
    if payload.get("schema_id") != "factorlab.reaka_k1_only_index_regime_atlas@1.0":
        raise PermissionError("k1_only_index_regime_schema_invalid")
    if payload.get("trading_identity") != "K1_only":
        raise PermissionError("k1_only_index_regime_identity_drift")
    if payload.get("industry_split") is not False:
        raise PermissionError("k1_only_index_regime_industry_split")
    if payload.get("new_factor_search_allowed") is not False:
        raise PermissionError("k1_only_index_regime_factor_search_opened")
    if payload.get("strategy_overlay_applied") is not False:
        raise PermissionError("k1_only_index_regime_overlay_opened")
    if payload.get("account_replayed") is not False:
        raise PermissionError("k1_only_index_regime_account_replayed")
    if payload.get("trend_deadband_sigma_multiple") != FROZEN_Z:
        raise PermissionError("k1_only_index_regime_z_drift")
    if tuple(cast(list[str], payload["grains"])) != GRAINS:
        raise PermissionError("k1_only_index_regime_grain_drift")
    if payload.get("source_closure") != source_closure():
        raise PermissionError("k1_only_index_regime_source_closure_drift")
    authority = cast(dict[str, object], payload["authority"])
    if authority.get("production_authority") is not False:
        raise PermissionError("k1_only_index_regime_production_not_closed")
    if authority.get("new_factor_admission") is not False:
        raise PermissionError("k1_only_index_regime_factor_admission_opened")
    return payload


def period_label(stamp: pd.Timestamp, grain: str) -> str:
    if grain == "weekly":
        iso = stamp.isocalendar()
        return f"{int(iso.year)}-W{int(iso.week):02d}"
    if grain == "monthly":
        return f"{stamp.year:04d}-{stamp.month:02d}"
    if grain == "quarterly":
        return f"{stamp.year:04d}Q{stamp.quarter}"
    raise ValueError("k1_only_index_regime_grain_invalid")


def data_role(year: int) -> str:
    if year <= 2010:
        return "index_warmup"
    if SELECTION_YEAR_MIN <= year <= SELECTION_YEAR_MAX:
        return "development_selection"
    if year == 2017:
        return "development_listing"
    if 2018 <= year <= 2025:
        return "consumed_blackbox_diagnostic"
    raise PermissionError(f"k1_only_index_regime_year_unassigned:{year}")


def load_cloudridge(tree: str) -> pd.DataFrame:
    relative = CLOUDRIDGE_TEMPLATE.format(tree=tree)
    path = ROOT / relative
    contract = load_contract()
    expected = cast(dict[str, object], contract["cloudridge"])
    if file_digest(path) != expected["file_digest"]:
        raise PermissionError("k1_only_index_regime_cloudridge_digest_drift")
    frame = pd.read_csv(path, usecols=["date", "daily_return", "index_level", "previous_level", "index_id"])
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    future = frame.loc[frame["date"] > HARD_END]
    if len(future) == 0:
        raise PermissionError("k1_only_index_regime_cloudridge_missing_future_tail_to_drop")
    frame = frame.loc[(frame["date"] >= WARMUP_START) & (frame["date"] <= HARD_END)].copy()
    if frame["date"].duplicated().any():
        raise PermissionError("k1_only_index_regime_cloudridge_duplicate_date")
    if set(frame["index_id"].astype(str)) != {"cldrgidx_fast_10d92324985baafb124f"}:
        raise PermissionError("k1_only_index_regime_cloudridge_index_id_drift")
    level = pd.to_numeric(frame["index_level"], errors="raise")
    previous = pd.to_numeric(frame["previous_level"], errors="raise")
    frame["log_return"] = np.log(level / previous)
    frame = frame.sort_values("date", kind="mergesort", ignore_index=True)
    if bool(frame["date"].gt(HARD_END).any()):
        raise PermissionError("k1_only_index_regime_2026_not_dropped")
    return frame.loc[:, ["date", "log_return"]]


def load_daily_four_group(tree: str) -> pd.DataFrame:
    development = pd.read_parquet(
        ATLAS_ROOT / tree / "development_realized_pnl_ledger.parquet",
        columns=["date", "variant_id", "component_id", "linked_log_contribution"],
    )
    blackbox = pd.read_parquet(
        BLACKBOX_ROOT / tree / "realized_pnl_ledger.parquet",
        columns=["date", "variant_id", "component_id", "linked_log_contribution"],
    )
    frame = pd.concat([development, blackbox], ignore_index=True)
    frame["date"] = pd.to_datetime(frame["date"], errors="raise").dt.normalize()
    if bool(frame["date"].gt(HARD_END).any()) or int(frame["date"].dt.year.min()) < 2011:
        raise PermissionError("k1_only_index_regime_ledger_year_bound")
    if bool(frame["date"].dt.year.eq(2026).any()):
        raise PermissionError("k1_only_index_regime_ledger_read_2026")
    frame["decision_clock"] = frame["variant_id"].astype(str)
    frame["component_group"] = frame["component_id"].replace({"transaction_cost": "other", "cash": "other", "position": "other"})
    grouped = (
        frame.loc[frame["component_group"].isin(GROUPS)]
        .groupby(["date", "decision_clock", "component_group"], sort=True)["linked_log_contribution"]
        .sum()
        .reset_index()
    )
    return grouped.sort_values(["date", "decision_clock", "component_group"], kind="mergesort", ignore_index=True)


def period_four_group(daily: pd.DataFrame, grain: str) -> pd.DataFrame:
    work = daily.copy()
    work["period"] = [period_label(stamp, grain) for stamp in work["date"]]
    work["year"] = work["date"].dt.year.astype(int)
    grouped = (
        work.groupby(["period", "decision_clock", "component_group"], sort=True)
        .agg(
            linked_log_contribution=("linked_log_contribution", "sum"),
            year=("year", "max"),
            last_date=("date", "max"),
            first_date=("date", "min"),
            row_count=("linked_log_contribution", "size"),
        )
        .reset_index()
    )
    grouped["grain"] = grain
    grouped["period_type"] = grain
    return grouped.sort_values(["period", "decision_clock", "component_group"], kind="mergesort", ignore_index=True)


def classify_index_periods(cloudridge: pd.DataFrame, grain: str, *, z: float = FROZEN_Z) -> pd.DataFrame:
    if z != FROZEN_Z:
        raise PermissionError("k1_only_index_regime_z_not_frozen")
    work = cloudridge.copy()
    work["date"] = pd.to_datetime(work["date"], errors="raise").dt.normalize()
    if bool(work["date"].gt(HARD_END).any()):
        raise PermissionError("k1_only_index_regime_classify_2026")
    work = work.sort_values("date", kind="mergesort", ignore_index=True)
    work["log_return"] = pd.to_numeric(work["log_return"], errors="raise")
    work["sigma_pit"] = work["log_return"].shift(1).expanding(min_periods=SIGMA_MIN_PERIODS).std(ddof=0)
    work["period"] = [period_label(stamp, grain) for stamp in work["date"]]
    rows: list[dict[str, object]] = []
    for period, local in work.groupby("period", sort=True):
        local = local.sort_values("date", kind="mergesort")
        first = pd.Timestamp(local["date"].iloc[0])
        last = pd.Timestamp(local["date"].iloc[-1])
        n_days = int(len(local))
        index_log = float(local["log_return"].sum())
        realized_vol = float(local["log_return"].std(ddof=0)) if n_days >= 2 else float("nan")
        sigma = float(local["sigma_pit"].iloc[0])
        band = float("nan") if not np.isfinite(sigma) else float(z * sigma * np.sqrt(n_days))
        if not np.isfinite(band):
            trend = "unresolved"
        elif index_log > band:
            trend = "up"
        elif index_log < -band:
            trend = "down"
        else:
            trend = "sideways"
        rows.append(
            {
                "grain": grain,
                "period": str(period),
                "first_date": first,
                "last_date": last,
                "year": int(last.year),
                "n_days": n_days,
                "index_log_return": index_log,
                "realized_vol": realized_vol,
                "sigma_pit": sigma,
                "band": band,
                "trend": trend,
            }
        )
    panel = pd.DataFrame(rows).sort_values("first_date", kind="mergesort", ignore_index=True)
    panel["vol_threshold"] = panel["realized_vol"].shift(1).expanding(min_periods=VOL_MEDIAN_MIN_PERIODS).median()
    vol = []
    for realized, threshold in zip(panel["realized_vol"].to_numpy(), panel["vol_threshold"].to_numpy(), strict=True):
        if not np.isfinite(realized) or not np.isfinite(threshold):
            vol.append("unresolved")
        elif float(realized) > float(threshold):
            vol.append("high")
        else:
            vol.append("low")
    panel["vol"] = vol
    combined = []
    for trend_name, vol_name in zip(panel["trend"].astype(str), panel["vol"].astype(str), strict=True):
        if trend_name == "unresolved" or vol_name == "unresolved":
            combined.append("unresolved")
        else:
            combined.append(f"{trend_name}_{vol_name}")
    panel["combined"] = combined
    panel["data_role"] = [data_role(int(year)) for year in panel["year"]]
    return panel


def contradiction_from_period(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    rows: list[dict[str, object]] = []
    for (grain, period, clock), local in work.groupby(["grain", "period", "decision_clock"], sort=True):
        values = {name: 0.0 for name in GROUPS}
        for row in local.itertuples(index=False):
            values[str(row.component_group)] = float(row.linked_log_contribution)
        if set(local["component_group"].astype(str)) - set(GROUPS):
            raise PermissionError(f"k1_only_index_regime_unknown_group:{period}")
        ordered = sorted(values.items(), key=lambda item: item[1], reverse=True)
        gain_name, gain_v = ordered[0]
        loss_name, loss_v = ordered[-1]
        year = int(local["year"].max())
        rows.append(
            {
                "grain": grain,
                "period": str(period),
                "decision_clock": str(clock),
                "year": year,
                "data_role": data_role(year),
                "max_gain_factor": LABEL[gain_name] if gain_v > 0.0 else "无正向主因",
                "max_gain_linked_log": gain_v if gain_v > 0.0 else 0.0,
                "max_loss_factor": LABEL[loss_name] if loss_v < 0.0 else "无负向主因",
                "max_loss_linked_log": loss_v if loss_v < 0.0 else 0.0,
                "index_linked_log": values["index"],
                "size_linked_log": values["size"],
                "industry_linked_log": values["industry"],
                "residual_linked_log": values["other"],
            }
        )
    return pd.DataFrame(rows).sort_values(["grain", "period", "decision_clock"], kind="mergesort", ignore_index=True)


def join_period_state(attribution: pd.DataFrame, states: pd.DataFrame) -> pd.DataFrame:
    keep = states.loc[
        :,
        [
            "grain",
            "period",
            "trend",
            "vol",
            "combined",
            "index_log_return",
            "realized_vol",
            "band",
            "n_days",
            "first_date",
            "last_date",
        ],
    ]
    merged = attribution.merge(keep, on=["grain", "period"], how="inner", validate="many_to_one")
    if len(merged) != len(attribution):
        missing = sorted(set(attribution["period"].astype(str)) - set(states["period"].astype(str)))
        raise PermissionError(f"k1_only_index_regime_state_join_gap:{missing[:8]}")
    return merged.sort_values(["grain", "period", "decision_clock"], kind="mergesort", ignore_index=True)


def _rate(frame: pd.DataFrame, *, trend: str, clock: str, field: str, expected: str) -> tuple[float, int]:
    local = frame.loc[
        frame["trend"].eq(trend)
        & frame["decision_clock"].eq(clock)
        & frame["data_role"].eq("development_selection")
        & frame["trend"].ne("unresolved")
    ]
    n = int(len(local))
    if n == 0:
        return float("nan"), 0
    hit = float(local[field].eq(expected).mean())
    return hit, n


def skeleton_score(joined: pd.DataFrame) -> dict[str, object]:
    grain = str(joined["grain"].iloc[0])
    clock_scores: list[float] = []
    detail: dict[str, object] = {"grain": grain, "clocks": {}}
    eligible = True
    for clock in CLOCKS:
        p_up, n_up = _rate(joined, trend="up", clock=clock, field="max_gain_factor", expected="指数")
        p_down, n_down = _rate(joined, trend="down", clock=clock, field="max_loss_factor", expected="指数")
        n_side = int(
            (joined["trend"].eq("sideways") & joined["decision_clock"].eq(clock) & joined["data_role"].eq("development_selection")).sum()
        )
        clock_eligible = n_up >= MIN_TREND_PERIODS and n_down >= MIN_TREND_PERIODS and n_side >= MIN_TREND_PERIODS
        eligible = eligible and clock_eligible
        score = float("nan") if (not np.isfinite(p_up) or not np.isfinite(p_down)) else 0.5 * float(p_up) + 0.5 * float(p_down)
        clock_scores.append(score)
        cast(dict[str, object], detail["clocks"])[clock] = {
            "p_index_max_gain_given_up": None if not np.isfinite(p_up) else float(p_up),
            "n_up": n_up,
            "p_index_max_loss_given_down": None if not np.isfinite(p_down) else float(p_down),
            "n_down": n_down,
            "n_sideways": n_side,
            "eligible": clock_eligible,
            "skeleton_score": None if not np.isfinite(score) else round(float(score), 12),
        }
    mean_score = float(np.mean(clock_scores)) if all(np.isfinite(clock_scores)) else float("nan")
    detail["eligible"] = bool(eligible and np.isfinite(mean_score))
    detail["skeleton_score"] = None if not np.isfinite(mean_score) else round(float(mean_score), 12)
    detail["passes_skeleton_bar"] = bool(detail["eligible"]) and np.isfinite(mean_score) and float(mean_score) >= SKELETON_BAR
    return detail


def select_grain(family_scores: list[dict[str, object]]) -> dict[str, object]:
    passed = [row for row in family_scores if bool(row.get("passes_skeleton_bar"))]
    if not passed:
        return {
            "selected_grain": None,
            "status": "blocked_no_explanatory_frequency",
            "tie_break": "coarser_grain",
            "skeleton_bar": SKELETON_BAR,
        }
    best_score = max(float(cast(float, row["skeleton_score"])) for row in passed)
    tied = [row for row in passed if float(cast(float, row["skeleton_score"])) == best_score]
    chosen = max(tied, key=lambda row: GRAIN_COARSENESS[str(row["grain"])])
    return {
        "selected_grain": chosen["grain"],
        "status": "passed_selected_on_2011_2016_only",
        "selected_skeleton_score": chosen["skeleton_score"],
        "tie_break": "coarser_grain",
        "skeleton_bar": SKELETON_BAR,
        "n_tied": len(tied),
    }


def regime_summary(joined: pd.DataFrame, *, role: str | None = None) -> pd.DataFrame:
    work = joined.copy()
    if role is not None:
        work = work.loc[work["data_role"].eq(role)]
    rows: list[dict[str, object]] = []
    for (clock, combined), local in work.groupby(["decision_clock", "combined"], sort=True):
        if str(combined) == "unresolved":
            continue
        values = {
            "index": float(local["index_linked_log"].sum()),
            "size": float(local["size_linked_log"].sum()),
            "industry": float(local["industry_linked_log"].sum()),
            "other": float(local["residual_linked_log"].sum()),
        }
        ordered = sorted(values.items(), key=lambda item: item[1], reverse=True)
        gain_name, gain_v = ordered[0]
        loss_name, loss_v = ordered[-1]
        rows.append(
            {
                "grain": str(local["grain"].iloc[0]),
                "data_role": role or "all_roles",
                "decision_clock": str(clock),
                "combined": str(combined),
                "combined_label": LABEL.get(str(combined), str(combined)),
                "n_periods": int(len(local)),
                "max_gain_factor": LABEL[gain_name] if gain_v > 0.0 else "无正向主因",
                "max_gain_linked_log": gain_v if gain_v > 0.0 else 0.0,
                "max_loss_factor": LABEL[loss_name] if loss_v < 0.0 else "无负向主因",
                "max_loss_linked_log": loss_v if loss_v < 0.0 else 0.0,
                "index_linked_log": values["index"],
                "size_linked_log": values["size"],
                "industry_linked_log": values["industry"],
                "residual_linked_log": values["other"],
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[
                "grain",
                "data_role",
                "decision_clock",
                "combined",
                "combined_label",
                "n_periods",
                "max_gain_factor",
                "max_gain_linked_log",
                "max_loss_factor",
                "max_loss_linked_log",
                "index_linked_log",
                "size_linked_log",
                "industry_linked_log",
                "residual_linked_log",
            ]
        )
    return pd.DataFrame(rows).sort_values(["decision_clock", "combined"], kind="mergesort", ignore_index=True)


def episode_atlas(states: pd.DataFrame, *, role: str = "development_selection") -> pd.DataFrame:
    work = states.loc[states["data_role"].eq(role) & states["combined"].ne("unresolved")].sort_values("first_date", kind="mergesort")
    if work.empty:
        return pd.DataFrame()
    episode_id = (work["combined"] != work["combined"].shift(1)).cumsum()
    grouped = work.groupby(["combined", episode_id], sort=True)
    rows: list[dict[str, object]] = []
    for (combined, _eid), local in grouped:
        rows.append(
            {
                "combined": str(combined),
                "combined_label": LABEL.get(str(combined), str(combined)),
                "start": str(pd.Timestamp(local["first_date"].iloc[0]).date()),
                "end": str(pd.Timestamp(local["last_date"].iloc[-1]).date()),
                "n_periods": int(len(local)),
                "index_log_return": float(local["index_log_return"].sum()),
            }
        )
    episodes = pd.DataFrame(rows)
    summary = (
        episodes.groupby(["combined", "combined_label"], sort=True)
        .agg(
            independent_episode_count=("n_periods", "size"),
            total_periods=("n_periods", "sum"),
            mean_duration_periods=("n_periods", "mean"),
            index_log_return=("index_log_return", "sum"),
        )
        .reset_index()
    )
    n_years = 6.0
    summary["episodes_per_year"] = summary["independent_episode_count"] / n_years
    routes = []
    for count, rate in zip(summary["independent_episode_count"].to_numpy(), summary["episodes_per_year"].to_numpy(), strict=True):
        if int(count) < 2:
            routes.append("diagnostic_only")
        elif int(count) < 8 or float(rate) < 1.0:
            routes.append("slow_context_low_rank_modulator")
        elif float(rate) < 4.0:
            routes.append("continuous_context_shared_dynamics")
        else:
            routes.append("identified_repeated_state")
    summary["learnability_route"] = routes
    summary["data_role"] = role
    return summary.sort_values("combined", kind="mergesort", ignore_index=True)


def pit_followability(joined: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for clock, local in joined.groupby("decision_clock", sort=True):
        local = local.sort_values("first_date", kind="mergesort").copy()
        local["prev_trend"] = local["trend"].shift(1)
        take = local.loc[
            local["data_role"].eq("development_selection") & local["prev_trend"].isin(TRENDS) & local["trend"].ne("unresolved")
        ]
        for prev in TRENDS:
            block = take.loc[take["prev_trend"].eq(prev)]
            n = int(len(block))
            if prev == "up":
                hit = float(block["max_gain_factor"].eq("指数").mean()) if n else float("nan")
                field = "p_index_max_gain"
            elif prev == "down":
                hit = float(block["max_loss_factor"].eq("指数").mean()) if n else float("nan")
                field = "p_index_max_loss"
            else:
                hit = float(block["max_gain_factor"].isin(["行业", "个股残差"]).mean()) if n else float("nan")
                field = "p_industry_or_residual_max_gain"
            rows.append(
                {
                    "decision_clock": str(clock),
                    "previous_trend": prev,
                    "n_periods": n,
                    "metric": field,
                    "rate": hit,
                    "data_role": "development_selection",
                    "lagged": True,
                }
            )
    return pd.DataFrame(rows)


def hypothesis_checks(joined: pd.DataFrame, *, role: str) -> list[dict[str, object]]:
    work = joined.loc[joined["data_role"].eq(role) & joined["combined"].ne("unresolved")]
    rows: list[dict[str, object]] = []
    for clock in CLOCKS:
        local = work.loc[work["decision_clock"].eq(clock)]

        def _p(clock_frame: pd.DataFrame, mask: pd.Series, field: str, expected: str) -> tuple[float, int]:
            block = clock_frame.loc[mask]
            n = int(len(block))
            return (float(block[field].eq(expected).mean()) if n else float("nan"), n)

        p_up, n_up = _p(local, local["trend"].eq("up"), "max_gain_factor", "指数")
        p_down, n_down = _p(local, local["trend"].eq("down"), "max_loss_factor", "指数")
        p_ind_side, n_ind_side = _p(local, local["combined"].eq("sideways_low"), "max_gain_factor", "行业")
        p_ind_up, n_ind_up = _p(local, local["trend"].eq("up"), "max_gain_factor", "行业")
        p_ind_down, n_ind_down = _p(local, local["trend"].eq("down"), "max_gain_factor", "行业")
        p_res_down, n_res_down = _p(local, local["trend"].eq("down"), "max_gain_factor", "个股残差")
        p_size_down, n_size_down = _p(local, local["trend"].eq("down"), "max_gain_factor", "规模")
        p_res_side, n_res_side = _p(local, local["combined"].eq("sideways_low"), "max_gain_factor", "个股残差")
        p_res_up_high, n_res_up_high = _p(local, local["combined"].eq("up_high"), "max_loss_factor", "个股残差")
        rows.extend(
            [
                {
                    "data_role": role,
                    "decision_clock": clock,
                    "hypothesis": "H1_skeleton_up_index_gain",
                    "rate": p_up,
                    "n": n_up,
                },
                {
                    "data_role": role,
                    "decision_clock": clock,
                    "hypothesis": "H1_skeleton_down_index_loss",
                    "rate": p_down,
                    "n": n_down,
                },
                {
                    "data_role": role,
                    "decision_clock": clock,
                    "hypothesis": "H2_industry_gain_sideways_low",
                    "rate": p_ind_side,
                    "n": n_ind_side,
                },
                {
                    "data_role": role,
                    "decision_clock": clock,
                    "hypothesis": "H2_industry_gain_up",
                    "rate": p_ind_up,
                    "n": n_ind_up,
                },
                {
                    "data_role": role,
                    "decision_clock": clock,
                    "hypothesis": "H2_industry_gain_down",
                    "rate": p_ind_down,
                    "n": n_ind_down,
                },
                {
                    "data_role": role,
                    "decision_clock": clock,
                    "hypothesis": "H3_residual_gain_down",
                    "rate": p_res_down,
                    "n": n_res_down,
                },
                {
                    "data_role": role,
                    "decision_clock": clock,
                    "hypothesis": "H3_size_gain_down",
                    "rate": p_size_down,
                    "n": n_size_down,
                },
                {
                    "data_role": role,
                    "decision_clock": clock,
                    "hypothesis": "H4_residual_gain_sideways_low",
                    "rate": p_res_side,
                    "n": n_res_side,
                },
                {
                    "data_role": role,
                    "decision_clock": clock,
                    "hypothesis": "H5_residual_loss_up_high",
                    "rate": p_res_up_high,
                    "n": n_res_up_high,
                },
            ]
        )
    return rows


def replay_quarterly_atlas(daily: pd.DataFrame, tree: str) -> float:
    current = period_four_group(daily, "quarterly")
    sealed = pd.read_csv(ATLAS_ROOT / tree / "four_group_quarterly.csv")
    sealed["period"] = sealed["period"].astype(str)
    merged = current.merge(
        sealed.loc[:, ["period", "decision_clock", "component_group", "linked_log_contribution"]],
        on=["period", "decision_clock", "component_group"],
        suffixes=("_now", "_atlas"),
        validate="one_to_one",
    )
    if len(merged) != len(current) or len(merged) != len(sealed):
        raise RuntimeError("k1_only_index_regime_quarterly_coverage_mismatch")
    error = float(
        np.max(
            np.abs(
                pd.to_numeric(merged["linked_log_contribution_now"], errors="raise").to_numpy(np.float64)
                - pd.to_numeric(merged["linked_log_contribution_atlas"], errors="raise").to_numpy(np.float64)
            )
        )
    )
    if error > 1.0e-10:
        raise RuntimeError(f"k1_only_index_regime_quarterly_replay_drift:{error}")
    return error


def execute_tree(*, tree: str, output_root: Path) -> dict[str, object]:
    if tree not in {"formal", "isolated"}:
        raise PermissionError("k1_only_index_regime_tree_invalid")
    if output_root.exists():
        raise FileExistsError(output_root)
    contract = load_contract()
    assert_no_scientific_wall_clock(contract)
    cloudridge = load_cloudridge(tree)
    daily = load_daily_four_group(tree)
    quarterly_error = replay_quarterly_atlas(daily, tree)
    family_scores: list[dict[str, object]] = []
    joined_by_grain: dict[str, pd.DataFrame] = {}
    for grain in GRAINS:
        states = classify_index_periods(cloudridge, grain)
        attribution = contradiction_from_period(period_four_group(daily, grain))
        joined = join_period_state(attribution, states)
        if bool(joined["year"].ge(2026).any()):
            raise PermissionError("k1_only_index_regime_joined_2026")
        family_scores.append(skeleton_score(joined))
        joined_by_grain[grain] = joined
    selection = select_grain(family_scores)
    selected = selection["selected_grain"]
    output_root.mkdir(parents=True)
    write_json(
        output_root / "family_scores.json",
        {
            "schema_id": "factorlab.reaka_k1_only_index_regime_family_scores@1.0",
            "selection_year_min": SELECTION_YEAR_MIN,
            "selection_year_max": SELECTION_YEAR_MAX,
            "rows": family_scores,
        },
    )
    write_json(output_root / "selection.json", selection)
    if selected is None:
        result = {
            "schema_id": "factorlab.reaka_k1_only_index_regime_atlas_result@1.0",
            "tree": tree,
            "trading_identity": "K1_only",
            "status": selection["status"],
            "selected_grain": None,
            "industry_split": False,
            "account_replayed": False,
            "strategy_overlay_applied": False,
            "new_factor_search_executed": False,
            "quarterly_replay_max_abs_error": quarterly_error,
            "fresh_oos": False,
            "production_authority": False,
            "contract_digest": contract["canonical_digest"],
        }
        written = write_json(output_root / "result.json", result)
        assert_no_scientific_wall_clock(written)
        return written
    joined = joined_by_grain[str(selected)]
    states = classify_index_periods(cloudridge, str(selected))
    summaries = pd.concat(
        [
            regime_summary(joined, role="development_selection"),
            regime_summary(joined, role="development_listing"),
            regime_summary(joined, role="consumed_blackbox_diagnostic"),
        ],
        ignore_index=True,
    )
    episodes = episode_atlas(states)
    follow = pit_followability(joined)
    checks = pd.DataFrame(
        hypothesis_checks(joined, role="development_selection")
        + hypothesis_checks(joined, role="development_listing")
        + hypothesis_checks(joined, role="consumed_blackbox_diagnostic")
    )
    joined.to_csv(output_root / "period_states.csv", index=False)
    summaries.to_csv(output_root / "regime_summary.csv", index=False)
    episodes.to_csv(output_root / "episode_atlas.csv", index=False)
    follow.to_csv(output_root / "pit_followability.csv", index=False)
    checks.to_csv(output_root / "hypothesis_checks.csv", index=False)
    states.to_csv(output_root / "index_states.csv", index=False)
    result = {
        "schema_id": "factorlab.reaka_k1_only_index_regime_atlas_result@1.0",
        "tree": tree,
        "trading_identity": "K1_only",
        "status": selection["status"],
        "selected_grain": selected,
        "selected_skeleton_score": selection.get("selected_skeleton_score"),
        "industry_split": False,
        "account_replayed": False,
        "strategy_overlay_applied": False,
        "new_factor_search_executed": False,
        "state_pairing_executed": False,
        "period_row_count": int(len(joined)),
        "quarterly_replay_max_abs_error": quarterly_error,
        "fresh_oos": False,
        "production_authority": False,
        "contract_digest": contract["canonical_digest"],
    }
    written = write_json(output_root / "result.json", result)
    assert_no_scientific_wall_clock(written)
    return written


__all__ = [
    "classify_index_periods",
    "contradiction_from_period",
    "execute_tree",
    "load_contract",
    "period_label",
    "select_grain",
    "skeleton_score",
    "source_closure",
]
