"""Idempotent observability configuration for factor_lab."""

from __future__ import annotations

import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from importlib import import_module
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Lock
from typing import Final, Literal, Protocol, cast

from factor_lab.core.settings import (
    LOG_ROTATION_BACKUP_COUNT,
    LOG_ROTATION_MAX_BYTES,
    LOGS_DIR,
    get_log_file_sink_path,
    get_logs_dir,
)

ContextPropagationMode = Literal["off", "compat", "strict"]
LogFormat = Literal["legacy", "dual", "json_v1"]

_TEXT_FORMATTER: Final[logging.Formatter] = logging.Formatter(
    "%(asctime)s %(levelname)s %(name)s %(message)s"
)
_HANDLER_REGISTRY: dict[tuple[str, str], logging.Handler] = {}
_REGISTRY_LOCK: Final[Lock] = Lock()


class _JsonFormatterFactory(Protocol):
    def __call__(
        self,
        *,
        context_mode: ContextPropagationMode = "compat",
    ) -> logging.Formatter:
        ...


class _FactorLabLoggerFactory(Protocol):
    def __call__(
        self,
        logger: object,
        *,
        context_mode: ContextPropagationMode = "compat",
    ) -> object:
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
_shared_formatter_module = import_module("shared.observability.json_formatter")
_logger_module = import_module(f"{__package__}.logger")
CONTEXT_ENVIRONMENT_FIELDS = cast(
    dict[str, str],
    _shared_context.CONTEXT_ENVIRONMENT_FIELDS,
)
bind_context_from_environment = cast(
    Callable[..., object],
    _shared_context.bind_context_from_environment,
)
JsonFormatter = cast(
    _JsonFormatterFactory,
    _shared_formatter_module.JsonFormatter,
)
FactorLabLogger = cast(
    _FactorLabLoggerFactory,
    _logger_module.FactorLabLogger,
)
unwrap_stdlib_logger = cast(
    Callable[[object | None], logging.Logger | None],
    _logger_module.unwrap_stdlib_logger,
)


@dataclass(slots=True)
class ObservabilityConfig:
    level: str = "INFO"
    log_format: LogFormat = "dual"
    context_propagation: ContextPropagationMode = "compat"
    console_output: bool = True
    log_dir: Path = field(default_factory=get_logs_dir)
    log_rotation_max_bytes: int = LOG_ROTATION_MAX_BYTES
    log_rotation_backup_count: int = LOG_ROTATION_BACKUP_COUNT

    @classmethod
    def from_env(cls) -> ObservabilityConfig:
        log_dir_raw = os.environ.get("FACTOR_LAB_LOG_DIR")
        max_bytes_raw = os.environ.get(
            "FACTOR_LAB_LOG_ROTATION_MAX_BYTES",
            str(LOG_ROTATION_MAX_BYTES),
        )
        backup_count_raw = os.environ.get(
            "FACTOR_LAB_LOG_ROTATION_BACKUP_COUNT",
            str(LOG_ROTATION_BACKUP_COUNT),
        )
        return cls(
            level=(
                os.environ.get("FACTOR_LAB_LOG_LEVEL", "INFO").strip().upper()
                or "INFO"
            ),
            log_format=_normalize_log_format(
                os.environ.get("FACTOR_LAB_LOG_FORMAT", "dual")
            ),
            context_propagation=_normalize_context_mode(
                os.environ.get("FACTOR_LAB_CONTEXT_PROPAGATION", "compat")
            ),
            console_output=_parse_bool(
                os.environ.get("FACTOR_LAB_LOG_TO_STDOUT"),
                True,
            ),
            log_dir=(
                Path(log_dir_raw).expanduser().resolve()
                if log_dir_raw
                else LOGS_DIR
            ),
            log_rotation_max_bytes=_safe_positive_int(
                max_bytes_raw,
                default=LOG_ROTATION_MAX_BYTES,
            ),
            log_rotation_backup_count=_safe_non_negative_int(
                backup_count_raw,
                default=LOG_ROTATION_BACKUP_COUNT,
            ),
        )

    def legacy_log_path(self, logger_name: str) -> Path:
        if self.log_dir == LOGS_DIR:
            return get_log_file_sink_path(_safe_logger_name(logger_name))
        return self.log_dir / f"{_safe_logger_name(logger_name)}.log"

    def json_log_path(self, logger_name: str) -> Path:
        if self.log_dir == LOGS_DIR:
            return get_log_file_sink_path(
                _safe_logger_name(logger_name),
                json_format=True,
            )
        return self.log_dir / f"{_safe_logger_name(logger_name)}.jsonl"


def configure_observability(
    name: str = "factor_lab",
    *,
    logger: object | None = None,
    config: ObservabilityConfig | None = None,
) -> object:
    resolved_config = config or ObservabilityConfig.from_env()
    base_logger = unwrap_stdlib_logger(logger) or logging.getLogger(name)
    base_logger.setLevel(_resolve_level(resolved_config.level))
    base_logger.propagate = False

    _seed_context_from_environment(resolved_config.context_propagation)
    desired_handlers = _build_handlers(base_logger.name, resolved_config)
    _synchronize_handlers(base_logger, desired_handlers)

    return FactorLabLogger(
        logger or base_logger,
        context_mode=resolved_config.context_propagation,
    )


def get_logger(
    name: str = "factor_lab",
    *,
    config: ObservabilityConfig | None = None,
) -> object:
    return configure_observability(name=name, config=config)


def _build_handlers(
    logger_name: str,
    config: ObservabilityConfig,
) -> dict[str, logging.Handler]:
    config.log_dir.mkdir(parents=True, exist_ok=True)
    level = _resolve_level(config.level)
    handlers: dict[str, logging.Handler] = {}

    if config.console_output:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        if config.log_format == "json_v1":
            console_handler.setFormatter(
                JsonFormatter(context_mode=config.context_propagation)
            )
            handlers["console:json"] = console_handler
        else:
            console_handler.setFormatter(_TEXT_FORMATTER)
            handlers["console:text"] = console_handler

    if config.log_format in {"legacy", "dual"}:
        legacy_path = config.legacy_log_path(logger_name)
        legacy_path.parent.mkdir(parents=True, exist_ok=True)
        legacy_handler = RotatingFileHandler(
            legacy_path,
            maxBytes=config.log_rotation_max_bytes,
            backupCount=config.log_rotation_backup_count,
            encoding="utf-8",
        )
        legacy_handler.setLevel(level)
        legacy_handler.setFormatter(_TEXT_FORMATTER)
        handlers[f"file:text:{legacy_path}"] = legacy_handler

    if config.log_format in {"dual", "json_v1"}:
        json_path = config.json_log_path(logger_name)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_handler = RotatingFileHandler(
            json_path,
            maxBytes=config.log_rotation_max_bytes,
            backupCount=config.log_rotation_backup_count,
            encoding="utf-8",
        )
        json_handler.setLevel(level)
        json_handler.setFormatter(JsonFormatter(context_mode=config.context_propagation))
        handlers[f"file:json:{json_path}"] = json_handler

    return handlers


def _synchronize_handlers(
    logger: logging.Logger,
    desired_handlers: dict[str, logging.Handler],
) -> None:
    active_keys: set[tuple[str, str]] = set()
    with _REGISTRY_LOCK:
        for handler_key, handler in desired_handlers.items():
            registry_key = (logger.name, handler_key)
            active_keys.add(registry_key)
            existing = _HANDLER_REGISTRY.get(registry_key)
            if existing is None:
                logger.addHandler(handler)
                _HANDLER_REGISTRY[registry_key] = handler
                continue
            existing.setLevel(handler.level)
            if handler.formatter is not None:
                existing.setFormatter(handler.formatter)
            if existing not in logger.handlers:
                logger.addHandler(existing)
            handler.close()

        for registry_key, handler in list(_HANDLER_REGISTRY.items()):
            if registry_key[0] != logger.name or registry_key in active_keys:
                continue
            if handler in logger.handlers:
                logger.removeHandler(handler)
            handler.close()
            del _HANDLER_REGISTRY[registry_key]


def _seed_context_from_environment(mode: ContextPropagationMode) -> None:
    if mode == "off":
        return
    if not any(
        os.environ.get(env_name)
        for env_name in CONTEXT_ENVIRONMENT_FIELDS.values()
    ):
        return
    _ = bind_context_from_environment(mode=mode)


def _safe_logger_name(logger_name: str) -> str:
    cleaned = logger_name.replace(".", "_").strip("_")
    return cleaned or "factor_lab"


def _resolve_level(level_name: str) -> int:
    level = getattr(logging, level_name.upper(), logging.INFO)
    return level if isinstance(level, int) else logging.INFO


def _parse_bool(raw_value: str | None, default: bool) -> bool:
    if raw_value is None:
        return default
    return raw_value.strip().lower() not in {"0", "false", "no", "off"}


def _normalize_log_format(raw_value: str) -> LogFormat:
    normalized = raw_value.strip().lower()
    if normalized == "legacy":
        return "legacy"
    if normalized == "json_v1":
        return "json_v1"
    return "dual"


def _normalize_context_mode(raw_value: str) -> ContextPropagationMode:
    normalized = raw_value.strip().lower()
    if normalized == "off":
        return "off"
    if normalized == "strict":
        return "strict"
    return "compat"


def _safe_positive_int(raw_value: str, *, default: int) -> int:
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def _safe_non_negative_int(raw_value: str, *, default: int) -> int:
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return parsed if parsed >= 0 else default
