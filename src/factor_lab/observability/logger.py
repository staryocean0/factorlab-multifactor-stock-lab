"""Canonical logger wrapper for factor_lab."""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Mapping
from importlib import import_module
from pathlib import Path
from types import TracebackType
from typing import Final, Literal, Protocol, cast

ContextPropagationMode = Literal["off", "compat", "strict"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
LogExtra = Mapping[str, object]

_STANDARD_LOGGING_KWARGS: Final[frozenset[str]] = frozenset(
    {"exc_info", "stack_info", "stacklevel"}
)
ExcInfoType = (
    bool
    | BaseException
    | tuple[type[BaseException], BaseException, TracebackType | None]
)


class _ResolvedContextProtocol(Protocol):
    def as_dict(self, *, include_none: bool = False) -> dict[str, str | None]:
        ...


def _ensure_workspace_root_on_path() -> None:
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "shared" / "observability").is_dir() and (
            parent / "docs" / "schemas" / "log-schema-v1.json"
        ).is_file():
            workspace_root = str(parent)
            while workspace_root in sys.path:
                sys.path.remove(workspace_root)
            sys.path.insert(0, workspace_root)
            break


_ensure_workspace_root_on_path()
_shared_context = import_module("shared.observability.context")
CONTEXT_FIELD_NAMES = cast(tuple[str, ...], _shared_context.CONTEXT_FIELD_NAMES)
resolve_context = cast(
    Callable[..., _ResolvedContextProtocol],
    _shared_context.resolve_context,
)


def unwrap_stdlib_logger(logger: object | None) -> logging.Logger | None:
    """Best-effort unwrapping for stdlib-backed Factor Lab loggers."""

    if logger is None:
        return None
    if isinstance(logger, logging.Logger):
        return logger
    candidate = getattr(logger, "logger", None)
    if isinstance(candidate, logging.Logger):
        return candidate
    candidate = getattr(logger, "_logger", None)
    if isinstance(candidate, logging.Logger):
        return candidate
    return None


class FactorLabLogger:
    """Small wrapper that emits canonical v1 log records for Factor Lab."""

    def __init__(
        self,
        logger: object,
        *,
        context_mode: ContextPropagationMode = "compat",
    ) -> None:
        self._logger = logger
        self._stdlib_logger = unwrap_stdlib_logger(logger)
        self._context_mode = context_mode

    def debug(
        self,
        message: str,
        *args: object,
        extra: LogExtra | None = None,
        **kwargs: object,
    ) -> None:
        self.event("DEBUG", message, *args, extra=extra, **kwargs)

    def info(
        self,
        message: str,
        *args: object,
        extra: LogExtra | None = None,
        **kwargs: object,
    ) -> None:
        self.event("INFO", message, *args, extra=extra, **kwargs)

    def warning(
        self,
        message: str,
        *args: object,
        extra: LogExtra | None = None,
        **kwargs: object,
    ) -> None:
        self.event("WARNING", message, *args, extra=extra, **kwargs)

    def error(
        self,
        message: str,
        *args: object,
        extra: LogExtra | None = None,
        **kwargs: object,
    ) -> None:
        self.event("ERROR", message, *args, extra=extra, **kwargs)

    def critical(
        self,
        message: str,
        *args: object,
        extra: LogExtra | None = None,
        **kwargs: object,
    ) -> None:
        self.event("CRITICAL", message, *args, extra=extra, **kwargs)

    def exception(
        self,
        message: str,
        *args: object,
        extra: LogExtra | None = None,
        **kwargs: object,
    ) -> None:
        kwargs.setdefault("exc_info", True)
        self.error(message, *args, extra=extra, **kwargs)

    def event(
        self,
        level: LogLevel,
        message: str,
        *args: object,
        extra: LogExtra | None = None,
        **kwargs: object,
    ) -> None:
        record_context, event_extra, logging_kwargs = self._prepare_payload(
            extra,
            kwargs,
        )
        resolve_kwargs: dict[str, object] = {
            "mode": "compat" if self._context_mode == "off" else self._context_mode,
            "bind": self._context_mode != "off",
        }
        for field_name in CONTEXT_FIELD_NAMES:
            if field_name in record_context:
                resolve_kwargs[field_name] = record_context[field_name]
        resolved = resolve_context(**resolve_kwargs)

        payload: dict[str, object] = {
            key: value for key, value in resolved.as_dict().items()
        }
        if event_extra:
            payload["extra"] = event_extra
        self._emit(level, message, args, payload, logging_kwargs)

    def performance(
        self,
        operation: str,
        duration_ms: float,
        *,
        level: LogLevel = "INFO",
        status: str = "ok",
        extra: LogExtra | None = None,
        **kwargs: object,
    ) -> None:
        event_extra: dict[str, object] = {
            "kind": "performance",
            "operation": operation,
            "duration_ms": round(float(duration_ms), 3),
            "status": status,
        }
        if extra is not None:
            for key, value in extra.items():
                event_extra[str(key)] = value
        self.event(level, "operation completed", extra=event_extra, **kwargs)

    def _prepare_payload(
        self,
        extra: LogExtra | None,
        kwargs: Mapping[str, object],
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
        context_fields: dict[str, object] = {}
        event_extra: dict[str, object] = {}
        logging_kwargs: dict[str, object] = {}

        if extra is not None:
            for key, value in extra.items():
                if key in CONTEXT_FIELD_NAMES:
                    context_fields[key] = value
                else:
                    event_extra[str(key)] = value

        for key, value in kwargs.items():
            if key in _STANDARD_LOGGING_KWARGS:
                logging_kwargs[key] = value
            elif key in CONTEXT_FIELD_NAMES:
                context_fields[key] = value
            else:
                event_extra[str(key)] = value
        return context_fields, event_extra, logging_kwargs

    def _emit(
        self,
        level: LogLevel,
        message: str,
        args: tuple[object, ...],
        payload: dict[str, object],
        logging_kwargs: dict[str, object],
    ) -> None:
        if self._stdlib_logger is not None:
            exc_info = _coerce_exc_info(logging_kwargs.get("exc_info"))
            stack_info = bool(logging_kwargs.get("stack_info", False))
            stacklevel = _coerce_stacklevel(logging_kwargs.get("stacklevel"))
            self._stdlib_logger.log(
                getattr(logging, level),
                message,
                *args,
                extra=payload,
                exc_info=exc_info,
                stack_info=stack_info,
                stacklevel=stacklevel,
            )
            return

        method = getattr(self._logger, level.lower())
        fallback_kwargs = dict(logging_kwargs)
        fallback_kwargs.update(payload)
        method(message, *args, **fallback_kwargs)


def _coerce_exc_info(value: object) -> ExcInfoType | None:
    if isinstance(value, (bool, BaseException)):
        return value
    if isinstance(value, tuple) and len(value) == 3:
        exc_type, exc_value, exc_traceback = value
        if isinstance(exc_type, type) and issubclass(exc_type, BaseException):
            if isinstance(exc_value, BaseException) and (
                exc_traceback is None or isinstance(exc_traceback, TracebackType)
            ):
                return (exc_type, exc_value, exc_traceback)
    return None


def _coerce_stacklevel(value: object) -> int:
    return value if isinstance(value, int) and value > 0 else 1
