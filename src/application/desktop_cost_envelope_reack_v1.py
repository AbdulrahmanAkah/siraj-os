"""Canonical Desktop cost-envelope re-acknowledgement transaction.

The media preflight review is intentionally read-only.  This module is the
application boundary used after an explicit human confirmation dialog.  It
does not edit the master-authorization projection and it never calls a
provider.  Instead, it appends one durable, content-addressed receipt whose
exact binding is checked against the current ledger-backed preflight before
and during the append.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from typing import Any, Mapping
import uuid

from src.application.artifact_provenance_v1 import (
    _THREAD_LOCK,
    _fsync_directory,
    _process_lock,
    canonical_json_bytes,
    canonical_sha256,
    read_jsonl,
    utc_now,
)
from src.application.episode_transition_ledger_v1 import ledger_path


DESKTOP_SOURCE = "DESKTOP_UI"
PROVIDER_EXECUTION = "PROVIDER_EXECUTION"
REACK_SCHEMA_VERSION = "siraj-desktop-cost-envelope-reack-v1"
REACK_RECEIPT_LEDGER = "episode-cost-envelope-reack-ledger-v1.jsonl"
VALID_STATUS = "VALID_BOUND_TO_CURRENT_COST_ENVELOPE"
UNBOUND_STATUS = "ACTIVE_BUT_UNBOUND_REACK_REQUIRED"
REACK_SCOPE = "EPISODE_WIDE_MASTER_AUTHORIZATION_V6_6_COST_ENVELOPE_REACK"


class CostEnvelopeReackError(RuntimeError):
    """A fail-closed re-acknowledgement error."""


@dataclass(frozen=True, slots=True)
class CostEnvelopeReackOutcome:
    status: str
    episode_id: str
    receipt_id: str
    receipt_path: str
    authorization_status: str
    cost_envelope_reack_required: bool
    provider_execution_allowed: bool
    provider_calls: int
    paid_attempts_created: int
    provider_execution_started: bool
    idempotent: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "episode_id": self.episode_id,
            "receipt_id": self.receipt_id,
            "receipt_path": self.receipt_path,
            "authorization_status": self.authorization_status,
            "cost_envelope_reack_required": self.cost_envelope_reack_required,
            "provider_execution_allowed": self.provider_execution_allowed,
            "provider_calls": self.provider_calls,
            "paid_attempts_created": self.paid_attempts_created,
            "provider_execution_started": self.provider_execution_started,
            "idempotent": self.idempotent,
        }


def reack_receipt_path(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / REACK_RECEIPT_LEDGER
    )


def _relative(repo: Path, path: Path) -> str:
    try:
        return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")
    except ValueError as exc:
        raise CostEnvelopeReackError("AUTHORIZATION_INPUT_OUTSIDE_REPOSITORY") from exc


def _number(value: Any, *, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise CostEnvelopeReackError("REACK_COST_FIELD_INVALID:" + field_name)
    return float(value)


def _authority(review: Any) -> Mapping[str, Any]:
    value = getattr(review, "media_plan_authority", {})
    if not isinstance(value, Mapping):
        raise CostEnvelopeReackError("REACK_MEDIA_PLAN_AUTHORITY_INVALID")
    return value


def review_binding(review: Any, repo_root: Path | None = None) -> dict[str, Any]:
    """Return the immutable identity/cost tuple bound by a human review."""

    authority = _authority(review)
    result_path = Path(str(review.result_path)).resolve()
    repo = Path(repo_root).resolve() if repo_root is not None else None
    result_path_value = (
        _relative(repo, result_path) if repo is not None else str(result_path)
    )
    envelope = review.cost_envelope_usd
    if not isinstance(envelope, Mapping):
        raise CostEnvelopeReackError("REACK_COST_ENVELOPE_INVALID")
    currency = envelope.get("currency")
    if not isinstance(currency, str) or not currency:
        raise CostEnvelopeReackError("REACK_COST_CURRENCY_REQUIRED")
    upper = _number(envelope.get("upper_bound"), field_name="upper_bound")
    if upper < 0:
        raise CostEnvelopeReackError("REACK_COST_ENVELOPE_NEGATIVE")
    plan_hash = authority.get("proposal_sha256")
    request_plan_hash = authority.get("provider_request_plan_hash")
    pricing_hash = envelope.get("pricing_registry_sha256")
    pricing_version = envelope.get("pricing_registry_version")
    if not all(isinstance(value, str) and value for value in (
        plan_hash,
        request_plan_hash,
        pricing_hash,
        pricing_version,
    )):
        raise CostEnvelopeReackError("REACK_PLAN_OR_PRICING_HASH_MISSING")

    authoritative = review.authoritative_state
    if not isinstance(authoritative, Mapping):
        raise CostEnvelopeReackError("REACK_AUTHORITATIVE_STATE_INVALID")
    ledger_head = str(review.current_ledger_head_sha256 or "")
    if not ledger_head:
        raise CostEnvelopeReackError("REACK_LEDGER_HEAD_MISSING")
    return {
        "episode_id": str(review.episode_id),
        "current_stage": PROVIDER_EXECUTION,
        "preflight_result": {
            "path": result_path_value,
            "file_sha256": str(review.result_file_sha256),
            "payload_sha256": str(review.result_sha256),
        },
        "media_plan_sha256": str(plan_hash),
        "provider_request_plan_sha256": str(request_plan_hash),
        "pricing_registry_sha256": str(pricing_hash),
        "pricing_registry_version": str(pricing_version),
        "ledger_head_sha256": ledger_head,
        "reviewed_preflight_input_ledger_head_sha256": str(
            review.reviewed_ledger_head_sha256 or ""
        ),
        "creative_overlay_sha256": str(
            authoritative.get("promoted_overlay_sha256") or ""
        ),
        "structural_fingerprint": str(
            authoritative.get("structural_fingerprint") or ""
        ),
        "duration_seconds": _number(
            authoritative.get("duration_seconds"),
            field_name="duration_seconds",
        ),
        "shot_count": int(authoritative.get("shot_count") or 0),
        "timeline_discontinuities": int(
            authoritative.get("timeline_discontinuities") or 0
        ),
        "provider_contract_status": str(
            getattr(review, "provider_contract_status", "UNKNOWN")
        ),
        "maximum_cost_envelope": {
            "amount": upper,
            "currency": currency,
        },
        "authorization_policy": str(review.authorization_policy),
        "authorization_scope": REACK_SCOPE,
    }


def _snapshot_binding(snapshot: Mapping[str, Any], repo_root: Path) -> dict[str, Any]:
    """Build the same binding from the object emitted by the Qt review dialog."""

    required = (
        "episode_id",
        "result_path",
        "result_file_sha256",
        "result_sha256",
        "current_ledger_head_sha256",
        "reviewed_ledger_head_sha256",
        "authoritative_state",
        "cost_envelope_usd",
        "authorization_policy",
        "media_plan_authority",
    )
    if any(key not in snapshot for key in required):
        missing = [key for key in required if key not in snapshot]
        raise CostEnvelopeReackError("REACK_REVIEW_SNAPSHOT_INCOMPLETE:" + ",".join(missing))
    authority = snapshot["media_plan_authority"]
    authoritative = snapshot["authoritative_state"]
    envelope = snapshot["cost_envelope_usd"]
    if not isinstance(authority, Mapping) or not isinstance(authoritative, Mapping):
        raise CostEnvelopeReackError("REACK_REVIEW_SNAPSHOT_INVALID")
    if not isinstance(envelope, Mapping):
        raise CostEnvelopeReackError("REACK_REVIEW_COST_ENVELOPE_INVALID")
    # Construct a small attribute-compatible object rather than trusting a
    # serialized snapshot to supply a second, subtly different schema.
    class _Snapshot:
        pass

    value = _Snapshot()
    value.episode_id = snapshot["episode_id"]
    value.result_path = snapshot["result_path"]
    value.result_file_sha256 = snapshot["result_file_sha256"]
    value.result_sha256 = snapshot["result_sha256"]
    value.current_ledger_head_sha256 = snapshot["current_ledger_head_sha256"]
    value.reviewed_ledger_head_sha256 = snapshot["reviewed_ledger_head_sha256"]
    value.authoritative_state = dict(authoritative)
    value.cost_envelope_usd = dict(envelope)
    value.media_plan_authority = dict(authority)
    value.authorization_policy = snapshot["authorization_policy"]
    value.provider_contract_status = snapshot.get("provider_contract_status", "UNKNOWN")
    return review_binding(value, repo_root)


def _binding_equal(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    return canonical_sha256(left) == canonical_sha256(right)


def _unsigned_receipt(receipt: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in receipt.items()
        if key != "receipt_sha256"
    }


def _validate_receipt(receipt: Mapping[str, Any], *, episode_id: str) -> bool:
    return (
        receipt.get("schema_version") == REACK_SCHEMA_VERSION
        and receipt.get("episode_id") == episode_id
        and receipt.get("status") == "COMMITTED"
        and isinstance(receipt.get("binding"), Mapping)
        and receipt.get("receipt_sha256")
        == canonical_sha256(_unsigned_receipt(receipt))
    )


def _committed_receipts(repo_root: Path, episode_id: str) -> list[dict[str, Any]]:
    path = reack_receipt_path(repo_root, episode_id)
    try:
        rows = read_jsonl(path)
    except Exception as exc:
        raise CostEnvelopeReackError("REACK_RECEIPT_CORRUPT") from exc
    valid: list[dict[str, Any]] = []
    for row in rows:
        if not _validate_receipt(row, episode_id=episode_id):
            raise CostEnvelopeReackError("REACK_RECEIPT_INVALID")
        valid.append(row)
    return valid


def effective_reack_for_review(repo_root: Path, review: Any) -> str | None:
    """Return valid-bound status only for an exact current review binding."""

    rows = _committed_receipts(repo_root, str(review.episode_id))
    # Legacy/forensic preflight fixtures may not carry the V2 cost fields.  In
    # the absence of a re-ack receipt that is simply "not acknowledged"; it
    # must not make a read-only review unreadable.
    if not rows:
        return None
    try:
        expected = review_binding(review, repo_root)
    except CostEnvelopeReackError:
        return None
    for row in reversed(rows):
        if _binding_equal(row["binding"], expected):
            return VALID_STATUS
    return None


def read_latest_reack_receipt(
    repo_root: Path,
    episode_id: str,
    *,
    binding: Mapping[str, Any] | None = None,
) -> dict[str, Any] | None:
    rows = _committed_receipts(repo_root, episode_id)
    if binding is None:
        return rows[-1] if rows else None
    for row in reversed(rows):
        if _binding_equal(row["binding"], binding):
            return row
    return None


class DesktopCostEnvelopeReackService:
    """Explicit, Desktop-only, provider-free acknowledgement service."""

    def __init__(self, repo_root: Path, episode_id: str) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.episode_id = episode_id

    def confirm(
        self,
        review_snapshot: Mapping[str, Any],
        *,
        source: str | None = None,
    ) -> CostEnvelopeReackOutcome:
        if source != DESKTOP_SOURCE:
            raise CostEnvelopeReackError(
                "PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY:" + str(source)
            )
        if not isinstance(review_snapshot, Mapping):
            raise CostEnvelopeReackError("REACK_REVIEW_SNAPSHOT_REQUIRED")
        if review_snapshot.get("episode_id") != self.episode_id:
            raise CostEnvelopeReackError("REACK_EPISODE_MISMATCH")

        # The snapshot is only a claim.  Re-read the canonical result and
        # ledger immediately before taking the lock and again while holding it.
        from src.application.desktop_media_cost_preflight_v1 import (
            MediaCostPreflightError,
            read_persisted_media_cost_preflight,
        )

        try:
            requested_binding = _snapshot_binding(review_snapshot, self.repo_root)
        except CostEnvelopeReackError:
            raise
        try:
            current = read_persisted_media_cost_preflight(
                self.repo_root,
                self.episode_id,
            )
        except MediaCostPreflightError as exc:
            raise CostEnvelopeReackError("REACK_CURRENT_STATE_UNREADABLE") from exc
        current_binding = review_binding(current, self.repo_root)
        if not _binding_equal(requested_binding, current_binding):
            raise CostEnvelopeReackError("STALE_STATE_REVIEW_REQUIRED")

        path = reack_receipt_path(self.repo_root, self.episode_id)
        # The lock covers duplicate detection and the durable append.  The
        # second canonical read closes the review/commit race.  Locking the
        # ledger first also closes the small window between the second read
        # and the receipt append; normal ledger writers use the same lock.
        authoritative_ledger_path = ledger_path(
            self.repo_root,
            self.episode_id,
        )
        with _THREAD_LOCK, _process_lock(authoritative_ledger_path), _process_lock(path):
            try:
                current = read_persisted_media_cost_preflight(
                    self.repo_root,
                    self.episode_id,
                )
            except MediaCostPreflightError as exc:
                raise CostEnvelopeReackError("REACK_CURRENT_STATE_UNREADABLE") from exc
            current_binding = review_binding(current, self.repo_root)
            if not _binding_equal(requested_binding, current_binding):
                raise CostEnvelopeReackError("STALE_STATE_REVIEW_REQUIRED")

            existing = _committed_receipts(self.repo_root, self.episode_id)
            for row in reversed(existing):
                if _binding_equal(row["binding"], current_binding):
                    return _outcome_from_receipt(
                        row,
                        path,
                        idempotent=True,
                    )

            if current.production_authorization not in {
                UNBOUND_STATUS,
                "AWAITING_HUMAN_AUTHORIZATION",
            }:
                raise CostEnvelopeReackError("REACK_AUTHORIZATION_STATE_INVALID")
            if current.next_stage != PROVIDER_EXECUTION:
                raise CostEnvelopeReackError("REACK_STAGE_INVALID")
            if current.pricing_status != "COMPLETE":
                raise CostEnvelopeReackError("REACK_PRICING_NOT_COMPLETE")
            if current.provider_contract_status != "PASS":
                raise CostEnvelopeReackError("REACK_PROVIDER_CONTRACT_NOT_PASS")
            if current.coverage_status != "PASS":
                raise CostEnvelopeReackError("REACK_MEDIA_POLICY_NOT_SATISFIED")

            reviewed_at = review_snapshot.get("reviewed_at_utc") or utc_now()
            if not isinstance(reviewed_at, str) or not reviewed_at:
                raise CostEnvelopeReackError("REACK_REVIEW_TIMESTAMP_REQUIRED")
            acknowledged_at = utc_now()
            unsigned: dict[str, Any] = {
                "schema_version": REACK_SCHEMA_VERSION,
                "receipt_id": str(uuid.uuid4()),
                "episode_id": self.episode_id,
                "status": "COMMITTED",
                "decision": "COST_ENVELOPE_REACK_APPROVED",
                "source": DESKTOP_SOURCE,
                "scope": REACK_SCOPE,
                "binding": current_binding,
                "reviewed_at_utc": reviewed_at,
                "acknowledged_at_utc": acknowledged_at,
                "previous_authorization_status": current.production_authorization,
                "resulting_authorization_status": VALID_STATUS,
                "cost_envelope_reack_required": False,
                "provider_execution_allowed_by_authorization": True,
                "production_status_after": "PAUSED_AWAITING_HUMAN_RESUME",
                "next_stage": PROVIDER_EXECUTION,
                "provider_calls": 0,
                "paid_attempts_created": 0,
                "provider_execution_started": False,
                "automatic_paid_retry": False,
                "automatic_paid_resubmission": False,
                "authorization_policy_version": current.authorization_policy,
                "provenance": {
                    "authority": "HUMAN_COST_ENVELOPE_REACK",
                    "ui_entrypoint": DESKTOP_SOURCE,
                    "canonical_preflight_result": current.result_path,
                    "ledger_head_sha256": current.current_ledger_head_sha256,
                },
            }
            unsigned["receipt_sha256"] = canonical_sha256(unsigned)
            payload = canonical_json_bytes(unsigned) + b"\n"
            with path.open("ab") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            _fsync_directory(path.parent)
            return _outcome_from_receipt(unsigned, path, idempotent=False)

    def acknowledge(
        self,
        review_snapshot: Mapping[str, Any],
        *,
        source: str | None = None,
    ) -> CostEnvelopeReackOutcome:
        """Semantic alias used by controllers that call the action an ack."""

        return self.confirm(review_snapshot, source=source)


def _outcome_from_receipt(
    receipt: Mapping[str, Any],
    path: Path,
    *,
    idempotent: bool,
) -> CostEnvelopeReackOutcome:
    return CostEnvelopeReackOutcome(
        status="ALREADY_COMMITTED" if idempotent else "COMMITTED",
        episode_id=str(receipt.get("episode_id") or ""),
        receipt_id=str(receipt.get("receipt_id") or ""),
        receipt_path=str(path),
        authorization_status=str(
            receipt.get("resulting_authorization_status") or VALID_STATUS
        ),
        cost_envelope_reack_required=bool(
            receipt.get("cost_envelope_reack_required", False)
        ),
        provider_execution_allowed=bool(
            receipt.get("provider_execution_allowed_by_authorization", False)
        ),
        provider_calls=int(receipt.get("provider_calls") or 0),
        paid_attempts_created=int(receipt.get("paid_attempts_created") or 0),
        provider_execution_started=bool(
            receipt.get("provider_execution_started", False)
        ),
        idempotent=idempotent,
    )


__all__ = [
    "CostEnvelopeReackError",
    "CostEnvelopeReackOutcome",
    "DesktopCostEnvelopeReackService",
    "REACK_RECEIPT_LEDGER",
    "REACK_SCHEMA_VERSION",
    "VALID_STATUS",
    "effective_reack_for_review",
    "read_latest_reack_receipt",
    "reack_receipt_path",
    "review_binding",
]
