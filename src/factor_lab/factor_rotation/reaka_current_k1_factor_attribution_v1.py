# pyright: reportAny=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportGeneralTypeIssues=false
# pyright: reportAttributeAccessIssue=false, reportIndexIssue=false
# pyright: reportArgumentType=false, reportReturnType=false
# pyright: reportCallIssue=false, reportOperatorIssue=false
"""Current REAKA K1 2019/2020 factor and score attribution.

The module keeps two questions physically separate:

1. realised account P&L is decomposed on the frozen K1 exposure matrix into
   market, size, industry, idiosyncratic residual, and transaction cost;
2. the frozen neural score is decomposed by exact four-group coalition
   Shapley over residual history, market, size, and industry inputs.

It never trains, changes a checkpoint, reads post-2020 rows, or creates a
candidate strategy.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, cast

import numpy as np
import pandas as pd
import torch
from numpy.typing import NDArray
from scipy.stats import rankdata, spearmanr

from factor_lab.factor_rotation.reaka_intraday_k1_fit_prefix_successor_v1 import (
    FIXED_CONFIG,
)
from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (
    CLOCK_SUFFIX,
    IntradayK1InputStore,
    normalize_batch,
    read_json,
)
from factor_lab.factor_rotation.reaka_intraday_k1_training_v1 import (
    SEEDS_FORMAL,
    build_model,
    load_state_tree,
)
from factor_lab.factor_rotation.reaka_stage6_daily_engine import Stage6ReakaModel
from factor_lab.governance.canonicalization import canonical_digest

ROOT: Final = Path(__file__).resolve().parents[3]
CONTRACT_PATH: Final = ROOT / "docs/ops/reaka_current_k1_2019_2020_factor_attribution@1.2.json"
ACCOUNT_ROOT: Final = (
    ROOT
    / "output/factor-rotation/reaka_intraday_portfolio_mapping_account_v2_2009_2020/annual_sessions"
)
INPUT_ROOT: Final = ROOT / "output/factor-rotation/reaka_intraday_portfolio_mapping_inputs_v2_2011_2020"
STORE_ROOT: Final = ROOT / "output/factor-rotation/reaka_intraday_K1_input_v1_2009_2020"
CHECKPOINT_ROOT: Final = (
    ROOT / "output/factor-rotation/reaka_intraday_K1_fit_prefix_successor_v1_2011_2017"
)
NORMALIZER_ROOT: Final = (
    ROOT / "docs/ops/evidence/reaka_intraday_K1_preflight_v1_20260831/preflight"
)

SCHEMA_ID: Final = "factorlab.reaka_current_K1_factor_attribution@1.0"
YEARS: Final = (2019, 2020)
CLOCKS: Final = ("14:30", "14:45")
SLIPPAGE_MULTIPLIERS: Final = (1.0, 2.0, 3.0)
POLICY_ID: Final = "N30_equal_backfill_unconstrained"
GROUPS: Final = ("residual_history", "market", "size", "industry")
RETURN_GROUPS: Final = ("market", "size", "industry", "idiosyncratic_residual", "transaction_cost")
SCIENTIFIC_FILES: Final = (
    "factor_input_inventory.json",
    "score_group_influence.csv",
    "daily_return_attribution.csv",
    "annual_attribution.csv",
    "result.json",
)


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _with_digest(payload: Mapping[str, object]) -> dict[str, object]:
    output = dict(payload)
    _ = output.pop("canonical_digest", None)
    output["canonical_digest"] = canonical_digest(output)
    return output


def write_json(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    output = _with_digest(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, lineterminator="\n", float_format="%.17g")


def factor_input_inventory(factor_ids: Sequence[str]) -> dict[str, object]:
    values = tuple(str(value) for value in factor_ids)
    market = tuple(value for value in values if value == "orthogonal_market_cloudridge_v1")
    size = tuple(value for value in values if value == "orthogonal_size_small_minus_large_v1")
    industries = tuple(value for value in values if value.startswith("L1_FACTOR_CORE:"))
    known = set(market) | set(size) | set(industries)
    unknown = tuple(value for value in values if value not in known)
    if len(values) != 14 or len(market) != 1 or len(size) != 1 or len(industries) != 12 or unknown:
        raise ValueError("current_K1_factor_inventory_invalid")
    return _with_digest(
        {
            "schema_id": "factorlab.reaka_current_K1_factor_input_inventory@1.0",
            "factor_count": len(values),
            "market_factor_ids": list(market),
            "size_factor_ids": list(size),
            "industry_factor_ids": list(industries),
            "quant_or_volume_price_input_ids": [],
            "quant_or_volume_price_input_count": 0,
            "residual_history_is_model_input": True,
            "residual_history_is_not_a_registered_factor_block": True,
            "feature_layout": {
                "state": "0:14",
                "state_mask": "14:28",
                "beta": "28:42",
                "reliability": "42:56",
                "exposure_mask": "56:70",
                "age": "70:71",
            },
            "production_authority": False,
        }
    )


def coalition_feature_batch(
    returns: NDArray[np.float32],
    features: NDArray[np.float32],
) -> tuple[NDArray[np.float32], NDArray[np.float32]]:
    """Build all sixteen result-free input coalitions in mask order 0..15."""

    if returns.ndim != 2 or features.ndim != 3 or features.shape[:2] != returns.shape:
        raise ValueError("current_K1_coalition_input_shape_invalid")
    if features.shape[2] != 71:
        raise ValueError("current_K1_coalition_feature_width_invalid")
    batch, points = returns.shape
    coalition_returns = np.zeros((16, batch, points), dtype=np.float32)
    coalition_features = np.zeros((16, batch, points, 71), dtype=np.float32)
    # Age is a structural channel and is all-zero in the current identity.
    coalition_features[..., 70] = features[None, ..., 70]
    ranges = {
        1: (0, 0),
        2: (1, 1),
        3: (2, 13),
    }
    for mask in range(16):
        if mask & 1:
            coalition_returns[mask] = returns
        for bit, (first, last) in ranges.items():
            if not mask & (1 << bit):
                continue
            for offset in (0, 14, 28, 42, 56):
                coalition_features[mask, :, :, offset + first : offset + last + 1] = features[
                    :, :, offset + first : offset + last + 1
                ]
    return coalition_returns, coalition_features


def exact_group_shapley(values: NDArray[np.float64]) -> NDArray[np.float64]:
    """Return exact four-player Shapley values from coalition values [16, n]."""

    if values.ndim != 2 or values.shape[0] != 16:
        raise ValueError("current_K1_shapley_value_shape_invalid")
    output = np.zeros((4, values.shape[1]), dtype=np.float64)
    factorial = math.factorial
    denominator = float(factorial(4))
    for group in range(4):
        bit = 1 << group
        for mask in range(16):
            if mask & bit:
                continue
            size = int(mask.bit_count())
            weight = factorial(size) * factorial(3 - size) / denominator
            output[group] += weight * (values[mask | bit] - values[mask])
    return output


def per_decision_rank_z(scores: NDArray[np.float64], decision_keys: NDArray[np.int64]) -> NDArray[np.float64]:
    output = np.zeros_like(scores, dtype=np.float64)
    for key in np.unique(decision_keys):
        local = decision_keys == key
        ranks = rankdata(scores[local], method="average")
        centered = ranks - ranks.mean()
        output[local] = centered / max(float(centered.std(ddof=0)), 1.0e-12)
    return output


def _top_symbols(scores: NDArray[np.float64], symbols: NDArray[np.str_], count: int = 30) -> set[str]:
    order = np.lexsort((symbols.astype(str), -scores))
    return set(symbols[order[:count]].astype(str))


def score_group_influence(
    *,
    store: IntradayK1InputStore,
    normalizer: Mapping[str, object],
    checkpoint_root: Path,
    year: int,
    device: torch.device,
    score_panel: pd.DataFrame,
    batch_size: int = 2048,
) -> tuple[pd.DataFrame, dict[str, object]]:
    years = np.asarray(store.inference_rows[:, 2], dtype=np.int64)
    indices = np.flatnonzero(years == year).astype(np.int64)
    if not len(indices):
        raise ValueError("current_K1_attribution_year_has_no_score_rows")
    rows = np.asarray(store.inference_rows[indices], dtype=np.int64)
    day_keys = rows[:, 0]
    row_symbols = np.asarray(store.symbols[rows[:, 1]]).astype(str)
    raw = np.empty((len(SEEDS_FORMAL), 16, len(indices)), dtype=np.float64)
    models: list[Stage6ReakaModel] = []
    for seed in SEEDS_FORMAL:
        model = build_model(FIXED_CONFIG, seed=seed).to(device).eval()
        load_state_tree(model, checkpoint_root / f"seed_{seed}")
        models.append(model)
    with torch.no_grad():
        for start in range(0, len(indices), batch_size):
            take = indices[start : start + batch_size]
            historical, features = store.assemble_inputs(take)
            returns, normalized = normalize_batch(historical, features, normalizer)
            coalition_returns, coalition_features = coalition_feature_batch(returns, normalized)
            shape = coalition_returns.shape
            return_tensor = torch.from_numpy(coalition_returns.reshape(shape[0] * shape[1], shape[2])).to(device)
            feature_tensor = torch.from_numpy(
                coalition_features.reshape(shape[0] * shape[1], shape[2], coalition_features.shape[-1])
            ).to(device)
            for seed_position, model in enumerate(models):
                forecast = model.forecast(return_tensor, feature_tensor)
                values = forecast.scores.detach().cpu().numpy().reshape(16, shape[1])
                raw[seed_position, :, start : start + len(take)] = values
    coalition_values = np.empty((16, len(indices)), dtype=np.float64)
    for mask in range(16):
        ranked = [per_decision_rank_z(raw[seed, mask], day_keys) for seed in range(len(SEEDS_FORMAL))]
        coalition_values[mask] = np.mean(np.vstack(ranked), axis=0)
    shapley = exact_group_shapley(coalition_values)
    if not np.allclose(shapley.sum(axis=0), coalition_values[15] - coalition_values[0], atol=1.0e-10, rtol=0.0):
        raise RuntimeError("current_K1_shapley_additivity_failed")

    panel = score_panel.copy()
    panel["decision_date"] = pd.to_datetime(panel["decision_date"])
    expected = pd.DataFrame(
        {
            "decision_date": pd.DatetimeIndex(store.calendar[day_keys]),
            "symbol": row_symbols,
            "replayed_score": coalition_values[15],
        }
    )
    joined = expected.merge(
        panel[["decision_date", "symbol", "score"]],
        on=["decision_date", "symbol"],
        how="left",
        validate="one_to_one",
    )
    if joined["score"].isna().any():
        raise ValueError("current_K1_score_replay_panel_join_failed")
    score_max_error = float(np.max(np.abs(joined["score"].to_numpy(float) - joined["replayed_score"].to_numpy(float))))

    full_top = np.zeros(len(indices), dtype=bool)
    top30_mismatches = 0
    group_jaccards: dict[str, list[float]] = {group: [] for group in GROUPS}
    group_spearman: dict[str, list[float]] = {group: [] for group in GROUPS}
    for day in np.unique(day_keys):
        local = day_keys == day
        full = _top_symbols(coalition_values[15, local], row_symbols[local])
        panel_local = joined.loc[joined["decision_date"].eq(pd.Timestamp(store.calendar[day]))]
        panel_top = _top_symbols(panel_local["score"].to_numpy(float), panel_local["symbol"].to_numpy(str))
        if full != panel_top:
            top30_mismatches += 1
        full_top[np.flatnonzero(local)[np.isin(row_symbols[local], list(full))]] = True
        for group_position, group in enumerate(GROUPS):
            removed_mask = 15 ^ (1 << group_position)
            removed = _top_symbols(coalition_values[removed_mask, local], row_symbols[local])
            union = full | removed
            group_jaccards[group].append(len(full & removed) / len(union) if union else 1.0)
            statistic = float(spearmanr(coalition_values[15, local], coalition_values[removed_mask, local]).statistic)
            group_spearman[group].append(statistic)

    absolute_all = np.abs(shapley).mean(axis=1)
    absolute_top = np.abs(shapley[:, full_top]).mean(axis=1)
    all_denominator = max(float(absolute_all.sum()), 1.0e-12)
    top_denominator = max(float(absolute_top.sum()), 1.0e-12)
    influence_rows: list[dict[str, object]] = []
    for position, group in enumerate(GROUPS):
        influence_rows.append(
            {
                "year": year,
                "group": group,
                "all_row_mean_abs_shapley": float(absolute_all[position]),
                "all_row_abs_share": float(absolute_all[position] / all_denominator),
                "top30_mean_abs_shapley": float(absolute_top[position]),
                "top30_abs_share": float(absolute_top[position] / top_denominator),
                "top30_mean_signed_shapley": float(shapley[position, full_top].mean()),
                "leave_group_out_mean_daily_spearman": float(np.mean(group_spearman[group])),
                "leave_group_out_mean_top30_jaccard": float(np.mean(group_jaccards[group])),
            }
        )
    diagnostics = {
        "row_count": len(indices),
        "decision_count": int(len(np.unique(day_keys))),
        "score_replay_max_abs_error": score_max_error,
        "score_replay_top30_mismatch_decisions": top30_mismatches,
        "shapley_additivity_max_abs_error": float(
            np.max(np.abs(shapley.sum(axis=0) - (coalition_values[15] - coalition_values[0])))
        ),
        "coalition_count": 16,
        "seed_count": len(SEEDS_FORMAL),
    }
    return pd.DataFrame(influence_rows), diagnostics


@dataclass(frozen=True, slots=True)
class SegmentFit:
    coefficient: NDArray[np.float64]
    rank: int
    condition_number: float
    observation_count: int


def fit_factor_segment(exposures: NDArray[np.float64], returns: NDArray[np.float64]) -> SegmentFit:
    if exposures.ndim != 2 or exposures.shape[1] != 14 or returns.shape != (len(exposures),):
        raise ValueError("current_K1_factor_segment_shape_invalid")
    valid = np.isfinite(returns) & np.isfinite(exposures).all(axis=1)
    design = exposures[valid]
    target = returns[valid]
    rank = int(np.linalg.matrix_rank(design)) if len(design) else 0
    if rank != 14:
        raise ValueError("current_K1_factor_segment_rank_deficient")
    condition = float(np.linalg.cond(design))
    if not math.isfinite(condition) or condition > 1.0e8:
        raise ValueError("current_K1_factor_segment_condition_failed")
    coefficient, *_ = np.linalg.lstsq(design, target, rcond=None)
    return SegmentFit(
        coefficient=np.asarray(coefficient, dtype=np.float64),
        rank=rank,
        condition_number=condition,
        observation_count=len(target),
    )


def linked_log_contributions(simple: Mapping[str, float], daily_return: float) -> dict[str, float]:
    total = float(sum(simple.values()))
    if abs(total - daily_return) > 1.0e-10:
        raise ValueError("current_K1_daily_simple_contribution_identity_failed")
    if daily_return <= -1.0:
        raise ValueError("current_K1_daily_return_below_minus_one")
    scale = math.log1p(daily_return) / daily_return if abs(daily_return) > 1.0e-15 else 1.0
    output = {key: float(value * scale) for key, value in simple.items()}
    if abs(sum(output.values()) - math.log1p(daily_return)) > 1.0e-12:
        raise RuntimeError("current_K1_daily_log_contribution_identity_failed")
    return output


def _market_year(clock: str, tree: str, year: int) -> pd.DataFrame:
    suffix = CLOCK_SUFFIX[clock]
    path = INPUT_ROOT / tree / f"daily_market_panel_{suffix}.parquet"
    columns = [
        "date",
        "symbol",
        "previous_tradable_close",
        "hfq_price_multiplier",
        "accounting_execution_price",
        "accounting_close_price",
    ]
    start = pd.Timestamp(f"{year}-01-01")
    end = pd.Timestamp(f"{year}-12-31")
    frame = pd.read_parquet(
        path,
        columns=columns,
        filters=[("date", ">=", start), ("date", "<=", end)],
    )
    frame["date"] = pd.to_datetime(frame["date"])
    frame["accounting_previous_close"] = pd.to_numeric(
        frame["previous_tradable_close"], errors="coerce"
    ).to_numpy(np.float64) * pd.to_numeric(
        frame["hfq_price_multiplier"], errors="coerce"
    ).to_numpy(np.float64)
    return frame.sort_values(["date", "symbol"], kind="mergesort", ignore_index=True)


def _account_frame(path: Path, name: str, *, clock: str, slip: float) -> pd.DataFrame:
    return pd.read_parquet(
        path / name,
        filters=[
            ("policy_id", "==", POLICY_ID),
            ("decision_clock", "==", clock),
            ("slippage_multiplier", "==", slip),
        ],
    )


def _exposure_index(store: IntradayK1InputStore, day: pd.Timestamp, *, before_current: bool) -> int:
    calendar = pd.DatetimeIndex(store.calendar)
    matches = np.flatnonzero(calendar == day)
    if len(matches) != 1:
        raise ValueError("current_K1_attribution_day_not_in_calendar")
    day_position = int(matches[0])
    side = "left" if before_current else "right"
    index = int(np.searchsorted(store.exposure_decision_positions, day_position, side=side) - 1)
    if index < 0:
        raise ValueError("current_K1_attribution_exposure_prefix_missing")
    return index


def _fit_for_prices(
    market: pd.DataFrame,
    *,
    start_column: str,
    end_column: str,
    store: IntradayK1InputStore,
    exposure_index: int,
) -> SegmentFit:
    local = market[["symbol", start_column, end_column]].dropna().copy()
    local = local.loc[(local[start_column] > 0.0) & (local[end_column] > 0.0)]
    symbol_positions = {str(symbol): position for position, symbol in enumerate(store.symbols.astype(str))}
    local["symbol_position"] = local["symbol"].astype(str).map(symbol_positions)
    local = local.dropna(subset=["symbol_position"])
    positions = local["symbol_position"].to_numpy(np.int64)
    available = np.asarray(store.exposure_available[exposure_index, positions], dtype=bool).any(axis=1)
    local = local.loc[available]
    positions = positions[available]
    returns = local[end_column].to_numpy(np.float64) / local[start_column].to_numpy(np.float64) - 1.0
    exposures = np.asarray(store.stock_factor_exposures[exposure_index, positions], dtype=np.float64)
    return fit_factor_segment(exposures, returns)


def _piece_contribution(
    *,
    symbol: str,
    start_value: float,
    actual_return: float,
    fit: SegmentFit,
    store: IntradayK1InputStore,
    exposure_index: int,
    symbol_positions: Mapping[str, int],
) -> dict[str, float]:
    position = symbol_positions.get(symbol)
    if position is None or not bool(np.asarray(store.exposure_available[exposure_index, position], dtype=bool).any()):
        return {"market": 0.0, "size": 0.0, "industry": 0.0, "idiosyncratic_residual": start_value * actual_return}
    exposure = np.asarray(store.stock_factor_exposures[exposure_index, position], dtype=np.float64)
    fitted = exposure * fit.coefficient
    return {
        "market": float(start_value * fitted[0]),
        "size": float(start_value * fitted[1]),
        "industry": float(start_value * fitted[2:].sum()),
        "idiosyncratic_residual": float(start_value * (actual_return - fitted.sum())),
    }


def account_return_attribution(
    *,
    tree: str,
    year: int,
    clock: str,
    slip: float,
    store: IntradayK1InputStore,
    market: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    account_root = ACCOUNT_ROOT / str(year) / tree
    prior_root = ACCOUNT_ROOT / str(year - 1) / tree
    daily = _account_frame(account_root, "portfolio_daily.parquet", clock=clock, slip=slip).sort_values("date")
    holdings = _account_frame(account_root, "holdings.parquet", clock=clock, slip=slip)
    prior_holdings = _account_frame(prior_root, "holdings.parquet", clock=clock, slip=slip)
    trades = _account_frame(account_root, "trades.parquet", clock=clock, slip=slip)
    prior_day = pd.Timestamp(prior_holdings["date"].max())
    prior_holdings = prior_holdings.loc[pd.to_datetime(prior_holdings["date"]).eq(prior_day)]
    holdings["date"] = pd.to_datetime(holdings["date"])
    trades["date"] = pd.to_datetime(trades["date"])
    market_groups = {pd.Timestamp(day): frame.set_index("symbol") for day, frame in market.groupby("date", sort=True)}
    holding_groups = {pd.Timestamp(day): frame.set_index("symbol") for day, frame in holdings.groupby("date", sort=True)}
    trade_groups = {pd.Timestamp(day): frame for day, frame in trades.groupby("date", sort=True)}
    prior_frame = prior_holdings.set_index("symbol")
    symbol_positions = {str(symbol): position for position, symbol in enumerate(store.symbols.astype(str))}
    rows: list[dict[str, object]] = []
    maximum_closure_error = 0.0
    maximum_condition = 0.0
    minimum_rank = 14
    for day_number, daily_row in enumerate(daily.itertuples(index=False)):
        day = pd.Timestamp(daily_row.date)
        current = holding_groups.get(day, pd.DataFrame()).copy()
        if day_number == 0:
            previous = prior_frame.copy()
            previous_nav = float(daily_row.nav) / (1.0 + float(daily_row.daily_return))
        else:
            previous_day = pd.Timestamp(daily.iloc[day_number - 1]["date"])
            previous = holding_groups.get(previous_day, pd.DataFrame()).copy()
            previous_nav = float(daily.iloc[day_number - 1]["nav"])
        day_market = market_groups[day]
        is_rebalance = bool(daily_row.is_rebalance)
        pre_index = _exposure_index(store, day, before_current=is_rebalance)
        post_index = _exposure_index(store, day, before_current=False)
        full_fit = _fit_for_prices(
            day_market.reset_index(),
            start_column="accounting_previous_close",
            end_column="accounting_close_price",
            store=store,
            exposure_index=pre_index,
        )
        pre_fit = full_fit
        post_fit = full_fit
        if is_rebalance:
            pre_fit = _fit_for_prices(
                day_market.reset_index(),
                start_column="accounting_previous_close",
                end_column="accounting_execution_price",
                store=store,
                exposure_index=pre_index,
            )
            post_fit = _fit_for_prices(
                day_market.reset_index(),
                start_column="accounting_execution_price",
                end_column="accounting_close_price",
                store=store,
                exposure_index=post_index,
            )
        for fit in (full_fit, pre_fit, post_fit):
            maximum_condition = max(maximum_condition, fit.condition_number)
            minimum_rank = min(minimum_rank, fit.rank)
        q0 = {str(symbol): float(value) for symbol, value in previous.get("shares", pd.Series(dtype=float)).items()}
        p0 = {str(symbol): float(value) for symbol, value in previous.get("mark_price", pd.Series(dtype=float)).items()}
        q1 = {str(symbol): float(value) for symbol, value in current.get("shares", pd.Series(dtype=float)).items()}
        p1 = {str(symbol): float(value) for symbol, value in current.get("mark_price", pd.Series(dtype=float)).items()}
        traded = set(trade_groups.get(day, pd.DataFrame()).get("symbol", pd.Series(dtype=str)).astype(str))
        simple = {group: 0.0 for group in RETURN_GROUPS}

        def add_piece(
            symbol: str,
            quantity: float,
            start_price: float,
            end_price: float,
            fit: SegmentFit,
            exposure_index: int,
            nav_value: float,
            accumulator: dict[str, float],
        ) -> None:
            if quantity == 0.0 or not (math.isfinite(start_price) and math.isfinite(end_price) and start_price > 0.0):
                return
            start_value = quantity * start_price / nav_value
            contribution = _piece_contribution(
                symbol=symbol,
                start_value=start_value,
                actual_return=end_price / start_price - 1.0,
                fit=fit,
                store=store,
                exposure_index=exposure_index,
                symbol_positions=symbol_positions,
            )
            for group, value in contribution.items():
                accumulator[group] += value

        for symbol in sorted(set(q0) | set(q1)):
            start_price = p0.get(symbol, float("nan"))
            close_price = p1.get(symbol, float("nan"))
            if symbol in traded:
                execution_price = (
                    float(day_market.loc[symbol, "accounting_execution_price"])
                    if symbol in day_market.index and pd.notna(day_market.loc[symbol, "accounting_execution_price"])
                    else float("nan")
                )
                add_piece(
                    symbol,
                    q0.get(symbol, 0.0),
                    start_price,
                    execution_price,
                    pre_fit,
                    pre_index,
                    previous_nav,
                    simple,
                )
                add_piece(
                    symbol,
                    q1.get(symbol, 0.0),
                    execution_price,
                    close_price,
                    post_fit,
                    post_index,
                    previous_nav,
                    simple,
                )
            else:
                add_piece(
                    symbol,
                    q0.get(symbol, 0.0),
                    start_price,
                    close_price,
                    full_fit,
                    pre_index,
                    previous_nav,
                    simple,
                )
        day_trades = trade_groups.get(day, pd.DataFrame())
        cost = 0.0
        if not day_trades.empty:
            cost_values = np.unique(day_trades["cost"].to_numpy(np.float64))
            if len(cost_values) != 1:
                raise ValueError("current_K1_daily_total_cost_not_unique_across_trade_legs")
            # P7 repeats the one daily total on every leg so each standalone
            # leg remains auditable.  It is not a per-leg charge.
            cost = float(cost_values[0]) / previous_nav
        simple["transaction_cost"] = -cost
        daily_return = float(daily_row.daily_return)
        closure_error = float(sum(simple.values()) - daily_return)
        # Any exact book arithmetic not represented by price pieces belongs to
        # idiosyncratic residual, never to a named factor.
        simple["idiosyncratic_residual"] -= closure_error
        closure_error = float(sum(simple.values()) - daily_return)
        maximum_closure_error = max(maximum_closure_error, abs(closure_error))
        linked = linked_log_contributions(simple, daily_return)
        for group in RETURN_GROUPS:
            rows.append(
                {
                    "year": year,
                    "date": day.strftime("%Y-%m-%d"),
                    "decision_clock": clock,
                    "slippage_multiplier": slip,
                    "group": group,
                    "simple_contribution": simple[group],
                    "linked_log_contribution": linked[group],
                    "daily_return": daily_return,
                    "is_rebalance": is_rebalance,
                }
            )
    detail = pd.DataFrame(rows).sort_values(
        ["date", "decision_clock", "slippage_multiplier", "group"], kind="mergesort", ignore_index=True
    )
    summary = (
        detail.groupby(["year", "decision_clock", "slippage_multiplier", "group"], sort=True)
        .agg(
            simple_contribution_sum=("simple_contribution", "sum"),
            linked_log_contribution=("linked_log_contribution", "sum"),
        )
        .reset_index()
    )
    diagnostics = {
        "daily_count": int(daily["date"].nunique()),
        "maximum_daily_simple_closure_error": maximum_closure_error,
        "maximum_cross_section_condition_number": maximum_condition,
        "minimum_cross_section_design_rank": minimum_rank,
        "net_log_return_recomputed": float(np.log1p(daily["daily_return"].to_numpy(np.float64)).sum()),
        "net_log_contribution_sum": float(summary["linked_log_contribution"].sum()),
        "trade_cost_semantics": "one_repeated_daily_total_counted_once_not_summed_over_legs",
    }
    return detail, summary, diagnostics


def load_contract() -> dict[str, object]:
    payload = read_json(CONTRACT_PATH)
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    if stored != canonical_digest(body):
        raise ValueError("current_K1_attribution_contract_digest_invalid")
    if payload.get("formal_execution_allowed") is not True:
        raise ValueError("current_K1_attribution_execution_not_open")
    return payload


def execute_year(
    *,
    tree: str,
    year: int,
    output_root: Path,
    device_name: str,
) -> dict[str, object]:
    if tree not in {"formal", "isolated"} or year not in YEARS:
        raise ValueError("current_K1_attribution_scope_invalid")
    contract = load_contract()
    if device_name not in {"cpu", "rocm"}:
        raise ValueError("current_K1_attribution_backend_invalid")
    device = torch.device("cuda:0" if device_name == "rocm" else "cpu")
    output_root.mkdir(parents=True, exist_ok=False)
    all_score: list[pd.DataFrame] = []
    all_daily: list[pd.DataFrame] = []
    all_annual: list[pd.DataFrame] = []
    diagnostics: dict[str, object] = {}
    inventory_payload: dict[str, object] | None = None
    input_digests: dict[str, str] = {}
    for clock in CLOCKS:
        suffix = CLOCK_SUFFIX[clock]
        store_path = STORE_ROOT / tree / suffix
        store = IntradayK1InputStore.load(store_path)
        inventory = factor_input_inventory(store.factor_ids)
        if inventory_payload is None:
            inventory_payload = inventory
        elif inventory["canonical_digest"] != inventory_payload["canonical_digest"]:
            raise ValueError("current_K1_attribution_clock_factor_inventory_mismatch")
        normalizer_path = NORMALIZER_ROOT / suffix / "normalizer.json"
        normalizer = read_json(normalizer_path)
        score_path = INPUT_ROOT / tree / f"bounded_score_panel_{suffix}.parquet"
        score_panel = pd.read_parquet(
            score_path,
            filters=[
                ("decision_date", ">=", pd.Timestamp(f"{year}-01-01")),
                ("decision_date", "<=", pd.Timestamp(f"{year}-12-31")),
            ],
        )
        influence, score_diagnostics = score_group_influence(
            store=store,
            normalizer=normalizer,
            checkpoint_root=CHECKPOINT_ROOT / tree / suffix / "checkpoints",
            year=year,
            device=device,
            score_panel=score_panel,
        )
        influence["decision_clock"] = clock
        all_score.append(influence)
        market = _market_year(clock, tree, year)
        for slip in SLIPPAGE_MULTIPLIERS:
            detail, annual, account_diagnostics = account_return_attribution(
                tree=tree,
                year=year,
                clock=clock,
                slip=slip,
                store=store,
                market=market,
            )
            all_daily.append(detail)
            all_annual.append(annual)
            diagnostics[f"{suffix}_slip_{slip:g}"] = account_diagnostics
        diagnostics[f"{suffix}_score"] = score_diagnostics
        for path in (
            store_path / "manifest.json",
            normalizer_path,
            score_path,
            INPUT_ROOT / tree / f"daily_market_panel_{suffix}.parquet",
        ):
            input_digests[str(path.relative_to(ROOT))] = file_digest(path)
        for seed in SEEDS_FORMAL:
            path = CHECKPOINT_ROOT / tree / suffix / "checkpoints" / f"seed_{seed}" / "manifest.json"
            input_digests[str(path.relative_to(ROOT))] = file_digest(path)
    if inventory_payload is None:
        raise RuntimeError("current_K1_attribution_inventory_missing")
    score_frame = pd.concat(all_score, ignore_index=True).sort_values(
        ["year", "decision_clock", "group"], kind="mergesort", ignore_index=True
    )
    daily_frame = pd.concat(all_daily, ignore_index=True).sort_values(
        ["date", "decision_clock", "slippage_multiplier", "group"], kind="mergesort", ignore_index=True
    )
    annual_frame = pd.concat(all_annual, ignore_index=True).sort_values(
        ["year", "decision_clock", "slippage_multiplier", "group"], kind="mergesort", ignore_index=True
    )
    write_json(output_root / "factor_input_inventory.json", inventory_payload)
    write_csv(output_root / "score_group_influence.csv", score_frame)
    write_csv(output_root / "daily_return_attribution.csv", daily_frame)
    write_csv(output_root / "annual_attribution.csv", annual_frame)
    result = write_json(
        output_root / "result.json",
        {
            "schema_id": SCHEMA_ID,
            "status": "completed_detailed_consumed_validation_attribution",
            "year": year,
            "candidate_identity": "d8-h8-K1-r0_fit_prefix_successor_incumbent",
            "policy_id": POLICY_ID,
            "decision_clocks": list(CLOCKS),
            "slippage_multipliers": list(SLIPPAGE_MULTIPLIERS),
            "return_groups": list(RETURN_GROUPS),
            "score_groups": list(GROUPS),
            "factor_input_inventory_digest": inventory_payload["canonical_digest"],
            "diagnostics": diagnostics,
            "training_boundary": {
                "model_train": "2011-2016",
                "internal_review": "2017",
                "confirmation": "2018",
                "detailed_consumed_validation_material": [2019, 2020],
                "post_2020_rows_read": 0,
            },
            "model_or_checkpoint_changed": False,
            "account_policy_changed": False,
            "result_used_for_training": False,
            "fresh_oos": False,
            "production_authority": False,
        },
    )
    scientific_digests = {name: file_digest(output_root / name) for name in SCIENTIFIC_FILES}
    receipt = write_json(
        output_root / "execution_receipt.json",
        {
            "schema_id": "factorlab.reaka_current_K1_factor_attribution_execution@1.0",
            "status": "completed",
            "tree": tree,
            "year": year,
            "backend": "pytorch_rocm_cuda_0" if device_name == "rocm" else "cpu",
            "contract_digest": contract["canonical_digest"],
            "result_digest": result["canonical_digest"],
            "scientific_file_digests": scientific_digests,
            "input_digests": dict(sorted(input_digests.items())),
            "source_digests": cast(Mapping[str, object], contract["source_closure"]),
            "post_2020_rows_read": 0,
            "training_run": False,
            "production_authority": False,
        },
    )
    return receipt


__all__ = [
    "GROUPS",
    "RETURN_GROUPS",
    "SCIENTIFIC_FILES",
    "coalition_feature_batch",
    "exact_group_shapley",
    "execute_year",
    "factor_input_inventory",
    "fit_factor_segment",
    "linked_log_contributions",
]
