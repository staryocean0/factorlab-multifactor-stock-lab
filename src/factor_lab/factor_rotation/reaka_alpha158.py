# pyright: reportAny=false, reportArgumentType=false, reportAttributeAccessIssue=false
# pyright: reportCallIssue=false, reportGeneralTypeIssues=false
# pyright: reportMissingTypeStubs=false, reportUnknownLambdaType=false
# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
"""Formula-faithful, in-memory Qlib Alpha158 materialization for REAKA.

The formula catalogue is pinned to Microsoft Qlib's formal ``v0.9.7`` release.
It is a local rewrite of the MIT-licensed loader and operator semantics, not a
runtime dependency on Qlib.  This module intentionally does not read DataHub,
write a historical feature surface, build model windows, or make a PIT claim.

Source lineage (Copyright (c) Microsoft Corporation, MIT License):

* ``qlib/contrib/data/loader.py`` defines the ordered Alpha158 expressions.
* ``qlib/data/ops.py`` defines the pandas rolling/operator semantics.
* ``qlib/data/_libs/rolling.pyx`` defines slope, R-square, and residuals.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Final

import numpy as np
import pandas as pd
from numpy.typing import NDArray

QLIB_ALPHA158_RELEASE: Final = "v0.9.7"
QLIB_ALPHA158_COMMIT: Final = "da920b7f954f48ab1bb64117c976710de198373e"
QLIB_ALPHA158_LOADER_URL: Final = f"https://github.com/microsoft/qlib/blob/{QLIB_ALPHA158_COMMIT}/qlib/contrib/data/loader.py"
QLIB_ALPHA158_LOADER_SHA256: Final = "814b7f7ab3d418ae3c87ce352220080b239eba2670eac9e38376b794be4075cb"
QLIB_ALPHA158_OPS_SHA256: Final = "6f648355725a85a9f17528d864281fc065f8a4f887261a9909f7495d5db42760"
QLIB_ALPHA158_ROLLING_SHA256: Final = "58b2e418a78558135cb1ecad88bfcff68cae98b2bb2695d8d2fade8b30c5dbf1"

ALPHA158_WINDOWS: Final = (5, 10, 20, 30, 60)
ALPHA158_MAX_LOOKBACK_BARS: Final = 60
# The certified DataHub product can differ from the adjusted OHLC envelope by
# sub-micro relative rounding on one-price/limit days.  Keep the domain guard,
# but do not reject a certified row over floating-point serialization noise.
ALPHA158_PRICE_ENVELOPE_RELATIVE_TOLERANCE: Final = 1e-6
ALPHA158_REQUIRED_COLUMNS: Final = (
    "symbol",
    "trading_day",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "vwap",
)
_EPSILON: Final = 1e-12


@dataclass(frozen=True, slots=True)
class Alpha158Formula:
    """One ordered member of the pinned official Alpha158 formula catalogue."""

    member_id: str
    family: str
    expression: str
    window: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "member_id": self.member_id,
            "family": self.family,
            "expression": self.expression,
            "window": self.window,
        }


@dataclass(frozen=True, slots=True)
class Alpha158Materialization:
    """A small, canonical in-memory feature matrix plus explicit observation mask."""

    coordinates: pd.DataFrame
    values: NDArray[np.float64]
    observed: NDArray[np.bool_]
    member_ids: tuple[str, ...]
    member_digest: str
    formula_digest: str

    def feature_frame(self) -> pd.DataFrame:
        features = pd.DataFrame(self.values, columns=self.member_ids)
        return pd.concat((self.coordinates.reset_index(drop=True), features), axis=1)

    def mask_frame(self) -> pd.DataFrame:
        masks = pd.DataFrame(self.observed, columns=self.member_ids)
        return pd.concat((self.coordinates.reset_index(drop=True), masks), axis=1)

    def receipt(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_id": "reaka_alpha158_in_memory_materialization@1.0",
            "source_release": QLIB_ALPHA158_RELEASE,
            "source_commit": QLIB_ALPHA158_COMMIT,
            "source_loader_sha256": QLIB_ALPHA158_LOADER_SHA256,
            "member_digest": self.member_digest,
            "formula_digest": self.formula_digest,
            "row_count": len(self.coordinates),
            "feature_count": len(self.member_ids),
            "observed_cell_count": int(self.observed.sum()),
            "coordinate_digest": _canonical_digest(
                [
                    {
                        "symbol": str(row.symbol),
                        "trading_day": pd.Timestamp(row.trading_day).date().isoformat(),
                    }
                    for row in self.coordinates.itertuples(index=False)
                ]
            ),
            "value_matrix_digest": _array_digest(self.values, dtype="<f8"),
            "observed_mask_digest": _array_digest(self.observed, dtype="|b1"),
            "missing_policy": "nan_preserved_with_explicit_observed_mask",
            "maximum_lookback_bars": ALPHA158_MAX_LOOKBACK_BARS,
            "ohlcv_vwap_price_space_consistency_validated": True,
            "datahub_surface_materialized": False,
            "strict_pit_claimed": False,
        }
        payload["canonical_digest"] = _canonical_digest(payload)
        return payload


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"


def _array_digest(values: NDArray[np.generic], *, dtype: str) -> str:
    canonical = np.ascontiguousarray(values, dtype=np.dtype(dtype))
    metadata = json.dumps(
        {"dtype": canonical.dtype.str, "shape": list(canonical.shape)},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    digest = hashlib.sha256(metadata)
    digest.update(b"\0")
    digest.update(canonical.tobytes(order="C"))
    return f"sha256:{digest.hexdigest()}"


_KBAR_FORMULAS: Final = (
    ("KMID", "($close-$open)/$open"),
    ("KLEN", "($high-$low)/$open"),
    ("KMID2", "($close-$open)/($high-$low+1e-12)"),
    ("KUP", "($high-Greater($open, $close))/$open"),
    ("KUP2", "($high-Greater($open, $close))/($high-$low+1e-12)"),
    ("KLOW", "(Less($open, $close)-$low)/$open"),
    ("KLOW2", "(Less($open, $close)-$low)/($high-$low+1e-12)"),
    ("KSFT", "(2*$close-$high-$low)/$open"),
    ("KSFT2", "(2*$close-$high-$low)/($high-$low+1e-12)"),
)

_PRICE_FORMULAS: Final = (
    ("OPEN0", "$open/$close"),
    ("HIGH0", "$high/$close"),
    ("LOW0", "$low/$close"),
    ("VWAP0", "$vwap/$close"),
)

_ROLLING_FAMILIES: Final = (
    "ROC",
    "MA",
    "STD",
    "BETA",
    "RSQR",
    "RESI",
    "MAX",
    "MIN",
    "QTLU",
    "QTLD",
    "RANK",
    "RSV",
    "IMAX",
    "IMIN",
    "IMXD",
    "CORR",
    "CORD",
    "CNTP",
    "CNTN",
    "CNTD",
    "SUMP",
    "SUMN",
    "SUMD",
    "VMA",
    "VSTD",
    "WVMA",
    "VSUMP",
    "VSUMN",
    "VSUMD",
)


def _rolling_expression(family: str, window: int) -> str:
    expressions = {
        "ROC": f"Ref($close, {window})/$close",
        "MA": f"Mean($close, {window})/$close",
        "STD": f"Std($close, {window})/$close",
        "BETA": f"Slope($close, {window})/$close",
        "RSQR": f"Rsquare($close, {window})",
        "RESI": f"Resi($close, {window})/$close",
        "MAX": f"Max($high, {window})/$close",
        "MIN": f"Min($low, {window})/$close",
        "QTLU": f"Quantile($close, {window}, 0.8)/$close",
        "QTLD": f"Quantile($close, {window}, 0.2)/$close",
        "RANK": f"Rank($close, {window})",
        "RSV": (f"($close-Min($low, {window}))/(Max($high, {window})-Min($low, {window})+1e-12)"),
        "IMAX": f"IdxMax($high, {window})/{window}",
        "IMIN": f"IdxMin($low, {window})/{window}",
        "IMXD": f"(IdxMax($high, {window})-IdxMin($low, {window}))/{window}",
        "CORR": f"Corr($close, Log($volume+1), {window})",
        "CORD": f"Corr($close/Ref($close,1), Log($volume/Ref($volume, 1)+1), {window})",
        "CNTP": f"Mean($close>Ref($close, 1), {window})",
        "CNTN": f"Mean($close<Ref($close, 1), {window})",
        "CNTD": (f"Mean($close>Ref($close, 1), {window})-Mean($close<Ref($close, 1), {window})"),
        "SUMP": (f"Sum(Greater($close-Ref($close, 1), 0), {window})/(Sum(Abs($close-Ref($close, 1)), {window})+1e-12)"),
        "SUMN": (f"Sum(Greater(Ref($close, 1)-$close, 0), {window})/(Sum(Abs($close-Ref($close, 1)), {window})+1e-12)"),
        "SUMD": (
            f"(Sum(Greater($close-Ref($close, 1), 0), {window})-"
            f"Sum(Greater(Ref($close, 1)-$close, 0), {window}))/"
            f"(Sum(Abs($close-Ref($close, 1)), {window})+1e-12)"
        ),
        "VMA": f"Mean($volume, {window})/($volume+1e-12)",
        "VSTD": f"Std($volume, {window})/($volume+1e-12)",
        "WVMA": (f"Std(Abs($close/Ref($close, 1)-1)*$volume, {window})/(Mean(Abs($close/Ref($close, 1)-1)*$volume, {window})+1e-12)"),
        "VSUMP": (f"Sum(Greater($volume-Ref($volume, 1), 0), {window})/(Sum(Abs($volume-Ref($volume, 1)), {window})+1e-12)"),
        "VSUMN": (f"Sum(Greater(Ref($volume, 1)-$volume, 0), {window})/(Sum(Abs($volume-Ref($volume, 1)), {window})+1e-12)"),
        "VSUMD": (
            f"(Sum(Greater($volume-Ref($volume, 1), 0), {window})-"
            f"Sum(Greater(Ref($volume, 1)-$volume, 0), {window}))/"
            f"(Sum(Abs($volume-Ref($volume, 1)), {window})+1e-12)"
        ),
    }
    return expressions[family]


def _build_formula_catalogue() -> tuple[Alpha158Formula, ...]:
    formulas = [
        Alpha158Formula(
            member_id=member_id,
            family="kbar",
            expression=expression,
        )
        for member_id, expression in _KBAR_FORMULAS
    ]
    formulas.extend(
        Alpha158Formula(
            member_id=member_id,
            family="relative_price",
            expression=expression,
            window=0,
        )
        for member_id, expression in _PRICE_FORMULAS
    )
    for family in _ROLLING_FAMILIES:
        formulas.extend(
            Alpha158Formula(
                member_id=f"{family}{window}",
                family=family,
                expression=_rolling_expression(family, window),
                window=window,
            )
            for window in ALPHA158_WINDOWS
        )
    return tuple(formulas)


ALPHA158_FORMULAS: Final = _build_formula_catalogue()
ALPHA158_MEMBER_IDS: Final = tuple(formula.member_id for formula in ALPHA158_FORMULAS)
ALPHA158_MEMBER_DIGEST: Final = _canonical_digest(ALPHA158_MEMBER_IDS)
ALPHA158_FORMULA_DIGEST: Final = _canonical_digest(
    [
        {
            "member_id": formula.member_id,
            "expression": formula.expression,
        }
        for formula in ALPHA158_FORMULAS
    ]
)

_EXPECTED_MEMBER_DIGEST: Final = "sha256:d5f52c2d75ea900ab29f4742eeb59d9692254ba7307ad36a807012db7d680e13"
_EXPECTED_FORMULA_DIGEST: Final = "sha256:71d65b80562638fa3785e755347591ad648688c9014ed5a3fbf09c05167432e7"

if len(ALPHA158_FORMULAS) != 158:
    raise AssertionError("reaka_alpha158_formula_count_drift")
if ALPHA158_MEMBER_DIGEST != _EXPECTED_MEMBER_DIGEST:
    raise AssertionError("reaka_alpha158_member_order_drift")
if ALPHA158_FORMULA_DIGEST != _EXPECTED_FORMULA_DIGEST:
    raise AssertionError("reaka_alpha158_official_formula_drift")


def alpha158_formula_catalogue() -> tuple[Alpha158Formula, ...]:
    """Return the immutable ordered formula catalogue."""

    return ALPHA158_FORMULAS


def alpha158_formula_receipt() -> dict[str, object]:
    """Return source and digest evidence without claiming numeric/PIT certification."""

    payload: dict[str, object] = {
        "schema_id": "reaka_alpha158_formula_catalogue@1.0",
        "source_release": QLIB_ALPHA158_RELEASE,
        "source_commit": QLIB_ALPHA158_COMMIT,
        "source_loader_url": QLIB_ALPHA158_LOADER_URL,
        "source_loader_sha256": QLIB_ALPHA158_LOADER_SHA256,
        "source_ops_sha256": QLIB_ALPHA158_OPS_SHA256,
        "source_rolling_sha256": QLIB_ALPHA158_ROLLING_SHA256,
        "member_count": len(ALPHA158_MEMBER_IDS),
        "member_digest": ALPHA158_MEMBER_DIGEST,
        "formula_digest": ALPHA158_FORMULA_DIGEST,
        "runtime_dependency_on_qlib": False,
        "official_runtime_golden_verified": False,
        "strict_pit_claimed": False,
    }
    payload["canonical_digest"] = _canonical_digest(payload)
    return payload


def _prepare_frame(frame: pd.DataFrame, *, output_rows: bool) -> pd.DataFrame:
    missing = [column for column in ALPHA158_REQUIRED_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"reaka_alpha158_required_columns_missing:{','.join(missing)}")
    prepared = frame.loc[:, ALPHA158_REQUIRED_COLUMNS].copy()
    if prepared.empty and output_rows:
        raise ValueError("reaka_alpha158_current_rows_empty")
    if prepared["symbol"].isna().any():
        raise ValueError("reaka_alpha158_symbol_missing")
    prepared["symbol"] = prepared["symbol"].astype(str).str.strip()
    if bool(prepared["symbol"].eq("").any()):
        raise ValueError("reaka_alpha158_symbol_empty")
    trading_day = pd.to_datetime(prepared["trading_day"], errors="coerce")
    if trading_day.isna().any():
        raise ValueError("reaka_alpha158_trading_day_invalid")
    if isinstance(trading_day.dtype, pd.DatetimeTZDtype):
        trading_day = trading_day.dt.tz_localize(None)
    prepared["trading_day"] = trading_day.dt.normalize()
    for column in ALPHA158_REQUIRED_COLUMNS[2:]:
        original = prepared[column]
        numeric = pd.to_numeric(original, errors="coerce")
        if bool((original.notna() & numeric.isna()).any()):
            raise ValueError(f"reaka_alpha158_non_numeric:{column}")
        prepared[column] = numeric.astype(np.float64)
        if bool(np.isinf(prepared[column].to_numpy(dtype=np.float64)).any()):
            raise ValueError(f"reaka_alpha158_nonfinite_input:{column}")
    for column in ("open", "high", "low", "close", "vwap"):
        values = prepared[column]
        if bool((values.notna() & (values <= 0.0)).any()):
            raise ValueError(f"reaka_alpha158_nonpositive_price:{column}")
    if bool((prepared["volume"].notna() & (prepared["volume"] < 0.0)).any()):
        raise ValueError("reaka_alpha158_negative_volume")
    # A supplied VWAP on a zero-volume row is not an observation, regardless
    # of its numeric value.  Clear it before checking price-space consistency.
    prepared.loc[prepared["volume"].eq(0.0), "vwap"] = np.nan
    finite_ohlc = prepared[["open", "high", "low", "close"]].notna().all(axis=1)
    invalid_ohlc = finite_ohlc & (
        prepared["high"].lt(prepared[["open", "close"]].max(axis=1))
        | prepared["low"].gt(prepared[["open", "close"]].min(axis=1))
        | prepared["high"].lt(prepared["low"])
    )
    if bool(invalid_ohlc.any()):
        raise ValueError("reaka_alpha158_ohlc_value_domain_invalid")
    finite_vwap_range = prepared[["low", "high", "vwap"]].notna().all(axis=1)
    invalid_vwap = finite_vwap_range & (
        prepared["vwap"].lt(prepared["low"] * (1.0 - ALPHA158_PRICE_ENVELOPE_RELATIVE_TOLERANCE))
        | prepared["vwap"].gt(prepared["high"] * (1.0 + ALPHA158_PRICE_ENVELOPE_RELATIVE_TOLERANCE))
    )
    if bool(invalid_vwap.any()):
        raise ValueError("reaka_alpha158_vwap_price_space_mismatch")
    prepared["_alpha158_output_row"] = output_rows
    return prepared


def _canonical_input(
    rows: pd.DataFrame,
    *,
    history: pd.DataFrame | None,
) -> pd.DataFrame:
    current = _prepare_frame(rows, output_rows=True)
    if history is None or history.empty:
        combined = current
    else:
        context = _prepare_frame(history, output_rows=False)
        current_symbols = set(current["symbol"])
        context = context.loc[context["symbol"].isin(current_symbols)].copy()
        if not context.empty:
            first_current = current.groupby("symbol", sort=False)["trading_day"].min()
            joined = context.join(first_current.rename("_first_current"), on="symbol")
            if bool((joined["trading_day"] >= joined["_first_current"]).any()):
                raise ValueError("reaka_alpha158_history_must_precede_current_rows")
            context = (
                context.sort_values(["symbol", "trading_day"], kind="mergesort")
                .groupby("symbol", sort=False, group_keys=False)
                .tail(ALPHA158_MAX_LOOKBACK_BARS)
            )
        combined = pd.concat((context, current), ignore_index=True)
    if combined.duplicated(["symbol", "trading_day"]).any():
        raise ValueError("reaka_alpha158_duplicate_symbol_trading_day")
    return combined.sort_values(["symbol", "trading_day"], kind="mergesort").reset_index(drop=True)


def _rolling_linear(
    values: NDArray[np.float64],
    window: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64], NDArray[np.float64]]:
    """Port Qlib's rolling_slope/rolling_rsquare/rolling_resi semantics."""

    slopes = np.full(values.shape, np.nan, dtype=np.float64)
    r_squares = np.full(values.shape, np.nan, dtype=np.float64)
    residuals = np.full(values.shape, np.nan, dtype=np.float64)
    for stop in range(values.size):
        start = max(0, stop - window + 1)
        sample = values[start : stop + 1]
        valid = np.isfinite(sample)
        if int(valid.sum()) < 2:
            continue
        positions = np.arange(1, sample.size + 1, dtype=np.float64)[valid]
        responses = sample[valid]
        centered_positions = positions - positions.mean()
        centered_responses = responses - responses.mean()
        position_energy = float(centered_positions @ centered_positions)
        response_energy = float(centered_responses @ centered_responses)
        if position_energy <= 0.0:
            continue
        covariance = float(centered_positions @ centered_responses)
        slope = covariance / position_energy
        slopes[stop] = slope
        if np.isfinite(values[stop]):
            intercept = float(responses.mean() - slope * positions.mean())
            residuals[stop] = values[stop] - (slope * sample.size + intercept)
        sample_std = float(np.std(responses, ddof=1))
        if response_energy > 0.0 and not np.isclose(sample_std, 0.0, atol=2e-5):
            r_squares[stop] = covariance * covariance / (position_energy * response_energy)
    return slopes, r_squares, residuals


def _rolling_moments(
    series: pd.Series,
    window: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return explicit-window sum/mean/std without incremental-state drift."""

    values = series.to_numpy(dtype=np.float64)
    sums = np.full(values.shape, np.nan, dtype=np.float64)
    means = np.full(values.shape, np.nan, dtype=np.float64)
    standard_deviations = np.full(values.shape, np.nan, dtype=np.float64)
    for stop in range(values.size):
        start = max(0, stop - window + 1)
        valid = values[start : stop + 1]
        valid = valid[np.isfinite(valid)]
        if valid.size == 0:
            continue
        sums[stop] = float(np.sum(valid))
        means[stop] = float(np.mean(valid))
        if valid.size >= 2:
            standard_deviations[stop] = float(np.std(valid, ddof=1))
    return pd.Series(sums), pd.Series(means), pd.Series(standard_deviations)


def _rolling_corr(left: pd.Series, right: pd.Series, window: int) -> pd.Series:
    left_values = left.to_numpy(dtype=np.float64)
    right_values = right.to_numpy(dtype=np.float64)
    result = np.full(left_values.shape, np.nan, dtype=np.float64)
    for stop in range(left_values.size):
        start = max(0, stop - window + 1)
        left_sample = left_values[start : stop + 1]
        right_sample = right_values[start : stop + 1]
        left_finite = left_sample[np.isfinite(left_sample)]
        right_finite = right_sample[np.isfinite(right_sample)]
        if left_finite.size < 2 or right_finite.size < 2:
            continue
        if np.isclose(np.std(left_finite, ddof=1), 0.0, atol=2e-5) or np.isclose(
            np.std(right_finite, ddof=1),
            0.0,
            atol=2e-5,
        ):
            continue
        paired = np.isfinite(left_sample) & np.isfinite(right_sample)
        if int(paired.sum()) < 2:
            continue
        paired_left = left_sample[paired]
        paired_right = right_sample[paired]
        centered_left = paired_left - paired_left.mean()
        centered_right = paired_right - paired_right.mean()
        denominator = float(np.sqrt((centered_left @ centered_left) * (centered_right @ centered_right)))
        if denominator > 0.0:
            result[stop] = float(centered_left @ centered_right) / denominator
    return pd.Series(result)


def _materialize_symbol(frame: pd.DataFrame) -> dict[str, NDArray[np.float64]]:
    open_price = frame["open"].reset_index(drop=True)
    high = frame["high"].reset_index(drop=True)
    low = frame["low"].reset_index(drop=True)
    close = frame["close"].reset_index(drop=True)
    volume = frame["volume"].reset_index(drop=True)
    vwap = frame["vwap"].reset_index(drop=True)
    high_low = high - low
    upper_body = pd.concat((open_price, close), axis=1).max(axis=1, skipna=False)
    lower_body = pd.concat((open_price, close), axis=1).min(axis=1, skipna=False)
    features: dict[str, pd.Series] = {
        "KMID": (close - open_price) / open_price,
        "KLEN": high_low / open_price,
        "KMID2": (close - open_price) / (high_low + _EPSILON),
        "KUP": (high - upper_body) / open_price,
        "KUP2": (high - upper_body) / (high_low + _EPSILON),
        "KLOW": (lower_body - low) / open_price,
        "KLOW2": (lower_body - low) / (high_low + _EPSILON),
        "KSFT": (2.0 * close - high - low) / open_price,
        "KSFT2": (2.0 * close - high - low) / (high_low + _EPSILON),
        "OPEN0": open_price / close,
        "HIGH0": high / close,
        "LOW0": low / close,
        "VWAP0": vwap / close,
    }
    close_ref = close.shift(1)
    volume_ref = volume.shift(1)
    close_delta = close - close_ref
    volume_delta = volume - volume_ref
    close_gain = close_delta.clip(lower=0.0)
    close_loss = (-close_delta).clip(lower=0.0)
    volume_gain = volume_delta.clip(lower=0.0)
    volume_loss = (-volume_delta).clip(lower=0.0)
    absolute_close_delta = close_delta.abs()
    absolute_volume_delta = volume_delta.abs()
    close_up = (close > close_ref).astype(np.float64)
    close_down = (close < close_ref).astype(np.float64)
    with np.errstate(divide="ignore", invalid="ignore"):
        close_ratio = close / close_ref
        log_volume = np.log(volume + 1.0)
        log_volume_ratio = np.log(volume / volume_ref + 1.0)
        weighted_move = (close_ratio - 1.0).abs() * volume
    for window in ALPHA158_WINDOWS:
        rolling_close = close.rolling(window, min_periods=1)
        rolling_high = high.rolling(window, min_periods=1)
        rolling_low = low.rolling(window, min_periods=1)
        _, close_mean, close_std = _rolling_moments(close, window)
        _, volume_mean, volume_std = _rolling_moments(volume, window)
        gain_sum, _, _ = _rolling_moments(close_gain, window)
        loss_sum, _, _ = _rolling_moments(close_loss, window)
        absolute_sum, _, _ = _rolling_moments(absolute_close_delta, window)
        volume_gain_sum, _, _ = _rolling_moments(volume_gain, window)
        volume_loss_sum, _, _ = _rolling_moments(volume_loss, window)
        absolute_volume_sum, _, _ = _rolling_moments(absolute_volume_delta, window)
        _, close_up_mean, _ = _rolling_moments(close_up, window)
        _, close_down_mean, _ = _rolling_moments(close_down, window)
        _, weighted_mean, weighted_std = _rolling_moments(weighted_move, window)
        slope, r_square, residual = _rolling_linear(close.to_numpy(dtype=np.float64), window)
        rolling_max = rolling_high.max()
        rolling_min = rolling_low.min()
        index_max = rolling_high.apply(lambda values: float(values.argmax() + 1), raw=True)
        index_min = rolling_low.apply(lambda values: float(values.argmin() + 1), raw=True)
        features.update(
            {
                f"ROC{window}": close.shift(window) / close,
                f"MA{window}": close_mean / close,
                f"STD{window}": close_std / close,
                f"BETA{window}": pd.Series(slope) / close,
                f"RSQR{window}": pd.Series(r_square),
                f"RESI{window}": pd.Series(residual) / close,
                f"MAX{window}": rolling_max / close,
                f"MIN{window}": rolling_min / close,
                f"QTLU{window}": rolling_close.quantile(0.8) / close,
                f"QTLD{window}": rolling_close.quantile(0.2) / close,
                f"RANK{window}": rolling_close.rank(pct=True),
                f"RSV{window}": (close - rolling_min) / (rolling_max - rolling_min + _EPSILON),
                f"IMAX{window}": index_max / window,
                f"IMIN{window}": index_min / window,
                f"IMXD{window}": (index_max - index_min) / window,
                f"CORR{window}": _rolling_corr(close, log_volume, window),
                f"CORD{window}": _rolling_corr(close_ratio, log_volume_ratio, window),
                f"CNTP{window}": close_up_mean,
                f"CNTN{window}": close_down_mean,
                f"CNTD{window}": close_up_mean - close_down_mean,
                f"SUMP{window}": gain_sum / (absolute_sum + _EPSILON),
                f"SUMN{window}": loss_sum / (absolute_sum + _EPSILON),
                f"SUMD{window}": (gain_sum - loss_sum) / (absolute_sum + _EPSILON),
                f"VMA{window}": volume_mean / (volume + _EPSILON),
                f"VSTD{window}": volume_std / (volume + _EPSILON),
                f"WVMA{window}": weighted_std / (weighted_mean + _EPSILON),
                f"VSUMP{window}": volume_gain_sum / (absolute_volume_sum + _EPSILON),
                f"VSUMN{window}": volume_loss_sum / (absolute_volume_sum + _EPSILON),
                f"VSUMD{window}": (volume_gain_sum - volume_loss_sum) / (absolute_volume_sum + _EPSILON),
            }
        )
    return {member_id: features[member_id].to_numpy(dtype=np.float64) for member_id in ALPHA158_MEMBER_IDS}


def materialize_alpha158(
    rows: pd.DataFrame,
    *,
    history: pd.DataFrame | None = None,
) -> Alpha158Materialization:
    """Materialize Alpha158 on a small panel using at most 60 prior context rows.

    ``history`` is an optional raw left context for chunked computation.  Every
    context row for a symbol must precede that symbol's first current row.  Only
    current rows are returned.  The method canonicalizes by symbol/date and is
    intentionally in-memory; a lake-scale surface belongs in a separate layer.
    """

    combined = _canonical_input(rows, history=history)
    values = np.full((len(combined), len(ALPHA158_MEMBER_IDS)), np.nan, dtype=np.float64)
    for _, positions in combined.groupby("symbol", sort=False).indices.items():
        position_array = np.asarray(positions, dtype=np.int64)
        symbol_features = _materialize_symbol(combined.iloc[position_array])
        values[position_array, :] = np.column_stack([symbol_features[member_id] for member_id in ALPHA158_MEMBER_IDS])
    values[~np.isfinite(values)] = np.nan
    output = combined["_alpha158_output_row"].to_numpy(dtype=np.bool_)
    output_values = np.ascontiguousarray(values[output], dtype=np.float64)
    observed = np.ascontiguousarray(np.isfinite(output_values), dtype=np.bool_)
    output_values.setflags(write=False)
    observed.setflags(write=False)
    coordinates = combined.loc[output, ["symbol", "trading_day"]].reset_index(drop=True)
    return Alpha158Materialization(
        coordinates=coordinates,
        values=output_values,
        observed=observed,
        member_ids=ALPHA158_MEMBER_IDS,
        member_digest=ALPHA158_MEMBER_DIGEST,
        formula_digest=ALPHA158_FORMULA_DIGEST,
    )
