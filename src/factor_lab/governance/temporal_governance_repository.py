# pyright: reportAny=false, reportExplicitAny=false
# pyright: reportUnannotatedClassAttribute=false, reportUnusedCallResult=false
"""SQLite repository for @5 temporal governance state."""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable, Mapping, Sequence
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, cast

from factor_lab.core.settings import get_runtime_database_path
from factor_lab.governance.canonicalization import canonical_digest, canonical_json
from factor_lab.governance.cutover_transition_contract import (
    validate_strategy_usage_cutover_transition_receipt,
)
from factor_lab.governance.evidence_resolver import (
    validate_manual_authorization_decision,
)

Record = dict[str, object]


def _is_sha256_digest(value: object) -> bool:
    text = str(value).strip()
    return (
        len(text) == 71
        and text.startswith("sha256:")
        and all(character in "0123456789abcdef" for character in text[7:])
    )


class TemporalGovernanceRepository:
    """Small SQLite repository with the uniqueness invariants required by @5."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        self.db_path = (
            Path(db_path) if db_path is not None else get_runtime_database_path()
        )
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            self._initialize_schema(connection)

    def register_search_scope_run(
        self, _payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Reject raw authority writes; use the SearchScope registry service."""

        return {
            "status": "blocked",
            "blockers": ["strict_search_scope_registry_service_required"],
        }

    def _register_validated_search_scope_run(
        self, payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Persist a SearchScope row after service-level validation."""

        campaign_id = _required_str(payload, "campaign_id")
        run_id = _required_str(payload, "run_id")
        return self._insert_unique_payload(
            table="search_scope_runs",
            key_columns=("campaign_id", "run_id"),
            key_values=(campaign_id, run_id),
            payload=payload,
            conflict_blocker="search_scope_run_duplicate_checksum_mismatch",
        )

    def get_search_scope_runs(self, campaign_id: str) -> tuple[Record, ...]:
        return self._select_payloads(
            "SELECT payload_json FROM search_scope_runs WHERE campaign_id = ?",
            (campaign_id,),
        )

    def record_data_usage_event(
        self, _payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Reject raw authority writes; use the DataUsage registry service."""

        return {
            "status": "blocked",
            "blockers": ["strict_data_usage_registry_service_required"],
        }

    def _record_validated_data_usage_event(
        self, payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Persist a DataUsage row after service-level validation."""

        access_event_id = _required_str(payload, "access_event_id")
        return self._insert_unique_payload(
            table="data_usage_events",
            key_columns=("access_event_id",),
            key_values=(access_event_id,),
            payload=payload,
            conflict_blocker="data_usage_event_duplicate_checksum_mismatch",
        )

    def get_data_usage_events(
        self, access_event_ids: Iterable[str] | None = None
    ) -> tuple[Record, ...]:
        if access_event_ids is None:
            return self._select_payloads(
                "SELECT payload_json FROM data_usage_events", ()
            )
        ids = tuple(access_event_ids)
        if not ids:
            return ()
        placeholders = ",".join("?" for _ in ids)
        query = (
            "SELECT payload_json FROM data_usage_events "
            f"WHERE access_event_id IN ({placeholders})"
        )
        return self._select_payloads(query, ids)

    def register_frozen_candidate(
        self, payload: Mapping[str, object]
    ) -> dict[str, object]:
        strategy_family = _required_str(payload, "strategy_family")
        candidate_fingerprint = _required_str(payload, "candidate_fingerprint")
        return self._insert_unique_payload(
            table="frozen_candidates",
            key_columns=("strategy_family", "candidate_fingerprint"),
            key_values=(strategy_family, candidate_fingerprint),
            payload=payload,
            conflict_blocker="frozen_candidate_duplicate_checksum_mismatch",
        )

    def get_frozen_candidate(
        self, strategy_family: str, candidate_fingerprint: str
    ) -> Record | None:
        rows = self._select_payloads(
            """
            SELECT payload_json FROM frozen_candidates
            WHERE strategy_family = ? AND candidate_fingerprint = ?
            """,
            (strategy_family, candidate_fingerprint),
        )
        return rows[0] if rows else None

    def record_usage_campaign_event(
        self, _payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Reject raw authority writes; use the project registry service."""

        return {
            "status": "blocked",
            "blockers": ["strict_factor_usage_registry_service_required"],
        }

    def _record_validated_usage_campaign_event(
        self, payload: Mapping[str, object]
    ) -> dict[str, object]:
        campaign_id = _required_str(payload, "campaign_id")
        event_id = _required_str(payload, "event_id")
        return self._insert_unique_payload(
            table="usage_campaign_events",
            key_columns=("campaign_id", "event_id"),
            key_values=(campaign_id, event_id),
            payload=payload,
            conflict_blocker="usage_campaign_event_duplicate_checksum_mismatch",
        )

    def get_usage_campaign_events(self, campaign_id: str) -> tuple[Record, ...]:
        return self._select_payloads(
            """
            SELECT payload_json FROM usage_campaign_events
            WHERE campaign_id = ? ORDER BY created_at, rowid
            """,
            (campaign_id,),
        )

    def register_factor_usage_hypothesis(
        self, _payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Reject raw writes; callers must use the strict project registry."""

        return {
            "status": "blocked",
            "blockers": ["strict_factor_usage_registry_service_required"],
        }

    def _register_validated_factor_usage_hypothesis(
        self, payload: Mapping[str, object]
    ) -> dict[str, object]:
        campaign_id = _required_str(payload, "campaign_id")
        hypothesis_id = _required_str(payload, "usage_hypothesis_id")
        strategy_id = _required_str(payload, "strategy_id")
        cutover_blockers = self._strategy_v2_write_blockers(strategy_id)
        if cutover_blockers:
            return {"status": "blocked", "blockers": cutover_blockers}
        return self._insert_unique_payload(
            table="factor_usage_hypotheses",
            key_columns=("campaign_id", "hypothesis_id"),
            key_values=(campaign_id, hypothesis_id),
            payload=payload,
            conflict_blocker="factor_usage_hypothesis_duplicate_checksum_mismatch",
        )

    def get_factor_usage_hypothesis(
        self, campaign_id: str, hypothesis_id: str
    ) -> Record | None:
        rows = self._select_payloads(
            """
            SELECT payload_json FROM factor_usage_hypotheses
            WHERE campaign_id = ? AND hypothesis_id = ?
            """,
            (campaign_id, hypothesis_id),
        )
        return rows[0] if rows else None

    def register_factor_usage_trial(
        self, _payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Reject raw writes; callers must use the resolver-backed registry."""

        return {
            "status": "blocked",
            "blockers": ["strict_factor_usage_registry_service_required"],
        }

    def _register_validated_factor_usage_trial(
        self, payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Persist a trial after the project registry validated its contract."""

        campaign_id = _required_str(payload, "campaign_id")
        trial_id = _required_str(payload, "trial_id")
        strategy_id = _required_str(payload, "strategy_id")
        cutover_blockers = self._strategy_v2_write_blockers(strategy_id)
        if cutover_blockers:
            return {"status": "blocked", "blockers": cutover_blockers}
        return self._insert_unique_payload(
            table="factor_usage_trials",
            key_columns=("campaign_id", "trial_id"),
            key_values=(campaign_id, trial_id),
            payload=payload,
            conflict_blocker="factor_usage_trial_duplicate_checksum_mismatch",
        )

    def get_factor_usage_trials(self, campaign_id: str) -> tuple[Record, ...]:
        return self._select_payloads(
            "SELECT payload_json FROM factor_usage_trials WHERE campaign_id = ?",
            (campaign_id,),
        )

    def register_frozen_strategy_factor_binding(
        self, _payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Reject raw writes; the binding DAG must resolve before persistence."""

        return {
            "status": "blocked",
            "blockers": ["strict_factor_usage_registry_service_required"],
        }

    def _register_validated_frozen_strategy_factor_binding(
        self, payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Persist a binding after the project registry resolved its full DAG."""

        strategy_id = _required_str(payload, "strategy_id")
        binding_id = _required_str(payload, "binding_id")
        cutover_blockers = self._strategy_v2_write_blockers(strategy_id)
        if cutover_blockers:
            return {"status": "blocked", "blockers": cutover_blockers}
        return self._insert_unique_payload(
            table="frozen_strategy_factor_bindings",
            key_columns=("strategy_id", "binding_id"),
            key_values=(strategy_id, binding_id),
            payload=payload,
            conflict_blocker="frozen_strategy_factor_binding_duplicate_checksum_mismatch",
        )

    def get_frozen_strategy_factor_binding(
        self, strategy_id: str, binding_id: str
    ) -> Record | None:
        rows = self._select_payloads(
            """
            SELECT payload_json FROM frozen_strategy_factor_bindings
            WHERE strategy_id = ? AND binding_id = ?
            """,
            (strategy_id, binding_id),
        )
        return rows[0] if rows else None

    def get_frozen_strategy_factor_bindings(
        self, strategy_id: str
    ) -> tuple[Record, ...]:
        """List the authoritative immutable bindings for one strategy."""

        return self._select_payloads(
            """
            SELECT payload_json FROM frozen_strategy_factor_bindings
            WHERE strategy_id = ? ORDER BY binding_id
            """,
            (strategy_id,),
        )

    def register_strategy_integration_claim(
        self, _payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Reject raw writes; claims require a resolver-backed registration."""

        return {
            "status": "blocked",
            "blockers": ["strict_factor_usage_registry_service_required"],
        }

    def _register_validated_strategy_integration_claim(
        self, payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Persist a claim after the project registry resolved its full DAG."""

        strategy_id = _required_str(payload, "strategy_id")
        claim_id = _required_str(payload, "claim_id")
        cutover_blockers = self._strategy_v2_write_blockers(strategy_id)
        if cutover_blockers:
            return {"status": "blocked", "blockers": cutover_blockers}
        return self._insert_unique_payload(
            table="strategy_integration_claims",
            key_columns=("strategy_id", "claim_id"),
            key_values=(strategy_id, claim_id),
            payload=payload,
            conflict_blocker="strategy_integration_claim_duplicate_checksum_mismatch",
        )

    def get_strategy_integration_claim(
        self, strategy_id: str, claim_id: str
    ) -> Record | None:
        rows = self._select_payloads(
            """
            SELECT payload_json FROM strategy_integration_claims
            WHERE strategy_id = ? AND claim_id = ?
            """,
            (strategy_id, claim_id),
        )
        return rows[0] if rows else None

    def get_strategy_integration_claims(self, strategy_id: str) -> tuple[Record, ...]:
        """List the authoritative claim ledger for one strategy."""

        return self._select_payloads(
            """
            SELECT payload_json FROM strategy_integration_claims
            WHERE strategy_id = ? ORDER BY claim_id
            """,
            (strategy_id,),
        )

    def register_strategy_factor_usage_evidence(
        self, _payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Reject raw writes; use StrategyFactorUsageEvidenceRegistry."""

        return {
            "status": "blocked",
            "blockers": ["strict_factor_usage_registry_service_required"],
        }

    def _register_validated_strategy_factor_usage_evidence(
        self, payload: Mapping[str, object]
    ) -> dict[str, object]:
        """Persist a validated exact-usage or legacy-wrapper record."""

        evidence_id = _required_str(payload, "usage_evidence_id")
        if str(payload.get("evidence_mode", "")) == "exact_usage":
            strategy_id = _required_str(payload, "strategy_id")
            cutover_blockers = self._strategy_v2_write_blockers(strategy_id)
            if cutover_blockers:
                return {"status": "blocked", "blockers": cutover_blockers}
        return self._insert_unique_payload(
            table="strategy_factor_usage_evidence_v2",
            key_columns=("usage_evidence_id",),
            key_values=(evidence_id,),
            payload=payload,
            conflict_blocker="strategy_usage_evidence_duplicate_checksum_mismatch",
        )

    def get_strategy_factor_usage_evidence(
        self,
        *,
        strategy_id: str | None = None,
        usage_evidence_id: str | None = None,
    ) -> tuple[Record, ...]:
        where: list[str] = []
        parameters: list[object] = []
        if strategy_id is not None:
            where.append("json_extract(payload_json, '$.strategy_id') = ?")
            parameters.append(strategy_id)
        if usage_evidence_id is not None:
            where.append("usage_evidence_id = ?")
            parameters.append(usage_evidence_id)
        predicate = f" WHERE {' AND '.join(where)}" if where else ""
        return self._select_payloads(
            "SELECT payload_json FROM strategy_factor_usage_evidence_v2"
            + predicate
            + " ORDER BY usage_evidence_id",
            tuple(parameters),
        )

    def get_strategy_factor_usage_evidence_by_id(
        self, usage_evidence_id: str
    ) -> Record | None:
        records = self.get_strategy_factor_usage_evidence(
            usage_evidence_id=usage_evidence_id
        )
        return records[0] if records else None

    def _strategy_v2_write_blockers(self, strategy_id: str) -> list[str]:
        """Apply the authoritative per-strategy v2 write matrix.

        ``shadow_audit`` intentionally permits auditable v2 evidence, binding,
        review and claim records.  Execution and authorization remain separate
        required-only gates.  Only ``legacy_read`` closes this write lane.
        """

        mode = str(self.get_strategy_usage_cutover_snapshot(strategy_id)["mode"])
        if mode == "legacy_read":
            return ["strategy_usage_cutover_shadow_or_required_required"]
        if mode not in {"shadow_audit", "required"}:
            return ["strategy_usage_cutover_mode_invalid"]
        return []

    def record_usage_discovery_cutover(
        self, payload: Mapping[str, object]
    ) -> dict[str, object]:
        strategy_id = _required_str(payload, "strategy_id")
        change_id = _required_str(payload, "change_id")
        return self._insert_unique_payload(
            table="usage_discovery_cutovers",
            key_columns=("strategy_id", "change_id"),
            key_values=(strategy_id, change_id),
            payload=payload,
            conflict_blocker="usage_discovery_cutover_duplicate_checksum_mismatch",
        )

    def get_latest_usage_discovery_cutover(self, strategy_id: str) -> Record | None:
        rows = self._select_payloads(
            """
            SELECT payload_json FROM usage_discovery_cutovers
            WHERE strategy_id = ? ORDER BY created_at DESC, rowid DESC LIMIT 1
            """,
            (strategy_id,),
        )
        return rows[0] if rows else None

    def get_strategy_usage_cutover_snapshot(self, strategy_id: str) -> Record:
        """Return the CAS cutover state; unregistered strategies default legacy."""

        rows = self._select_payloads(
            """
            SELECT payload_json FROM strategy_usage_cutover_state
            WHERE strategy_id = ?
            """,
            (strategy_id,),
        )
        if rows:
            return rows[0]
        return {
            "strategy_id": strategy_id,
            "mode": "legacy_read",
            "version": 0,
            "required_history": False,
            "authorized_claim_ids": [],
        }

    def compare_and_swap_strategy_usage_cutover(
        self,
        receipt: Mapping[str, object],
        *,
        rich_cutover: Mapping[str, object] | None = None,
        rollback_snapshot_digest: str = "",
        evidence_catalog: Mapping[str, Mapping[str, object]] | None = None,
    ) -> dict[str, object]:
        """Append one transition receipt and atomically advance its snapshot.

        The receipt remains the stable append-only CAS contract.  Resolver-
        backed rich cutover identity and rollback snapshot digests are stored
        in the authoritative state row so later execution gates can re-check
        the exact context that passed the transition gate.
        """

        contract = validate_strategy_usage_cutover_transition_receipt(receipt)
        if contract["status"] != "valid":
            return {
                "status": "blocked",
                "blockers": list(_string_sequence(contract.get("blockers"))),
            }
        strategy_id = _required_str(receipt, "strategy_id")
        transition_id = _required_str(receipt, "transition_id")
        expected_state = _required_str(receipt, "expected_prior_state")
        next_state = _required_str(receipt, "next_state")
        _ = _required_str(receipt, "authorization_ref")
        allowed_transitions = {
            ("legacy_read", "shadow_audit"),
            ("shadow_audit", "required"),
            ("required", "shadow_audit"),
        }
        if (expected_state, next_state) not in allowed_transitions:
            return {
                "status": "blocked",
                "blockers": ["invalid_usage_discovery_cutover_transition"],
            }
        if (
            expected_state == "required"
            and next_state == "shadow_audit"
            and not str(receipt.get("rollback_snapshot_ref", "")).strip()
        ):
            return {"status": "blocked", "blockers": ["rollback_snapshot_ref_required"]}
        expected_version = int(str(receipt.get("expected_prior_version", "-1")))
        receipt_digest = _required_str(receipt, "receipt_digest")
        digest_payload = dict(receipt)
        digest_payload.pop("receipt_digest", None)
        if receipt_digest != canonical_digest(digest_payload):
            return {
                "status": "blocked",
                "blockers": ["cutover_transition_receipt_digest_mismatch"],
            }
        authorization_digest = str(receipt.get("authorization_digest", ""))
        rich_cutover_digest = str(receipt.get("rich_cutover_digest", ""))
        assurance_records = [
            dict(cast(Mapping[str, object], item))
            for item in _object_sequence(receipt.get("assurance_records"))
            if isinstance(item, Mapping)
        ]
        if next_state == "required":
            rich_blockers: list[str] = []
            if rich_cutover is None:
                rich_blockers.append("required_rich_cutover_context_required")
            elif str(rich_cutover.get("cutover_digest", "")) != rich_cutover_digest:
                rich_blockers.append("required_rich_cutover_digest_mismatch")
            else:
                semantic_cutover = dict(rich_cutover)
                semantic_cutover.pop("cutover_digest", None)
                semantic_cutover.pop("checksum", None)
                if rich_cutover_digest != canonical_digest(semantic_cutover):
                    rich_blockers.append("required_rich_cutover_integrity_invalid")
            if not _is_sha256_digest(authorization_digest):
                rich_blockers.append("required_authorization_digest_required")
            expected_assurances: dict[str, str] = {}
            if isinstance(rich_cutover, Mapping):
                for kind, field in (
                    ("evidence", "evidence_refs"),
                    ("test", "test_refs"),
                ):
                    for ref in _string_sequence(rich_cutover.get(field)):
                        expected_assurances[ref] = kind
            recorded_assurances: dict[str, tuple[str, str]] = {}
            for item in assurance_records:
                ref = str(item.get("ref", ""))
                digest = str(item.get("digest", ""))
                kind = str(item.get("kind", ""))
                if (
                    not ref
                    or ref in recorded_assurances
                    or not _is_sha256_digest(digest)
                ):
                    rich_blockers.append("required_assurance_ledger_invalid")
                    continue
                recorded_assurances[ref] = (digest, kind)
            if set(recorded_assurances) != set(expected_assurances) or any(
                recorded_assurances[ref][1] != kind
                for ref, kind in expected_assurances.items()
                if ref in recorded_assurances
            ):
                rich_blockers.append("required_assurance_ledger_mismatch")
            if rich_blockers:
                return {"status": "blocked", "blockers": sorted(set(rich_blockers))}
            # The public repository boundary re-runs resolver-backed checks;
            # callers cannot bypass the transition service by fabricating a
            # syntactically valid receipt and invoking CAS directly.
            if evidence_catalog is None or rich_cutover is None:
                return {
                    "status": "blocked",
                    "blockers": ["required_resolver_context_required"],
                }
            repository_blockers = _required_public_cas_blockers(
                receipt,
                rich_cutover=rich_cutover,
                expected_version=expected_version + 1,
                expected_assurances=expected_assurances,
                recorded_assurances=recorded_assurances,
                catalog=evidence_catalog,
            )
            if repository_blockers:
                return {
                    "status": "blocked",
                    "blockers": sorted(set(repository_blockers)),
                }
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT mode, version, payload_json FROM strategy_usage_cutover_state
                WHERE strategy_id = ?
                """,
                (strategy_id,),
            ).fetchone()
            current_state = str(row["mode"]) if row else "legacy_read"
            current_version = int(row["version"]) if row else 0
            if current_state != expected_state or current_version != expected_version:
                return {
                    "status": "blocked",
                    "blockers": ["usage_cutover_stale_compare_and_swap"],
                    "current_state": current_state,
                    "current_version": current_version,
                }
            prior_payload = (
                cast(Record, json.loads(str(row["payload_json"]))) if row else {}
            )
            prior_ids = set(_string_sequence(prior_payload.get("authorized_claim_ids")))
            next_ids = set(_string_sequence(receipt.get("authorized_claim_ids")))
            if not prior_ids.issubset(next_ids):
                return {
                    "status": "blocked",
                    "blockers": ["authorized_claim_ids_cannot_be_removed"],
                }
            if expected_state == "required" and next_state == "shadow_audit":
                rollback_blockers = _rollback_public_cas_blockers(
                    receipt,
                    authoritative_snapshot=prior_payload,
                    rollback_snapshot_digest=rollback_snapshot_digest,
                    catalog=evidence_catalog,
                )
                if rollback_blockers:
                    return {
                        "status": "blocked",
                        "blockers": sorted(set(rollback_blockers)),
                    }
            try:
                connection.execute(
                    """
                    INSERT INTO strategy_usage_cutover_transitions (
                        strategy_id, transition_id, prior_version, next_version,
                        payload_json, checksum
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        strategy_id,
                        transition_id,
                        current_version,
                        current_version + 1,
                        canonical_json(receipt),
                        receipt_digest,
                    ),
                )
            except sqlite3.IntegrityError:
                return {
                    "status": "blocked",
                    "blockers": ["usage_cutover_transition_id_already_exists"],
                }
            if rich_cutover is not None:
                connection.execute(
                    """
                    INSERT INTO strategy_usage_cutover_artifacts (
                        strategy_id, version, transition_id, payload_json, checksum
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        strategy_id,
                        current_version + 1,
                        transition_id,
                        canonical_json(rich_cutover),
                        _required_str(rich_cutover, "cutover_digest"),
                    ),
                )
            snapshot: Record = {
                "strategy_id": strategy_id,
                "mode": next_state,
                "version": current_version + 1,
                "required_history": receipt.get("required_history") is True,
                "authorized_claim_ids": sorted(next_ids),
                "latest_transition_id": transition_id,
                "latest_transition_digest": receipt_digest,
                "authorization_ref": str(receipt.get("authorization_ref", "")),
                "authorization_digest": authorization_digest,
                "assurance_records": assurance_records,
            }
            prior_rich_cutover = prior_payload.get("rich_cutover")
            if rich_cutover is not None:
                snapshot["rich_cutover"] = dict(rich_cutover)
                snapshot["rich_cutover_digest"] = str(
                    rich_cutover.get("cutover_digest", "")
                )
                if next_state == "required":
                    snapshot["required_authorization_ref"] = str(
                        receipt.get("authorization_ref", "")
                    )
                    snapshot["required_authorization_digest"] = authorization_digest
                    snapshot["required_assurance_records"] = assurance_records
                    snapshot["required_cutover_version"] = current_version + 1
                    snapshot["required_transition_digest"] = receipt_digest
            elif isinstance(prior_rich_cutover, Mapping):
                snapshot["rich_cutover"] = dict(
                    cast(Mapping[str, object], prior_rich_cutover)
                )
                snapshot["rich_cutover_digest"] = str(
                    prior_payload.get("rich_cutover_digest", "")
                )
                for field in (
                    "required_authorization_ref",
                    "required_authorization_digest",
                    "required_assurance_records",
                    "required_cutover_version",
                    "required_transition_digest",
                ):
                    if field in prior_payload:
                        snapshot[field] = prior_payload[field]
            if rollback_snapshot_digest:
                snapshot["rollback_snapshot_ref"] = str(
                    receipt.get("rollback_snapshot_ref", "")
                )
                snapshot["rollback_snapshot_digest"] = rollback_snapshot_digest
            elif prior_payload.get("rollback_snapshot_ref"):
                snapshot["rollback_snapshot_ref"] = str(
                    prior_payload.get("rollback_snapshot_ref", "")
                )
                snapshot["rollback_snapshot_digest"] = str(
                    prior_payload.get("rollback_snapshot_digest", "")
                )
            connection.execute(
                """
                INSERT INTO strategy_usage_cutover_state (
                    strategy_id, mode, version, payload_json, checksum
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(strategy_id) DO UPDATE SET
                    mode = excluded.mode,
                    version = excluded.version,
                    payload_json = excluded.payload_json,
                    checksum = excluded.checksum,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    strategy_id,
                    next_state,
                    current_version + 1,
                    canonical_json(snapshot),
                    canonical_digest(snapshot),
                ),
            )
        return {
            "status": "transitioned",
            "strategy_id": strategy_id,
            "mode": next_state,
            "version": current_version + 1,
            "receipt_digest": receipt_digest,
            "blockers": [],
        }

    def get_strategy_usage_cutover_transitions(
        self, strategy_id: str
    ) -> tuple[Record, ...]:
        return self._select_payloads(
            """
            SELECT payload_json FROM strategy_usage_cutover_transitions
            WHERE strategy_id = ? ORDER BY next_version
            """,
            (strategy_id,),
        )

    def get_strategy_usage_cutover_artifacts(
        self, strategy_id: str
    ) -> tuple[Record, ...]:
        """Return immutable rich cutover rows committed by the strategy CAS."""

        return self._select_payloads(
            """
            SELECT payload_json FROM strategy_usage_cutover_artifacts
            WHERE strategy_id = ? ORDER BY version
            """,
            (strategy_id,),
        )

    def get_lockbox_state(
        self, strategy_family: str, candidate_fingerprint: str
    ) -> str | None:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT state FROM lockbox_state
                WHERE strategy_family = ? AND candidate_fingerprint = ?
                """,
                (strategy_family, candidate_fingerprint),
            ).fetchone()
        return str(row["state"]) if row else None

    def set_lockbox_state(
        self,
        *,
        strategy_family: str,
        candidate_fingerprint: str,
        state: str,
        payload: Mapping[str, object],
    ) -> dict[str, object]:
        checksum = canonical_digest(payload)
        payload_json = canonical_json(payload)
        with self._transaction() as connection:
            connection.execute(
                """
                INSERT INTO lockbox_state (
                    strategy_family, candidate_fingerprint, state,
                    payload_json, checksum
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(strategy_family, candidate_fingerprint)
                DO UPDATE SET
                    state = excluded.state,
                    payload_json = excluded.payload_json,
                    checksum = excluded.checksum,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    strategy_family,
                    candidate_fingerprint,
                    state,
                    payload_json,
                    checksum,
                ),
            )
        return {
            "status": "recorded",
            "state": state,
            "checksum": checksum,
            "strategy_family": strategy_family,
            "candidate_fingerprint": candidate_fingerprint,
        }

    def open_lockbox_once(
        self, payload: Mapping[str, object], *, required_current_state: str
    ) -> dict[str, object]:
        """Atomically insert the one-shot open event and move state to opened."""

        strategy_family = _required_str(payload, "strategy_family")
        candidate_fingerprint = _required_str(payload, "candidate_fingerprint")
        checksum = canonical_digest(payload)
        payload_json = canonical_json(payload)
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT state FROM lockbox_state
                WHERE strategy_family = ? AND candidate_fingerprint = ?
                """,
                (strategy_family, candidate_fingerprint),
            ).fetchone()
            current_state = str(row["state"]) if row else ""
            if current_state != required_current_state:
                return {
                    "status": "blocked",
                    "blockers": ["lockbox_required_state_missing"],
                    "current_state": current_state,
                }
            try:
                connection.execute(
                    """
                    INSERT INTO lockbox_open_events (
                        strategy_family, candidate_fingerprint, payload_json, checksum
                    )
                    VALUES (?, ?, ?, ?)
                    """,
                    (strategy_family, candidate_fingerprint, payload_json, checksum),
                )
            except sqlite3.IntegrityError:
                return {
                    "status": "blocked",
                    "blockers": ["lockbox_already_opened"],
                    "current_state": current_state,
                }
            connection.execute(
                """
                UPDATE lockbox_state
                SET state = 'LOCKBOX_OPENED',
                    payload_json = ?,
                    checksum = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE strategy_family = ? AND candidate_fingerprint = ?
                """,
                (payload_json, checksum, strategy_family, candidate_fingerprint),
            )
        return {
            "status": "opened",
            "state": "LOCKBOX_OPENED",
            "checksum": checksum,
            "strategy_family": strategy_family,
            "candidate_fingerprint": candidate_fingerprint,
        }

    def record_lockbox_access(self, payload: Mapping[str, object]) -> dict[str, object]:
        receipt_id = _required_str(payload, "receipt_id")
        return self._insert_unique_payload(
            table="lockbox_access_receipts",
            key_columns=("receipt_id",),
            key_values=(receipt_id,),
            payload=payload,
            conflict_blocker="lockbox_access_receipt_duplicate_checksum_mismatch",
        )

    def consume_lockbox_access_once(
        self,
        receipt: Mapping[str, object],
        *,
        data_usage_event: Mapping[str, object],
        target_state: str = "LOCKBOX_SEALED_REVIEW_REQUIRED",
    ) -> dict[str, object]:
        """Atomically consume one opened lockbox and record its access state.

        Single-dataset legacy callers keep sealing on access. A complete atomic
        data bundle may instead enter ``LOCKBOX_DATA_ACCESSED`` so the scientific
        calculation can finish exactly once before recording its terminal verdict.
        """

        receipt_id = _required_str(receipt, "receipt_id")
        strategy_family = _required_str(receipt, "strategy_family")
        candidate_fingerprint = _required_str(receipt, "candidate_fingerprint")
        if data_usage_event.get("access_event_id") != receipt_id:
            return {
                "status": "blocked",
                "blockers": ["lockbox_data_usage_event_id_mismatch"],
            }
        if data_usage_event.get("candidate_fingerprint") != candidate_fingerprint:
            return {
                "status": "blocked",
                "blockers": ["lockbox_data_usage_candidate_fingerprint_mismatch"],
            }
        if target_state not in {
            "LOCKBOX_DATA_ACCESSED",
            "LOCKBOX_SEALED_REVIEW_REQUIRED",
        }:
            return {
                "status": "blocked",
                "blockers": ["lockbox_access_target_state_invalid"],
            }
        receipt_checksum = canonical_digest(receipt)
        receipt_json = canonical_json(receipt)
        usage_checksum = canonical_digest(data_usage_event)
        usage_json = canonical_json(data_usage_event)
        sealed_payload = {
            "artifact_type": "lockbox_consumption_transition",
            "strategy_family": strategy_family,
            "candidate_fingerprint": candidate_fingerprint,
            "receipt_id": receipt_id,
            "from_state": "LOCKBOX_OPENED",
            "to_state": target_state,
        }
        sealed_checksum = canonical_digest(sealed_payload)
        sealed_json = canonical_json(sealed_payload)
        with self._transaction() as connection:
            row = connection.execute(
                """
                SELECT state FROM lockbox_state
                WHERE strategy_family = ? AND candidate_fingerprint = ?
                """,
                (strategy_family, candidate_fingerprint),
            ).fetchone()
            current_state = str(row["state"]) if row else ""
            if current_state != "LOCKBOX_OPENED":
                return {
                    "status": "blocked",
                    "blockers": ["lockbox_already_consumed_or_not_open"],
                    "current_state": current_state,
                }
            try:
                connection.execute(
                    """
                    INSERT INTO lockbox_consumptions (
                        strategy_family, candidate_fingerprint, receipt_id,
                        payload_json, checksum
                    ) VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        strategy_family,
                        candidate_fingerprint,
                        receipt_id,
                        receipt_json,
                        receipt_checksum,
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO data_usage_events (
                        access_event_id, payload_json, checksum
                    ) VALUES (?, ?, ?)
                    """,
                    (receipt_id, usage_json, usage_checksum),
                )
                connection.execute(
                    """
                    INSERT INTO lockbox_access_receipts (
                        receipt_id, payload_json, checksum
                    ) VALUES (?, ?, ?)
                    """,
                    (receipt_id, receipt_json, receipt_checksum),
                )
            except sqlite3.IntegrityError:
                return {
                    "status": "blocked",
                    "blockers": ["lockbox_access_already_consumed"],
                    "current_state": current_state,
                }
            connection.execute(
                """
                UPDATE lockbox_state
                SET state = ?,
                    payload_json = ?, checksum = ?,
                    updated_at = CURRENT_TIMESTAMP
                WHERE strategy_family = ? AND candidate_fingerprint = ?
                """,
                (
                    target_state,
                    sealed_json,
                    sealed_checksum,
                    strategy_family,
                    candidate_fingerprint,
                ),
            )
        return {
            "status": "registered",
            "state": target_state,
            "checksum": receipt_checksum,
            "blockers": [],
        }

    def get_lockbox_access_receipt(self, receipt_id: str) -> Record | None:
        rows = self._select_payloads(
            "SELECT payload_json FROM lockbox_access_receipts WHERE receipt_id = ?",
            (receipt_id,),
        )
        return rows[0] if rows else None

    def _insert_unique_payload(
        self,
        *,
        table: str,
        key_columns: tuple[str, ...],
        key_values: tuple[str, ...],
        payload: Mapping[str, object],
        conflict_blocker: str,
    ) -> dict[str, object]:
        checksum = canonical_digest(payload)
        payload_json = canonical_json(payload)
        columns = (*key_columns, "payload_json", "checksum")
        placeholders = ",".join("?" for _ in columns)
        values = (*key_values, payload_json, checksum)
        with self._transaction() as connection:
            try:
                joined_columns = ",".join(columns)
                connection.execute(
                    f"INSERT INTO {table} ({joined_columns}) VALUES ({placeholders})",
                    values,
                )
            except sqlite3.IntegrityError:
                where_clause = " AND ".join(f"{column} = ?" for column in key_columns)
                row = connection.execute(
                    f"SELECT checksum FROM {table} WHERE {where_clause}", key_values
                ).fetchone()
                existing_checksum = str(row["checksum"]) if row else ""
                if existing_checksum == checksum:
                    return {
                        "status": "idempotent",
                        "checksum": checksum,
                        "blockers": [],
                    }
                return {
                    "status": "blocked",
                    "checksum": checksum,
                    "existing_checksum": existing_checksum,
                    "blockers": [conflict_blocker],
                }
        return {"status": "registered", "checksum": checksum, "blockers": []}

    def _select_payloads(
        self, query: str, parameters: tuple[object, ...]
    ) -> tuple[Record, ...]:
        with self._connect() as connection:
            rows = connection.execute(query, parameters).fetchall()
        payloads: list[Record] = []
        for row in rows:
            loaded = json.loads(str(row["payload_json"]))
            if isinstance(loaded, dict):
                payloads.append(cast(Record, loaded))
        return tuple(payloads)

    @contextmanager
    def _transaction(self) -> Any:
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_schema(self, connection: sqlite3.Connection) -> None:
        for statement in _SCHEMA_STATEMENTS:
            connection.execute(statement)
        connection.commit()


_SCHEMA_STATEMENTS: Final[tuple[str, ...]] = (
    """
    CREATE TABLE IF NOT EXISTS search_scope_runs (
        campaign_id TEXT NOT NULL,
        run_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(campaign_id, run_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS data_usage_events (
        access_event_id TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS frozen_candidates (
        strategy_family TEXT NOT NULL,
        candidate_fingerprint TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(strategy_family, candidate_fingerprint)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS usage_campaign_events (
        campaign_id TEXT NOT NULL,
        event_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(campaign_id, event_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS factor_usage_hypotheses (
        campaign_id TEXT NOT NULL,
        hypothesis_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(campaign_id, hypothesis_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS factor_usage_trials (
        campaign_id TEXT NOT NULL,
        trial_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(campaign_id, trial_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS frozen_strategy_factor_bindings (
        strategy_id TEXT NOT NULL,
        binding_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(strategy_id, binding_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_integration_claims (
        strategy_id TEXT NOT NULL,
        claim_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(strategy_id, claim_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_factor_usage_evidence_v2 (
        usage_evidence_id TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS usage_discovery_cutovers (
        strategy_id TEXT NOT NULL,
        change_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(strategy_id, change_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_usage_cutover_state (
        strategy_id TEXT PRIMARY KEY,
        mode TEXT NOT NULL,
        version INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_usage_cutover_transitions (
        strategy_id TEXT NOT NULL,
        transition_id TEXT NOT NULL,
        prior_version INTEGER NOT NULL,
        next_version INTEGER NOT NULL,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(strategy_id, transition_id),
        UNIQUE(strategy_id, next_version)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS strategy_usage_cutover_artifacts (
        strategy_id TEXT NOT NULL,
        version INTEGER NOT NULL,
        transition_id TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(strategy_id, version),
        UNIQUE(strategy_id, transition_id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lockbox_state (
        strategy_family TEXT NOT NULL,
        candidate_fingerprint TEXT NOT NULL,
        state TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(strategy_family, candidate_fingerprint)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lockbox_open_events (
        strategy_family TEXT NOT NULL,
        candidate_fingerprint TEXT NOT NULL,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        opened_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(strategy_family, candidate_fingerprint)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lockbox_access_receipts (
        receipt_id TEXT PRIMARY KEY,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lockbox_consumptions (
        strategy_family TEXT NOT NULL,
        candidate_fingerprint TEXT NOT NULL,
        receipt_id TEXT NOT NULL UNIQUE,
        payload_json TEXT NOT NULL,
        checksum TEXT NOT NULL,
        consumed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(strategy_family, candidate_fingerprint)
    )
    """,
)


def _required_str(payload: Mapping[str, object], key: str) -> str:
    value = str(payload.get(key, "")).strip()
    if not value:
        raise ValueError(f"{key} is required")
    return value


def _string_sequence(value: object) -> tuple[str, ...]:
    if not isinstance(value, Iterable) or isinstance(value, (str, bytes, Mapping)):
        return ()
    return tuple(str(item) for item in value)


def _object_sequence(value: object) -> tuple[object, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(value)


def _catalog_artifact_blockers(
    ref: str,
    *,
    catalog: Mapping[str, Mapping[str, object]],
    expected_artifact_type: str,
    expected_digest: str,
) -> tuple[list[str], Mapping[str, object]]:
    payload = catalog.get(ref)
    if payload is None:
        return ["artifact_not_resolved"], {}
    blockers: list[str] = []
    if str(payload.get("artifact_type", "")) != expected_artifact_type:
        blockers.append("artifact_type_mismatch")
    recorded_digest = str(payload.get("checksum") or payload.get("sha256") or "")
    semantic_payload = dict(payload)
    semantic_payload.pop("checksum", None)
    semantic_payload.pop("sha256", None)
    semantic_payload.pop("computed_checksum", None)
    recomputed_digest = canonical_digest(semantic_payload)
    digest_verified = bool(recorded_digest and recorded_digest == recomputed_digest)
    if recorded_digest and not digest_verified:
        # Rich governance receipts expose one semantic digest both through a
        # typed field (for example ``receipt_digest``) and ``checksum``.  The
        # alias is valid only when removing that exact typed field reproduces
        # the recorded digest; neither field is trusted without recomputation.
        for field, value in tuple(semantic_payload.items()):
            if (field.endswith("_digest") or field.endswith("_checksum")) and str(
                value
            ) == recorded_digest:
                typed_payload = dict(semantic_payload)
                typed_payload.pop(field, None)
                if recorded_digest == canonical_digest(typed_payload):
                    digest_verified = True
                    break
    if not digest_verified:
        blockers.append("artifact_digest_mismatch")
    if recorded_digest != expected_digest:
        blockers.append("artifact_expected_digest_mismatch")
    return blockers, payload


def _required_public_cas_blockers(
    receipt: Mapping[str, object],
    *,
    rich_cutover: Mapping[str, object],
    expected_version: int,
    expected_assurances: Mapping[str, str],
    recorded_assurances: Mapping[str, tuple[str, str]],
    catalog: Mapping[str, Mapping[str, object]],
) -> list[str]:
    """Revalidate promotion authority at the public persistence boundary."""

    blockers: list[str] = []
    strategy_id = str(receipt.get("strategy_id", ""))
    owner = str(rich_cutover.get("owner", ""))
    for field, expected in (
        ("artifact_type", "strategy_usage_cutover"),
        ("schema_id", "strategy_usage_cutover@1.0"),
        ("canonicalization_version", "factorlab_canonical_json@1"),
    ):
        if str(rich_cutover.get(field, "")) != expected:
            blockers.append(f"required_rich_cutover_{field}_mismatch")
    for field, expected in (
        ("strategy_id", strategy_id),
        ("mode", "required"),
        ("version", expected_version),
    ):
        if str(rich_cutover.get(field, "")) != str(expected):
            blockers.append(f"required_rich_cutover_{field}_mismatch")
    if not owner:
        blockers.append("required_rich_cutover_owner_required")
    for field in (
        "strategy_family_id",
        "change_id",
        "action_space_ref",
        "action_space_version",
        "adapter_ref",
        "baseline_artifact_ref",
        "effective_at",
        "reason",
    ):
        if not str(rich_cutover.get(field, "")).strip():
            blockers.append(f"required_rich_cutover_{field}_required")
    for field in (
        "action_space_digest",
        "adapter_digest",
        "baseline_digest",
    ):
        if not _is_sha256_digest(rich_cutover.get(field)):
            blockers.append(f"required_rich_cutover_{field}_invalid")
    if str(rich_cutover.get("rollback_target", "")) != "shadow_audit":
        blockers.append("required_rich_cutover_rollback_target_invalid")
    if not _string_sequence(rich_cutover.get("evidence_refs")):
        blockers.append("required_rich_cutover_evidence_refs_required")
    if not _string_sequence(rich_cutover.get("test_refs")):
        blockers.append("required_rich_cutover_test_refs_required")
    if rich_cutover.get("required_history") is not True:
        blockers.append("required_rich_cutover_required_history_must_be_true")
    if rich_cutover.get("legacy_new_promotion_allowed") is not False:
        blockers.append("required_rich_cutover_legacy_promotion_must_be_closed")
    if rich_cutover.get("production_authority") is not False:
        blockers.append("required_rich_cutover_cannot_grant_production_authority")
    labels = rich_cutover.get("field_labels_zh")
    if not isinstance(labels, Mapping) or not labels:
        blockers.append("required_rich_cutover_field_labels_zh_required")
    if set(_string_sequence(rich_cutover.get("authorized_claim_ids"))) != set(
        _string_sequence(receipt.get("authorized_claim_ids"))
    ):
        blockers.append("required_rich_cutover_authorized_claim_ids_mismatch")

    resolved_dependencies: dict[str, Mapping[str, object]] = {}
    for label, ref_field, digest_field, artifact_type in (
        (
            "action_space",
            "action_space_ref",
            "action_space_digest",
            "strategy_factor_action_space",
        ),
        (
            "adapter",
            "adapter_ref",
            "adapter_digest",
            "strategy_factor_execution_adapter",
        ),
        (
            "baseline",
            "baseline_artifact_ref",
            "baseline_digest",
            "strategy_baseline",
        ),
    ):
        dependency_blockers, dependency = _catalog_artifact_blockers(
            str(rich_cutover.get(ref_field, "")),
            catalog=catalog,
            expected_artifact_type=artifact_type,
            expected_digest=str(rich_cutover.get(digest_field, "")),
        )
        blockers.extend(f"required_{label}:{item}" for item in dependency_blockers)
        resolved_dependencies[label] = dependency

    action_space = resolved_dependencies.get("action_space", {})
    adapter = resolved_dependencies.get("adapter", {})
    baseline = resolved_dependencies.get("baseline", {})

    # Import at the call boundary because factor_usage_discovery owns the
    # action-space machine contract and imports this module's canonical digest
    # helper.  The public CAS must execute the same validator as the service;
    # duplicating a looser action-space subset here would reopen the direct-CAS
    # bypass this boundary is meant to close.
    from factor_lab.governance.factor_usage_discovery import (
        validate_strategy_factor_action_space,
    )

    action_space_validation = validate_strategy_factor_action_space(action_space)
    blockers.extend(
        f"required_action_space:contract:{item}"
        for item in _string_sequence(action_space_validation.get("blockers"))
    )
    blockers.extend(
        f"required_action_space:contract:{item}"
        for item in _complete_dependency_contract_blockers(
            action_space,
            required_fields=(
                "action_space_id",
                "action_space_version",
                "strategy_family_id",
                "strategy_id",
                "baseline_artifact_ref",
                "baseline_digest",
                "action_ids",
                "input_contract_refs",
                "output_contract_refs",
                "temporal_semantics_ref",
                "cost_fill_semantics_ref",
                "forbidden_actions",
                "extension_policy",
                "owner_ref",
                "field_labels_zh",
                "canonical_digest",
            ),
            digest_fields=("baseline_digest", "canonical_digest"),
            sequence_fields=(
                "action_ids",
                "input_contract_refs",
                "output_contract_refs",
                "forbidden_actions",
            ),
            allow_empty_sequences=("forbidden_actions",),
            unique_sequence_fields=("action_ids",),
            mapping_fields=("extension_policy", "field_labels_zh"),
        )
    )
    blockers.extend(
        f"required_adapter:contract:{item}"
        for item in _complete_dependency_contract_blockers(
            adapter,
            required_fields=(
                "strategy_family_id",
                "strategy_id",
                "action_space_ref",
                "action_space_digest",
                "action_space_version",
                "baseline_artifact_ref",
                "baseline_digest",
                "supported_action_ids",
                "field_labels_zh",
                "checksum",
            ),
            digest_fields=("action_space_digest", "baseline_digest", "checksum"),
            sequence_fields=("supported_action_ids",),
            unique_sequence_fields=("supported_action_ids",),
            mapping_fields=("field_labels_zh",),
        )
    )
    blockers.extend(
        f"required_baseline:contract:{item}"
        for item in _complete_dependency_contract_blockers(
            baseline,
            required_fields=(
                "strategy_family_id",
                "strategy_id",
                "action_space_ref",
                "action_space_version",
                "field_labels_zh",
                "checksum",
            ),
            digest_fields=("checksum",),
            mapping_fields=("field_labels_zh",),
        )
    )
    for label, payload, schema_id in (
        ("action_space", action_space, "strategy_factor_action_space@1.0"),
        ("adapter", adapter, "strategy_factor_execution_adapter@1.0"),
        ("baseline", baseline, "strategy_baseline@1.0"),
    ):
        if str(payload.get("schema_id", "")) != schema_id:
            blockers.append(f"required_{label}:schema_id_mismatch")
        if str(payload.get("canonicalization_version", "")) != (
            "factorlab_canonical_json@1"
        ):
            blockers.append(f"required_{label}:canonicalization_version_mismatch")
        for field in ("strategy_family_id", "strategy_id"):
            if str(payload.get(field, "")) != str(rich_cutover.get(field, "")):
                blockers.append(f"required_{label}:{field}_mismatch")
    for field in ("action_space_ref", "action_space_version"):
        expected = rich_cutover.get(field, "")
        for label, payload in (("adapter", adapter), ("baseline", baseline)):
            if str(payload.get(field, "")) != str(expected):
                blockers.append(f"required_{label}:{field}_mismatch")
    if str(adapter.get("action_space_digest", "")) != str(
        rich_cutover.get("action_space_digest", "")
    ):
        blockers.append("required_adapter:action_space_digest_mismatch")
    for field in ("baseline_artifact_ref", "baseline_digest"):
        if str(adapter.get(field, "")) != str(rich_cutover.get(field, "")):
            blockers.append(f"required_adapter:{field}_mismatch")
    if str(action_space.get("baseline_artifact_ref", "")) != str(
        rich_cutover.get("baseline_artifact_ref", "")
    ):
        blockers.append("required_action_space:baseline_artifact_ref_mismatch")
    if str(action_space.get("baseline_digest", "")) != str(
        rich_cutover.get("baseline_digest", "")
    ):
        blockers.append("required_action_space:baseline_digest_mismatch")
    if str(action_space.get("owner_ref", "")) != owner:
        blockers.append("required_action_space:owner_ref_mismatch")
    action_ids = set(_string_sequence(action_space.get("action_ids")))
    supported_actions = set(_string_sequence(adapter.get("supported_action_ids")))
    if not action_ids or not action_ids.issubset(supported_actions):
        blockers.append("required_adapter:action_membership_mismatch")

    effective_at = _aware_timestamp(str(rich_cutover.get("effective_at", "")))
    occurred_at = _aware_timestamp(str(receipt.get("occurred_at", "")))
    if effective_at is None:
        blockers.append("required_rich_cutover_effective_at_invalid")
    if occurred_at is None:
        blockers.append("required_transition_occurred_at_invalid")
    if effective_at is not None and occurred_at is not None:
        if effective_at > occurred_at:
            blockers.append("required_rich_cutover_effective_at_after_occurred_at")
        if effective_at > datetime.now(UTC):
            blockers.append("required_rich_cutover_not_yet_effective")

    authorization_digest = str(receipt.get("authorization_digest", ""))
    authorization_blockers, authorization = _catalog_artifact_blockers(
        str(receipt.get("authorization_ref", "")),
        catalog=catalog,
        expected_artifact_type="manual_authorization_decision",
        expected_digest=authorization_digest,
    )
    blockers.extend(f"required_authorization:{item}" for item in authorization_blockers)
    blockers.extend(
        f"required_authorization:{item}"
        for item in validate_manual_authorization_decision(authorization)
    )
    for field, expected in (
        ("strategy_id", strategy_id),
        ("owner", owner),
        ("cutover_digest", rich_cutover.get("cutover_digest", "")),
        ("change_id", rich_cutover.get("change_id", "")),
        ("mode", "required"),
        ("version", expected_version),
    ):
        if str(authorization.get(field, "")) != str(expected):
            blockers.append(f"required_authorization:{field}_mismatch")

    for index, (ref, expected_kind) in enumerate(expected_assurances.items()):
        digest, recorded_kind = recorded_assurances.get(ref, ("", ""))
        expected_artifact_type = (
            "strategy_usage_cutover_evidence"
            if expected_kind == "evidence"
            else "strategy_usage_cutover_test"
        )
        assurance_blockers, assurance = _catalog_artifact_blockers(
            ref,
            catalog=catalog,
            expected_artifact_type=expected_artifact_type,
            expected_digest=digest,
        )
        blockers.extend(
            f"required_assurance:{index}:{item}" for item in assurance_blockers
        )
        if recorded_kind != expected_kind:
            blockers.append(f"required_assurance:{index}:kind_mismatch")
            continue
        blockers.extend(
            f"required_assurance:{index}:{item}"
            for item in _assurance_contract_blockers(
                assurance,
                cutover=rich_cutover,
                expected_kind=expected_kind,
                catalog=catalog,
            )
        )
    return blockers


def _complete_dependency_contract_blockers(
    payload: Mapping[str, object],
    *,
    required_fields: Sequence[str],
    digest_fields: Sequence[str] = (),
    sequence_fields: Sequence[str] = (),
    allow_empty_sequences: Sequence[str] = (),
    unique_sequence_fields: Sequence[str] = (),
    mapping_fields: Sequence[str] = (),
) -> list[str]:
    """Validate every field in one cutover dependency machine contract.

    Resolution already proves the artifact type and recomputes its semantic
    checksum.  This helper closes the remaining schema surface: presence,
    exact digest shape, collection shape/uniqueness, namespaced action IDs and
    non-empty Chinese label mappings.  Callers pass the complete schema field
    list rather than selecting a convenient identity subset.
    """

    blockers: list[str] = []
    digest_keys = set(digest_fields)
    sequence_keys = set(sequence_fields)
    mapping_keys = set(mapping_fields)
    empty_sequences = set(allow_empty_sequences)
    unique_sequences = set(unique_sequence_fields)
    for field in required_fields:
        if field not in payload:
            blockers.append(f"{field}_required")
            continue
        value = payload.get(field)
        if field in digest_keys:
            if not _is_sha256_digest(value):
                blockers.append(f"{field}_invalid")
            continue
        if field in sequence_keys:
            if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
                blockers.append(f"{field}_sequence_required")
                continue
            if any(not isinstance(item, str) for item in value):
                blockers.append(f"{field}_items_must_be_strings")
            normalized = tuple(str(item).strip() for item in value)
            if any(not item for item in normalized) or (
                field not in empty_sequences and not normalized
            ):
                blockers.append(f"{field}_required")
            if field in unique_sequences and len(normalized) != len(set(normalized)):
                blockers.append(f"{field}_duplicate")
            if field in {"action_ids", "supported_action_ids"} and any(
                ":" not in item for item in normalized
            ):
                blockers.append(f"{field}_must_be_namespaced")
            continue
        if field in mapping_keys:
            if not isinstance(value, Mapping):
                blockers.append(f"{field}_object_required")
            elif field == "field_labels_zh":
                labels = cast(Mapping[object, object], value)
                if not labels or any(
                    not str(key).strip() or not str(label).strip()
                    for key, label in labels.items()
                ):
                    blockers.append("field_labels_zh_required")
            continue
        if not str(value).strip():
            blockers.append(f"{field}_required")
    return blockers


def _rollback_public_cas_blockers(
    receipt: Mapping[str, object],
    *,
    authoritative_snapshot: Mapping[str, object],
    rollback_snapshot_digest: str,
    catalog: Mapping[str, Mapping[str, object]] | None,
) -> list[str]:
    """Re-resolve the complete required-state ledger before rollback."""

    blockers: list[str] = []
    authorization_digest = str(receipt.get("authorization_digest", ""))
    if not _is_sha256_digest(authorization_digest):
        blockers.append("rollback_authorization_digest_required")
    if not _is_sha256_digest(rollback_snapshot_digest):
        blockers.append("rollback_snapshot_digest_required")
    if catalog is None:
        return [*blockers, "rollback_resolver_context_required"]

    strategy_id = str(receipt.get("strategy_id", ""))
    rollback_snapshot_ref = str(receipt.get("rollback_snapshot_ref", ""))
    expected_prior_version = int(str(receipt.get("expected_prior_version", "-1")))
    prior_rich_cutover = authoritative_snapshot.get("rich_cutover")
    rich_cutover: Mapping[str, object]
    if isinstance(prior_rich_cutover, Mapping):
        rich_cutover = cast(Mapping[str, object], prior_rich_cutover)
    else:
        rich_cutover = {}
    prior_owner = str(rich_cutover.get("owner", ""))
    if not prior_owner:
        blockers.append("rollback_prior_rich_cutover_owner_required")

    authorization_blockers, rollback_authorization = _catalog_artifact_blockers(
        str(receipt.get("authorization_ref", "")),
        catalog=catalog,
        expected_artifact_type="manual_authorization_decision",
        expected_digest=authorization_digest,
    )
    blockers.extend(f"rollback_authorization:{item}" for item in authorization_blockers)
    blockers.extend(
        f"rollback_authorization:{item}"
        for item in validate_manual_authorization_decision(rollback_authorization)
    )
    for field, expected in (
        ("strategy_id", strategy_id),
        ("owner", prior_owner),
        ("mode", "shadow_audit"),
        ("version", expected_prior_version + 1),
        ("rollback_snapshot_ref", rollback_snapshot_ref),
    ):
        if str(rollback_authorization.get(field, "")) != str(expected):
            blockers.append(f"rollback_authorization:{field}_mismatch")

    snapshot_blockers, rollback_snapshot = _catalog_artifact_blockers(
        rollback_snapshot_ref,
        catalog=catalog,
        expected_artifact_type="strategy_usage_required_snapshot",
        expected_digest=rollback_snapshot_digest,
    )
    blockers.extend(f"rollback_snapshot:{item}" for item in snapshot_blockers)
    if str(rollback_snapshot.get("strategy_id", "")) != strategy_id:
        blockers.append("rollback_snapshot:strategy_id_mismatch")

    requested_ids = set(_string_sequence(receipt.get("authorized_claim_ids")))
    authoritative_ids = set(
        _string_sequence(authoritative_snapshot.get("authorized_claim_ids"))
    )
    raw_entries = _object_sequence(rollback_snapshot.get("authorized_claims"))
    entries: dict[str, Mapping[str, object]] = {}
    invalid_entries = False
    for item in raw_entries:
        if not isinstance(item, Mapping):
            invalid_entries = True
            continue
        entry = cast(Mapping[str, object], item)
        claim_id = str(entry.get("claim_id", ""))
        if not claim_id or claim_id in entries:
            invalid_entries = True
            continue
        entries[claim_id] = entry
    if invalid_entries or len(entries) != len(raw_entries):
        blockers.append("rollback_snapshot:authorized_claim_entries_invalid")
    entry_ids = set(entries)
    if requested_ids != authoritative_ids or entry_ids != authoritative_ids:
        blockers.append("rollback_snapshot:authorized_claim_ids_mismatch")
    revoked_ids = set(_string_sequence(rollback_snapshot.get("revoked_claim_ids")))
    if not revoked_ids.issubset(authoritative_ids):
        blockers.append("rollback_snapshot:contains_unknown_revoked_claim")

    required_version = authoritative_snapshot.get("required_cutover_version", -1)
    required_transition_digest = str(
        authoritative_snapshot.get("required_transition_digest", "")
    )
    rich_cutover_digest = str(authoritative_snapshot.get("rich_cutover_digest", ""))
    if str(required_version) != str(expected_prior_version):
        blockers.append("rollback_snapshot:required_cutover_version_mismatch")
    if not _is_sha256_digest(required_transition_digest):
        blockers.append("rollback_snapshot:required_transition_digest_invalid")
    if not _is_sha256_digest(rich_cutover_digest):
        blockers.append("rollback_snapshot:rich_cutover_digest_invalid")

    for claim_id, entry in entries.items():
        blockers.extend(
            _rollback_entry_blockers(
                claim_id,
                entry,
                strategy_id=strategy_id,
                required_version=required_version,
                required_transition_digest=required_transition_digest,
                rich_cutover_digest=rich_cutover_digest,
                catalog=catalog,
            )
        )
    return blockers


def _rollback_entry_blockers(
    claim_id: str,
    entry: Mapping[str, object],
    *,
    strategy_id: str,
    required_version: object,
    required_transition_digest: str,
    rich_cutover_digest: str,
    catalog: Mapping[str, Mapping[str, object]],
) -> list[str]:
    blockers: list[str] = []
    production_digest = str(entry.get("production_authorization_digest", ""))
    execution_ref = str(entry.get("prior_execution_receipt_ref", ""))
    execution_digest = str(entry.get("prior_execution_receipt_digest", ""))
    for field, actual, expected in (
        (
            "prior_required_cutover_version",
            entry.get("prior_required_cutover_version"),
            required_version,
        ),
        (
            "prior_required_transition_digest",
            entry.get("prior_required_transition_digest", ""),
            required_transition_digest,
        ),
        (
            "prior_rich_cutover_digest",
            entry.get("prior_rich_cutover_digest", ""),
            rich_cutover_digest,
        ),
    ):
        if str(actual) != str(expected):
            blockers.append(f"rollback_entry:{claim_id}:{field}_mismatch")
    if not _is_sha256_digest(production_digest):
        blockers.append(
            f"rollback_entry:{claim_id}:production_authorization_digest_invalid"
        )
    if not execution_ref or not _is_sha256_digest(execution_digest):
        blockers.append(
            f"rollback_entry:{claim_id}:prior_execution_receipt_identity_invalid"
        )

    common_identity = (
        ("strategy_id", strategy_id),
        ("integration_claim_ref", str(entry.get("claim_ref", ""))),
        ("binding_ref", str(entry.get("binding_ref", ""))),
        ("candidate_fingerprint", str(entry.get("candidate_fingerprint", ""))),
        ("cutover_version", required_version),
        ("cutover_digest", rich_cutover_digest),
        ("cutover_transition_digest", required_transition_digest),
    )
    execution_blockers, execution = _catalog_artifact_blockers(
        execution_ref,
        catalog=catalog,
        expected_artifact_type="strategy_usage_execution_receipt",
        expected_digest=execution_digest,
    )
    blockers.extend(
        f"rollback_entry:{claim_id}:execution:{item}" for item in execution_blockers
    )
    if (
        execution.get("status") != "eligible"
        or execution.get("execution_eligible") is not True
    ):
        blockers.append(f"rollback_entry:{claim_id}:execution_not_eligible")
    if execution.get("mode") != "required":
        blockers.append(f"rollback_entry:{claim_id}:execution_not_required")
    if execution.get("production_authority") is not False:
        blockers.append(f"rollback_entry:{claim_id}:execution_grants_authority")
    for field, expected in common_identity:
        if str(execution.get(field, "")) != str(expected):
            blockers.append(f"rollback_entry:{claim_id}:execution_{field}_mismatch")

    production_ref = str(entry.get("production_authorization_ref", ""))
    production_blockers, production = _catalog_artifact_blockers(
        production_ref,
        catalog=catalog,
        expected_artifact_type="project_production_authorization",
        expected_digest=production_digest,
    )
    blockers.extend(
        f"rollback_entry:{claim_id}:production:{item}" for item in production_blockers
    )
    if production.get("production_authority") is not True:
        blockers.append(f"rollback_entry:{claim_id}:production_not_granted")
    if production.get("revoked") is not False:
        blockers.append(f"rollback_entry:{claim_id}:production_revoked")
    production_identity = (
        ("strategy_id", strategy_id),
        ("claim_ref", str(entry.get("claim_ref", ""))),
        ("binding_ref", str(entry.get("binding_ref", ""))),
        ("candidate_fingerprint", str(entry.get("candidate_fingerprint", ""))),
        ("cutover_version", required_version),
        ("cutover_digest", rich_cutover_digest),
        ("cutover_transition_digest", required_transition_digest),
    )
    for field, expected in production_identity:
        if str(production.get(field, "")) != str(expected):
            blockers.append(f"rollback_entry:{claim_id}:production_{field}_mismatch")
    return blockers


def _assurance_contract_blockers(
    assurance: Mapping[str, object],
    *,
    cutover: Mapping[str, object],
    expected_kind: str,
    catalog: Mapping[str, Mapping[str, object]],
) -> list[str]:
    blockers: list[str] = []
    for field in (
        "strategy_family_id",
        "strategy_id",
        "change_id",
        "mode",
        "version",
        "cutover_digest",
        "action_space_ref",
        "action_space_digest",
        "action_space_version",
        "adapter_ref",
        "adapter_digest",
        "baseline_artifact_ref",
        "baseline_digest",
    ):
        if str(assurance.get(field, "")) != str(cutover.get(field, "")):
            blockers.append(f"{field}_mismatch")
    if str(assurance.get("schema_id", "")) != "strategy_usage_cutover_assurance@1.0":
        blockers.append("schema_id_mismatch")
    if str(assurance.get("canonicalization_version", "")) != (
        "factorlab_canonical_json@1"
    ):
        blockers.append("canonicalization_version_mismatch")
    if str(assurance.get("assurance_kind", "")) != expected_kind:
        blockers.append("assurance_kind_mismatch")
    if str(assurance.get("status", "")) != "passed":
        blockers.append("assurance_status_not_passed")
    result_refs = _string_sequence(assurance.get("result_refs"))
    result_digests = _string_sequence(assurance.get("result_digests"))
    if (
        not result_refs
        or len(result_refs) != len(result_digests)
        or len(set(result_refs)) != len(result_refs)
        or any(not _is_sha256_digest(item) for item in result_digests)
    ):
        return [*blockers, "assurance_result_ledger_invalid"]
    expected_result_type = (
        "strategy_usage_shadow_result"
        if expected_kind == "evidence"
        else "strategy_usage_conformance_result"
    )
    expected_result_schema = f"{expected_result_type}@1.0"
    for index, (ref, digest) in enumerate(
        zip(result_refs, result_digests, strict=True)
    ):
        result_blockers, resolved = _catalog_artifact_blockers(
            ref,
            catalog=catalog,
            expected_artifact_type=expected_result_type,
            expected_digest=digest,
        )
        blockers.extend(f"assurance_result:{index}:{item}" for item in result_blockers)
        if str(resolved.get("schema_id", "")) != expected_result_schema:
            blockers.append(f"assurance_result:{index}:schema_id_mismatch")
        if str(resolved.get("canonicalization_version", "")) != (
            "factorlab_canonical_json@1"
        ):
            blockers.append(
                f"assurance_result:{index}:canonicalization_version_mismatch"
            )
        field_labels = resolved.get("field_labels_zh")
        if not isinstance(field_labels, Mapping) or not field_labels:
            blockers.append(f"assurance_result:{index}:field_labels_zh_required")
        for field in (
            "strategy_family_id",
            "strategy_id",
            "change_id",
            "mode",
            "version",
            "cutover_digest",
        ):
            if str(resolved.get(field, "")) != str(cutover.get(field, "")):
                blockers.append(f"assurance_result:{index}:{field}_mismatch")
        if resolved.get("status") != "passed":
            blockers.append(f"assurance_result:{index}:status_not_passed")
        if resolved.get("passed") is not True:
            blockers.append(f"assurance_result:{index}:passed_not_true")
    return blockers


def _aware_timestamp(value: str) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


__all__ = [
    "Record",
    "TemporalGovernanceRepository",
    "canonical_digest",
    "canonical_json",
]
