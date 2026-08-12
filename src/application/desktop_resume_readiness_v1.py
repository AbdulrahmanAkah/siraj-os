"""Ledger-backed, desktop-only production-resume boundary.

This module keeps inspection side-effect free and defines the supported
Desktop-only resume boundary.  It prepares an explicit human resume intent;
the confirmed local MEDIA_COST_PREFLIGHT executor is invoked only through the
controller's explicit execution method.  Inspection and intent preparation
never create paid authorization or contact a provider.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import threading
import uuid
from typing import Any, Callable, Mapping

from src.application.artifact_provenance_v1 import canonical_sha256, sha256_file

from src.application.cinematic_shot_contracts import (
    structural_fingerprint as contract_structural_fingerprint,
    structural_shots_from_storyboard,
)
from src.application.controlled_alignment_validation_v1 import (
    _required_structural_fingerprint,
)
from src.application.episode_transition_ledger_v1 import (
    BASE_STAGE_ORDER,
    ledger_path,
    project_state,
    read_entries,
)
from src.application.worker_lifecycle_v1 import WorkerLifecycle


EPISODE_002 = "episode-002-adam-temptation-fall-repentance"
PRODUCTION_RESUME_ENTRYPOINT = "DESKTOP_UI_ONLY"
DESKTOP_SOURCE = "DESKTOP_UI"
MEDIA_COST_PREFLIGHT = "MEDIA_COST_PREFLIGHT"
LOCAL_ASSEMBLY_AND_MONTAGE = "LOCAL_ASSEMBLY_AND_MONTAGE"
SEMANTIC_EDITORIAL_AND_TECHNICAL_QA = "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA"
AUTHORITATIVE_STATE_SOURCE = "episode-transition-ledger-v1.jsonl"
EXPECTED_OVERLAY_SHA256 = (
    "254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509"
)
EXPECTED_STRUCTURAL_FINGERPRINT = (
    "94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42"
)


class DesktopResumePolicyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DesktopEpisodeState:
    episode_id: str
    current_stage: str
    status: str
    completed_stages: tuple[str, ...]
    alignment_gate: str
    duplicate_gate: str
    promoted_overlay_sha256: str
    authoritative_structural_fingerprint: str
    provider_plan_contract_fingerprint: str
    duration_seconds: float
    shot_count: int
    timeline_discontinuities: int
    ledger_path: str
    ledger_head_sha256: str
    ledger_entry_count: int
    production_resume_authorized: bool = False
    production_resume_entrypoint: str = PRODUCTION_RESUME_ENTRYPOINT

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DesktopResumeIntent:
    episode_id: str
    first_stage: str
    source: str
    requires_explicit_human_action: bool
    ledger_head_sha256: str = ""
    promoted_overlay_sha256: str = ""
    structural_fingerprint: str = ""
    creates_authorization: bool = False
    starts_production: bool = False
    # Opaque capability issued by the Desktop controller for one reviewed
    # resume action.  It is never persisted in the episode ledger and is
    # required by the real provider-stage executor so a CLI/direct script
    # cannot fabricate a production context from a plain mapping.
    execution_token: str = ""
    # Provider-stage resume capabilities are bound to the complete reviewed
    # preflight tuple, not just the ledger/creative structural identity.
    # These values are captured by the Desktop controller and compared again
    # immediately before the paid gateway boundary.
    preflight_file_sha256: str = ""
    preflight_payload_sha256: str = ""
    media_plan_sha256: str = ""
    provider_request_plan_sha256: str = ""
    pricing_registry_sha256: str = ""
    pricing_registry_version: str = ""
    reack_receipt_id: str = ""
    maximum_cost_envelope_usd: float | None = None
    currency: str = ""

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as exc:
        raise DesktopResumePolicyError("AUTHORITATIVE_INPUT_UNREADABLE:" + str(path)) from exc
    if not isinstance(value, dict):
        raise DesktopResumePolicyError("AUTHORITATIVE_INPUT_OBJECT_REQUIRED:" + str(path))
    return value


def _paths(repo: Path, episode_id: str) -> dict[str, Path]:
    episode = repo / "projects" / episode_id
    return {
        "ledger": ledger_path(repo, episode_id),
        "storyboard": episode / "preproduction" / "audio-bound-storyboard-v6-1.json",
        "timeline": episode / "preproduction" / "audio-timestamps-and-beats-v6-1.json",
        "overlay": episode / "preproduction" / "siraj-creative-shot-direction-promoted-v1.json",
        "plan": episode / "preproduction" / "siraj-promoted-provider-ready-prompt-plan-v1.json",
        "promotion_state": episode / "orchestration" / "episode-creative-promotion-state-v1.json",
        "duplicate_gate": episode / "orchestration" / "prompt-similarity-duplicate-gate-promoted-v1.json",
        "gate_closure": episode / "orchestration" / "luna-gate-001-local-closure-v1.json",
    }


def _assert_ledger_structural_authority(entries: list[dict[str, Any]]) -> None:
    matching = [
        artifact
        for entry in entries
        if entry.get("stage") == "AUDIO_BOUND_STORYBOARD"
        for artifact in entry.get("output_artifacts", [])
        if artifact.get("logical_output") == "FULL_AUTHORITATIVE_STORYBOARD_STRUCTURAL_FINGERPRINT"
    ]
    if not matching or matching[-1].get("sha256") != EXPECTED_STRUCTURAL_FINGERPRINT:
        raise DesktopResumePolicyError("LEDGER_STRUCTURAL_FINGERPRINT_MISMATCH")


def read_desktop_episode_state(
    repo_root: Path,
    episode_id: str = EPISODE_002,
) -> DesktopEpisodeState:
    """Read only the authoritative ledger plus its bound current artifacts."""

    repo = Path(repo_root).resolve()
    paths = _paths(repo, episode_id)
    if any(not path.is_file() for path in paths.values()):
        missing = [key for key, path in paths.items() if not path.is_file()]
        raise DesktopResumePolicyError("DESKTOP_READINESS_INPUT_MISSING:" + ",".join(missing))

    projection = project_state(repo, episode_id, order=BASE_STAGE_ORDER)
    entries = read_entries(repo, episode_id)
    storyboard = _read_json(paths["storyboard"])
    timeline = _read_json(paths["timeline"])
    overlay = _read_json(paths["overlay"])
    plan = _read_json(paths["plan"])
    promotion = _read_json(paths["promotion_state"])
    duplicate_gate = _read_json(paths["duplicate_gate"])
    gate_closure = _read_json(paths["gate_closure"])
    structures = structural_shots_from_storyboard(storyboard)
    authoritative_fp = _required_structural_fingerprint(storyboard)
    contract_fp = contract_structural_fingerprint(structures)

    if (
        projection.current_stage not in BASE_STAGE_ORDER
        or projection.status != "READY"
        or "NARRATION_VISUAL_ALIGNMENT_GATE" not in projection.completed_stages
        or "PROMPT_SIMILARITY_AND_DUPLICATE_GATE" not in projection.completed_stages
        or authoritative_fp != EXPECTED_STRUCTURAL_FINGERPRINT
        or len(structures) != 55
        or float(timeline.get("total_duration_seconds")) != 623.584
        or sum(left.end_ms != right.start_ms for left, right in zip(structures, structures[1:])) != 0
        or overlay.get("storyboard_structural_fingerprint") != contract_fp
        or plan.get("storyboard_structural_fingerprint") != contract_fp
        or plan.get("creative_overlay_sha256") != EXPECTED_OVERLAY_SHA256
        or promotion.get("candidate_sha256") != EXPECTED_OVERLAY_SHA256
        or duplicate_gate.get("status") != "PASS"
        or gate_closure.get("status") != "CLOSED_BY_LOCAL_DUPLICATE_GATE"
    ):
        raise DesktopResumePolicyError("DESKTOP_READINESS_AUTHORITATIVE_BINDING_INVALID")
    _assert_ledger_structural_authority(entries)

    if projection.current_stage == "PROVIDER_EXECUTION":
        # The ledger's latest completed preflight output is authoritative.  The
        # historical v1 filename remains a compatibility fallback for isolated
        # fixtures that predate immutable V2 result publication.
        preflight_result = paths["ledger"].parent / "media-cost-preflight-v1.json"
        found_active_result = False
        for entry in reversed(entries):
            if entry.get("stage") != MEDIA_COST_PREFLIGHT or entry.get("status") != "COMPLETED":
                continue
            for reference in reversed(entry.get("output_artifacts") or []):
                if reference.get("logical_output") != "MEDIA_COST_PREFLIGHT_RESULT":
                    continue
                raw_path = str(reference.get("path") or "")
                candidate = Path(raw_path)
                if not candidate.is_absolute():
                    candidate = repo / candidate
                candidate = candidate.resolve()
                # A ledger-bound but missing result is fail-closed; do not
                # silently fall back to an older preflight artifact.
                preflight_result = candidate
                found_active_result = True
                break
            if found_active_result:
                break
        if not preflight_result.is_file():
            raise DesktopResumePolicyError("PREFLIGHT_RESULT_REQUIRED_FOR_NEXT_STAGE")
        persisted = _read_json(preflight_result)
        completed_receipts = [
            entry
            for entry in entries
            if entry.get("stage") == MEDIA_COST_PREFLIGHT
            and entry.get("status") == "COMPLETED"
        ]
        expected_result_hash = canonical_sha256(
            {key: value for key, value in persisted.items() if key != "result_sha256"}
        )
        matching_completion = [
            entry
            for entry in completed_receipts
            if entry.get("metadata", {}).get("transaction_id") == persisted.get("transaction_id")
            and any(
                str(ref.get("path", "")).endswith(preflight_result.name)
                and ref.get("sha256") == sha256_file(preflight_result)
                for ref in entry.get("output_artifacts", [])
            )
        ]
        if (
            persisted.get("schema_version") != "siraj-desktop-media-cost-preflight-v1"
            or persisted.get("episode_id") != episode_id
            or persisted.get("stage") != MEDIA_COST_PREFLIGHT
            or persisted.get("status") != "PERSISTED_AWAITING_TRANSITION_COMMIT"
            or persisted.get("provider_calls") != 0
            or persisted.get("paid_attempts_created") != 0
            or persisted.get("next_stage_executed") is not False
            or persisted.get("result_sha256") != expected_result_hash
            or len(matching_completion) != 1
        ):
            raise DesktopResumePolicyError("PREFLIGHT_COMPLETION_PROVENANCE_INVALID")

    return DesktopEpisodeState(
        episode_id=episode_id,
        current_stage=projection.current_stage,
        status=projection.status,
        completed_stages=projection.completed_stages,
        alignment_gate="PASS",
        duplicate_gate="PASS",
        promoted_overlay_sha256=EXPECTED_OVERLAY_SHA256,
        authoritative_structural_fingerprint=authoritative_fp,
        provider_plan_contract_fingerprint=contract_fp,
        duration_seconds=float(timeline["total_duration_seconds"]),
        shot_count=len(structures),
        timeline_discontinuities=0,
        ledger_path=str(paths["ledger"]),
        ledger_head_sha256=sha256_file(paths["ledger"]),
        ledger_entry_count=len(entries),
    )


def _reviewed_provider_binding(repo_root: Path, episode_id: str) -> dict[str, Any]:
    """Capture the exact provider-stage review tuple for one Desktop intent."""

    from src.application.desktop_cost_envelope_reack_v1 import (
        read_latest_reack_receipt,
        review_binding,
    )
    from src.application.desktop_media_cost_preflight_v1 import (
        read_persisted_media_cost_preflight,
    )

    review = read_persisted_media_cost_preflight(repo_root, episode_id)
    expected = review_binding(review, repo_root)
    receipt = read_latest_reack_receipt(
        repo_root,
        episode_id,
        binding=expected,
    )
    envelope = expected["maximum_cost_envelope"]
    return {
        "episode_id": episode_id,
        "stage": "PROVIDER_EXECUTION",
        "preflight_file_sha256": str(expected["preflight_result"]["file_sha256"]),
        "preflight_payload_sha256": str(expected["preflight_result"]["payload_sha256"]),
        "media_plan_sha256": str(expected["media_plan_sha256"]),
        "provider_request_plan_sha256": str(expected["provider_request_plan_sha256"]),
        "pricing_registry_sha256": str(expected["pricing_registry_sha256"]),
        "pricing_registry_version": str(expected["pricing_registry_version"]),
        "reack_receipt_id": str(receipt.get("receipt_id") or "") if receipt else "",
        "maximum_cost": float(envelope["amount"]),
        "currency": str(envelope["currency"]),
        "ledger_head_sha256": str(expected["ledger_head_sha256"]),
        "creative_overlay_sha256": str(expected["creative_overlay_sha256"]),
        "structural_fingerprint": str(expected["structural_fingerprint"]),
        "request_plan_hash": str(expected["provider_request_plan_sha256"]),
    }


class DesktopProductionResumeController:
    """Desktop UI boundary for reviewed local stage execution."""

    def __init__(self, repo_root: Path, episode_id: str = EPISODE_002) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.episode_id = episode_id
        self.worker_lifecycle = WorkerLifecycle()
        self._execution_active = False
        self._execution_lock = threading.Lock()
        self._pending_execution_capability: object | None = None

    def _claim_execution(self) -> None:
        with self._execution_lock:
            if self._execution_active:
                raise DesktopResumePolicyError("DUPLICATE_RESUME_TRANSACTION_BLOCKED")
            self._execution_active = True

    def _release_execution(self) -> None:
        with self._execution_lock:
            self._execution_active = False

    def _assert_provider_execution_authorized(self) -> None:
        """Fail closed before any provider-stage resume runner is entered."""

        if self.inspect().current_stage != "PROVIDER_EXECUTION":
            return
        from src.application.desktop_media_cost_preflight_v1 import (
            MediaCostPreflightError,
            read_persisted_media_cost_preflight,
        )

        try:
            review = read_persisted_media_cost_preflight(
                self.repo_root,
                self.episode_id,
            )
        except MediaCostPreflightError as exc:
            raise DesktopResumePolicyError(
                "PROVIDER_EXECUTION_AUTHORIZATION_STATE_UNREADABLE"
            ) from exc
        if not review.provider_execution_allowed:
            raise DesktopResumePolicyError("COST_ENVELOPE_REACK_REQUIRED")

    def inspect(self) -> DesktopEpisodeState:
        return read_desktop_episode_state(self.repo_root, self.episode_id)

    def prepare_resume(self, *, source: str) -> DesktopResumeIntent:
        if source != DESKTOP_SOURCE:
            raise DesktopResumePolicyError(
                "PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY:"
                + str(source)
            )
        state = self.inspect()
        execution_token = uuid.uuid4().hex
        self._pending_execution_capability = object()
        provider_binding: dict[str, Any] = {}
        if state.current_stage == "PROVIDER_EXECUTION":
            # A missing/invalid acknowledgement remains a normal fail-closed
            # execution result; the UI can still open the read-only review.
            # Valid bindings are captured here so a later click cannot float
            # over a changed plan or pricing registry.
            try:
                provider_binding = _reviewed_provider_binding(
                    self.repo_root,
                    self.episode_id,
                )
            except Exception:
                provider_binding = {}
        return DesktopResumeIntent(
            episode_id=state.episode_id,
            first_stage=state.current_stage,
            source=source,
            requires_explicit_human_action=True,
            ledger_head_sha256=state.ledger_head_sha256,
            promoted_overlay_sha256=state.promoted_overlay_sha256,
            structural_fingerprint=state.authoritative_structural_fingerprint,
            execution_token=execution_token,
            preflight_file_sha256=str(provider_binding.get("preflight_file_sha256") or ""),
            preflight_payload_sha256=str(provider_binding.get("preflight_payload_sha256") or ""),
            media_plan_sha256=str(provider_binding.get("media_plan_sha256") or ""),
            provider_request_plan_sha256=str(
                provider_binding.get("provider_request_plan_sha256") or ""
            ),
            pricing_registry_sha256=str(provider_binding.get("pricing_registry_sha256") or ""),
            pricing_registry_version=str(
                provider_binding.get("pricing_registry_version") or ""
            ),
            reack_receipt_id=str(provider_binding.get("reack_receipt_id") or ""),
            maximum_cost_envelope_usd=(
                float(provider_binding["maximum_cost"])
                if provider_binding.get("maximum_cost") is not None
                else None
            ),
            currency=str(provider_binding.get("currency") or ""),
        )

    def execution_authorization(
        self,
        intent: DesktopResumeIntent,
    ) -> dict[str, Any]:
        """Issue the in-memory authorization context owned by the Desktop UI."""

        if intent.source != DESKTOP_SOURCE or not intent.execution_token:
            raise DesktopResumePolicyError("DESKTOP_EXECUTION_CONTEXT_REQUIRED")
        if self._pending_execution_capability is None:
            raise DesktopResumePolicyError("DESKTOP_EXECUTION_CONTEXT_EXPIRED")
        if intent.first_stage == SEMANTIC_EDITORIAL_AND_TECHNICAL_QA:
            return {
                "authorization_id": "desktop-ui-semantic-qa-" + uuid.uuid4().hex,
                "source": DESKTOP_SOURCE,
                "scope": "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA_DESKTOP_RESUME",
                "episode_id": intent.episode_id,
                "stage": intent.first_stage,
                "execution_token": intent.execution_token,
                "_desktop_capability": self._pending_execution_capability,
            }
        if intent.first_stage == LOCAL_ASSEMBLY_AND_MONTAGE:
            return {
                "authorization_id": "desktop-ui-local-assembly-" + uuid.uuid4().hex,
                "source": DESKTOP_SOURCE,
                "scope": "LOCAL_ASSEMBLY_AND_MONTAGE_LOCAL_ONLY",
                "episode_id": intent.episode_id,
                "stage": intent.first_stage,
                "execution_token": intent.execution_token,
                "_desktop_capability": self._pending_execution_capability,
                "provider_calls": 0,
                "paid_operation": False,
            }
        return {
            "authorization_id": "desktop-ui-provider-resume-" + uuid.uuid4().hex,
            "source": DESKTOP_SOURCE,
            "scope": "PROVIDER_EXECUTION_DESKTOP_RESUME",
            "episode_id": intent.episode_id,
            "stage": intent.first_stage,
            "execution_token": intent.execution_token,
            # An in-memory identity token cannot be serialized or fabricated
            # by a CLI/direct script.  The token is intentionally omitted from
            # any persisted ledger/artifact.
            "_desktop_capability": self._pending_execution_capability,
            "provider_execution_binding": {
                key: value
                for key, value in {
                    "episode_id": intent.episode_id,
                    "stage": intent.first_stage,
                    "preflight_file_sha256": intent.preflight_file_sha256,
                    "preflight_payload_sha256": intent.preflight_payload_sha256,
                    "media_plan_sha256": intent.media_plan_sha256,
                    "provider_request_plan_sha256": intent.provider_request_plan_sha256,
                    "pricing_registry_sha256": intent.pricing_registry_sha256,
                    "pricing_registry_version": intent.pricing_registry_version,
                    "reack_receipt_id": intent.reack_receipt_id,
                    "maximum_cost": intent.maximum_cost_envelope_usd,
                    "currency": intent.currency,
                    "ledger_head_sha256": intent.ledger_head_sha256,
                    "creative_overlay_sha256": intent.promoted_overlay_sha256,
                    "structural_fingerprint": intent.structural_fingerprint,
                    "request_plan_hash": intent.provider_request_plan_sha256,
                }.items()
                if value not in (None, "")
            },
            "provider_calls": 0,
            "paid_operation": True,
        }

    def simulate_offline_resume(
        self,
        *,
        source: str,
        stage_runner: Callable[[str], Any],
    ) -> Any:
        """Offline-only seam for UI-flow tests; the caller supplies a fake."""

        intent = self.prepare_resume(source=source)
        self._assert_provider_execution_authorized()
        self._claim_execution()
        try:
            self.worker_lifecycle = self.worker_lifecycle.start_requested(now=0.0)
            self.worker_lifecycle = self.worker_lifecycle.entered(now=0.1)
            result = stage_runner(intent.first_stage)
        except Exception as exc:
            self.worker_lifecycle = self.worker_lifecycle.terminal(error=str(exc)).finished()
            raise
        finally:
            self._release_execution()
        self.worker_lifecycle = self.worker_lifecycle.terminal().finished()
        return result

    def execute_confirmed_resume(
        self,
        intent: DesktopResumeIntent,
        *,
        authorization: Mapping[str, Any],
        result_path: Path | None = None,
        provider_gateway: Any | None = None,
        fault_injector: Callable[[str], None] | None = None,
        progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> Any:
        """Execute only the reviewed current stage through the canonical service."""

        # SIRAJ_EP002_CANONICAL_DESKTOP_SEMANTIC_QA_V3
        if intent.first_stage == SEMANTIC_EDITORIAL_AND_TECHNICAL_QA:
            reviewed_state = self.inspect()
            if intent.ledger_head_sha256 != reviewed_state.ledger_head_sha256:
                raise DesktopResumePolicyError("STALE_STATE_REVIEW_REQUIRED")
            if authorization.get("source") != DESKTOP_SOURCE:
                raise DesktopResumePolicyError("PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY")
            if authorization.get("execution_token") != intent.execution_token:
                raise DesktopResumePolicyError("DESKTOP_EXECUTION_CONTEXT_REQUIRED")
            if authorization.get("_desktop_capability") is not self._pending_execution_capability:
                raise DesktopResumePolicyError("DESKTOP_EXECUTION_CONTEXT_REQUIRED")
            self._claim_execution()
            try:
                self.worker_lifecycle = self.worker_lifecycle.start_requested()
                self.worker_lifecycle = self.worker_lifecycle.entered()
                from src.application.desktop_semantic_editorial_qa_v3 import (
                    CanonicalDesktopSemanticQAExecutor,
                )
                result = CanonicalDesktopSemanticQAExecutor(
                    self.repo_root,
                    self.episode_id,
                ).execute(intent, authorization=authorization)
            except Exception as exc:
                self.worker_lifecycle = self.worker_lifecycle.terminal(error=str(exc)).finished()
                raise
            finally:
                self._release_execution()
            self.worker_lifecycle = self.worker_lifecycle.terminal().finished()
            return result

        # SIRAJ_EP002_CANONICAL_DESKTOP_LOCAL_ASSEMBLY_RESUME_V1
        if intent.first_stage == LOCAL_ASSEMBLY_AND_MONTAGE:
            reviewed_state = self.inspect()
            if (
                intent.ledger_head_sha256 != reviewed_state.ledger_head_sha256
                or intent.promoted_overlay_sha256 != reviewed_state.promoted_overlay_sha256
                or intent.structural_fingerprint
                != reviewed_state.authoritative_structural_fingerprint
            ):
                raise DesktopResumePolicyError("STALE_STATE_REVIEW_REQUIRED")
            if authorization.get("source") != DESKTOP_SOURCE:
                raise DesktopResumePolicyError("PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY")
            if authorization.get("execution_token") != intent.execution_token:
                raise DesktopResumePolicyError("DESKTOP_EXECUTION_CONTEXT_REQUIRED")
            if authorization.get("_desktop_capability") is not self._pending_execution_capability:
                raise DesktopResumePolicyError("DESKTOP_EXECUTION_CONTEXT_REQUIRED")
            if (
                authorization.get("scope") != "LOCAL_ASSEMBLY_AND_MONTAGE_LOCAL_ONLY"
                or authorization.get("paid_operation") is not False
                or authorization.get("provider_calls") != 0
            ):
                raise DesktopResumePolicyError("DESKTOP_LOCAL_ASSEMBLY_AUTHORIZATION_INVALID")
            self._claim_execution()
            try:
                self.worker_lifecycle = self.worker_lifecycle.start_requested()
                self.worker_lifecycle = self.worker_lifecycle.entered()
                from src.application.desktop_local_assembly_montage_v1 import (
                    CanonicalDesktopLocalAssemblyMontageExecutor,
                )
                result = CanonicalDesktopLocalAssemblyMontageExecutor(
                    self.repo_root, self.episode_id,
                ).execute(intent, authorization=authorization)
            except Exception as exc:
                self.worker_lifecycle = self.worker_lifecycle.terminal(error=str(exc)).finished()
                raise
            finally:
                self._release_execution()
            self.worker_lifecycle = self.worker_lifecycle.terminal().finished()
            return result

        if intent.first_stage == "PROVIDER_EXECUTION":
            reviewed_state = self.inspect()
            if (
                intent.ledger_head_sha256 != reviewed_state.ledger_head_sha256
                or intent.promoted_overlay_sha256 != reviewed_state.promoted_overlay_sha256
                or intent.structural_fingerprint != reviewed_state.authoritative_structural_fingerprint
            ):
                raise DesktopResumePolicyError("STALE_STATE_REVIEW_REQUIRED")
            self._assert_provider_execution_authorized()
            if authorization.get("source") != DESKTOP_SOURCE:
                raise DesktopResumePolicyError(
                    "PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY"
                )
            if authorization.get("execution_token") != intent.execution_token:
                raise DesktopResumePolicyError("DESKTOP_EXECUTION_CONTEXT_REQUIRED")
            if authorization.get("_desktop_capability") is not self._pending_execution_capability:
                raise DesktopResumePolicyError("DESKTOP_EXECUTION_CONTEXT_REQUIRED")
            try:
                current_binding = _reviewed_provider_binding(
                    self.repo_root,
                    self.episode_id,
                )
            except Exception as exc:
                # A changed/corrupt preflight or pricing binding is a stale
                # review, never a reason to reload and continue.
                raise DesktopResumePolicyError("STALE_STATE_REVIEW_REQUIRED") from exc
            intent_binding = {
                "preflight_file_sha256": intent.preflight_file_sha256,
                "preflight_payload_sha256": intent.preflight_payload_sha256,
                "media_plan_sha256": intent.media_plan_sha256,
                "provider_request_plan_sha256": intent.provider_request_plan_sha256,
                "pricing_registry_sha256": intent.pricing_registry_sha256,
                "reack_receipt_id": intent.reack_receipt_id,
                "maximum_cost": intent.maximum_cost_envelope_usd,
                "currency": intent.currency,
            }
            expected_intent_binding = {
                "preflight_file_sha256": current_binding["preflight_file_sha256"],
                "preflight_payload_sha256": current_binding["preflight_payload_sha256"],
                "media_plan_sha256": current_binding["media_plan_sha256"],
                "provider_request_plan_sha256": current_binding["provider_request_plan_sha256"],
                "pricing_registry_sha256": current_binding["pricing_registry_sha256"],
                "reack_receipt_id": current_binding["reack_receipt_id"],
                "maximum_cost": current_binding["maximum_cost"],
                "currency": current_binding["currency"],
            }
            if canonical_sha256(intent_binding) != canonical_sha256(expected_intent_binding):
                raise DesktopResumePolicyError("STALE_STATE_REVIEW_REQUIRED")
            if canonical_sha256(authorization.get("provider_execution_binding", {})) != canonical_sha256(
                {
                    key: value
                    for key, value in current_binding.items()
                    if key in {
                        "episode_id",
                        "stage",
                        "preflight_file_sha256",
                        "preflight_payload_sha256",
                        "media_plan_sha256",
                        "provider_request_plan_sha256",
                        "pricing_registry_sha256",
                        "pricing_registry_version",
                        "reack_receipt_id",
                        "maximum_cost",
                        "currency",
                        "ledger_head_sha256",
                        "creative_overlay_sha256",
                        "structural_fingerprint",
                        "request_plan_hash",
                    }
                }
            ):
                raise DesktopResumePolicyError("STALE_STATE_REVIEW_REQUIRED")
            self._claim_execution()
            try:
                self.worker_lifecycle = self.worker_lifecycle.start_requested()
                self.worker_lifecycle = self.worker_lifecycle.entered()
                from src.application.desktop_provider_execution_v1 import (
                    CanonicalDesktopProviderExecutionExecutor,
                )

                result = CanonicalDesktopProviderExecutionExecutor(
                    self.repo_root,
                    self.episode_id,
                    gateway=provider_gateway,
                    fault_injector=fault_injector,
                    progress_callback=progress_callback,
                ).execute(
                    intent,
                    authorization=authorization,
                )
            except Exception as exc:
                self.worker_lifecycle = self.worker_lifecycle.terminal(error=str(exc)).finished()
                raise
            finally:
                self._release_execution()
            self.worker_lifecycle = self.worker_lifecycle.terminal().finished()
            return result
        if intent.first_stage != MEDIA_COST_PREFLIGHT:
            raise DesktopResumePolicyError(
                "CANONICAL_DESKTOP_STAGE_NOT_IMPLEMENTED:" + intent.first_stage
            )
        self._claim_execution()
        try:
            self.worker_lifecycle = self.worker_lifecycle.start_requested()
            self.worker_lifecycle = self.worker_lifecycle.entered()
            from src.application.desktop_media_cost_preflight_v1 import (
                CanonicalMediaCostPreflightExecutor,
            )

            result = CanonicalMediaCostPreflightExecutor(
                self.repo_root,
                self.episode_id,
            ).execute(
                intent,
                authorization=authorization,
                result_path=result_path,
            )
        except Exception as exc:
            self.worker_lifecycle = self.worker_lifecycle.terminal(error=str(exc)).finished()
            raise
        finally:
            self._release_execution()
        self.worker_lifecycle = self.worker_lifecycle.terminal().finished()
        return result


def supported_desktop_composition_root() -> str:
    return "src.application.desktop_resume_readiness_v1.DesktopProductionResumeController"
