"""Version constants and utilities."""

from factor_lab.core.errors import ValidationError

# API Version
API_VERSION = "1.0.0"
API_VERSION_PREFIX = "/api/v1"

# Protocol Versions
EVAL_DAILY_VERSION = "1.0"
POLICY_PACK_P0_VERSION = "1.0"

# Schema Versions
FACTOR_FRAME_SCHEMA_VERSION = "1.0"
EVAL_METRICS_TABLE_SCHEMA_VERSION = "1.0"

# Data Format Versions
PARQUET_FORMAT_VERSION = "2.0"

# Feature flags for version compatibility
SUPPORTED_PROTOCOLS = ["eval_daily@1.0"]
SUPPORTED_POLICY_PACKS = ["policy_pack_p0_default@1.0"]


def validate_policy_pack(policy_pack: str) -> str:
    """Return a supported policy pack or fail explicitly."""
    if policy_pack in SUPPORTED_POLICY_PACKS:
        return policy_pack
    raise ValidationError(f"Unsupported policy_pack: {policy_pack}")


def parse_version(version_string: str) -> tuple[int, int, int]:
    """Parse version string to tuple."""
    raw_parts = version_string.split(".")[:3]
    padded_parts = raw_parts + ["0"] * (3 - len(raw_parts))
    major, minor, patch = (int(part) for part in padded_parts)
    return major, minor, patch


def is_protocol_compatible(protocol: str) -> bool:
    """Check if protocol version is supported."""
    return protocol in SUPPORTED_PROTOCOLS
