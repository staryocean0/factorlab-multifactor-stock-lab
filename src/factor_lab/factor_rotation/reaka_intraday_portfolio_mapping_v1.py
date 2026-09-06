# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportGeneralTypeIssues=false, reportOptionalMemberAccess=false
# pyright: reportAny=false, reportIndexIssue=false, reportMissingTypeStubs=false
# pyright: reportUnknownVariableType=false, reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false, reportUnknownLambdaType=false
# pyright: reportUnusedCallResult=false, reportCallIssue=false
"""Result-free REAKA P7 intraday portfolio-mapping infrastructure."""

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
from numpy.typing import NDArray
from scipy.stats import rankdata

from factor_lab.governance.canonicalization import canonical_digest

SCHEMA_ID: Final = "factorlab.reaka_intraday_portfolio_mapping@1.2"
CONTRACT_RELATIVE: Final = Path("docs/ops/reaka_intraday_portfolio_mapping@1.2.json")
CONTRACT_DIGEST: Final = (
    "sha256:36f630c37ac8bfe9fee4d98b6a341562fb96549fff6d423fa7f0a62dbacafd0b"
)
COMMON_ROOT_POLICY_ID: Final = "N30_equal_backfill_unconstrained"
CLOCKS: Final = ("14:30", "14:45")
CLOCK_SUFFIX: Final = {"14:30": "1430", "14:45": "1445"}
SEEDS_FORMAL: Final = (11, 29, 47)
ANNUAL_YEARS: Final = tuple(range(2009, 2021))
SLIPPAGE_MULTIPLIERS: Final = (1.0, 2.0, 3.0)
COMMISSION_BPS: Final = 2.5
TRANSFER_FEE_BPS: Final = 0.1
STAMP_TAX_SELL_BPS: Final = 10.0
BASELINE_SLIPPAGE_BPS: Final = 2.0
INITIAL_NAV: Final = 1_000_000.0
INDUSTRY_CAP_FRACTION: Final = 0.25
SIZE_TERCILE_CAP_FRACTION: Final = 0.50
INPUT_SCHEMA_ID: Final = "factorlab.reaka_intraday_portfolio_mapping_input@1.0"
SESSION_SCHEMA_ID: Final = "factorlab.reaka_intraday_portfolio_mapping_session@1.0"
VALIDATION_SCHEMA_ID: Final = "factorlab.reaka_intraday_portfolio_mapping_validation@1.0"
ADMISSION_SCHEMA_ID: Final = "factorlab.reaka_intraday_portfolio_mapping_admission@1.0"


@dataclass(frozen=True, slots=True)
class PortfolioPolicy:
    policy_id: str
    top_n: int
    weighting: str
    buy_unavailable: str
    size_concentration: str

    @property
    def single_name_cap(self) -> float:
        if self.weighting == "equal":
            return 1.0 / float(self.top_n)
        return 2.0 / float(self.top_n)

    def complexity_distance_to(self, root: PortfolioPolicy) -> int:
        distance = 0
        if self.top_n != root.top_n:
            distance += 1
        if self.weighting != root.weighting:
            distance += 1
        if self.buy_unavailable != root.buy_unavailable:
            distance += 1
        if self.size_concentration != root.size_concentration:
            distance += 1
        return distance


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def contract_path(root: Path | None = None) -> Path:
    return (root or repo_root()) / CONTRACT_RELATIVE


def read_json(path: Path) -> dict[str, object]:
    return cast(dict[str, object], json.loads(path.read_text(encoding="utf-8")))


def write_json(path: Path, payload: Mapping[str, object]) -> dict[str, object]:
    output = dict(payload)
    output.pop("canonical_digest", None)
    output["canonical_digest"] = canonical_digest(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return output


def file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_valid(payload: Mapping[str, object]) -> bool:
    body = dict(payload)
    stored = body.pop("canonical_digest", None)
    return stored == canonical_digest(body)


def load_contract(root: Path | None = None) -> dict[str, object]:
    payload = read_json(contract_path(root))
    if payload.get("schema_id") != SCHEMA_ID:
        raise ValueError("portfolio_mapping_contract_schema_invalid")
    if payload.get("canonical_digest") != CONTRACT_DIGEST or not canonical_valid(payload):
        raise ValueError("portfolio_mapping_contract_digest_invalid")
    return payload


def _policy_id(
    top_n: int,
    weighting: str,
    buy_unavailable: str,
    size_concentration: str,
) -> str:
    size_token = "unconstrained" if size_concentration == "none" else "size_tercile_50pct"
    return f"N{top_n}_{weighting}_{buy_unavailable}_{size_token}"


def build_policy_grid() -> tuple[PortfolioPolicy, ...]:
    policies: list[PortfolioPolicy] = []
    for top_n in (10, 30, 50):
        for weighting in ("equal", "rank_linear_capped"):
            for buy_unavailable in ("cash", "backfill"):
                for size_concentration in ("none", "PIT_total_market_cap_tercile_max_50pct"):
                    policies.append(
                        PortfolioPolicy(
                            policy_id=_policy_id(top_n, weighting, buy_unavailable, size_concentration),
                            top_n=top_n,
                            weighting=weighting,
                            buy_unavailable=buy_unavailable,
                            size_concentration=size_concentration,
                        )
                    )
    if len(policies) != 24:
        raise ValueError("portfolio_mapping_policy_grid_invalid")
    if not any(policy.policy_id == COMMON_ROOT_POLICY_ID for policy in policies):
        raise ValueError("portfolio_mapping_common_root_missing")
    return tuple(policies)


def common_root_policy() -> PortfolioPolicy:
    return policy_by_id(COMMON_ROOT_POLICY_ID)


def policy_by_id(policy_id: str) -> PortfolioPolicy:
    for policy in build_policy_grid():
        if policy.policy_id == policy_id:
            return policy
    raise KeyError(f"portfolio_mapping_policy_unknown:{policy_id}")


def validate_contract_payload(payload: Mapping[str, object]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema_id") != SCHEMA_ID:
        blockers.append("schema_id_invalid")
    if not canonical_valid(payload):
        blockers.append("canonical_digest_invalid")
    if payload.get("canonical_digest") != CONTRACT_DIGEST:
        blockers.append("contract_digest_mismatch")
    common = cast(Mapping[str, object], payload.get("common_root_policy", {}))
    if common.get("policy_id") != COMMON_ROOT_POLICY_ID:
        blockers.append("common_root_policy_invalid")
    family = cast(Mapping[str, object], payload.get("candidate_family", {}))
    if family.get("executable_policy_count") != 24:
        blockers.append("executable_policy_count_invalid")
    permissions = cast(Mapping[str, object], payload.get("current_permissions", {}))
    if permissions.get("infrastructure_implementation_allowed") is not True:
        blockers.append("infrastructure_not_authorized")
    for field in (
        "score_extension_execution_allowed",
        "account_mapping_execution_allowed",
        "post_2020_read_allowed",
        "production_authority",
    ):
        if permissions.get(field) is not False:
            blockers.append(f"authority_must_be_false:{field}")
    return blockers


def buy_cost_bps(slippage_multiplier: float) -> float:
    return COMMISSION_BPS + TRANSFER_FEE_BPS + BASELINE_SLIPPAGE_BPS * float(slippage_multiplier)


def sell_cost_bps(slippage_multiplier: float) -> float:
    return (
        COMMISSION_BPS
        + TRANSFER_FEE_BPS
        + STAMP_TAX_SELL_BPS
        + BASELINE_SLIPPAGE_BPS * float(slippage_multiplier)
    )


def average_tie_ranks(scores: NDArray[np.float64], symbols: Sequence[str]) -> NDArray[np.float64]:
    order = np.lexsort((np.asarray(list(symbols), dtype=str), -scores))
    sorted_scores = scores[order]
    ranks = rankdata(sorted_scores, method="average")
    output = np.empty_like(ranks, dtype=np.float64)
    output[order] = ranks
    return output


def per_decision_rank_z(
    scores: NDArray[np.float64],
    symbols: Sequence[str],
) -> NDArray[np.float64]:
    ranks = average_tie_ranks(scores, symbols)
    centered = ranks - ranks.mean()
    scale = centered.std(ddof=0)
    if scale <= 0.0:
        return np.zeros_like(centered)
    return centered / scale


def ensemble_seed_rank_z(
    seed_scores: Mapping[int, NDArray[np.float64]],
    symbols: Sequence[str],
) -> NDArray[np.float64]:
    parts = [per_decision_rank_z(seed_scores[seed], symbols) for seed in SEEDS_FORMAL]
    return np.mean(np.vstack(parts), axis=0)


def rank_portfolio_table(frame: pd.DataFrame) -> pd.DataFrame:
    required = {"symbol", "score"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("portfolio_mapping_score_columns_missing:" + ",".join(sorted(missing)))
    work = frame.loc[:, ["symbol", "score"]].copy()
    work["symbol"] = work["symbol"].astype(str)
    work["score"] = pd.to_numeric(work["score"], errors="coerce")
    work = work.loc[np.isfinite(work["score"])].copy()
    work["rank"] = average_tie_ranks(
        work["score"].to_numpy(dtype=np.float64),
        work["symbol"].tolist(),
    )
    return work.sort_values(["score", "symbol"], ascending=[False, True], kind="mergesort").reset_index(drop=True)


def rank_linear_weights(ranks: Sequence[float], top_n: int) -> dict[int, float]:
    if not ranks:
        return {}
    cap = 2.0 / float(top_n)
    # ``average_tie_ranks`` assigns larger ranks to larger scores.  Keep that
    # direction here: the strongest score receives the largest weight, while
    # exact score ties retain identical raw weights.
    raw = {position: float(rank) for position, rank in enumerate(ranks)}
    total = float(sum(raw.values()))
    if total <= 0.0:
        return {position: 1.0 / len(raw) for position in raw}
    # Do not renormalize after a cap binds: the removed target remains cash.
    return {position: min(value / total, cap) for position, value in raw.items()}


def equal_weights(count: int) -> float:
    if count <= 0:
        return 0.0
    return 1.0 / float(count)


def target_weights_for_policy(
    policy: PortfolioPolicy,
    ranked_symbols: Sequence[str],
    ranks_by_symbol: Mapping[str, float],
) -> dict[str, float]:
    chosen = list(ranked_symbols[: policy.top_n])
    if not chosen:
        return {}
    if policy.weighting == "equal":
        # The policy identity is N, not "however many happened to fill".
        # A missing slot therefore remains cash rather than levering survivors.
        weight = equal_weights(policy.top_n)
        return {symbol: weight for symbol in chosen}
    rank_values = [ranks_by_symbol[symbol] for symbol in chosen]
    rank_weights = rank_linear_weights(rank_values, policy.top_n)
    return {symbol: rank_weights[position] for position, symbol in enumerate(chosen)}


@dataclass(frozen=True, slots=True)
class TradabilityRow:
    symbol: str
    buy_ok: bool
    sell_ok: bool


def select_target_symbols(
    ranked: pd.DataFrame,
    *,
    policy: PortfolioPolicy,
    previous_shares: Mapping[str, float],
    tradability: Mapping[str, TradabilityRow],
) -> tuple[list[str], list[dict[str, object]]]:
    events: list[dict[str, object]] = []
    forced: list[str] = []
    for symbol in sorted(previous_shares):
        qty = float(previous_shares[symbol])
        if qty <= 0.0:
            continue
        gate = tradability.get(symbol)
        if gate is None or not gate.sell_ok:
            forced.append(symbol)
            events.append(
                {
                    "symbol": symbol,
                    "event_type": "forced_carry",
                    "reason": "sell_unavailable",
                }
            )
    remaining = max(policy.top_n - len(forced), 0)
    chosen = list(forced)
    if remaining == 0:
        return chosen, events
    candidate_rows = [
        row for row in ranked.itertuples(index=False) if str(row.symbol) not in set(chosen)
    ]
    # Cash mode freezes the intended slots before execution eligibility is
    # observed.  Only backfill may inspect lower-ranked rows.
    if policy.buy_unavailable == "cash":
        candidate_rows = candidate_rows[:remaining]
    for row in candidate_rows:
        symbol = str(row.symbol)
        if symbol in chosen:
            continue
        gate = tradability.get(symbol)
        held = float(previous_shares.get(symbol, 0.0)) > 0.0
        if held and gate is not None and not gate.buy_ok:
            chosen.append(symbol)
            events.append(
                {
                    "symbol": symbol,
                    "event_type": "held_buy_blocked_carry",
                    "reason": "buy_unavailable_existing_position",
                }
            )
            if len(chosen) - len(forced) >= remaining:
                break
            continue
        if gate is None or not gate.buy_ok:
            if policy.buy_unavailable == "backfill":
                events.append(
                    {
                        "symbol": symbol,
                        "event_type": "buy_skip_backfill",
                        "reason": "buy_unavailable",
                    }
                )
                continue
            events.append(
                {
                    "symbol": symbol,
                    "event_type": "buy_skip_cash",
                    "reason": "buy_unavailable",
                }
            )
            continue
        chosen.append(symbol)
        if len(chosen) - len(forced) >= remaining:
            break
    return chosen, events


def apply_size_tercile_cap(
    weights: Mapping[str, float],
    *,
    size_labels: Mapping[str, str],
    cap_fraction: float = SIZE_TERCILE_CAP_FRACTION,
) -> dict[str, float]:
    if not weights:
        return {}
    missing = [symbol for symbol in weights if not str(size_labels.get(symbol, "")).strip()]
    if missing:
        raise ValueError("portfolio_mapping_PIT_size_coverage_incomplete:" + ",".join(sorted(missing)[:8]))
    adjusted = {symbol: float(weight) for symbol, weight in weights.items()}
    for _ in range(16):
        buckets: dict[str, float] = {}
        for symbol, weight in adjusted.items():
            bucket = size_labels.get(symbol)
            if bucket is None:
                continue
            buckets[bucket] = buckets.get(bucket, 0.0) + weight
        overflow = {
            bucket: total - cap_fraction
            for bucket, total in buckets.items()
            if total > cap_fraction + 1.0e-12
        }
        if not overflow:
            break
        for bucket, excess in overflow.items():
            members = [symbol for symbol in adjusted if size_labels.get(symbol) == bucket]
            bucket_total = sum(adjusted[symbol] for symbol in members)
            if bucket_total <= 0.0:
                continue
            scale = max((bucket_total - excess) / bucket_total, 0.0)
            for symbol in members:
                adjusted[symbol] *= scale
    return adjusted


def apply_industry_cap(
    weights: Mapping[str, float],
    *,
    industry_labels: Mapping[str, str],
    cap_fraction: float = INDUSTRY_CAP_FRACTION,
    require_full_coverage: bool = True,
) -> tuple[dict[str, float], bool]:
    if not weights:
        return {}, True
    if require_full_coverage:
        for symbol in weights:
            label = industry_labels.get(symbol)
            if label is None or not str(label).strip():
                return dict(weights), False
    adjusted = {symbol: float(weight) for symbol, weight in weights.items()}
    for _ in range(16):
        buckets: dict[str, float] = {}
        for symbol, weight in adjusted.items():
            bucket = industry_labels.get(symbol, "")
            if not bucket:
                return dict(weights), False
            buckets[bucket] = buckets.get(bucket, 0.0) + weight
        overflow = {
            bucket: total - cap_fraction
            for bucket, total in buckets.items()
            if total > cap_fraction + 1.0e-12
        }
        if not overflow:
            return adjusted, True
        for bucket, excess in overflow.items():
            members = [symbol for symbol in adjusted if industry_labels.get(symbol) == bucket]
            bucket_total = sum(adjusted[symbol] for symbol in members)
            if bucket_total <= 0.0:
                continue
            scale = max((bucket_total - excess) / bucket_total, 0.0)
            for symbol in members:
                adjusted[symbol] *= scale
    return adjusted, True


def turnover_from_weights(
    current_weights: Mapping[str, float],
    target_weights: Mapping[str, float],
) -> tuple[float, float, dict[str, float], dict[str, float]]:
    names = set(current_weights) | set(target_weights)
    buy: dict[str, float] = {}
    sell: dict[str, float] = {}
    buy_sum = 0.0
    sell_sum = 0.0
    for name in sorted(names):
        delta = float(target_weights.get(name, 0.0)) - float(current_weights.get(name, 0.0))
        if delta > 0.0:
            buy[name] = delta
            buy_sum += delta
        elif delta < 0.0:
            sell[name] = -delta
            sell_sum += -delta
    return buy_sum, sell_sum, buy, sell


def current_weights_from_book(
    *,
    shares: Mapping[str, float],
    prices: Mapping[str, float],
    cash: float,
) -> tuple[dict[str, float], float]:
    stock_value = 0.0
    for symbol, qty in shares.items():
        price = prices.get(symbol)
        if qty > 0.0 and price is not None and np.isfinite(price) and float(price) > 0.0:
            stock_value += float(qty) * float(price)
    nav = stock_value + float(cash)
    if nav <= 0.0:
        return {}, nav
    weights = {
        symbol: float(qty) * float(prices[symbol]) / nav
        for symbol, qty in shares.items()
        if qty > 0.0 and symbol in prices and np.isfinite(prices[symbol]) and float(prices[symbol]) > 0.0
    }
    return weights, nav


def allocate_target_shares(
    *,
    nav_after_cost: float,
    target_weights: Mapping[str, float],
    execution_prices: Mapping[str, float],
    forced_shares: Mapping[str, float],
) -> tuple[dict[str, float], float]:
    shares = {symbol: float(qty) for symbol, qty in forced_shares.items() if float(qty) > 0.0}
    forced_value = sum(
        float(shares[symbol]) * float(execution_prices[symbol])
        for symbol in shares
        if symbol in execution_prices and np.isfinite(execution_prices[symbol])
    )
    remaining = max(float(nav_after_cost) - forced_value, 0.0)
    free_symbols = [
        symbol
        for symbol in target_weights
        if symbol not in shares
        and symbol in execution_prices
        and np.isfinite(execution_prices[symbol])
        and float(execution_prices[symbol]) > 0.0
    ]
    if not free_symbols:
        return shares, max(float(nav_after_cost) - forced_value, 0.0)
    for symbol in sorted(free_symbols):
        price = float(execution_prices[symbol])
        allocation = min(
            max(float(target_weights[symbol]), 0.0) * float(nav_after_cost),
            remaining,
        )
        if allocation <= 0.0:
            continue
        shares[symbol] = allocation / price
        remaining -= allocation
    stock_value = sum(
        float(shares[symbol]) * float(execution_prices[symbol])
        for symbol in shares
        if symbol in execution_prices and np.isfinite(execution_prices[symbol])
    )
    residual_cash = max(float(nav_after_cost) - stock_value, 0.0)
    return shares, residual_cash


def apply_rebalance_day(
    *,
    previous_shares: Mapping[str, float],
    previous_cash: float,
    open_prices: Mapping[str, float],
    close_prices: Mapping[str, float],
    target_weights: Mapping[str, float],
    forced_symbols: Sequence[str],
    slippage_multiplier: float,
    previous_mark_prices: Mapping[str, float] | None = None,
    blocked_buy_symbols: Sequence[str] = (),
) -> dict[str, object]:
    shares = {symbol: float(qty) for symbol, qty in previous_shares.items()}
    cash = float(previous_cash)
    fallback = previous_mark_prices or {}
    mark_open: dict[str, float] = {}
    for symbol in shares:
        value = open_prices.get(symbol, fallback.get(symbol))
        if value is None or not np.isfinite(float(value)) or float(value) <= 0.0:
            raise ValueError(f"portfolio_mapping_unpriced_held_position:{symbol}")
        mark_open[symbol] = float(value)
    current_weights, nav = current_weights_from_book(shares=shares, prices=mark_open, cash=cash)
    if nav <= 0.0 and not target_weights:
        nav = cash
    adjusted_targets = dict(target_weights)
    forced_set = set(forced_symbols)
    blocked_buy_set = set(blocked_buy_symbols)
    if forced_symbols:
        forced_weight = sum(current_weights.get(symbol, 0.0) for symbol in forced_symbols)
        adjustable = [symbol for symbol in adjusted_targets if symbol not in forced_symbols]
        leftover = max(1.0 - forced_weight, 0.0)
        forced_map = {symbol: current_weights.get(symbol, 0.0) for symbol in forced_symbols}
        if adjustable and leftover > 0.0:
            adjustable_total = sum(max(float(adjusted_targets.get(symbol, 0.0)), 0.0) for symbol in adjustable)
            scale = min(1.0, leftover / adjustable_total) if adjustable_total > 0.0 else 0.0
            adjusted_targets = {
                **forced_map,
                **{symbol: max(float(adjusted_targets.get(symbol, 0.0)), 0.0) * scale for symbol in adjustable},
            }
        else:
            adjusted_targets = forced_map
    # A held name that cannot be bought may be reduced but never increased.
    for symbol in blocked_buy_set - forced_set:
        if symbol in adjusted_targets:
            adjusted_targets[symbol] = min(
                float(adjusted_targets[symbol]),
                float(current_weights.get(symbol, 0.0)),
            )
    buy_weight, sell_weight, buy_legs, sell_legs = turnover_from_weights(current_weights, adjusted_targets)
    if forced_set.intersection(sell_legs):
        raise ValueError("portfolio_mapping_forced_carry_sell_leg_created")
    if blocked_buy_set.intersection(buy_legs):
        raise ValueError("portfolio_mapping_blocked_buy_leg_created")
    cost = nav * (
        buy_weight * buy_cost_bps(slippage_multiplier) / 10000.0
        + sell_weight * sell_cost_bps(slippage_multiplier) / 10000.0
    )
    nav_after_cost = nav - cost
    forced_share_map = {
        symbol: float(shares.get(symbol, 0.0))
        for symbol in forced_symbols
        if float(shares.get(symbol, 0.0)) > 0.0
    }
    next_shares, next_cash = allocate_target_shares(
        nav_after_cost=nav_after_cost,
        target_weights=adjusted_targets,
        execution_prices=open_prices,
        forced_shares=forced_share_map,
    )
    close_marks: dict[str, float] = {}
    for symbol in next_shares:
        value = close_prices.get(symbol, open_prices.get(symbol, fallback.get(symbol)))
        if value is None or not np.isfinite(float(value)) or float(value) <= 0.0:
            raise ValueError(f"portfolio_mapping_unpriced_close_position:{symbol}")
        close_marks[symbol] = float(value)
    close_value = sum(float(next_shares[symbol]) * close_marks[symbol] for symbol in next_shares)
    close_nav = close_value + next_cash
    return {
        "overnight_nav": nav,
        "nav_after_cost": nav_after_cost,
        "close_nav": close_nav,
        "cash": next_cash,
        "shares": next_shares,
        "buy_weight": buy_weight,
        "sell_weight": sell_weight,
        "buy_legs": buy_legs,
        "sell_legs": sell_legs,
        "cost": cost,
        "target_weights": adjusted_targets,
        "close_mark_prices": close_marks,
    }


def apply_non_rebalance_day(
    *,
    shares: Mapping[str, float],
    cash: float,
    close_prices: Mapping[str, float],
    previous_mark_prices: Mapping[str, float] | None = None,
) -> float:
    value = float(cash)
    fallback = previous_mark_prices or {}
    for symbol, qty in shares.items():
        price = close_prices.get(symbol, fallback.get(symbol))
        if qty <= 0.0:
            continue
        if price is None or not np.isfinite(float(price)) or float(price) <= 0.0:
            raise ValueError(f"portfolio_mapping_unpriced_non_rebalance_position:{symbol}")
        value += float(qty) * float(price)
    return value


def account_metrics(daily_returns: Sequence[float]) -> dict[str, float]:
    values = np.asarray(list(daily_returns), dtype=np.float64)
    if values.size == 0:
        return {
            "total_return": 0.0,
            "annualized_return": 0.0,
            "sharpe": 0.0,
            "maximum_drawdown": 0.0,
            "net_log_return": 0.0,
        }
    wealth = np.cumprod(1.0 + values)
    total_return = float(wealth[-1] - 1.0)
    annualized = float((wealth[-1]) ** (252.0 / max(values.size, 1)) - 1.0)
    vol = float(values.std(ddof=1)) if values.size > 1 else 0.0
    sharpe = float(values.mean() / vol * math.sqrt(252.0)) if vol > 0.0 else 0.0
    running_max = np.maximum.accumulate(wealth)
    drawdown = wealth / running_max - 1.0
    return {
        "total_return": total_return,
        "annualized_return": annualized,
        "sharpe": sharpe,
        "maximum_drawdown": float(drawdown.min()),
        "net_log_return": float(np.log1p(values).sum()),
    }


def evaluate_annual_gate(increments: Sequence[float]) -> dict[str, object]:
    affected = [value for value in increments if abs(value) > 1.0e-12]
    positive = [value for value in affected if value > 0.0]
    contract = load_contract()
    gate = cast(Mapping[str, object], contract["whole_policy_selection"]["annual_gate"])
    passed = (
        len(affected) >= int(gate["minimum_affected_years"])
        and len(positive) / max(len(affected), 1) >= float(gate["minimum_positive_share"])
        and float(np.median(affected) if affected else 0.0) >= float(gate["median_increment_minimum"])
        and float(sum(affected)) > float(gate["total_increment_minimum"])
    )
    return {
        "affected_years": len(affected),
        "positive_years": len(positive),
        "positive_share": len(positive) / max(len(affected), 1),
        "median_increment": float(np.median(affected) if affected else 0.0),
        "total_increment": float(sum(affected)),
        "passed": passed,
    }


def evaluate_quarterly_gate(
    increments: Sequence[float] | Sequence[tuple[int, int, float]],
) -> dict[str, object]:
    contract = load_contract()
    gate = cast(Mapping[str, object], contract["whole_policy_selection"]["quarterly_gate"])
    threshold = float(gate["affected_absolute_increment"])
    dated = bool(increments and isinstance(increments[0], tuple))
    rows = (
        [(int(year), int(quarter), float(value)) for year, quarter, value in cast(Sequence[tuple[int, int, float]], increments)]
        if dated
        else [(0, position + 1, float(value)) for position, value in enumerate(cast(Sequence[float], increments))]
    )
    affected_rows = [row for row in rows if abs(row[2]) >= threshold]
    affected = [row[2] for row in affected_rows]
    positive = [value for value in affected if value > 0.0]
    distinct_years = len({row[0] for row in affected_rows}) if dated else 0
    passed = (
        len(affected) >= int(gate["minimum_affected_quarters"])
        and distinct_years >= int(gate["minimum_distinct_years"])
        and len(positive) / max(len(affected), 1) >= float(gate["minimum_positive_share"])
        and float(np.median(affected) if affected else 0.0) >= float(gate["median_increment_minimum"])
        and float(sum(affected)) > float(gate["total_increment_minimum"])
    )
    return {
        "affected_quarters": len(affected),
        "positive_quarters": len(positive),
        "positive_share": len(positive) / max(len(affected), 1),
        "distinct_years": distinct_years,
        "median_increment": float(np.median(affected) if affected else 0.0),
        "total_increment": float(sum(affected)),
        "passed": passed,
    }


def evaluate_economics_gate(
    *,
    challenger_metrics: Mapping[str, float],
    root_metrics: Mapping[str, float],
    cost_multipliers: Sequence[float],
    challenger_by_cost: Mapping[float, float],
    root_by_cost: Mapping[float, float],
) -> dict[str, object]:
    contract = cast(Mapping[str, object], load_contract()["whole_policy_selection"]["economics_gate_each_clock"])
    base_pass = (
        challenger_metrics["net_log_return"] - root_metrics["net_log_return"]
        >= float(contract["net_log_return_increment_minimum"])
        and challenger_metrics["sharpe"] - root_metrics["sharpe"] >= float(contract["sharpe_increment_minimum"])
        and root_metrics["maximum_drawdown"] - challenger_metrics["maximum_drawdown"]
        <= float(contract["maximum_drawdown_worsening_limit"])
    )
    stress_pass = all(
        challenger_by_cost[multiplier] - root_by_cost[multiplier] > 0.0 for multiplier in cost_multipliers
    )
    return {"base_pass": base_pass, "stress_pass": stress_pass, "passed": base_pass and stress_pass}


def tie_break_policies(
    candidates: Sequence[str],
    *,
    clock_increments: Mapping[str, float],
    root: PortfolioPolicy | None = None,
) -> str:
    if not candidates:
        raise ValueError("portfolio_mapping_tie_break_empty")
    common = root or common_root_policy()
    ranked = sorted(
        candidates,
        key=lambda policy_id: (
            policy_by_id(policy_id).complexity_distance_to(common),
            -clock_increments.get(policy_id, float("-inf")),
            policy_id,
        ),
    )
    return ranked[0]


def validate_admission(
    payload: Mapping[str, object],
    *,
    required_phase: str | None = None,
) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema_id") != ADMISSION_SCHEMA_ID:
        blockers.append("admission_schema_invalid")
    if not canonical_valid(payload):
        blockers.append("admission_digest_invalid")
    if payload.get("contract_digest") != CONTRACT_DIGEST:
        blockers.append("admission_contract_digest_mismatch")
    for field, expected in (
        ("infrastructure_implementation_allowed", True),
        ("post_2020_read_allowed", False),
        ("production_authority", False),
    ):
        if payload.get(field) is not expected:
            blockers.append(f"admission_authority_invalid:{field}")
    score_allowed = payload.get("score_extension_execution_allowed") is True
    account_allowed = payload.get("account_mapping_execution_allowed") is True
    if account_allowed and not score_allowed:
        blockers.append("admission_account_requires_score_extension")
    phase = required_phase or str(payload.get("phase") or "infrastructure")
    expected = {
        "infrastructure": (False, False),
        "score_extension": (True, False),
        "account_execution": (True, True),
    }.get(phase)
    if expected is None:
        blockers.append("admission_phase_invalid")
    elif (score_allowed, account_allowed) != expected:
        blockers.append(f"admission_phase_authority_mismatch:{phase}")
    return blockers


def validate_year_request(
    *,
    year: int,
    prior_receipt: Mapping[str, object] | None,
) -> list[str]:
    blockers: list[str] = []
    if year not in ANNUAL_YEARS:
        blockers.append("year_out_of_range")
    if year > 2020:
        blockers.append("post_2020_forbidden")
    if year == 2009:
        if prior_receipt is not None and prior_receipt.get("session_year") not in {None, 2008}:
            blockers.append("2009_prior_receipt_invalid")
        return blockers
    if prior_receipt is None:
        blockers.append("prior_receipt_missing")
        return blockers
    if prior_receipt.get("session_year") != year - 1:
        blockers.append("prior_receipt_year_mismatch")
    if not str(prior_receipt.get("canonical_digest", "")).startswith("sha256:"):
        blockers.append("prior_receipt_digest_missing")
    return blockers


def assert_no_future_filter(columns: Sequence[str]) -> None:
    forbidden = {
        "target_return",
        "future_h20",
        "future_target_available",
        "target_ok",
        "entry_ok",
        "label_return",
        "entry_return",
        "forward_return",
    }
    present = sorted(forbidden.intersection(columns))
    if present:
        raise ValueError("portfolio_mapping_future_filter_forbidden:" + ",".join(present))


def validate_score_panel(frame: pd.DataFrame) -> None:
    required = {"decision_date", "decision_clock", "symbol", "score"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("portfolio_mapping_score_panel_columns_missing:" + ",".join(sorted(missing)))
    assert_no_future_filter(frame.columns)
    if not set(frame["decision_clock"].astype(str).unique()).issubset(set(CLOCKS)):
        raise ValueError("portfolio_mapping_score_panel_clock_invalid")
    dates = pd.to_datetime(frame["decision_date"], errors="raise")
    if not frame.empty and int(dates.dt.year.max()) > 2020:
        raise ValueError("portfolio_mapping_score_panel_post_2020_forbidden")
    if frame.duplicated(["decision_date", "decision_clock", "symbol"]).any():
        raise ValueError("portfolio_mapping_score_panel_duplicate")


def validate_market_panel(frame: pd.DataFrame) -> None:
    required = {
        "date",
        "decision_clock",
        "symbol",
        "raw_execution_price",
        "raw_close_price",
        "hfq_price_multiplier",
        "hfq_factor_source",
        "accounting_execution_price",
        "accounting_close_price",
        "buy_ok",
        "sell_ok",
        "size_bucket",
    }
    missing = required - set(frame.columns)
    if missing:
        raise ValueError("portfolio_mapping_market_panel_columns_missing:" + ",".join(sorted(missing)))
    forbidden = {"target_return", "future_h20", "forward_return", "label_return"}
    if forbidden.intersection(frame.columns):
        raise ValueError("portfolio_mapping_market_panel_future_return_forbidden")
    dates = pd.to_datetime(frame["date"], errors="raise")
    if not frame.empty and int(dates.dt.year.max()) > 2020:
        raise ValueError("portfolio_mapping_market_panel_post_2020_forbidden")
    if frame.duplicated(["date", "decision_clock", "symbol"]).any():
        raise ValueError("portfolio_mapping_market_panel_duplicate")
    allowed_sources = {"certified_adjust_factors_v9", "bounded_xdxr_event_formula_v1"}
    if not set(frame["hfq_factor_source"].astype(str).unique()).issubset(allowed_sources):
        raise ValueError("portfolio_mapping_HFQ_factor_source_invalid")
    factor = pd.to_numeric(frame["hfq_price_multiplier"], errors="coerce").to_numpy(np.float64)
    raw_execution = pd.to_numeric(frame["raw_execution_price"], errors="coerce").to_numpy(np.float64)
    raw_close = pd.to_numeric(frame["raw_close_price"], errors="coerce").to_numpy(np.float64)
    accounting_execution = pd.to_numeric(
        frame["accounting_execution_price"], errors="coerce"
    ).to_numpy(np.float64)
    accounting_close = pd.to_numeric(frame["accounting_close_price"], errors="coerce").to_numpy(np.float64)
    if not np.isfinite(factor).all() or (factor <= 0.0).any():
        raise ValueError("portfolio_mapping_hfq_factor_missing_or_invalid")
    execution_mask = np.isfinite(raw_execution)
    if not np.array_equal(execution_mask, np.isfinite(accounting_execution)):
        raise ValueError("portfolio_mapping_accounting_execution_finite_mask_failed")
    if not np.allclose(
        accounting_execution[execution_mask],
        raw_execution[execution_mask] * factor[execution_mask],
        rtol=1.0e-12,
        atol=1.0e-12,
    ):
        raise ValueError("portfolio_mapping_accounting_execution_identity_failed")
    close_mask = np.isfinite(raw_close)
    if not np.array_equal(close_mask, np.isfinite(accounting_close)):
        raise ValueError("portfolio_mapping_accounting_close_finite_mask_failed")
    if not np.allclose(
        accounting_close[close_mask],
        raw_close[close_mask] * factor[close_mask],
        rtol=1.0e-12,
        atol=1.0e-12,
    ):
        raise ValueError("portfolio_mapping_accounting_close_identity_failed")


def _slot_weights(policy: PortfolioPolicy, ranked_rows: pd.DataFrame) -> dict[str, float]:
    if ranked_rows.empty:
        return {}
    work = ranked_rows.reset_index(drop=True)
    count = len(work)
    if policy.weighting == "equal":
        raw = np.full(count, 1.0 / float(policy.top_n), dtype=np.float64)
    else:
        full = np.asarray(
            [2.0 * (policy.top_n - position) / (policy.top_n * (policy.top_n + 1.0)) for position in range(count)],
            dtype=np.float64,
        )
        scores = pd.to_numeric(work["score"], errors="raise").to_numpy(np.float64)
        raw = full.copy()
        start = 0
        while start < count:
            stop = start + 1
            while stop < count and scores[stop] == scores[start]:
                stop += 1
            raw[start:stop] = float(full[start:stop].mean())
            start = stop
        raw = np.minimum(raw, 2.0 / float(policy.top_n))
    return {
        str(symbol): float(weight)
        for symbol, weight in zip(work["symbol"].astype(str), raw, strict=True)
    }


def build_execution_target(
    ranked: pd.DataFrame,
    *,
    policy: PortfolioPolicy,
    previous_shares: Mapping[str, float],
    current_weights: Mapping[str, float],
    tradability: Mapping[str, TradabilityRow],
    size_labels: Mapping[str, str],
) -> tuple[dict[str, float], list[str], list[str], list[dict[str, object]]]:
    """Build one causal target before account arithmetic.

    Cash policies freeze intended slots before execution status.  Backfill
    policies alone traverse lower ranks.  Group-cap reductions remain cash.
    """

    selected, events = select_target_symbols(
        ranked,
        policy=policy,
        previous_shares=previous_shares,
        tradability=tradability,
    )
    forced = sorted(
        symbol
        for symbol, qty in previous_shares.items()
        if float(qty) > 0.0 and (symbol not in tradability or not tradability[symbol].sell_ok)
    )
    remaining = max(policy.top_n - len(forced), 0)
    non_forced = [symbol for symbol in selected if symbol not in set(forced)]
    if policy.buy_unavailable == "cash":
        intended = ranked.loc[~ranked["symbol"].astype(str).isin(forced)].head(remaining).copy()
        slot_weights = _slot_weights(policy, intended)
        target = {symbol: slot_weights[symbol] for symbol in non_forced if symbol in slot_weights}
    else:
        intended = ranked.loc[ranked["symbol"].astype(str).isin(non_forced)].copy()
        order = {symbol: position for position, symbol in enumerate(non_forced)}
        intended["_selection_order"] = intended["symbol"].astype(str).map(order)
        intended = intended.sort_values("_selection_order", kind="mergesort").head(remaining)
        target = _slot_weights(policy, intended)
    for symbol in forced:
        target[symbol] = float(current_weights.get(symbol, 0.0))
    if policy.size_concentration == "PIT_total_market_cap_tercile_max_50pct":
        target = apply_size_tercile_cap(target, size_labels=size_labels)
        for symbol in forced:
            target[symbol] = max(float(target.get(symbol, 0.0)), float(current_weights.get(symbol, 0.0)))
    adjustable = [symbol for symbol in target if symbol not in forced]
    forced_total = sum(float(target[symbol]) for symbol in forced)
    adjustable_total = sum(float(target[symbol]) for symbol in adjustable)
    if forced_total + adjustable_total > 1.0 + 1.0e-12 and adjustable_total > 0.0:
        scale = max(1.0 - forced_total, 0.0) / adjustable_total
        for symbol in adjustable:
            target[symbol] *= scale
    blocked_buy = sorted(symbol for symbol, gate in tradability.items() if not gate.buy_ok)
    return target, forced, blocked_buy, events


@dataclass(frozen=True, slots=True)
class AccountPath:
    daily: pd.DataFrame
    holdings: pd.DataFrame
    trades: pd.DataFrame
    events: pd.DataFrame
    metrics: dict[str, float]


def run_account_path(
    *,
    scores: pd.DataFrame,
    market: pd.DataFrame,
    policy: PortfolioPolicy,
    clock: str,
    slippage_multiplier: float,
    end_year: int,
) -> AccountPath:
    if clock not in CLOCKS or end_year not in ANNUAL_YEARS:
        raise ValueError("portfolio_mapping_account_identity_invalid")
    validate_score_panel(scores)
    validate_market_panel(market)
    score_clock = scores.loc[scores["decision_clock"].astype(str).eq(clock)].copy()
    score_clock["decision_date"] = pd.to_datetime(score_clock["decision_date"], errors="raise")
    score_clock = score_clock.loc[score_clock["decision_date"].dt.year.le(end_year)]
    market_clock = market.loc[market["decision_clock"].astype(str).eq(clock)].copy()
    market_clock["date"] = pd.to_datetime(market_clock["date"], errors="raise")
    market_clock = market_clock.loc[market_clock["date"].dt.year.le(end_year)]
    decision_groups = {
        pd.Timestamp(day): frame.copy()
        for day, frame in score_clock.groupby("decision_date", sort=True)
    }
    market_groups = {
        pd.Timestamp(day): frame.copy()
        for day, frame in market_clock.groupby("date", sort=True)
    }
    shares: dict[str, float] = {}
    cash = float(INITIAL_NAV)
    nav = float(INITIAL_NAV)
    previous_marks: dict[str, float] = {}
    daily_rows: list[dict[str, object]] = []
    holding_rows: list[dict[str, object]] = []
    trade_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    for day in sorted(market_groups):
        day_market = market_groups[day].sort_values("symbol", kind="mergesort")
        close_prices = {
                str(row.symbol): float(row.accounting_close_price)
            for row in day_market.itertuples(index=False)
            if pd.notna(row.accounting_close_price)
            and np.isfinite(float(row.accounting_close_price))
            and float(row.accounting_close_price) > 0.0
        }
        previous_nav = nav
        if day in decision_groups:
            ranked = rank_portfolio_table(decision_groups[day])
            execution_prices = {
                str(row.symbol): float(row.accounting_execution_price)
                for row in day_market.itertuples(index=False)
                if pd.notna(row.accounting_execution_price)
                and np.isfinite(float(row.accounting_execution_price))
                and float(row.accounting_execution_price) > 0.0
            }
            tradability = {
                str(row.symbol): TradabilityRow(
                    symbol=str(row.symbol),
                    buy_ok=bool(row.buy_ok) and str(row.symbol) in execution_prices,
                    sell_ok=bool(row.sell_ok) and str(row.symbol) in execution_prices,
                )
                for row in day_market.itertuples(index=False)
            }
            mark_execution = {
                symbol: execution_prices.get(symbol, previous_marks.get(symbol, float("nan")))
                for symbol in shares
            }
            current_weights, execution_nav = current_weights_from_book(
                shares=shares,
                prices=mark_execution,
                cash=cash,
            )
            size_labels = {
                str(row.symbol): str(row.size_bucket)
                for row in day_market.itertuples(index=False)
                if pd.notna(row.size_bucket) and str(row.size_bucket).strip()
            }
            target, forced, blocked_buy, events = build_execution_target(
                ranked,
                policy=policy,
                previous_shares=shares,
                current_weights=current_weights,
                tradability=tradability,
                size_labels=size_labels,
            )
            result = apply_rebalance_day(
                previous_shares=shares,
                previous_cash=cash,
                open_prices=execution_prices,
                close_prices=close_prices,
                target_weights=target,
                forced_symbols=forced,
                blocked_buy_symbols=blocked_buy,
                previous_mark_prices=previous_marks,
                slippage_multiplier=slippage_multiplier,
            )
            shares = cast(dict[str, float], result["shares"])
            cash = float(result["cash"])
            nav = float(result["close_nav"])
            for event in events:
                event_rows.append({"date": day, **event})
            for direction, legs in (
                ("buy", cast(Mapping[str, float], result["buy_legs"])),
                ("sell", cast(Mapping[str, float], result["sell_legs"])),
            ):
                for symbol, weight in sorted(legs.items()):
                    trade_rows.append(
                        {
                            "date": day,
                            "symbol": symbol,
                            "direction": direction,
                            "weight": float(weight),
                            "cost": float(result["cost"]),
                            "execution_nav": float(execution_nav),
                        }
                    )
        else:
            nav = apply_non_rebalance_day(
                shares=shares,
                cash=cash,
                close_prices=close_prices,
                previous_mark_prices=previous_marks,
            )
        daily_return = nav / previous_nav - 1.0 if previous_nav > 0.0 else 0.0
        daily_rows.append(
            {
                "date": day,
                "nav": nav,
                "daily_return": daily_return,
                "cash": cash,
                "cash_weight": cash / nav if nav > 0.0 else 0.0,
                "holding_count": len(shares),
                "is_rebalance": day in decision_groups,
            }
        )
        for symbol, qty in sorted(shares.items()):
            mark = close_prices.get(symbol, previous_marks.get(symbol))
            if mark is None:
                raise ValueError(f"portfolio_mapping_holding_mark_missing:{day.date()}:{symbol}")
            holding_rows.append(
                {
                    "date": day,
                    "symbol": symbol,
                    "shares": float(qty),
                    "mark_price": float(mark),
                    "market_value": float(qty) * float(mark),
                }
            )
        for symbol, price in close_prices.items():
            previous_marks[symbol] = price
    daily = pd.DataFrame(daily_rows)
    return AccountPath(
        daily=daily,
        holdings=pd.DataFrame(holding_rows),
        trades=pd.DataFrame(trade_rows),
        events=pd.DataFrame(event_rows),
        metrics=account_metrics(daily["daily_return"].tolist() if not daily.empty else []),
    )


def _period_log_returns(daily: pd.DataFrame, frequency: str) -> pd.DataFrame:
    if daily.empty:
        columns = ["year", "net_log_return"] if frequency == "year" else ["year", "quarter", "net_log_return"]
        return pd.DataFrame(columns=columns)
    work = daily.copy()
    work["date"] = pd.to_datetime(work["date"], errors="raise")
    work["year"] = work["date"].dt.year
    work["quarter"] = work["date"].dt.quarter
    keys = ["year"] if frequency == "year" else ["year", "quarter"]
    return (
        work.groupby(keys, sort=True)["daily_return"]
        .apply(lambda values: float(np.log1p(values.to_numpy(np.float64)).sum()))
        .rename("net_log_return")
        .reset_index()
    )


def run_policy_family(
    *,
    scores: pd.DataFrame,
    market: pd.DataFrame,
    end_year: int,
) -> dict[str, object]:
    policies = build_policy_grid()
    paths: dict[tuple[str, str, float], AccountPath] = {}
    metric_rows: list[dict[str, object]] = []
    annual_rows: list[dict[str, object]] = []
    quarterly_rows: list[dict[str, object]] = []
    daily_parts: list[pd.DataFrame] = []
    holding_parts: list[pd.DataFrame] = []
    trade_parts: list[pd.DataFrame] = []
    event_parts: list[pd.DataFrame] = []
    for policy in policies:
        for clock in CLOCKS:
            for multiplier in SLIPPAGE_MULTIPLIERS:
                path = run_account_path(
                    scores=scores,
                    market=market,
                    policy=policy,
                    clock=clock,
                    slippage_multiplier=multiplier,
                    end_year=end_year,
                )
                key = (policy.policy_id, clock, multiplier)
                paths[key] = path
                metric_rows.append(
                    {
                        "policy_id": policy.policy_id,
                        "decision_clock": clock,
                        "slippage_multiplier": multiplier,
                        **path.metrics,
                    }
                )
                for row in _period_log_returns(path.daily, "year").to_dict("records"):
                    annual_rows.append(
                        {
                            **row,
                            "policy_id": policy.policy_id,
                            "decision_clock": clock,
                            "slippage_multiplier": multiplier,
                        }
                    )
                for row in _period_log_returns(path.daily, "quarter").to_dict("records"):
                    quarterly_rows.append(
                        {
                            **row,
                            "policy_id": policy.policy_id,
                            "decision_clock": clock,
                            "slippage_multiplier": multiplier,
                        }
                    )
                for name, frame, target in (
                    ("daily", path.daily, daily_parts),
                    ("holdings", path.holdings, holding_parts),
                    ("trades", path.trades, trade_parts),
                    ("events", path.events, event_parts),
                ):
                    if frame.empty:
                        continue
                    local = frame.loc[pd.to_datetime(frame["date"]).dt.year.eq(end_year)].copy()
                    if not local.empty:
                        local["policy_id"] = policy.policy_id
                        local["decision_clock"] = clock
                        local["slippage_multiplier"] = multiplier
                        local["output_kind"] = name
                        target.append(local)
    metrics = pd.DataFrame(metric_rows).sort_values(
        ["policy_id", "decision_clock", "slippage_multiplier"], kind="mergesort"
    ).reset_index(drop=True)
    annual = pd.DataFrame(
        annual_rows,
        columns=["year", "net_log_return", "policy_id", "decision_clock", "slippage_multiplier"],
    )
    quarterly = pd.DataFrame(
        quarterly_rows,
        columns=[
            "year",
            "quarter",
            "net_log_return",
            "policy_id",
            "decision_clock",
            "slippage_multiplier",
        ],
    )
    eligible: list[str] = []
    gate_rows: list[dict[str, object]] = []
    increments: dict[str, float] = {}
    for policy in policies:
        if policy.policy_id == COMMON_ROOT_POLICY_ID:
            continue
        clock_passes: list[bool] = []
        worst_clock = math.inf
        for clock in CLOCKS:
            candidate_base = metrics.loc[
                metrics["policy_id"].eq(policy.policy_id)
                & metrics["decision_clock"].eq(clock)
                & metrics["slippage_multiplier"].eq(1.0)
            ].iloc[0].to_dict()
            root_base = metrics.loc[
                metrics["policy_id"].eq(COMMON_ROOT_POLICY_ID)
                & metrics["decision_clock"].eq(clock)
                & metrics["slippage_multiplier"].eq(1.0)
            ].iloc[0].to_dict()
            annual_candidate = annual.loc[
                annual["policy_id"].eq(policy.policy_id)
                & annual["decision_clock"].eq(clock)
                & annual["slippage_multiplier"].eq(1.0)
            ].set_index("year")["net_log_return"]
            annual_root = annual.loc[
                annual["policy_id"].eq(COMMON_ROOT_POLICY_ID)
                & annual["decision_clock"].eq(clock)
                & annual["slippage_multiplier"].eq(1.0)
            ].set_index("year")["net_log_return"]
            annual_index = sorted(set(annual_candidate.index) | set(annual_root.index))
            annual_increment = [float(annual_candidate.get(year, 0.0) - annual_root.get(year, 0.0)) for year in annual_index]
            candidate_q = quarterly.loc[
                quarterly["policy_id"].eq(policy.policy_id)
                & quarterly["decision_clock"].eq(clock)
                & quarterly["slippage_multiplier"].eq(1.0)
            ].set_index(["year", "quarter"])["net_log_return"]
            root_q = quarterly.loc[
                quarterly["policy_id"].eq(COMMON_ROOT_POLICY_ID)
                & quarterly["decision_clock"].eq(clock)
                & quarterly["slippage_multiplier"].eq(1.0)
            ].set_index(["year", "quarter"])["net_log_return"]
            quarter_index = sorted(set(candidate_q.index) | set(root_q.index))
            quarterly_increment = [
                (int(year), int(quarter), float(candidate_q.get((year, quarter), 0.0) - root_q.get((year, quarter), 0.0)))
                for year, quarter in quarter_index
            ]
            by_cost = {
                multiplier: float(
                    metrics.loc[
                        metrics["policy_id"].eq(policy.policy_id)
                        & metrics["decision_clock"].eq(clock)
                        & metrics["slippage_multiplier"].eq(multiplier),
                        "net_log_return",
                    ].iloc[0]
                )
                for multiplier in SLIPPAGE_MULTIPLIERS
            }
            root_by_cost = {
                multiplier: float(
                    metrics.loc[
                        metrics["policy_id"].eq(COMMON_ROOT_POLICY_ID)
                        & metrics["decision_clock"].eq(clock)
                        & metrics["slippage_multiplier"].eq(multiplier),
                        "net_log_return",
                    ].iloc[0]
                )
                for multiplier in SLIPPAGE_MULTIPLIERS
            }
            annual_gate = evaluate_annual_gate(annual_increment)
            quarterly_gate = evaluate_quarterly_gate(quarterly_increment)
            economics_gate = evaluate_economics_gate(
                challenger_metrics=cast(Mapping[str, float], candidate_base),
                root_metrics=cast(Mapping[str, float], root_base),
                cost_multipliers=(2.0, 3.0),
                challenger_by_cost=by_cost,
                root_by_cost=root_by_cost,
            )
            passed = bool(annual_gate["passed"] and quarterly_gate["passed"] and economics_gate["passed"])
            clock_passes.append(passed)
            net_increment = float(candidate_base["net_log_return"] - root_base["net_log_return"])
            worst_clock = min(worst_clock, net_increment)
            gate_rows.append(
                {
                    "policy_id": policy.policy_id,
                    "decision_clock": clock,
                    "annual_passed": bool(annual_gate["passed"]),
                    "quarterly_passed": bool(quarterly_gate["passed"]),
                    "economics_passed": bool(economics_gate["passed"]),
                    "all_passed": passed,
                    "net_log_return_increment": net_increment,
                }
            )
        increments[policy.policy_id] = worst_clock
        if all(clock_passes):
            eligible.append(policy.policy_id)
    selected = tie_break_policies(eligible, clock_increments=increments) if eligible else COMMON_ROOT_POLICY_ID

    def _clock_nomination(challenger_clock: str, comparison_clock: str) -> dict[str, object]:
        challenger_base = metrics.loc[
            metrics["policy_id"].eq(selected)
            & metrics["decision_clock"].eq(challenger_clock)
            & metrics["slippage_multiplier"].eq(1.0)
        ].iloc[0]
        comparison_base = metrics.loc[
            metrics["policy_id"].eq(selected)
            & metrics["decision_clock"].eq(comparison_clock)
            & metrics["slippage_multiplier"].eq(1.0)
        ].iloc[0]
        challenger_annual = annual.loc[
            annual["policy_id"].eq(selected)
            & annual["decision_clock"].eq(challenger_clock)
            & annual["slippage_multiplier"].eq(1.0)
        ].set_index("year")["net_log_return"]
        comparison_annual = annual.loc[
            annual["policy_id"].eq(selected)
            & annual["decision_clock"].eq(comparison_clock)
            & annual["slippage_multiplier"].eq(1.0)
        ].set_index("year")["net_log_return"]
        supported_years = sorted(set(challenger_annual.index) | set(comparison_annual.index))
        annual_differences = [
            float(challenger_annual.get(year, 0.0) - comparison_annual.get(year, 0.0))
            for year in supported_years
        ]
        challenger_q = quarterly.loc[
            quarterly["policy_id"].eq(selected)
            & quarterly["decision_clock"].eq(challenger_clock)
            & quarterly["slippage_multiplier"].eq(1.0)
        ].set_index(["year", "quarter"])["net_log_return"]
        comparison_q = quarterly.loc[
            quarterly["policy_id"].eq(selected)
            & quarterly["decision_clock"].eq(comparison_clock)
            & quarterly["slippage_multiplier"].eq(1.0)
        ].set_index(["year", "quarter"])["net_log_return"]
        quarter_index = sorted(set(challenger_q.index) | set(comparison_q.index))
        quarter_differences = [
            (
                int(year),
                int(quarter),
                float(challenger_q.get((year, quarter), 0.0) - comparison_q.get((year, quarter), 0.0)),
            )
            for year, quarter in quarter_index
        ]
        stress_differences = {
            multiplier: float(
                metrics.loc[
                    metrics["policy_id"].eq(selected)
                    & metrics["decision_clock"].eq(challenger_clock)
                    & metrics["slippage_multiplier"].eq(multiplier),
                    "net_log_return",
                ].iloc[0]
                - metrics.loc[
                    metrics["policy_id"].eq(selected)
                    & metrics["decision_clock"].eq(comparison_clock)
                    & metrics["slippage_multiplier"].eq(multiplier),
                    "net_log_return",
                ].iloc[0]
            )
            for multiplier in (2.0, 3.0)
        }
        quarter_gate = evaluate_quarterly_gate(quarter_differences)
        passed = bool(
            len(supported_years) >= 10
            and sum(value > 0.0 for value in annual_differences) >= 7
            and float(challenger_base["net_log_return"]) > float(comparison_base["net_log_return"])
            and float(challenger_base["sharpe"]) > float(comparison_base["sharpe"])
            and float(challenger_base["maximum_drawdown"]) >= float(comparison_base["maximum_drawdown"])
            and bool(quarter_gate["passed"])
            and all(value > 0.0 for value in stress_differences.values())
        )
        return {
            "challenger_clock": challenger_clock,
            "comparison_clock": comparison_clock,
            "supported_year_count": len(supported_years),
            "positive_annual_difference_count": sum(value > 0.0 for value in annual_differences),
            "quarterly_gate": quarter_gate,
            "stress_net_log_return_differences": stress_differences,
            "passed": passed,
        }

    clock_1430 = _clock_nomination("14:30", "14:45")
    clock_1445 = _clock_nomination("14:45", "14:30")
    nominated_clock = "14:30" if clock_1430["passed"] else "14:45" if clock_1445["passed"] else None
    def _concat(parts: list[pd.DataFrame]) -> pd.DataFrame:
        return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return {
        "selected_policy_id": selected,
        "eligible_policy_ids": eligible,
        "clock_nomination": {
            "nominated_clock": nominated_clock,
            "default_when_none": "parallel_1430_1445_research_books",
            "tests": [clock_1430, clock_1445],
        },
        "metrics": metrics,
        "annual": annual,
        "quarterly": quarterly,
        "gates": pd.DataFrame(gate_rows),
        "daily": _concat(daily_parts),
        "holdings": _concat(holding_parts),
        "trades": _concat(trade_parts),
        "events": _concat(event_parts),
        "attempt_count": len(policies) * len(CLOCKS) * len(SLIPPAGE_MULTIPLIERS),
    }


def compare_tree_bytes(left: Path, right: Path) -> tuple[bool, list[str]]:
    mismatches: list[str] = []
    left_files = {path.relative_to(left).as_posix(): path for path in left.rglob("*") if path.is_file()}
    right_files = {path.relative_to(right).as_posix(): path for path in right.rglob("*") if path.is_file()}
    for name in sorted(set(left_files) | set(right_files)):
        lpath = left_files.get(name)
        rpath = right_files.get(name)
        if lpath is None or rpath is None:
            mismatches.append(name)
            continue
        if lpath.read_bytes() != rpath.read_bytes():
            mismatches.append(name)
    return not mismatches, mismatches


def source_closure_for_module() -> dict[str, str]:
    root = repo_root()
    files = [
        root / "docs/ops/reaka_intraday_portfolio_mapping@1.0.json",
        root / "docs/ops/reaka_intraday_portfolio_mapping@1.1.json",
        root / "docs/ops/reaka_intraday_portfolio_mapping@1.2.json",
        root / "docs/ops/reaka_intraday_portfolio_mapping_whitepaper.md",
        root / "docs/user/reaka_intraday_portfolio_mapping_workflow.md",
        root / "src/factor_lab/factor_rotation/reaka_intraday_portfolio_mapping_v1.py",
        root / "scripts/factor_rotation/build_reaka_intraday_portfolio_mapping_inputs_v1.py",
        root / "scripts/factor_rotation/prepare_reaka_intraday_portfolio_mapping_session_v1.py",
        root / "scripts/factor_rotation/validate_reaka_intraday_portfolio_mapping_v1.py",
        root / "tests/unit/test_reaka_intraday_portfolio_mapping_v1.py",
        root / "src/factor_lab/factor_rotation/macro_regime_dual_strategy_round2.py",
        root / "src/factor_lab/factor_rotation/orthogonal_index_timing_transport_ot1_v1.py",
        root / "src/factor_lab/factor_rotation/reaka_intraday_k1_preflight_v1.py",
        root / "src/factor_lab/factor_rotation/reaka_intraday_k1_training_v1.py",
        root / "src/factor_lab/factor_rotation/reaka_intraday_k1_fit_prefix_successor_v1.py",
        root / "src/factor_lab/factor_rotation/reaka_paper_v1.py",
        root / "src/factor_lab/factor_rotation/reaka_parameter_governance.py",
        root / "src/factor_lab/factor_rotation/reaka_prediction_root_routing.py",
        root / "src/factor_lab/factor_rotation/reaka_stage5_parameter_compiler.py",
        root / "src/factor_lab/factor_rotation/reaka_stage6_daily_engine.py",
        root / "src/factor_lab/factor_rotation/reaka_stage6_paper_faithful_freeze.py",
        root / "src/factor_lab/factor_rotation/reaka_stage6_parameter_calibration.py",
        root / "src/factor_lab/factor_rotation/reaka_stage6_task_alignment.py",
        root / "src/factor_lab/factor_rotation/reaka_stage6_temporal_coordinate.py",
        root / "src/factor_lab/governance/canonicalization.py",
    ]
    return {str(path.relative_to(root)): file_digest(path) for path in files if path.is_file()}


def validate_input_manifest(payload: Mapping[str, object]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema_id") != INPUT_SCHEMA_ID:
        blockers.append("input_schema_invalid")
    if not canonical_valid(payload):
        blockers.append("input_digest_invalid")
    if payload.get("contract_digest") != CONTRACT_DIGEST:
        blockers.append("input_contract_digest_mismatch")
    if payload.get("future_entry_or_target_filter_applied") is not False:
        blockers.append("future_filter_applied")
    if int(payload.get("post_2020_rows", 0)) != 0:
        blockers.append("post_2020_rows_present")
    clocks = payload.get("decision_clocks")
    if clocks != list(CLOCKS):
        blockers.append("decision_clocks_invalid")
    return blockers


def validate_session_receipt(payload: Mapping[str, object]) -> list[str]:
    blockers: list[str] = []
    if payload.get("schema_id") != SESSION_SCHEMA_ID:
        blockers.append("session_schema_invalid")
    if not canonical_valid(payload):
        blockers.append("session_digest_invalid")
    if payload.get("contract_digest") != CONTRACT_DIGEST:
        blockers.append("session_contract_digest_mismatch")
    if payload.get("account_mapping_execution_allowed") is not True:
        blockers.append("session_account_execution_not_admitted")
    if payload.get("production_authority") is not False:
        blockers.append("session_production_not_closed")
    if int(payload.get("policy_count", 0)) != 24:
        blockers.append("session_policy_count_invalid")
    if int(payload.get("attempt_count", 0)) != 144:
        blockers.append("session_attempt_count_invalid")
    if int(payload.get("post_2020_rows_read", -1)) != 0:
        blockers.append("session_post_2020_read")
    if payload.get("fresh_oos") is not False:
        blockers.append("session_fresh_oos_invalid")
    return blockers


__all__ = [
    "ADMISSION_SCHEMA_ID",
    "AccountPath",
    "ANNUAL_YEARS",
    "CLOCKS",
    "COMMON_ROOT_POLICY_ID",
    "CONTRACT_DIGEST",
    "INPUT_SCHEMA_ID",
    "PortfolioPolicy",
    "SCHEMA_ID",
    "SESSION_SCHEMA_ID",
    "SEEDS_FORMAL",
    "SLIPPAGE_MULTIPLIERS",
    "TradabilityRow",
    "VALIDATION_SCHEMA_ID",
    "account_metrics",
    "allocate_target_shares",
    "apply_industry_cap",
    "apply_non_rebalance_day",
    "apply_rebalance_day",
    "apply_size_tercile_cap",
    "average_tie_ranks",
    "assert_no_future_filter",
    "build_policy_grid",
    "build_execution_target",
    "buy_cost_bps",
    "common_root_policy",
    "compare_tree_bytes",
    "contract_path",
    "ensemble_seed_rank_z",
    "evaluate_annual_gate",
    "evaluate_economics_gate",
    "evaluate_quarterly_gate",
    "file_digest",
    "load_contract",
    "per_decision_rank_z",
    "policy_by_id",
    "rank_linear_weights",
    "rank_portfolio_table",
    "read_json",
    "repo_root",
    "select_target_symbols",
    "sell_cost_bps",
    "source_closure_for_module",
    "target_weights_for_policy",
    "tie_break_policies",
    "turnover_from_weights",
    "run_account_path",
    "run_policy_family",
    "validate_admission",
    "validate_contract_payload",
    "validate_input_manifest",
    "validate_market_panel",
    "validate_score_panel",
    "validate_session_receipt",
    "validate_year_request",
    "write_json",
]
