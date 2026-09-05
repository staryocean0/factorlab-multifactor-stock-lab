"""Storage URI helpers for local artifacts and external dataset inputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast
from urllib.parse import unquote, urlparse

import requests

from factor_lab.core.settings import get_data_home


def _file_uri_to_path(storage_uri: str) -> Path:
    parsed = urlparse(storage_uri)
    path_text = unquote(parsed.path)
    if parsed.netloc:
        path_text = f"//{parsed.netloc}{path_text}"
    if len(path_text) >= 3 and path_text.startswith("/") and path_text[2] == ":":
        path_text = path_text.lstrip("/")
    return Path(path_text)


def is_http_storage_uri(storage_uri: str) -> bool:
    return storage_uri.startswith(("http://", "https://"))


def resolve_local_storage_path(
    storage_uri: str,
    *,
    base_dir: Path | None = None,
) -> Path:
    if storage_uri.startswith("file://"):
        return _file_uri_to_path(storage_uri)

    candidate = Path(storage_uri)
    if candidate.is_absolute():
        return candidate

    anchor = (base_dir or get_data_home()).resolve()
    return (anchor / candidate).resolve()


def read_json_storage_uri(
    storage_uri: str,
    *,
    allow_http: bool = False,
    base_dir: Path | None = None,
) -> object:
    if is_http_storage_uri(storage_uri):
        if not allow_http:
            raise ValueError(f"HTTP storage_uri is not allowed here: {storage_uri}")
        response = requests.get(storage_uri, timeout=30)
        response.raise_for_status()
        return cast(object, response.json())

    path = resolve_local_storage_path(storage_uri, base_dir=base_dir)
    return cast(object, json.loads(path.read_text(encoding="utf-8")))


def to_portable_storage_uri(path: Path) -> str:
    """Prefer a FACTOR_LAB_HOME-relative POSIX path for local artifacts."""
    resolved_path = path.resolve()
    data_home = get_data_home().resolve()
    try:
        return resolved_path.relative_to(data_home).as_posix()
    except ValueError:
        return str(resolved_path)


def describe_storage_uri(
    storage_uri: str,
    *,
    base_dir: Path | None = None,
) -> dict[str, str | None]:
    payload: dict[str, str | None] = {
        "storage_uri": storage_uri,
        "storage_file_uri": None,
        "storage_path": None,
    }
    if is_http_storage_uri(storage_uri):
        return payload

    path = resolve_local_storage_path(storage_uri, base_dir=base_dir).resolve()
    payload["storage_file_uri"] = path.as_uri()
    data_home = get_data_home().resolve()
    try:
        payload["storage_path"] = path.relative_to(data_home).as_posix()
    except ValueError:
        payload["storage_path"] = None
    return payload

