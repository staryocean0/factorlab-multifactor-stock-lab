"""Stage 6 share-based portfolio execution engine.

This module implements the frozen 2026-08-18 execution contract.  It does
not rank tasks, horizons or sizes by returns and does not train models.
"""

# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportGeneralTypeIssues=false, reportOptionalMemberAccess=false
# pyright: reportOptionalSubscript=false, reportMissingTypeArgument=false
# pyright: reportReturnType=false, reportIndexIssue=false
# pyright: reportOperatorIssue=false, reportCallIssue=false
# pyright: reportUnknownVariableType=false, reportUnknownArgumentType=false
# pyright: reportUnknownMemberType=false, reportUnusedCallResult=false
# pyright: reportPossiblyUnboundVariable=false, reportUnusedExpression=false
# pyright: reportImplicitRelativeImport=false
# pyright: reportAny=false, reportExplicitAny=false, reportMissingTypeStubs=false

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np
import pandas as pd

CADENCE_INTERVALS: dict[str, int] = {"daily": 1, "weekly": 5, "biweekly": 10}
PORTFOLIO_SIZES: tuple[int, ...] = (30, 50, 100)
SLIPPAGE_MULTIPLIERS: tuple[float, ...] = (1.0, 2.0, 3.0)
COMMISSION_BPS = 2.5
TRANSFER_FEE_BPS = 0.1
STAMP_TAX_SELL_BPS = 5.0
BASELINE_SLIPPAGE_BPS = 2.0
TICK_SIZE = 0.01
INITIAL_NAV = 1_000_000.0


def buy_cost_bps(slippage_multiplier: float) -> float:
    return COMMISSION_BPS + TRANSFER_FEE_BPS + BASELINE_SLIPPAGE_BPS * float(slippage_multiplier)


def sell_cost_bps(slippage_multiplier: float) -> float:
    return (
        COMMISSION_BPS
        + TRANSFER_FEE_BPS
        + STAMP_TAX_SELL_BPS
        + BASELINE_SLIPPAGE_BPS * float(slippage_multiplier)
    )


def round_tick(price: float) -> float:
    if not np.isfinite(price):
        return float("nan")
    return float(np.round(price / TICK_SIZE) * TICK_SIZE)


def map_risk_warning_for_rules(state: str) -> str:
    value = str(state or "").strip().lower()
    if value in {"st", "star_st", "risk_warning", "*st"}:
        return "risk_warning"
    if value in {"normal"}:
        return "normal"
    return "unknown"


@dataclass(frozen=True, slots=True)
class ExecutionEligibility:
    buy_ok: bool
    sell_ok: bool
    paused: bool
    limit_up_price: float | None
    limit_down_price: float | None
    is_limit_up: bool
    is_limit_down: bool
    has_limit: bool | None
    rule_status: str
    rule_id: str
    reason: str


def eligibility_from_row(
    row: Mapping[str, object],
    *,
    previous_tradable_close: float | None,
    open_price: float | None,
    resolved: Mapping[str, object],
) -> ExecutionEligibility:
    suspension = str(row.get("suspension_status") or "")
    paused = suspension in {"full_day", "intraday_halt"}
    status = str(resolved.get("status") or "")
    params = dict(resolved.get("params") or {})
    has_limit: bool | None
    raw_limit = params.get("has_limit", None)
    if raw_limit == True:  # noqa: E712
        has_limit = True
    elif raw_limit == False:  # noqa: E712
        has_limit = False
    else:
        has_limit = None
    limit_up = None
    limit_down = None
    is_limit_up = False
    is_limit_down = False
    reason = "ok"
    if paused:
        reason = f"paused:{suspension}"
    elif status != "resolved":
        reason = f"price_limit_{status}:{resolved.get('rule_id') or resolved.get('gap_id') or resolved.get('detail')}"
    elif previous_tradable_close is None or not np.isfinite(float(previous_tradable_close)):
        reason = "missing_previous_tradable_close"
    elif open_price is None or not np.isfinite(float(open_price)) or float(open_price) <= 0:
        reason = "missing_open_price"
    else:
        if has_limit:
            up_ratio = float(params["upper_ratio"])
            down_ratio = float(params["lower_ratio"])
            limit_up = round_tick(float(previous_tradable_close) * (1.0 + up_ratio))
            limit_down = round_tick(float(previous_tradable_close) * (1.0 - down_ratio))
            is_limit_up = float(open_price) >= float(limit_up) - 1e-12
            is_limit_down = float(open_price) <= float(limit_down) + 1e-12
        elif has_limit is False:
            reason = "no_limit_rule"
        else:
            reason = "limit_flag_unknown"
    buy_ok = (not paused) and reason in {"ok", "no_limit_rule"} and not is_limit_up
    sell_ok = (not paused) and reason in {"ok", "no_limit_rule"} and not is_limit_down
    if reason == "no_limit_rule":
        # Uncapped first-five days remain executable if the name is not paused
        # and has a valid open; ipo_day without a resolved rule stays blocked.
        buy_ok = (not paused) and open_price is not None and np.isfinite(float(open_price)) and float(open_price) > 0
        sell_ok = buy_ok
        if status != "resolved":
            buy_ok = False
            sell_ok = False
            reason = f"price_limit_{status}"
    return ExecutionEligibility(
        buy_ok=bool(buy_ok),
        sell_ok=bool(sell_ok),
        paused=bool(paused),
        limit_up_price=limit_up,
        limit_down_price=limit_down,
        is_limit_up=bool(is_limit_up),
        is_limit_down=bool(is_limit_down),
        has_limit=has_limit,
        rule_status=status,
        rule_id=str(resolved.get("rule_id") or resolved.get("gap_id") or ""),
        reason=reason,
    )


def rank_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    work = frame.copy()
    work["finite_score"] = np.isfinite(pd.to_numeric(work["score"], errors="coerce"))
    work["positive_channels"] = pd.to_numeric(work["available_channel_count"], errors="coerce").fillna(0) > 0
    work["eligible_new_buy"] = work["finite_score"] & work["positive_channels"]
    return work.sort_values(
        ["eligible_new_buy", "score", "symbol"],
        ascending=[False, False, True],
        kind="mergesort",
    ).reset_index(drop=True)


def select_target_symbols(
    ranked: pd.DataFrame,
    *,
    size: int,
    previous_shares: Mapping[str, float],
    eligibility: Mapping[str, ExecutionEligibility],
) -> tuple[list[str], list[dict[str, object]]]:
    forced: list[str] = []
    events: list[dict[str, object]] = []
    for symbol in sorted(previous_shares):
        if float(previous_shares[symbol]) <= 0:
            continue
        gate = eligibility.get(symbol)
        if gate is None or not gate.sell_ok:
            forced.append(symbol)
            events.append(
                {
                    "symbol": symbol,
                    "event_type": "forced_carry",
                    "reason": "sell_unavailable" if gate is not None else "missing_eligibility",
                    "detail": gate.reason if gate is not None else "missing_eligibility",
                }
            )
    remaining = max(int(size) - len(forced), 0)
    chosen: list[str] = list(forced)
    if remaining == 0 and forced:
        events.append(
            {
                "symbol": "",
                "event_type": "forced_carry_exceeds_limit",
                "reason": "open_no_new_names",
                "detail": f"forced={len(forced)};size={size}",
            }
        )
        return chosen, events
    for row in ranked.itertuples(index=False):
        symbol = str(row.symbol)
        if symbol in chosen:
            continue
        if not bool(row.eligible_new_buy):
            continue
        gate = eligibility.get(symbol)
        is_held = float(previous_shares.get(symbol, 0.0)) > 0
        if is_held and gate is not None and not gate.buy_ok:
            chosen.append(symbol)
            events.append(
                {
                    "symbol": symbol,
                    "event_type": "held_buy_blocked_carry",
                    "reason": "buy_unavailable_existing_position",
                    "detail": gate.reason,
                }
            )
            if len(chosen) - len(forced) >= remaining:
                break
            continue
        if gate is None or not gate.buy_ok:
            events.append(
                {
                    "symbol": symbol,
                    "event_type": "buy_skip_backfill",
                    "reason": "buy_unavailable",
                    "detail": gate.reason if gate is not None else "missing_eligibility",
                }
            )
            continue
        chosen.append(symbol)
        if len(chosen) - len(forced) >= remaining:
            break
    return chosen, events


def allocate_shares(
    *,
    nav_after_cost: float,
    open_prices: Mapping[str, float],
    target_symbols: list[str],
    forced_symbols: list[str],
    previous_shares: Mapping[str, float],
) -> dict[str, float]:
    shares: dict[str, float] = {}
    forced_value = 0.0
    for symbol in forced_symbols:
        qty = float(previous_shares.get(symbol, 0.0))
        price = float(open_prices.get(symbol, float("nan")))
        if qty > 0 and np.isfinite(price) and price > 0:
            shares[symbol] = qty
            forced_value += qty * price
    tradable_nav = max(float(nav_after_cost) - forced_value, 0.0)
    new_symbols = [
        symbol
        for symbol in target_symbols
        if symbol not in shares
        and np.isfinite(float(open_prices.get(symbol, float("nan"))))
        and float(open_prices.get(symbol, float("nan"))) > 0
    ]
    if not new_symbols:
        return shares
    weight = tradable_nav / float(len(new_symbols))
    for symbol in new_symbols:
        price = float(open_prices[symbol])
        shares[symbol] = weight / price
    return shares


def _valid_price(value: object) -> bool:
    try:
        price = float(value)
    except (TypeError, ValueError):
        return False
    return bool(np.isfinite(price) and price > 0)


def _resolve_mark_prices(
    symbols: set[str],
    primary: Mapping[str, float],
    fallback: Mapping[str, float],
    *,
    context: str,
) -> dict[str, float]:
    resolved: dict[str, float] = {}
    for symbol in sorted(symbols):
        primary_value = primary.get(symbol)
        fallback_value = fallback.get(symbol)
        if _valid_price(primary_value):
            resolved[symbol] = float(primary_value)
        elif _valid_price(fallback_value):
            resolved[symbol] = float(fallback_value)
        else:
            raise ValueError(f"stage6_portfolio_unpriced_position:{context}:{symbol}")
    return resolved


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
        if delta > 0:
            buy[name] = delta
            buy_sum += delta
        elif delta < 0:
            sell[name] = -delta
            sell_sum += -delta
    return buy_sum, sell_sum, buy, sell


def apply_rebalance_day(
    *,
    previous_close_nav: float,
    previous_shares: Mapping[str, float],
    previous_close_prices: Mapping[str, float],
    open_prices: Mapping[str, float],
    close_prices: Mapping[str, float],
    target_symbols: list[str],
    forced_symbols: list[str],
    slippage_multiplier: float,
) -> dict[str, object]:
    held_symbols = {symbol for symbol, qty in previous_shares.items() if float(qty) > 0}
    execution_prices = _resolve_mark_prices(
        held_symbols,
        open_prices,
        previous_close_prices,
        context="execution_open",
    )
    for symbol in target_symbols:
        if symbol not in execution_prices and _valid_price(open_prices.get(symbol)):
            execution_prices[symbol] = float(open_prices[symbol])
    overnight_nav = 0.0
    current_weights: dict[str, float] = {}
    for symbol, qty in sorted(previous_shares.items()):
        if qty > 0:
            overnight_nav += float(qty) * execution_prices[symbol]
    if not held_symbols:
        overnight_nav = float(previous_close_nav)
    for symbol, qty in sorted(previous_shares.items()):
        if qty > 0 and overnight_nav > 0:
            current_weights[symbol] = float(qty) * execution_prices[symbol] / overnight_nav
    # Equal-weight target over names that remain after forced carry.
    target_names = list(dict.fromkeys(target_symbols))
    if not target_names:
        target_names = [s for s, q in previous_shares.items() if q > 0]
    target_weights = {symbol: 1.0 / len(target_names) for symbol in target_names} if target_names else {}
    # Forced names keep their current open-weight; remaining names share leftover equally.
    if forced_symbols:
        forced_w = sum(current_weights.get(symbol, 0.0) for symbol in forced_symbols)
        leftover = max(1.0 - forced_w, 0.0)
        adjustable = [s for s in target_names if s not in forced_symbols]
        target_weights = {s: current_weights.get(s, 0.0) for s in forced_symbols}
        if adjustable:
            each = leftover / len(adjustable)
            for symbol in adjustable:
                target_weights[symbol] = each
        else:
            # all forced: renormalize current
            total = sum(current_weights.get(s, 0.0) for s in forced_symbols) or 1.0
            target_weights = {s: current_weights.get(s, 0.0) / total for s in forced_symbols}
    buy_weight, sell_weight, buy_legs, sell_legs = turnover_from_weights(
        current_weights, target_weights
    )
    cost = overnight_nav * (
        buy_weight * buy_cost_bps(slippage_multiplier) / 10000.0
        + sell_weight * sell_cost_bps(slippage_multiplier) / 10000.0
    )
    nav_after_cost = overnight_nav - cost
    shares = allocate_shares(
        nav_after_cost=nav_after_cost,
        open_prices=execution_prices,
        target_symbols=list(target_weights),
        forced_symbols=forced_symbols,
        previous_shares=previous_shares,
    )
    if target_weights and not shares and nav_after_cost > 0:
        raise ValueError("stage6_portfolio_legal_target_produced_empty_share_book")
    close_mark_prices = _resolve_mark_prices(
        {symbol for symbol, qty in shares.items() if float(qty) > 0},
        close_prices,
        execution_prices,
        context="execution_close",
    )
    close_nav = 0.0
    for symbol, qty in shares.items():
        if qty > 0:
            close_nav += float(qty) * close_mark_prices[symbol]
    return {
        "overnight_nav": float(overnight_nav),
        "nav_after_cost": float(nav_after_cost),
        "close_nav": float(close_nav),
        "buy_weight": float(buy_weight),
        "sell_weight": float(sell_weight),
        "cost": float(cost),
        "shares": shares,
        "buy_legs": buy_legs,
        "sell_legs": sell_legs,
        "current_weights": current_weights,
        "target_weights": target_weights,
        "execution_prices": execution_prices,
        "close_mark_prices": close_mark_prices,
    }


def apply_non_rebalance_day(
    *,
    shares: Mapping[str, float],
    close_prices: Mapping[str, float],
    previous_close_prices: Mapping[str, float] | None = None,
    fallback_nav: float | None = None,
) -> float:
    held_symbols = {symbol for symbol, qty in shares.items() if float(qty) > 0}
    if not held_symbols:
        return float(fallback_nav) if fallback_nav is not None else 0.0
    mark_prices = _resolve_mark_prices(
        held_symbols,
        close_prices,
        previous_close_prices or {},
        context="non_rebalance_close",
    )
    nav = 0.0
    for symbol, qty in shares.items():
        if qty > 0:
            nav += float(qty) * mark_prices[symbol]
    return float(nav)


def book_identity(shares: Mapping[str, float]) -> tuple[tuple[str, float], ...]:
    return tuple(
        (symbol, round(float(qty), 10))
        for symbol, qty in sorted(shares.items())
        if float(qty) > 0
    )


def book_path_digest(holdings: pd.DataFrame) -> str:
    digest = hashlib.sha256()
    if holdings.empty:
        return digest.hexdigest()
    required = holdings.loc[:, ["date", "symbol", "shares"]].copy()
    required["date"] = pd.to_datetime(required["date"], errors="raise")
    required["symbol"] = required["symbol"].astype(str)
    required["shares"] = pd.to_numeric(required["shares"], errors="raise")
    required = required.sort_values(["date", "symbol"], kind="mergesort")
    for row in required.itertuples(index=False):
        digest.update(
            f"{pd.Timestamp(row.date).date().isoformat()}|{row.symbol}|{float(row.shares):.10f}\n".encode()
        )
    return digest.hexdigest()


def run_account(
    *,
    calendar: list[pd.Timestamp],
    rebalance_execution_dates: set[pd.Timestamp],
    scores_by_decision: Mapping[pd.Timestamp, pd.DataFrame],
    open_prices: pd.DataFrame,
    close_prices: pd.DataFrame,
    eligibility_by_date: Mapping[pd.Timestamp, Mapping[str, ExecutionEligibility]],
    size: int,
    slippage_multiplier: float,
    decision_to_execution: Mapping[pd.Timestamp, pd.Timestamp],
    initial_shares: Mapping[str, float] | None = None,
    initial_nav: float = INITIAL_NAV,
    initial_started: bool = False,
    initial_previous_close_prices: Mapping[str, float] | None = None,
) -> dict[str, pd.DataFrame]:
    daily_rows: list[dict[str, object]] = []
    holding_rows: list[dict[str, object]] = []
    trade_rows: list[dict[str, object]] = []
    turnover_rows: list[dict[str, object]] = []
    event_rows: list[dict[str, object]] = []
    shares: dict[str, float] = {
        str(symbol): float(quantity) for symbol, quantity in dict(initial_shares or {}).items()
    }
    nav = float(initial_nav)
    started = bool(initial_started)
    previous_close_prices: dict[str, float] = {
        str(symbol): float(price) for symbol, price in dict(initial_previous_close_prices or {}).items()
    }
    execution_to_decision = {value: key for key, value in decision_to_execution.items()}
    for i, current in enumerate(calendar):
        current_ts = pd.Timestamp(current)
        is_rebalance = current_ts in rebalance_execution_dates
        if (not started) and (not is_rebalance):
            continue
        needed: set[str] = set(shares)
        ranked_preview = None
        if is_rebalance:
            decision = execution_to_decision.get(current_ts)
            ranked_preview = scores_by_decision.get(pd.Timestamp(decision)) if decision is not None else None
            if ranked_preview is not None and not ranked_preview.empty:
                needed.update(ranked_preview["symbol"].astype(str).tolist())
        open_map: dict[str, float] = {}
        close_map: dict[str, float] = {}
        holding_mark_prices: dict[str, float] = {}
        if current_ts in open_prices.index:
            open_row = open_prices.loc[current_ts]
            for symbol in sorted(needed):
                value = (
                    open_row.get(symbol, np.nan)
                    if hasattr(open_row, "get")
                    else open_row[symbol]
                    if symbol in open_row.index
                    else np.nan
                )
                if np.isfinite(value):
                    open_map[symbol] = float(value)
        if current_ts in close_prices.index:
            close_row = close_prices.loc[current_ts]
            for symbol in sorted(needed):
                value = (
                    close_row.get(symbol, np.nan)
                    if hasattr(close_row, "get")
                    else close_row[symbol]
                    if symbol in close_row.index
                    else np.nan
                )
                if np.isfinite(value):
                    close_map[symbol] = float(value)
        if is_rebalance:
            decision = execution_to_decision.get(current_ts)
            ranked = scores_by_decision.get(pd.Timestamp(decision)) if decision is not None else None
            no_preference = False
            if ranked is not None and not ranked.empty:
                finite_score = np.isfinite(pd.to_numeric(ranked["score"], errors="coerce"))
                positive_channels = pd.to_numeric(
                    ranked["available_channel_count"], errors="coerce"
                ).fillna(0).gt(0)
                no_preference = not bool((finite_score & positive_channels).any())
            if ranked is None or ranked.empty or no_preference:
                event_rows.append(
                    {
                        "date": current_ts,
                        "symbol": "",
                        "event_type": "neutral_keep" if no_preference else "missing_decision_scores",
                        "reason": "zero_factor_preference_keep_whole_book" if no_preference else "no_scores",
                        "detail": "",
                    }
                )
                close_nav = (
                    apply_non_rebalance_day(
                        shares=shares,
                        close_prices=close_map,
                        previous_close_prices=previous_close_prices,
                        fallback_nav=nav,
                    )
                    if started
                    else nav
                )
                nav = close_nav if started else nav
                if started:
                    holding_mark_prices = _resolve_mark_prices(
                        set(shares),
                        close_map,
                        previous_close_prices,
                        context="missing_scores_close",
                    )
                    daily_rows.append(
                        {
                            "date": current_ts,
                            "is_rebalance": True,
                            "overnight_nav": nav,
                            "nav_after_cost": nav,
                            "close_nav": nav,
                            "buy_weight": 0.0,
                            "sell_weight": 0.0,
                            "cost": 0.0,
                            "started": True,
                        }
                    )
                elif no_preference:
                    daily_rows.append(
                        {
                            "date": current_ts,
                            "is_rebalance": True,
                            "overnight_nav": nav,
                            "nav_after_cost": nav,
                            "close_nav": nav,
                            "buy_weight": 0.0,
                            "sell_weight": 0.0,
                            "cost": 0.0,
                            "started": False,
                        }
                    )
            else:
                gates = eligibility_by_date.get(current_ts, {})
                ranked = rank_candidates(ranked)
                target_symbols, events = select_target_symbols(
                    ranked,
                    size=size,
                    previous_shares=shares,
                    eligibility=gates,
                )
                forced = [
                    str(item["symbol"])
                    for item in events
                    if item["event_type"] in {"forced_carry", "held_buy_blocked_carry"}
                    and item["symbol"]
                ]
                for item in events:
                    event_rows.append({"date": current_ts, **item})
                if not started and not target_symbols:
                    event_rows.append(
                        {
                            "date": current_ts,
                            "symbol": "",
                            "event_type": "inception_delayed",
                            "reason": "opportunity_absent",
                            "detail": "",
                        }
                    )
                    daily_rows.append(
                        {
                            "date": current_ts,
                            "is_rebalance": True,
                            "overnight_nav": nav,
                            "nav_after_cost": nav,
                            "close_nav": nav,
                            "buy_weight": 0.0,
                            "sell_weight": 0.0,
                            "cost": 0.0,
                            "started": False,
                        }
                    )
                    previous_close_prices = close_map
                    continue
                if started and not target_symbols:
                    target_symbols = list(shares)
                    event_rows.append(
                        {
                            "date": current_ts,
                            "symbol": "",
                            "event_type": "carry_existing_book",
                            "reason": "zero_eligible_after_inception",
                            "detail": "",
                        }
                    )
                result = apply_rebalance_day(
                    previous_close_nav=nav,
                    previous_shares=shares,
                    previous_close_prices=previous_close_prices,
                    open_prices=open_map,
                    close_prices=close_map,
                    target_symbols=target_symbols,
                    forced_symbols=forced,
                    slippage_multiplier=slippage_multiplier,
                )
                old_shares = dict(shares)
                shares = {str(k): float(v) for k, v in dict(result["shares"]).items()}
                nav = float(result["close_nav"])
                holding_mark_prices = {
                    str(k): float(v) for k, v in dict(result["close_mark_prices"]).items()
                }
                started = True
                for symbol, qty in dict(result["buy_legs"]).items():
                    trade_rows.append(
                        {
                            "date": current_ts,
                            "symbol": symbol,
                            "side": "buy",
                            "weight": qty,
                            "open_price": open_map.get(symbol),
                            "shares": shares.get(symbol, 0.0) - old_shares.get(symbol, 0.0),
                        }
                    )
                for symbol, qty in dict(result["sell_legs"]).items():
                    trade_rows.append(
                        {
                            "date": current_ts,
                            "symbol": symbol,
                            "side": "sell",
                            "weight": qty,
                            "open_price": open_map.get(symbol),
                            "shares": old_shares.get(symbol, 0.0) - shares.get(symbol, 0.0),
                        }
                    )
                turnover_rows.append(
                    {
                        "date": current_ts,
                        "buy_weight": result["buy_weight"],
                        "sell_weight": result["sell_weight"],
                        "cost": result["cost"],
                        "buy_cost_bps": buy_cost_bps(slippage_multiplier),
                        "sell_cost_bps": sell_cost_bps(slippage_multiplier),
                    }
                )
                daily_rows.append(
                    {
                        "date": current_ts,
                        "is_rebalance": True,
                        "overnight_nav": result["overnight_nav"],
                        "nav_after_cost": result["nav_after_cost"],
                        "close_nav": result["close_nav"],
                        "buy_weight": result["buy_weight"],
                        "sell_weight": result["sell_weight"],
                        "cost": result["cost"],
                        "started": True,
                    }
                )
        else:
            if not started:
                continue
            nav = apply_non_rebalance_day(
                shares=shares,
                close_prices=close_map,
                previous_close_prices=previous_close_prices,
                fallback_nav=nav,
            )
            holding_mark_prices = _resolve_mark_prices(
                set(shares),
                close_map,
                previous_close_prices,
                context="holding_close",
            )
            daily_rows.append(
                {
                    "date": current_ts,
                    "is_rebalance": False,
                    "overnight_nav": nav,
                    "nav_after_cost": nav,
                    "close_nav": nav,
                    "buy_weight": 0.0,
                    "sell_weight": 0.0,
                    "cost": 0.0,
                    "started": started,
                }
            )
        for symbol, qty in shares.items():
            if qty <= 0:
                continue
            holding_rows.append(
                {
                    "date": current_ts,
                    "symbol": symbol,
                    "shares": qty,
                    "open_price": open_map.get(symbol),
                    "close_price": close_map.get(symbol),
                    "mark_price": holding_mark_prices.get(symbol),
                    "weight": (
                        qty * float(holding_mark_prices[symbol]) / nav
                        if symbol in holding_mark_prices and nav > 0
                        else 0.0
                    ),
                }
            )
        previous_close_prices.update(holding_mark_prices)
        _ = i
    return {
        "portfolio_daily": pd.DataFrame(daily_rows),
        "holdings": pd.DataFrame(holding_rows),
        "trades": pd.DataFrame(trade_rows),
        "turnover_and_costs": pd.DataFrame(turnover_rows),
        "forced_carry_events": pd.DataFrame(event_rows),
    }


def account_metrics(daily: pd.DataFrame) -> dict[str, float]:
    if daily.empty:
        return {
            "net_return": 0.0,
            "sharpe": 0.0,
            "max_drawdown": 0.0,
            "day_count": 0.0,
        }
    nav = pd.to_numeric(daily["close_nav"], errors="coerce")
    full_nav = pd.concat(
        [pd.Series([INITIAL_NAV], dtype=float), nav.reset_index(drop=True)],
        ignore_index=True,
    )
    rets = full_nav.pct_change().replace([np.inf, -np.inf], np.nan).dropna()
    net = float(nav.iloc[-1] / INITIAL_NAV - 1.0) if nav.iloc[0] else 0.0
    sharpe = 0.0
    if len(rets) > 1 and float(rets.std()) > 0:
        sharpe = float(np.sqrt(252.0) * rets.mean() / rets.std())
    peak = full_nav.cummax()
    dd = (full_nav / peak - 1.0).min()
    return {
        "net_return": net,
        "sharpe": sharpe,
        "max_drawdown": float(dd) if np.isfinite(dd) else 0.0,
        "day_count": float(len(daily)),
    }


__all__ = [
    "CADENCE_INTERVALS",
    "ExecutionEligibility",
    "INITIAL_NAV",
    "PORTFOLIO_SIZES",
    "SLIPPAGE_MULTIPLIERS",
    "account_metrics",
    "allocate_shares",
    "apply_non_rebalance_day",
    "apply_rebalance_day",
    "book_identity",
    "book_path_digest",
    "buy_cost_bps",
    "eligibility_from_row",
    "map_risk_warning_for_rules",
    "rank_candidates",
    "run_account",
    "select_target_symbols",
    "sell_cost_bps",
    "turnover_from_weights",
]
