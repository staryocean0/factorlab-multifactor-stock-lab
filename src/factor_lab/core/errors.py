"""Backward-compatible Factor Lab error exports."""

from __future__ import annotations

from factor_lab.observability.exceptions import (
    ConfirmationRequiredError,
    ConflictError,
    FactorLabError,
    GateBlockedError,
    InternalServerError,
    JsonScalar,
    JsonValue,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)


class CanonicalFactorLabError(FactorLabError):
    """Error bridge that keeps legacy code while mapping canonical_code."""

    def __init__(
        self,
        code: str,
        message: str,
        **kwargs,
    ) -> None:
        kwargs.setdefault("canonical_code", code)
        super().__init__(code, message, **kwargs)


class ApiLayerError(CanonicalFactorLabError):
    """Base error for API layer failures."""


class ServiceLayerError(CanonicalFactorLabError):
    """Base error for service layer failures."""


class GovernanceLayerError(CanonicalFactorLabError):
    """Base error for governance layer failures."""


__all__ = [
    "ApiLayerError",
    "CanonicalFactorLabError",
    "ConflictError",
    "ConfirmationRequiredError",
    "FactorLabError",
    "GateBlockedError",
    "GovernanceLayerError",
    "InternalServerError",
    "JsonScalar",
    "JsonValue",
    "NotFoundError",
    "ServiceLayerError",
    "UnauthorizedError",
    "ValidationError",
]
