"""Synthetic causal and accounting counterexamples; no fitting or market data."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timedelta, timezone

import pytest

from factor_lab.factor_rotation.reaka_financial_residual import (
    FinancialReturnConvention,
    FrozenFinancialCoefficients,
    RealizedFinancialReturn,
    calculate_financial_return_residual,
)


UTC = timezone.utc
START = datetime(2020, 1, 6, 7, 0, tzinfo=UTC)
END = datetime(2020, 1, 7, 7, 0, tzinfo=UTC)
CONVENTION = FinancialReturnConvention("one_trading_day", "declared_close_to_close_total_return", "CNY")


def _inputs() -> tuple[RealizedFinancialReturn, dict[str, RealizedFinancialReturn], FrozenFinancialCoefficients]:
    stock = RealizedFinancialReturn("stock-A", "2020-01-06_to_2020-01-07", CONVENTION, START, END, END, 0.25)
    factors = {
        "market": replace(stock, series_id="market-v1", value=0.125),
        "size": replace(stock, series_id="size-v1", value=-0.0625),
        "industry": replace(stock, series_id="industry-A-v1", value=0.0625),
    }
    coefficients = FrozenFinancialCoefficients(
        stock_id=stock.series_id,
        convention=CONVENTION,
        factor_ids={key: value.series_id for key, value in factors.items()},
        betas={"market": 1.0, "size": 0.5, "industry": 2.0},
        intercept=0.015625,
        latest_estimation_label_end_at=START - timedelta(days=3),
        latest_estimation_label_available_at=START - timedelta(days=3) + timedelta(minutes=1),
        information_available_at=START - timedelta(hours=2),
        frozen_at=START - timedelta(hours=1),
    )
    return stock, factors, coefficients


def test_realized_financial_components_conserve_return_with_signed_exposures() -> None:
    stock, factors, coefficients = _inputs()
    result = calculate_financial_return_residual(stock, factors, coefficients, prediction_at=START, as_of=END)
    assert result.factor_contributions == {"market": 0.125, "size": -0.03125, "industry": 0.125}
    assert result.intercept_contribution == 0.015625
    assert result.explained_return == 0.234375
    assert result.epsilon_return == 0.015625
    assert result.observed_return == result.explained_return + result.epsilon_return
    assert result.available_at == END


def test_exact_factor_explanation_allows_zero_residual() -> None:
    stock, factors, coefficients = _inputs()
    result = calculate_financial_return_residual(
        replace(stock, value=0.234375), factors, coefficients, prediction_at=START, as_of=END,
    )
    assert result.epsilon_return == 0.0


def test_no_intercept_is_explicit_and_negative_residual_is_valid() -> None:
    stock, factors, coefficients = _inputs()
    result = calculate_financial_return_residual(
        replace(stock, value=-0.25), factors, replace(coefficients, intercept=None), prediction_at=START, as_of=END,
    )
    assert result.intercept_contribution == 0.0
    assert result.epsilon_return == -0.46875


def test_late_factor_publication_delays_residual_even_when_stock_return_is_known() -> None:
    stock, factors, coefficients = _inputs()
    factors["industry"] = replace(factors["industry"], available_at=END + timedelta(hours=2))
    with pytest.raises(ValueError, match="unavailable before all realized labels"):
        calculate_financial_return_residual(stock, factors, coefficients, prediction_at=START, as_of=END)
    result = calculate_financial_return_residual(
        stock, factors, coefficients, prediction_at=START, as_of=END + timedelta(hours=2),
    )
    assert result.available_at == END + timedelta(hours=2)


def test_realized_financial_residual_cannot_be_read_at_prediction_time() -> None:
    stock, factors, coefficients = _inputs()
    with pytest.raises(ValueError, match="unavailable before all realized labels"):
        calculate_financial_return_residual(stock, factors, coefficients, prediction_at=START, as_of=START)


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -float("inf"), True, "0.01"])
def test_nonfinite_or_non_numeric_observations_and_coefficients_are_rejected(bad: object) -> None:
    stock, _, coefficients = _inputs()
    with pytest.raises(ValueError, match="finite real number"):
        replace(stock, value=bad)
    with pytest.raises(ValueError, match="finite real number"):
        replace(coefficients, intercept=bad)
    with pytest.raises(ValueError, match="finite real number"):
        replace(coefficients, betas={**coefficients.betas, "market": bad})


def test_finite_inputs_whose_product_overflows_are_rejected() -> None:
    stock, factors, coefficients = _inputs()
    factors["market"] = replace(factors["market"], value=1e308)
    with pytest.raises(ValueError, match="finite real number"):
        calculate_financial_return_residual(
            stock, factors, replace(coefficients, betas={**coefficients.betas, "market": 1e308}),
            prediction_at=START, as_of=END,
        )


@pytest.mark.parametrize("key", ["market", "size", "industry"])
def test_missing_factor_cannot_silently_be_assigned_zero(key: str) -> None:
    stock, factors, coefficients = _inputs()
    del factors[key]
    with pytest.raises(ValueError, match="exactly market, size, industry"):
        calculate_financial_return_residual(stock, factors, coefficients, prediction_at=START, as_of=END)
    with pytest.raises(ValueError, match="exactly market, size, industry"):
        replace(coefficients, betas={k: v for k, v in coefficients.betas.items() if k != key})


def test_extra_factor_is_a_different_decomposition_not_an_ignored_input() -> None:
    stock, factors, coefficients = _inputs()
    factors["momentum"] = replace(stock, series_id="momentum-v1")
    with pytest.raises(ValueError, match="exactly market, size, industry"):
        calculate_financial_return_residual(stock, factors, coefficients, prediction_at=START, as_of=END)


@pytest.mark.parametrize(
    "changes",
    [
        {"period_id": "different-period"},
        {"start_at": START - timedelta(days=1)},
        {"end_at": END - timedelta(minutes=1)},
        {"convention": replace(CONVENTION, horizon_id="twenty_trading_days")},
        {"convention": replace(CONVENTION, return_basis="price_return_without_dividends")},
        {"convention": replace(CONVENTION, currency="USD")},
    ],
)
def test_realized_factors_must_share_exact_stock_interval_and_return_convention(changes: dict[str, object]) -> None:
    stock, factors, coefficients = _inputs()
    factors["size"] = replace(factors["size"], **changes)
    with pytest.raises(ValueError, match="factor period/horizon/units/return basis mismatch"):
        calculate_financial_return_residual(stock, factors, coefficients, prediction_at=START, as_of=END)


@pytest.mark.parametrize("unit", ["log_return", "percentage_points", "simple_return_percent"])
def test_log_and_percentage_units_require_explicit_conversion_before_calculation(unit: str) -> None:
    with pytest.raises(ValueError, match="unit must be simple_decimal_return"):
        replace(CONVENTION, unit=unit)


def test_coefficients_cannot_be_transplanted_between_horizons_or_stocks() -> None:
    stock, factors, coefficients = _inputs()
    with pytest.raises(ValueError, match="stock identity"):
        calculate_financial_return_residual(
            replace(stock, series_id="stock-B"), factors, coefficients, prediction_at=START, as_of=END,
        )
    with pytest.raises(ValueError, match="coefficient convention"):
        calculate_financial_return_residual(
            stock, factors, replace(coefficients, convention=replace(CONVENTION, horizon_id="twenty_trading_days")),
            prediction_at=START, as_of=END,
        )


def test_financial_factor_identity_is_bound_beyond_dictionary_role_name() -> None:
    stock, factors, coefficients = _inputs()
    factors["industry"] = replace(factors["industry"], series_id="different-industry-v1")
    with pytest.raises(ValueError, match="factor identity mismatch"):
        calculate_financial_return_residual(stock, factors, coefficients, prediction_at=START, as_of=END)


@pytest.mark.parametrize(
    "changes",
    [
        {"latest_estimation_label_end_at": START + timedelta(days=1)},
        {"latest_estimation_label_available_at": START + timedelta(days=1)},
        {"information_available_at": START + timedelta(minutes=1)},
    ],
)
def test_coefficients_reject_future_or_immature_estimation_labels_and_inputs(changes: dict[str, datetime]) -> None:
    _, _, coefficients = _inputs()
    with pytest.raises(ValueError, match="available before coefficient freeze"):
        replace(coefficients, **changes)


def test_post_prediction_freeze_and_prediction_inside_realization_interval_are_rejected() -> None:
    stock, factors, coefficients = _inputs()
    with pytest.raises(ValueError, match="frozen_at <= prediction_at"):
        calculate_financial_return_residual(
            stock, factors, replace(coefficients, frozen_at=START + timedelta(minutes=1)),
            prediction_at=START, as_of=END,
        )
    with pytest.raises(ValueError, match="prediction_at <= return start_at"):
        calculate_financial_return_residual(
            stock, factors, coefficients, prediction_at=START + timedelta(minutes=1), as_of=END,
        )


def test_return_cannot_be_available_before_its_label_end() -> None:
    stock, _, _ = _inputs()
    with pytest.raises(ValueError, match="end_at <= available_at"):
        replace(stock, available_at=END - timedelta(seconds=1))


def test_timezone_equivalence_uses_instants_not_wall_clock_text() -> None:
    stock, factors, coefficients = _inputs()
    china = timezone(timedelta(hours=8))
    factors = {
        key: replace(value, start_at=START.astimezone(china), end_at=END.astimezone(china))
        for key, value in factors.items()
    }
    result = calculate_financial_return_residual(
        stock, factors, coefficients, prediction_at=START.astimezone(china), as_of=END.astimezone(china),
    )
    assert result.epsilon_return == 0.015625
    assert result.available_at.tzinfo == UTC


def test_naive_datetimes_are_rejected_instead_of_guessing_exchange_timezone() -> None:
    stock, factors, coefficients = _inputs()
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(stock, start_at=START.replace(tzinfo=None))
    with pytest.raises(ValueError, match="timezone-aware"):
        replace(coefficients, frozen_at=START.replace(tzinfo=None))
    for argument in ("prediction_at", "as_of"):
        times = {"prediction_at": START, "as_of": END}
        times[argument] = times[argument].replace(tzinfo=None)
        with pytest.raises(ValueError, match="timezone-aware"):
            calculate_financial_return_residual(stock, factors, coefficients, **times)


def test_caller_cannot_mutate_previously_frozen_betas_or_return_components() -> None:
    stock, factors, coefficients = _inputs()
    mutable_betas = dict(coefficients.betas)
    coefficients = replace(coefficients, betas=mutable_betas)
    mutable_betas["market"] = 99.0
    assert coefficients.betas["market"] == 1.0
    with pytest.raises(TypeError):
        coefficients.betas["market"] = 99.0
    with pytest.raises(FrozenInstanceError):
        coefficients.intercept = 99.0
    result = calculate_financial_return_residual(stock, factors, coefficients, prediction_at=START, as_of=END)
    with pytest.raises(TypeError):
        result.factor_contributions["market"] = 99.0
