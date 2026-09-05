"""factor_lab exception adapters built on the shared foundation."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import TYPE_CHECKING, NoReturn, TypeAlias, cast


def _ensure_workspace_root_on_path() -> None:
    for parent in Path(__file__).resolve().parents:
        if (parent / "shared" / "observability" / "exceptions.py").is_file():
            root = str(parent)
            while root in sys.path:
                sys.path.remove(root)
            sys.path.insert(0, root)
            return
    raise ModuleNotFoundError("workspace shared observability package not found")


_ensure_workspace_root_on_path()

_shared_exceptions = importlib.import_module("shared.observability.exceptions")

JsonScalar: TypeAlias = str | int | float | bool | None
JsonValue: TypeAlias = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

if TYPE_CHECKING:
    class QuantException(Exception):
        message: str = ""
        canonical_code: str = ""
        request_id: str = ""
        trace_id: str = ""
        status_code: int = 500

        def __init__(
            self,
            message: str,
            *,
            canonical_code: str | None = None,
            error_code: str | None = None,
            code: str | None = None,
            legacy_code: str | None = None,
            details: dict[str, JsonValue] | None = None,
            status_code: int | None = None,
            retryable: bool | None = None,
            request_id: str | None = None,
            trace_id: str | None = None,
            meta: dict[str, JsonValue] | None = None,
            recovery_hint: str | None = None,
        ) -> None:
            super().__init__(message)

        def to_envelope(
            self,
            *,
            request_id: str | None = None,
            trace_id: str | None = None,
            meta: dict[str, JsonValue] | None = None,
            include_error_request_id: bool = False,
        ) -> dict[str, JsonValue]:
            return {}

        @classmethod
        def raise_from(
            cls,
            cause: BaseException,
            *args: object,
            **kwargs: object,
        ) -> NoReturn:
            raise cls(str(cause))
else:
    QuantException = cast(type[Exception], _shared_exceptions.QuantException)


class FactorLabError(QuantException):
    """Canonical exception for factor_lab with legacy envelope compatibility."""

    def __init__(
        self,
        code: str,
        message: str,
        request_id: str | None = None,
        details: dict[str, JsonValue] | None = None,
        retryable: bool = False,
        status_code: int = 400,
        trace_id: str | None = None,
        canonical_code: str | None = None,
        error_code: str | None = None,
        legacy_code: str | None = None,
        meta: dict[str, JsonValue] | None = None,
        recovery_hint: str | None = None,
    ) -> None:
        super().__init__(
            message,
            canonical_code=canonical_code,
            error_code=error_code,
            code=code,
            legacy_code=legacy_code,
            details=details,
            status_code=status_code,
            retryable=retryable,
            request_id=request_id,
            trace_id=trace_id,
            meta=meta,
            recovery_hint=recovery_hint,
        )

    def to_dict(self) -> dict[str, JsonValue]:
        return self.to_envelope(include_error_request_id=True)


class ValidationError(FactorLabError):
    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            "E_VALIDATION",
            message,
            retryable=False,
            status_code=400,
            **kwargs,
        )


class NotFoundError(FactorLabError):
    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            "E_NOT_FOUND",
            message,
            retryable=False,
            status_code=404,
            **kwargs,
        )


class ConflictError(FactorLabError):
    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            "E_CONFLICT",
            message,
            retryable=False,
            status_code=409,
            **kwargs,
        )


class ConfirmationRequiredError(FactorLabError):
    def __init__(self, message: str, **kwargs) -> None:
        super().__init__(
            "E_CONFIRMATION_REQUIRED",
            message,
            retryable=False,
            status_code=409,
            **kwargs,
        )


class GateBlockedError(FactorLabError):
    gate_name: str

    def __init__(self, message: str, gate_name: str, **kwargs) -> None:
        details = dict(kwargs.pop("details", {}) or {})
        details.setdefault("gate_name", gate_name)
        super().__init__(
            "E_GATE_BLOCKED",
            message,
            retryable=False,
            status_code=409,
            details=details,
            **kwargs,
        )
        self.gate_name = gate_name


class UnauthorizedError(FactorLabError):
    def __init__(self, message: str, *, status_code: int = 401, **kwargs) -> None:
        super().__init__(
            "E_UNAUTHORIZED",
            message,
            retryable=False,
            status_code=status_code,
            **kwargs,
        )


class InternalServerError(FactorLabError):
    def __init__(self, message: str = "An unexpected error occurred", **kwargs) -> None:
        super().__init__(
            "E_INTERNAL_ERROR",
            message,
            retryable=True,
            status_code=500,
            **kwargs,
        )
