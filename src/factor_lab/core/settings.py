"""Core settings and configuration."""

from __future__ import annotations

import os
from pathlib import Path

VALID_RUNTIME_ENVIRONMENTS = frozenset(
    {"development", "test", "staging", "production"}
)
PRODUCTION_RUNTIME_ENVIRONMENTS = frozenset({"staging", "production"})
LOCAL_RUNTIME_ENVIRONMENTS = frozenset({"development", "test"})
VALID_DEPLOYMENT_PROFILES = frozenset(
    {"local_dev", "small_team_controlled", "platform"}
)
PRODUCTION_DEPLOYMENT_PROFILES = frozenset(
    {"small_team_controlled", "platform"}
)
DEFAULT_LOCAL_DATAHUB_API_URL = "http://127.0.0.1:8400"

# Project root
PROJECT_ROOT = Path(__file__).parent.parent.parent


# Data directories
def get_data_home() -> Path:
    configured = os.environ.get(
        "FACTOR_LAB_HOME",
        PROJECT_ROOT / ".local" / "factor-lab",
    )
    path = Path(configured).expanduser()
    if not path.is_absolute():
        path = (PROJECT_ROOT / path).resolve()
    else:
        path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_artifacts_dir() -> Path:
    path = get_data_home() / "artifacts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_staging_dir() -> Path:
    path = get_data_home() / "staging"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_logs_dir() -> Path:
    configured = os.environ.get("FACTOR_LAB_LOG_DIR", "").strip()
    if configured:
        path = Path(configured).expanduser()
        if not path.is_absolute():
            path = (PROJECT_ROOT / path).resolve()
        else:
            path = path.resolve()
    else:
        path = get_data_home() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_log_file_sink_path(sink_name: str, *, json_format: bool = False) -> Path:
    """Return canonical log sink path under LOGS_DIR."""

    safe_name = sink_name.replace(".", "_").strip("_") or "factor_lab"
    extension = "jsonl" if json_format else "log"
    return get_logs_dir() / f"{safe_name}.{extension}"


def get_log_rotation_max_bytes() -> int:
    raw_value = os.environ.get("FACTOR_LAB_LOG_ROTATION_MAX_BYTES", "10485760").strip()
    try:
        parsed = int(raw_value)
    except ValueError:
        parsed = 10485760
    return parsed if parsed > 0 else 10485760


def get_log_rotation_backup_count() -> int:
    raw_value = os.environ.get("FACTOR_LAB_LOG_ROTATION_BACKUP_COUNT", "5").strip()
    try:
        parsed = int(raw_value)
    except ValueError:
        parsed = 5
    return parsed if parsed >= 0 else 5


def get_runtime_state_path() -> Path:
    return get_runtime_snapshot_path()


def get_runtime_snapshot_path() -> Path:
    return get_data_home() / "runtime_state.json"


def get_runtime_database_path() -> Path:
    return get_data_home() / "runtime_state.sqlite3"


def _normalize_runtime_environment(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "dev": "development",
        "local": "development",
        "testing": "test",
        "prod": "production",
    }
    return aliases.get(normalized, normalized)


def get_runtime_environment() -> str:
    environment = _normalize_runtime_environment(
        os.environ.get("FACTOR_LAB_ENV", "development")
    )
    if environment not in VALID_RUNTIME_ENVIRONMENTS:
        supported = ", ".join(sorted(VALID_RUNTIME_ENVIRONMENTS))
        raise RuntimeError(
            f"Unsupported FACTOR_LAB_ENV '{environment}'. Expected one of: {supported}"
        )
    return environment


def get_deployment_profile() -> str:
    environment = get_runtime_environment()
    default_profile = "local_dev" if environment in {"development", "test"} else ""
    profile = os.environ.get("FACTOR_LAB_DEPLOYMENT_PROFILE", default_profile).strip()
    if profile not in VALID_DEPLOYMENT_PROFILES:
        supported = ", ".join(sorted(VALID_DEPLOYMENT_PROFILES))
        raise RuntimeError(
            "FACTOR_LAB_DEPLOYMENT_PROFILE must be configured with one of: "
            + supported
        )
    return profile


def validate_runtime_configuration() -> None:
    environment = get_runtime_environment()
    deployment_profile = get_deployment_profile()
    if environment in PRODUCTION_RUNTIME_ENVIRONMENTS:
        if deployment_profile not in PRODUCTION_DEPLOYMENT_PROFILES:
            raise RuntimeError(
                "Non-development environments require "
                + "FACTOR_LAB_DEPLOYMENT_PROFILE to be one of: "
                + ", ".join(sorted(PRODUCTION_DEPLOYMENT_PROFILES))
            )


def get_runtime_configuration_snapshot() -> dict[str, object]:
    validate_runtime_configuration()
    return {
        "environment": get_runtime_environment(),
        "deployment_profile": get_deployment_profile(),
    }


def _normalize_service_url(value: str, *, env_name: str) -> str:
    normalized = value.strip().rstrip("/")
    if not normalized:
        return ""
    if "://" not in normalized:
        raise RuntimeError(
            f"{env_name} must be configured as scheme://host[:port]"
        )
    return normalized


def get_datahub_api_url() -> str:
    configured = _normalize_service_url(
        os.environ.get("DATAHUB_API_URL", ""),
        env_name="DATAHUB_API_URL",
    )
    if configured:
        return configured
    if get_runtime_environment() in LOCAL_RUNTIME_ENVIRONMENTS:
        return DEFAULT_LOCAL_DATAHUB_API_URL
    raise RuntimeError(
        "DATAHUB_API_URL is required outside local development/test runtime. "
        + "Configure it as scheme://host[:port] without /api/v1 suffix."
    )


def get_datahub_timeout_seconds() -> float:
    raw_value = os.environ.get("DATAHUB_TIMEOUT_SECONDS", "30.0").strip()
    try:
        parsed = float(raw_value)
    except ValueError as exc:
        raise RuntimeError(
            f"Invalid DATAHUB_TIMEOUT_SECONDS value: {raw_value}"
        ) from exc
    if parsed <= 0:
        raise RuntimeError("DATAHUB_TIMEOUT_SECONDS must be greater than 0")
    return parsed


DATA_HOME = get_data_home()
ARTIFACTS_DIR = get_artifacts_dir()
STAGING_DIR = get_staging_dir()
LOGS_DIR = get_logs_dir()
LOG_FILE_SINK = get_log_file_sink_path("factor_lab")
LOG_JSON_FILE_SINK = get_log_file_sink_path("factor_lab", json_format=True)
LOG_ROTATION_MAX_BYTES = get_log_rotation_max_bytes()
LOG_ROTATION_BACKUP_COUNT = get_log_rotation_backup_count()
RUNTIME_STATE_PATH = get_runtime_state_path()
RUNTIME_SNAPSHOT_PATH = get_runtime_snapshot_path()
RUNTIME_DATABASE_PATH = get_runtime_database_path()

# Database
DATABASE_URL = os.environ.get(
    "DATABASE_URL", "sqlite:///./.local/factor-lab/factor_lab.db"
)

# API
API_PREFIX = "/api/v1"
API_VERSION = "1.0.0"

# MLflow
MLFLOW_TRACKING_URI = os.environ.get("MLFLOW_TRACKING_URI", "http://localhost:5000")
MLFLOW_EXPERIMENT_NAME = "factor_lab"

# Prefect
PREFECT_API_URL = os.environ.get("PREFECT_API_URL", "http://localhost:4200")

# Streamlit
STREAMLIT_PORT = int(os.environ.get("STREAMLIT_SERVER_PORT", "8501"))

# Auth scopes
SCOPES = {
    "read": "fl:read",
    "write": "fl:write",
    "governance": "fl:governance",
}

# Time format
ISO8601_FORMAT = "%Y-%m-%dT%H:%M:%SZ"

# Hash algorithm for deterministic IDs
HASH_ALGORITHM = "sha256"
