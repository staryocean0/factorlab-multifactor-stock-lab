"""Helpers for ONE proposed R3 experiment, not repository-wide permissions.

These routines check supplied timestamps, declared pair identities, and saved
file bytes. They do not verify external PIT, execute a selector or trainer,
certify a successful checkpoint reload, or make old data fresh OOS.
"""
from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any

SCHEMA = "factorlab.r3_time_isolated_design@1.0"
PAIR_FIELDS = (
    "seed", "clock", "recipe_digest", "source_digest", "environment_digest",
    "selection_digest", "normalizer_digest", "train_rows_digest",
    "prediction_rows_digest", "pre_dmd_state_digest", "batch_order_digest",
)
ARTIFACT_ROLES = frozenset({
    "checkpoint", "normalizer", "source_snapshot", "environment", "selection",
    "scores", "coordinates",
})


def strict_json(text: str) -> dict[str, Any]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key: {key}")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError(f"non-finite JSON: {value}")

    obj = json.loads(text, object_pairs_hook=unique, parse_constant=nonfinite)
    if not isinstance(obj, dict):
        raise ValueError("a JSON object is required")
    return obj


def _instant(value: str) -> datetime:
    if not isinstance(value, str) or "T" not in value:
        raise ValueError("explicit time and UTC offset required")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("naive time is not an availability timestamp")
    return result


def selection_mask(
    decisions: Sequence[str], maturities: Sequence[str | None],
    input_ends: Sequence[str | None], *, freeze_at: str, start_at: str,
) -> list[bool]:
    """Allow only known, mature prefix outcomes; never choose by outcome value.

    maturity is the maximum availability time of ALL outcome dependencies,
    not merely the decision's year. input_end is the latest dependency of the
    candidate signal. Unknown times are excluded; malformed times raise.
    Call before joining/aggregating any future-outcome table.
    """
    if not (len(decisions) == len(maturities) == len(input_ends)):
        raise ValueError("coordinate lengths differ")
    start, freeze = _instant(start_at), _instant(freeze_at)
    if start > freeze:
        raise ValueError("selection interval is reversed")
    keep = []
    for d, m, x in zip(decisions, maturities, input_ends, strict=True):
        decision = _instant(d)
        mature = _instant(m) if m is not None else None
        input_end = _instant(x) if x is not None else None
        keep.append(bool(
            start <= decision <= freeze and mature is not None
            and input_end is not None and input_end <= decision <= mature <= freeze
        ))
    return keep


def fit_history_mask(
    decisions: Sequence[str], input_ends: Sequence[str | None], *,
    fit_start_at: str, freeze_at: str,
) -> list[bool]:
    """History-only training eligibility; deliberately accepts NO future label.

    Earlier training features may use a rule selected at the common freeze;
    input_end describes the raw history, not a claim of historic fitted weights.
    """
    if len(decisions) != len(input_ends):
        raise ValueError("coordinate lengths differ")
    start, freeze = _instant(fit_start_at), _instant(freeze_at)
    if start > freeze:
        raise ValueError("fit interval is reversed")
    return [bool(start <= _instant(d) <= freeze and x is not None
                 and _instant(x) <= _instant(d))
            for d, x in zip(decisions, input_ends, strict=True)]


def validate_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a design description; success is NOT empirical acceptance."""
    errors: list[str] = []
    try:
        if plan.get("schema_id") != SCHEMA:
            errors.append("unsupported design schema")
        for key in ("real_fit_executed", "local_task_dispatched", "read_2026",
                    "fresh_oos", "production_authority", "historical_artifacts_mutable"):
            if plan.get(key) is not False:
                errors.append(f"design-only {key} must be boolean false")
        if plan.get("stage") != "design_only":
            errors.append("this checker describes design-only scope")
        t = plan["time"]
        freeze = _instant(t["freeze_at"])
        if not (date.fromisoformat(t["selection_start"]) <= freeze.date()
                < date.fromisoformat(t["evaluation_start"])
                <= date.fromisoformat(t["evaluation_end"]) < date(2026, 1, 1)):
            errors.append("selection/evaluation intervals not separated")
        if date.fromisoformat(t["evaluation_end"]) > date.fromisoformat(t["existing_input_calendar_end"]):
            errors.append("evaluation exceeds the declared existing input calendar")
        excluded = t["design_used_review_year_excluded_from_scoring"]
        if type(excluded) is not int or date.fromisoformat(t["evaluation_start"]).year <= excluded:
            errors.append("design-used review year cannot re-enter the primary score")
        if not (date.fromisoformat(t["fit_start"]) <= freeze.date()):
            errors.append("fit start is after freeze")
        if t.get("label_policy") != "all_dependencies_mature_by_freeze_before_aggregation":
            errors.append("label-maturity isolation is required for this experiment")
        if t.get("post_freeze_model_update") is not False:
            errors.append("the proposed fixed-origin model cannot refit during evaluation")
        if plan.get("arms") != ["F", "H"] or plan.get("reuse_old_scores_as_primary") is not False:
            errors.append("primary comparison requires new matched F/H, not old score reuse")
        if plan.get("shared_backend") is not True:
            errors.append("both arms must share one declared backend")
        seeds, clocks = plan["seeds"], plan["clocks"]
        if (not isinstance(seeds, list) or not seeds or any(type(s) is not int for s in seeds)
                or len(set(seeds)) != len(seeds)):
            errors.append("invalid seed inventory")
        if clocks != ["1430", "1445"]:
            errors.append("both declared clocks must be retained")
        budget = plan["future_budget"]
        if (type(budget.get("max_new_fits")) is not int
                or budget["max_new_fits"] != 2 * len(seeds) * len(clocks)
                or type(budget.get("max_cycles_per_fit")) is not int
                or budget["max_cycles_per_fit"] != 3
                or type(budget.get("max_total_cycles")) is not int
                or budget["max_total_cycles"] != budget["max_new_fits"] * 3):
            errors.append("fixed two-arm budget is inconsistent")
        if set(plan["required_artifact_roles"]) != ARTIFACT_ROLES:
            errors.append("persistence roles are incomplete")
    except (KeyError, TypeError, ValueError) as exc:
        errors.append(f"invalid design: {exc}")
    return {"design_consistency": "passed" if not errors else "failed",
            "errors": errors, "data_readiness": "not_evaluated",
            "market_experiment_executed": False, "runner_integration_verified": False,
            "PIT_certified": False, "fresh_oos": False, "production_authority": False}


def compare_pair_identity(left: Mapping[str, Any], right: Mapping[str, Any]) -> list[str]:
    """Check recorded equalities, not the truth of their runtime provenance."""
    issues = []
    if left.get("arm") != "F" or right.get("arm") != "H":
        issues.append("expected F then H")
    for key in PAIR_FIELDS:
        a, b = left.get(key), right.get(key)
        if a is None or b is None or type(a) is not type(b) or a != b:
            issues.append(f"missing/mismatched {key}")
        elif key.endswith("_digest"):
            if not isinstance(a, str) or not a.startswith("sha256:") or len(a) != 71:
                issues.append(f"invalid {key}")
            else:
                try:
                    int(a[7:], 16)
                except ValueError:
                    issues.append(f"invalid {key}")
        elif key == "seed" and type(a) is not int:
            issues.append("seed must be integer, not bool")
        elif key == "clock" and a not in {"1430", "1445"}:
            issues.append("unsupported clock")
    return issues


def _safe(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative or "\\" in relative or ":" in relative:
        raise ValueError("invalid relative artifact path")
    posix = PurePosixPath(relative)
    if posix.is_absolute() or ".." in posix.parts or relative in {".", ""}:
        raise ValueError("artifact path escapes run directory")
    path = root / relative
    if not path.resolve().is_relative_to(root):
        raise ValueError("artifact path escapes run directory")
    for part in [path, *path.parents]:
        if part == root:
            break
        if part.is_symlink():
            raise ValueError("artifact symlinks are not accepted")
    return path


def _file_identity(path: Path) -> dict[str, Any]:
    before = path.stat()
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    after = path.stat()
    if (before.st_ino, before.st_size, before.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
        raise ValueError("artifact changed while hashing")
    if not after.st_size:
        raise ValueError("empty artifact is not saved model evidence")
    return {"bytes": after.st_size, "sha256": "sha256:" + h.hexdigest()}


def artifact_inventory(root: Path, artifacts: Mapping[str, str]) -> dict[str, Any]:
    """Hash actual saved paths, including EVERY tensor below checkpoint dir.

    No file is written. This does not deserialize weights or execute inference.
    The caller must also perform the documented fresh-object reload probe.
    """
    root = root.resolve()
    if not ARTIFACT_ROLES <= set(artifacts):
        raise ValueError("missing required saved-artifact role")
    files: dict[str, Any] = {}
    for role, relative in sorted(artifacts.items()):
        path = _safe(root, relative)
        if not path.exists():
            raise ValueError(f"artifact missing: {role}")
        entries = sorted(path.rglob("*")) if path.is_dir() else [path]
        count = 0
        for entry in entries:
            key = entry.relative_to(root).as_posix()
            safe = _safe(root, key)
            if safe.is_file():
                if key in files:
                    raise ValueError("artifact roles overlap")
                files[key] = {"role": role, **_file_identity(safe)}
                count += 1
        if not count:
            raise ValueError(f"empty artifact role: {role}")
    return {"schema_id": "factorlab.r3_saved_artifact_inventory@1.0",
            "artifacts": dict(artifacts), "files": files,
            "reload_verified": False, "scientific_acceptance": False}


def verify_artifact_inventory(root: Path, saved: Mapping[str, Any]) -> list[str]:
    """Rehash bodies instead of trusting self-reported digest fields."""
    try:
        if saved.get("schema_id") != "factorlab.r3_saved_artifact_inventory@1.0":
            return ["unsupported artifact inventory schema"]
        current = artifact_inventory(root, saved["artifacts"])
        return [] if current["files"] == saved["files"] else ["saved artifact bytes/file-set changed"]
    except (OSError, KeyError, TypeError, ValueError) as exc:
        return [f"artifact verification failed: {exc}"]
