#!/usr/bin/env python3
# pyright: reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportGeneralTypeIssues=false, reportOptionalMemberAccess=false
# pyright: reportMissingImports=false, reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false, reportUnknownArgumentType=false
# pyright: reportMissingTypeStubs=false, reportReturnType=false
# pyright: reportUnusedCallResult=false, reportAny=false
# pyright: reportUnknownParameterType=false, reportMissingTypeArgument=false
# pyright: reportIndexIssue=false, reportUnusedParameter=false
# pyright: reportCallIssue=false, reportOperatorIssue=false
"""Build bounded REAKA P7 portfolio-mapping inputs from read-only K1 checkpoints."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Mapping
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from scipy.stats import rankdata

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from factor_lab.factor_rotation.reaka_intraday_k1_preflight_v1 import (  # noqa: E402
    CLOCK_SUFFIX,
    IntradayK1InputStore,
    read_json,
)
from factor_lab.factor_rotation.reaka_intraday_k1_training_v1 import (  # noqa: E402
    SEEDS_FORMAL,
    build_model,
    load_state_tree,
    score_rows,
)
from factor_lab.factor_rotation.reaka_intraday_portfolio_mapping_v1 import (  # noqa: E402
    ADMISSION_SCHEMA_ID,
    CLOCKS,
    CONTRACT_DIGEST,
    INPUT_SCHEMA_ID,
    assert_no_future_filter,
    file_digest,
    load_contract,
    source_closure_for_module,
    validate_admission,
    validate_market_panel,
    validate_score_panel,
    write_json,
)

FIXED_K1_CONFIG = {
    "candidate_id": "d8_h8_lr0p03_max3_fit_prefix_K1_r0",
    "capacity_id": "d8_h8",
    "latent_dimension": 8,
    "hidden_dimension": 8,
    "learning_rate": 0.03,
    "max_cycles": 3,
    "operator_count": 1,
    "residual_identity": "r0_exact_zero",
}
BOUNDED_XDXR_SYMBOLS = frozenset(
    {"000004", "002808", "002898", "300029", "600193", "600421", "600599", "600608", "600636", "600696"}
)


def _size_bucket_map(
    score_frame: pd.DataFrame,
    *,
    market_cap_path: Path,
    clock: str,
) -> dict[tuple[pd.Timestamp, str], str]:
    decisions = score_frame.loc[:, ["decision_date", "symbol"]].drop_duplicates().copy()
    decisions["decision_date"] = pd.to_datetime(decisions["decision_date"], errors="raise").dt.normalize()
    decisions["decision_timestamp"] = decisions["decision_date"] + pd.to_timedelta(
        14 * 60 + (30 if clock == "14:30" else 45), unit="m"
    )
    cap = pd.read_parquet(
        market_cap_path,
        columns=["symbol", "available_at", "total_market_cap"],
    )
    cap["symbol"] = cap["symbol"].astype(str)
    cap["available_at"] = (
        pd.to_datetime(cap["available_at"], errors="raise", utc=True)
        .dt.tz_convert("Asia/Shanghai")
        .dt.tz_localize(None)
        .astype("datetime64[ns]")
    )
    decisions["decision_timestamp"] = decisions["decision_timestamp"].astype("datetime64[ns]")
    cap["total_market_cap"] = pd.to_numeric(cap["total_market_cap"], errors="coerce")
    resolved_parts: list[pd.DataFrame] = []
    for symbol, left in decisions.groupby("symbol", sort=True):
        right = cap.loc[cap["symbol"].eq(str(symbol)), ["available_at", "total_market_cap"]].sort_values(
            "available_at", kind="mergesort"
        )
        local = left.sort_values("decision_timestamp", kind="mergesort")
        if right.empty:
            local["total_market_cap"] = np.nan
        else:
            local = pd.merge_asof(
                local,
                right,
                left_on="decision_timestamp",
                right_on="available_at",
                direction="backward",
                allow_exact_matches=True,
            )
        resolved_parts.append(local)
    resolved = pd.concat(resolved_parts, ignore_index=True) if resolved_parts else decisions.assign(total_market_cap=np.nan)
    output: dict[tuple[pd.Timestamp, str], str] = {}
    for day, local in resolved.groupby("decision_date", sort=True):
        finite = local.loc[np.isfinite(pd.to_numeric(local["total_market_cap"], errors="coerce"))].copy()
        if finite.empty:
            continue
        percentile = finite["total_market_cap"].rank(method="first", pct=True)
        labels = np.where(percentile <= 1.0 / 3.0, "small", np.where(percentile <= 2.0 / 3.0, "middle", "large"))
        for symbol, label in zip(finite["symbol"].astype(str), labels, strict=True):
            output[(pd.Timestamp(day), symbol)] = str(label)
    return output


def _materialize_raw_market_panel(
    score_frame: pd.DataFrame,
    *,
    clock: str,
    target_fill_root: Path,
    daily_panel_paths: list[Path],
    market_cap_path: Path,
) -> pd.DataFrame:
    suffix = CLOCK_SUFFIX[clock]
    calendar = np.load(target_fill_root / "calendar.npy", allow_pickle=False).astype("datetime64[ns]")
    symbols = np.load(target_fill_root / "symbols.npy", allow_pickle=False).astype(str)
    entry = np.load(target_fill_root / f"entry_open_{suffix}.npy", allow_pickle=False)
    if entry.shape != (len(calendar), len(symbols)):
        raise ValueError("portfolio_mapping_target_fill_shape_invalid")
    score_symbols = set(score_frame["symbol"].astype(str))
    score_dates = pd.DatetimeIndex(pd.to_datetime(score_frame["decision_date"], errors="raise").unique())
    if score_dates.empty:
        raise ValueError("portfolio_mapping_score_dates_empty")
    daily_parts = [
        pd.read_parquet(
            path,
            columns=[
                "trading_day",
                "symbol",
                "close",
                "previous_tradable_close",
                "paused",
                "limit_up",
                "limit_down",
                "rule_status",
            ],
        )
        for path in daily_panel_paths
    ]
    daily = pd.concat(daily_parts, ignore_index=True)
    daily["date"] = pd.to_datetime(daily["trading_day"], errors="raise").dt.normalize()
    daily["symbol"] = daily["symbol"].astype(str)
    daily = daily.loc[
        daily["symbol"].isin(score_symbols)
        & daily["date"].between(score_dates.min(), score_dates.max(), inclusive="both")
    ].copy()
    daily = daily.sort_values(["date", "symbol"], kind="mergesort").drop_duplicates(
        ["date", "symbol"], keep="last"
    )
    day_index = {pd.Timestamp(value): position for position, value in enumerate(pd.to_datetime(calendar))}
    symbol_index = {symbol: position for position, symbol in enumerate(symbols)}
    rows_day = daily["date"].map(day_index)
    rows_symbol = daily["symbol"].map(symbol_index)
    valid_axis = rows_day.notna() & rows_symbol.notna()
    daily = daily.loc[valid_axis].copy()
    di = rows_day.loc[valid_axis].to_numpy(np.int64)
    si = rows_symbol.loc[valid_axis].to_numpy(np.int64)
    daily["raw_execution_price"] = np.asarray(entry[di, si], dtype=np.float64)
    daily["raw_close_price"] = pd.to_numeric(daily["close"], errors="coerce")
    raw_execution = pd.to_numeric(daily["raw_execution_price"], errors="coerce")
    limit_up = pd.to_numeric(daily["limit_up"], errors="coerce")
    limit_down = pd.to_numeric(daily["limit_down"], errors="coerce")
    executable = raw_execution.gt(0.0) & np.isfinite(raw_execution) & ~daily["paused"].astype(bool)
    rule_resolved = daily["rule_status"].astype(str).eq("resolved")
    daily["buy_ok"] = executable & rule_resolved & (~np.isfinite(limit_up) | raw_execution.lt(limit_up - 1.0e-12))
    daily["sell_ok"] = executable & rule_resolved & (~np.isfinite(limit_down) | raw_execution.gt(limit_down + 1.0e-12))
    size_map = _size_bucket_map(score_frame, market_cap_path=market_cap_path, clock=clock)
    daily["size_bucket"] = [
        size_map.get((pd.Timestamp(day), str(symbol)), "")
        for day, symbol in zip(daily["date"], daily["symbol"], strict=True)
    ]
    daily["decision_clock"] = clock
    return daily.loc[
        :,
        [
            "date",
            "decision_clock",
            "symbol",
            "raw_execution_price",
            "raw_close_price",
            "previous_tradable_close",
            "buy_ok",
            "sell_ok",
            "size_bucket",
        ],
    ].reset_index(drop=True)


def _rankz_by_decision(
    scores: np.ndarray,
    decision_keys: np.ndarray,
) -> np.ndarray:
    output = np.zeros_like(scores, dtype=np.float64)
    for key in np.unique(decision_keys):
        local = decision_keys == key
        ranks = rankdata(scores[local], method="average")
        centered = ranks - ranks.mean()
        scale = centered.std(ddof=0)
        output[local] = centered / max(scale, 1.0e-12)
    return output


def _ensemble_seed_scores(
    *,
    store: IntradayK1InputStore,
    normalizer: Mapping[str, object],
    checkpoint_root: Path,
    indices: np.ndarray,
) -> tuple[np.ndarray, pd.DataFrame]:
    device = torch.device("cpu")
    rows = np.asarray(store.inference_rows[indices], dtype=np.int64)
    symbols = store.symbols[rows[:, 1]].astype(str)
    decision_days = rows[:, 0]
    decision_keys = decision_days
    rank_parts: list[np.ndarray] = []
    for seed in SEEDS_FORMAL:
        model = build_model(FIXED_K1_CONFIG, seed=seed).to(device)
        load_state_tree(model, checkpoint_root / f"checkpoints/seed_{seed}")
        scores, _, _, _ = score_rows(
            model,
            store=store,
            normalizer=normalizer,
            indices=indices,
            device=device,
        )
        rank_parts.append(_rankz_by_decision(scores, decision_keys))
    ensemble = np.mean(np.vstack(rank_parts), axis=0)
    frame = pd.DataFrame(
        {
            "symbol": symbols,
            "decision_position": decision_days,
            "decision_date": pd.to_datetime(store.calendar[decision_days]).normalize(),
            "score": ensemble,
        }
    )
    return ensemble, frame


def _attach_hfq_accounting(
    raw_market: pd.DataFrame,
    *,
    adjustment_factors_path: Path,
    xdxr_events_path: Path,
) -> pd.DataFrame:
    required = {
        "date",
        "decision_clock",
        "symbol",
        "raw_execution_price",
        "raw_close_price",
        "previous_tradable_close",
        "buy_ok",
        "sell_ok",
        "size_bucket",
    }
    missing = required - set(raw_market.columns)
    if missing:
        raise ValueError("portfolio_mapping_raw_market_columns_missing:" + ",".join(sorted(missing)))
    market = raw_market.copy()
    market["date"] = pd.to_datetime(market["date"], errors="raise").dt.normalize()
    market["symbol"] = market["symbol"].astype(str)
    factors = pd.read_parquet(
        adjustment_factors_path,
        columns=["symbol", "trading_day", "instrument_type", "factor_type", "price_multiplier"],
        filters=[("instrument_type", "=", "stock"), ("factor_type", "=", "hfq")],
    )
    factors["date"] = pd.to_datetime(factors["trading_day"], errors="raise").dt.normalize()
    factors["symbol"] = factors["symbol"].astype(str)
    factors = factors.loc[:, ["date", "symbol", "price_multiplier"]]
    if factors.duplicated(["date", "symbol"]).any():
        raise ValueError("portfolio_mapping_hfq_factor_duplicate")
    market = market.merge(factors, on=["date", "symbol"], how="left", validate="many_to_one")
    market = market.rename(columns={"price_multiplier": "hfq_price_multiplier"})
    market["hfq_factor_source"] = np.where(
        market["hfq_price_multiplier"].notna(),
        "certified_adjust_factors_v9",
        "",
    )
    missing_mask = market["hfq_price_multiplier"].isna()
    if missing_mask.any():
        asof_missing_symbols: set[str] = set(market.loc[missing_mask, "symbol"].astype(str))
        factor_groups = {
            str(symbol): local.sort_values("date", kind="mergesort")
            for symbol, local in factors.loc[factors["symbol"].isin(asof_missing_symbols)].groupby(
                "symbol", sort=True
            )
        }
        for symbol, missing_rows in market.loc[missing_mask].groupby("symbol", sort=True):
            history = factor_groups.get(str(symbol))
            if history is None or history.empty:
                continue
            history_dates = history["date"].to_numpy(dtype="datetime64[ns]")
            history_values = history["price_multiplier"].to_numpy(np.float64)
            query_dates = missing_rows["date"].to_numpy(dtype="datetime64[ns]")
            positions = np.searchsorted(history_dates, query_dates, side="right") - 1
            valid = positions >= 0
            if valid.any():
                market.loc[missing_rows.index[valid], "hfq_price_multiplier"] = history_values[
                    positions[valid]
                ]
                market.loc[missing_rows.index[valid], "hfq_factor_source"] = (
                    "certified_adjust_factors_v9"
                )
    missing_mask = market["hfq_price_multiplier"].isna()
    if missing_mask.any():
        repair_symbols: set[str] = set(market.loc[missing_mask, "symbol"].astype(str))
        unknown = sorted(repair_symbols - BOUNDED_XDXR_SYMBOLS)
        if unknown:
            raise ValueError("portfolio_mapping_unregistered_HFQ_symbol_gap:" + ",".join(unknown))
        primary_symbols = set(factors["symbol"].astype(str))
        partial = sorted(repair_symbols.intersection(primary_symbols))
        if partial:
            raise ValueError("portfolio_mapping_partial_primary_HFQ_gap:" + ",".join(partial))
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
            filters=[("code", "in", sorted(repair_symbols)), ("category", "=", 1)],
        )
        events["date"] = pd.to_datetime(events["date"], errors="raise").dt.normalize()
        events["code"] = events["code"].astype(str)
        events = events.loc[
            events["date"].between(market["date"].min(), market["date"].max(), inclusive="both")
        ].copy()
        if events.duplicated(["date", "code"]).any():
            raise ValueError("portfolio_mapping_duplicate_XDXR_category1_event")
        if (pd.to_numeric(events["peigu"], errors="raise") != 0.0).any():
            raise ValueError("portfolio_mapping_XDXR_peigu_not_preregistered")
        if (pd.to_numeric(events["suogu"], errors="raise") != 0.0).any():
            raise ValueError("portfolio_mapping_XDXR_suogu_not_preregistered")
        bounded_event_count = 0
        for symbol in sorted(repair_symbols):
            local = market.loc[market["symbol"].eq(symbol)].sort_values(
                "date", kind="mergesort"
            )
            local_dates = local["date"].to_numpy(dtype="datetime64[ns]")
            local_factor = np.ones(len(local), dtype=np.float64)
            local_events = events.loc[
                events["code"].eq(symbol)
                & events["date"].between(local["date"].min(), local["date"].max(), inclusive="both")
            ].sort_values("date", kind="mergesort")
            bounded_event_count += len(local_events)
            for event in local_events.itertuples(index=False):
                event_date = pd.Timestamp(event.date)
                event_rows = local.loc[local["date"].eq(event_date)]
                if len(event_rows) != 1:
                    raise ValueError(f"portfolio_mapping_XDXR_event_market_row_missing:{symbol}:{event_date.date()}")
                previous_close = float(event_rows.iloc[0]["previous_tradable_close"])
                if not np.isfinite(previous_close) or previous_close <= 0.0:
                    raise ValueError(f"portfolio_mapping_XDXR_previous_close_invalid:{symbol}:{event_date.date()}")
                numerator = previous_close * (10.0 + float(event.songzhuangu) + float(event.peigu))
                denominator = (
                    10.0 * previous_close
                    - float(event.fenhong)
                    + float(event.peigu) * float(event.peigujia)
                )
                if denominator <= 0.0:
                    raise ValueError(f"portfolio_mapping_XDXR_theoretical_price_invalid:{symbol}:{event_date.date()}")
                step = numerator / denominator
                if not np.isfinite(step) or step <= 0.0:
                    raise ValueError(f"portfolio_mapping_XDXR_step_invalid:{symbol}:{event_date.date()}")
                local_factor[local_dates >= event_date.to_datetime64()] *= step
            market.loc[local.index, "hfq_price_multiplier"] = local_factor
            market.loc[local.index, "hfq_factor_source"] = "bounded_xdxr_event_formula_v1"
        if repair_symbols == set(BOUNDED_XDXR_SYMBOLS) and bounded_event_count != 22:
            raise ValueError(
                f"portfolio_mapping_bounded_XDXR_event_count_invalid:{bounded_event_count}"
            )
    if market["hfq_price_multiplier"].isna().any():
        raise ValueError("portfolio_mapping_HFQ_factor_coverage_gap_after_bounded_repair")
    market["accounting_execution_price"] = (
        pd.to_numeric(market["raw_execution_price"], errors="coerce")
        * pd.to_numeric(market["hfq_price_multiplier"], errors="raise")
    )
    market["accounting_close_price"] = (
        pd.to_numeric(market["raw_close_price"], errors="coerce")
        * pd.to_numeric(market["hfq_price_multiplier"], errors="raise")
    )
    return market


def build_bounded_inputs(
    *,
    admission: Mapping[str, object],
    tree: str,
    clock: str,
    store_root: Path,
    checkpoint_root: Path,
    normalizer_path: Path,
    market_panel: Path | None,
    adjustment_factors_path: Path,
    xdxr_events_path: Path,
    output_root: Path,
    maximum_year: int = 2020,
    target_fill_root: Path | None = None,
    daily_panel_paths: list[Path] | None = None,
    market_cap_path: Path | None = None,
) -> dict[str, object]:
    blockers = validate_admission(admission, required_phase="score_extension")
    if admission.get("source_digests") != source_closure_for_module():
        blockers.append("score_extension_admission_source_closure_drift")
    if blockers:
        raise ValueError("portfolio_mapping_admission_invalid:" + ",".join(blockers))
    if admission.get("score_extension_execution_allowed") is not True:
        raise ValueError("portfolio_mapping_score_extension_closed")
    load_contract(ROOT)
    store = IntradayK1InputStore.load(store_root)
    normalizer = read_json(normalizer_path)
    years = np.asarray(store.inference_rows[:, 2], dtype=np.int64)
    indices = np.flatnonzero(years <= maximum_year).astype(np.int64)
    if np.any(years[indices] > 2020):
        raise ValueError("portfolio_mapping_post_2020_rows_forbidden")
    _, score_frame = _ensemble_seed_scores(
        store=store,
        normalizer=normalizer,
        checkpoint_root=checkpoint_root,
        indices=indices,
    )
    score_frame["decision_clock"] = clock
    score_frame = score_frame.sort_values(
        ["decision_date", "symbol"], kind="mergesort"
    ).reset_index(drop=True)
    validate_score_panel(score_frame)
    if market_panel is not None:
        raw_market = pd.read_parquet(market_panel)
    else:
        if target_fill_root is None or not daily_panel_paths or market_cap_path is None:
            raise ValueError("portfolio_mapping_raw_market_source_incomplete")
        raw_market = _materialize_raw_market_panel(
            score_frame,
            clock=clock,
            target_fill_root=target_fill_root,
            daily_panel_paths=daily_panel_paths,
            market_cap_path=market_cap_path,
        )
    market = _attach_hfq_accounting(
        raw_market,
        adjustment_factors_path=adjustment_factors_path,
        xdxr_events_path=xdxr_events_path,
    )
    market = market.loc[
        market["decision_clock"].astype(str).eq(clock)
        & pd.to_datetime(market["date"], errors="raise").dt.year.le(maximum_year)
    ].sort_values(["date", "symbol"], kind="mergesort").reset_index(drop=True)
    validate_market_panel(market)
    assert_no_future_filter(score_frame.columns)
    output_root.mkdir(parents=True, exist_ok=True)
    panel_path = output_root / f"bounded_score_panel_{CLOCK_SUFFIX[clock]}.parquet"
    score_frame.to_parquet(panel_path, index=False)
    market_path = output_root / f"daily_market_panel_{CLOCK_SUFFIX[clock]}.parquet"
    market.to_parquet(market_path, index=False)
    raw_market_source_digests: dict[str, object]
    if market_panel is not None:
        raw_market_source_digests = {"prebuilt_raw_market_panel": file_digest(market_panel)}
    else:
        assert target_fill_root is not None and daily_panel_paths and market_cap_path is not None
        raw_market_source_digests = {
            "target_fill_manifest": file_digest(target_fill_root / "manifest.json"),
            "daily_panels": {path.name + f"#{position}": file_digest(path) for position, path in enumerate(daily_panel_paths)},
            "market_cap": file_digest(market_cap_path),
        }
    manifest = write_json(
        output_root / f"input_manifest_{CLOCK_SUFFIX[clock]}.json",
        {
            "schema_id": INPUT_SCHEMA_ID,
            "contract_digest": CONTRACT_DIGEST,
            "tree_neutral": True,
            "decision_clocks": list(CLOCKS),
            "decision_clock": clock,
            "store_manifest_digest": file_digest(store_root / "manifest.json"),
            "checkpoint_manifest_digests": {
                str(seed): file_digest(checkpoint_root / f"checkpoints/seed_{seed}/manifest.json")
                for seed in SEEDS_FORMAL
            },
            "normalizer_digest": file_digest(normalizer_path),
            "panel_digest": file_digest(panel_path),
            "market_panel_digest": file_digest(market_path),
            "adjustment_factor_file_digest": file_digest(adjustment_factors_path),
            "xdxr_event_file_digest": file_digest(xdxr_events_path),
            "hfq_factor_source_counts": {
                str(key): int(value)
                for key, value in market["hfq_factor_source"].value_counts(dropna=False).sort_index().items()
            },
            "raw_market_source_digests": raw_market_source_digests,
            "row_count": int(len(score_frame)),
            "inference_row_count": int(len(indices)),
            "maximum_year": maximum_year,
            "post_2020_rows": 0,
            "future_entry_or_target_filter_applied": False,
            "seed_ensemble": "mean_of_per_decision_cross_sectional_average_tie_rankz_over_11_29_47",
            "execution_backend": "cpu",
            "parent_checkpoints_read_only": True,
            "source_digests": source_closure_for_module(),
            "account_mapping_execution_allowed": False,
            "production_authority": False,
        },
    )
    closure = write_json(
        output_root / f"source_closure_{CLOCK_SUFFIX[clock]}.json",
        {
            "schema_id": "factorlab.reaka_intraday_portfolio_mapping_source_closure@1.0",
            "contract_digest": CONTRACT_DIGEST,
            "tree_neutral": True,
            "decision_clock": clock,
            "source_digests": source_closure_for_module(),
            "input_manifest_digest": manifest["canonical_digest"],
            "account_mapping_execution_allowed": False,
        },
    )
    return {
        "manifest": manifest,
        "source_closure": closure,
        "panel_path": str(panel_path),
        "market_panel_path": str(market_path),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--admission", required=True, type=Path)
    parser.add_argument("--tree", choices=("formal", "isolated"), required=True)
    parser.add_argument("--clock", choices=CLOCKS, required=True)
    parser.add_argument("--store-root", required=True, type=Path)
    parser.add_argument("--checkpoint-root", required=True, type=Path)
    parser.add_argument("--normalizer", required=True, type=Path)
    parser.add_argument("--market-panel", type=Path, default=None)
    parser.add_argument("--target-fill-root", type=Path, default=None)
    parser.add_argument("--daily-panel", action="append", type=Path, default=[])
    parser.add_argument("--market-cap", type=Path, default=None)
    parser.add_argument("--adjustment-factors", required=True, type=Path)
    parser.add_argument("--xdxr-events", required=True, type=Path)
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--maximum-year", type=int, default=2020)
    args = parser.parse_args()
    admission = read_json(args.admission if args.admission.is_absolute() else ROOT / args.admission)
    if admission.get("schema_id") != ADMISSION_SCHEMA_ID:
        raise SystemExit("admission_schema_invalid")
    load_contract(ROOT)
    blockers = validate_admission(admission, required_phase="score_extension")
    if blockers:
        raise SystemExit("score_extension_admission_invalid:" + ",".join(blockers))
    result = build_bounded_inputs(
        admission=admission,
        tree=args.tree,
        clock=args.clock,
        store_root=args.store_root,
        checkpoint_root=args.checkpoint_root,
        normalizer_path=args.normalizer,
        market_panel=args.market_panel,
        adjustment_factors_path=args.adjustment_factors,
        xdxr_events_path=args.xdxr_events,
        output_root=args.output_root,
        maximum_year=args.maximum_year,
        target_fill_root=args.target_fill_root,
        daily_panel_paths=list(args.daily_panel),
        market_cap_path=args.market_cap,
    )
    print(json.dumps({"status": "completed", "manifest_digest": result["manifest"]["canonical_digest"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
