"""Live navigation and stable semantics, not a research-permission engine.

Historical byte contracts remain historical. This module never fits a model,
loads market panels, signs evidence, or turns a missing dependency into a
project-wide prohibition. Markdown checks cover inline/reference links and
ATX heading anchors; they are structural checks, not a proof of prose meaning.
"""
from __future__ import annotations

import json
import re
import subprocess
from collections import Counter
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from factor_lab.governance.reaka_foundation_contract import INVARIANTS

POINTER = "CURRENT.json"
SCHEMA = "factorlab.reaka_multifactor_current_manifest@1.4"
REQUIRED_ENTRIES = {
    "README.md", "AGENTS.md", "ai-readme.md", "docs/INDEX.md",
    "docs/user/cloud_execution_prompt.md",
    ".codex/skills/strategy-slice-rebuild/SKILL.md",
}
ROLES = ("semantics", "state", "workflow", "whitepaper", "audit")
LIST_ROLES = ("entrypoints", "implementation", "tests", "ci", "agent_interfaces")
SKIP_DIRS = {".git", ".venv", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}
INLINE_LINK = re.compile(r"!?\[[^\]\n]*\]\((<[^>]+>|[^\s)]+)(?:\s+[\"'][^\n]*?[\"'])?\)")
REF_DEF = re.compile(r"^\s{0,3}\[([^\]]+)\]:\s*(<[^>]+>|\S+)", re.M)
REF_LINK = re.compile(r"\[([^\]\n]+)\]\[([^\]\n]*)\]")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> dict[str, Any]:
    def invalid_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")
    result = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object,
                        parse_constant=invalid_constant)
    if not isinstance(result, dict):
        raise ValueError(f"JSON object required: {path.name}")
    return result


def safe_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"invalid repository path: {relative!r}")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or ":" in relative:
        raise ValueError(f"unsafe repository path: {relative}")
    resolved = (root / path).resolve()
    if not resolved.is_relative_to(root.resolve()):
        raise ValueError(f"escaping repository path: {relative}")
    return resolved


def _strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
        raise ValueError(f"nonempty string list required: {label}")
    if len(value) != len(set(value)):
        raise ValueError(f"duplicate paths in {label}")
    return value


def current_sources(manifest_path: str, manifest: dict[str, Any]) -> set[str]:
    paths = {POINTER, manifest_path}
    for role in ROLES:
        value = manifest.get(role)
        if not isinstance(value, str) or not value:
            raise ValueError(f"missing role: {role}")
        paths.add(value)
    for role in LIST_ROLES:
        paths.update(_strings(manifest.get(role), role))
    routes = manifest.get("reading_routes")
    if not isinstance(routes, dict) or "takeover" not in routes:
        raise ValueError("reading_routes.takeover required")
    for name, route in routes.items():
        paths.update(_strings(route, f"reading_routes.{name}"))
    components = manifest.get("components", {})
    if not isinstance(components, dict):
        raise ValueError("components must be an object")
    for name, files in components.items():
        paths.update(_strings(files, f"components.{name}"))
    return paths


def markdown_body(text: str) -> str:
    """Ignore fenced and inline code, retaining ordinary Markdown links."""
    lines: list[str] = []
    fence: str | None = None
    for line in text.splitlines():
        marker = re.match(r"^\s*(`{3,}|~{3,})", line)
        if marker:
            char = marker.group(1)[0]
            if fence is None:
                fence = char
            elif char == fence:
                fence = None
            continue
        if fence is None:
            lines.append(line)
    return re.sub(r"`[^`\n]*`", "", "\n".join(lines))


def heading_anchors(text: str) -> set[str]:
    seen: dict[str, int] = {}
    anchors: set[str] = set()
    for heading in re.findall(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", markdown_body(text), re.M):
        slug = re.sub(r"[^\w\- ]", "", heading.lower()).replace(" ", "-")
        count = seen.get(slug, 0)
        seen[slug] = count + 1
        anchors.add(slug if count == 0 else f"{slug}-{count}")
    anchors.update(re.findall(r"\bid=[\"']([^\"']+)[\"']", text))
    return anchors


def markdown_links(text: str) -> list[str]:
    text = markdown_body(text)
    links = [m.group(1).strip("<>") for m in INLINE_LINK.finditer(text)]
    definitions = {key.lower(): target.strip("<>") for key, target in REF_DEF.findall(text)}
    for title, ref in REF_LINK.findall(text):
        key = (ref or title).lower()
        # Without a matching definition [a][b] is plain text, often matrix
        # indexing in this repository, not a broken Markdown reference.
        if key in definitions:
            links.append(definitions[key])
    links.extend(definitions.values())
    return list(dict.fromkeys(links))


def link_issues(root: Path, source: str, known_paths: set[str] | None = None) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    file = safe_path(root, source)
    for link in markdown_links(file.read_text(encoding="utf-8")):
        parsed = urlsplit(link)
        if parsed.scheme in {"http", "https", "mailto"} or parsed.netloc:
            continue
        target = (file.parent / unquote(parsed.path)).resolve() if parsed.path else file
        reason = ""
        if parsed.scheme or not target.is_relative_to(root.resolve()):
            reason = "outside_repository"
        elif not target.exists():
            relative = target.relative_to(root.resolve()).as_posix()
            reason = "not_materialized" if known_paths and relative in known_paths else "missing_target"
        elif parsed.fragment and target.suffix.lower() == ".md":
            if unquote(parsed.fragment) not in heading_anchors(target.read_text(encoding="utf-8")):
                reason = "missing_heading_anchor"
        if reason:
            result.append({"source": source, "target": link, "reason": reason})
    return result


def assess_dependencies(root: Path, required: list[str]) -> dict[str, Any]:
    """File-availability precheck only. An empty dependency list is valid."""
    required = _strings(required, "required dependencies")
    missing = [path for path in required if not safe_path(root, path).is_file()]
    return {"required": required, "missing": missing,
            "availability": "blocked_for_this_task" if missing else "available",
            "pit_verified": False, "research_permission_granted": False}


def navigation_inventory(root: Path) -> dict[str, Any]:
    root = root.resolve()
    try:
        output = subprocess.run(["git", "ls-files", "-z"], cwd=root, capture_output=True,
                                check=True, timeout=30).stdout
        paths = set(output.decode().split("\0")) - {""}
        source = "git_index"
    except (OSError, subprocess.SubprocessError, UnicodeError):
        paths = {p.relative_to(root).as_posix() for p in root.rglob("*")
                 if p.is_file() and not SKIP_DIRS.intersection(p.relative_to(root).parts)}
        source = "filesystem_no_git_index"
    docs = sorted(p for p in paths if p.lower().endswith(".md") and safe_path(root, p).is_file())
    issues: list[dict[str, str]] = []
    referenced: set[str] = set()
    link_count = 0
    for path in docs:
        links = markdown_links(safe_path(root, path).read_text(encoding="utf-8"))
        link_count += len(links)
        issues.extend(link_issues(root, path, paths))
        for link in links:
            parsed = urlsplit(link)
            if parsed.scheme or parsed.netloc:
                continue
            target = (safe_path(root, path).parent / unquote(parsed.path)).resolve()
            if target.is_relative_to(root):
                referenced.add(target.relative_to(root).as_posix())
    return {"inventory_source": source, "tracked_paths": len(paths),
            "materialized_markdown_files": len(docs), "markdown_links": link_count,
            "issues": issues, "issue_reason_counts": dict(Counter(x["reason"] for x in issues)),
            "issues_by_source": dict(Counter(x["source"] for x in issues)),
            "unreferenced_markdown": sorted(set(docs) - referenced),
            "agent_instruction_files": sorted(p for p in paths if Path(p).name in {"AGENTS.md", "SKILL.md"}),
            "limitations": "Inline/reference Markdown and ATX anchors only; external targets and prose semantics not verified. Unreferenced historical documents are not automatically defects."}


def validate_infrastructure(root: Path, *, inventory: bool = False) -> dict[str, Any]:
    root = root.resolve()
    errors: list[str] = []
    warnings: list[str] = []
    paths: set[str] = set()
    manifest_path: str | None = None
    state: dict[str, Any] = {}
    try:
        pointer = read_json(root / POINTER)
        if pointer.get("schema_id") != "factorlab.repository_current@1.0":
            raise ValueError("invalid CURRENT.json schema")
        manifest_path = pointer.get("manifest")
        manifest = read_json(safe_path(root, manifest_path))
        if manifest.get("schema_id") != SCHEMA:
            raise ValueError("unsupported current manifest schema")
        paths = current_sources(manifest_path, manifest)
        if not REQUIRED_ENTRIES <= set(manifest["entrypoints"]):
            errors.append("required entry route missing")
        for path in sorted(paths):
            if not safe_path(root, path).is_file():
                errors.append(f"missing current source: {path}")
        for key in ("production_authority", "local_factorlab_pointer_authority"):
            if manifest.get(key) is not False:
                errors.append(f"authority must remain ungranted: {key}")
        for key in ("next_legal_action", "research_actions"):
            if key in manifest:
                errors.append(f"temporary global permission does not belong in current manifest: {key}")
        semantics = read_json(safe_path(root, manifest["semantics"]))
        if semantics.get("schema_id") != "factorlab.reaka_foundation_semantics@1.2":
            errors.append("invalid stable semantics schema")
        actual = semantics.get("invariants")
        if not isinstance(actual, dict) or set(actual) != set(INVARIANTS):
            errors.append("semantic invariant inventory drift")
        else:
            for key, value in INVARIANTS.items():
                if actual[key] is not value:
                    errors.append(f"semantic invariant drift: {key}")
        if "research_actions" in semantics or "allowed_actions" in semantics:
            errors.append("temporary execution permissions do not belong in stable semantics")
        state = read_json(safe_path(root, manifest["state"]))
        if state.get("schema_id") != "factorlab.research_state@1.0":
            errors.append("invalid state schema")
        for key in ("current_task", "as_of", "next_useful_action"):
            if not isinstance(state.get(key), str) or not state[key]:
                errors.append(f"state field required: {key}")
        if state.get("production_authority") is not False:
            errors.append("state cannot grant production authority")
        for section, field in (("r1", "receipt"), ("r2", "recovery_request"), ("historical_stage4", "receipt")):
            record = state.get(section)
            if not isinstance(record, dict) or not isinstance(record.get("status"), str):
                errors.append(f"state section required: {section}")
                continue
            target = record.get(field)
            if not safe_path(root, target).is_file():
                errors.append(f"missing evidence locator: {section}.{field}")
        for entry in manifest["entrypoints"] + manifest["agent_interfaces"]:
            path = safe_path(root, entry)
            if path.is_file() and "CURRENT.json" not in path.read_text(encoding="utf-8"):
                errors.append(f"entry does not route to CURRENT.json: {entry}")
        active_docs = set(manifest["entrypoints"] + manifest["agent_interfaces"]) | {manifest["workflow"], manifest["whitepaper"], manifest["audit"]}
        for path in sorted(active_docs):
            if path.endswith(".md") and safe_path(root, path).is_file():
                for issue in link_issues(root, path):
                    errors.append(f"current link {issue['reason']}: {path} -> {issue['target']}")
        warnings.append("Repository visibility and redistribution permission are not verified by an offline validator; a historical private_repository_required flag is not proof of privacy.")
    except (OSError, ValueError, TypeError, KeyError) as exc:
        errors.append(f"infrastructure unreadable: {type(exc).__name__}: {exc}")
    result: dict[str, Any] = {
        "schema_id": "factorlab.infrastructure_validation@1.4", "current_manifest": manifest_path,
        "infrastructure_consistency": "passed" if not errors else "failed",
        "checked_current_sources": len(paths), "errors": errors, "warnings": warnings,
        "current_task": state.get("current_task"),
        "dataset_readiness": "not_evaluated", "historical_reproduction": "not_evaluated",
        "scientific_acceptance": "not_evaluated", "production_authority": False,
        "research_permission": "not_granted_by_infrastructure_validation",
    }
    if inventory:
        try:
            result["navigation_inventory"] = navigation_inventory(root)
        except (OSError, ValueError, TypeError) as exc:
            result["errors"].append(f"navigation inventory failed: {exc}")
            result["infrastructure_consistency"] = "failed"
    return result
