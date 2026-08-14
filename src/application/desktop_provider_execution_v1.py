"""Canonical Desktop-only provider execution for a reviewed media plan.

This module is the production boundary between the full Desktop UI and the
single paid-operation gateway.  It deliberately consumes the immutable
MEDIA_COST_PREFLIGHT units; it never invokes the media planner or Luna.

The default gateway uses :mod:`paid_operation_gateway`.  Tests may inject a
fake gateway, but the application service, receipts, cost checks, and state
guards remain identical in both cases.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Any, Callable, Mapping, Protocol, Sequence
import uuid

from src.application.artifact_provenance_v1 import (
    append_jsonl as _siraj_base_append_jsonl_v2,
    artifact_reference,
    atomic_write_json,
    canonical_json_bytes,
    canonical_sha256,
    read_jsonl,
    sha256_file,
    utc_now,
    write_new_json,
)
from src.application.desktop_cost_envelope_reack_v1 import (
    VALID_STATUS,
    read_latest_reack_receipt,
    review_binding,
)
from src.application.desktop_media_cost_preflight_v1 import (
    MediaCostPreflightError,
    MediaCostPreflightReview,
    read_persisted_media_cost_preflight,
)
from src.application.desktop_resume_readiness_v1 import (
    DESKTOP_SOURCE,
    EPISODE_002,
    DesktopResumeIntent,
    DesktopResumePolicyError,
    read_desktop_episode_state,
)
from src.application.episode_transition_ledger_v1 import (
    append_transition_if_head,
    ledger_path,
    project_state,
)
from src.application.paid_operation_gateway import (
    PaidOperationRequest,
    PaidOperationResult,
    execute_bytes as execute_paid_bytes,
    execute_json as execute_paid_json,
    http_download_transport,
    http_json_transport,
    record_provider_operation_id,
    SUBMITTED_PENDING,
)
from src.application.provider_model_contracts import (
    CONTRACT_VERSION as PROVIDER_CONTRACT_VERSION,
    is_uuid4,
    validate_runware_task,
)
from src.application.provider_attempt_reconciliation_v1 import (
    NOT_SUBMITTED_ELIGIBLE,
    PROVEN_NOT_CHARGED,
    PROVEN_NOT_SUBMITTED,
    PROVEN_SUBMITTED_TERMINAL_REJECTED,
    TERMINAL_REJECTION_REAUTHORIZATION_REQUIRED,
    current_reconciliation_receipts,
    reconciliation_for_attempt,
    reconciliation_for_request,
)
from src.application.provider_terminal_replacement_authorization_v1 import (
    apply_terminal_replacement_prompt,
    consume_terminal_replacement_authorization,
    consumption_for_authorization,
    terminal_replacement_authorization_for_request,
    terminal_replacement_authorization_matches_reconciliation,
)
from src.application.runware_image_model_routing_v1 import build_runware_image_task
from src.application.runware_seedream_negative_prompt_recovery_v1 import (
    classify_runware_terminal_provider_rejection_v2,
)
from src.application.siraj_episode_master_authorization_v6_6 import (
    master_authorization_reference,
)


STAGE = "PROVIDER_EXECUTION"
NEXT_STAGE = "LOCAL_ASSEMBLY_AND_MONTAGE"
SCHEMA_VERSION = "siraj-desktop-provider-execution-v1"
STAGE_RECEIPT_LEDGER = "provider-execution-stage-receipts-v1.jsonl"
ATTEMPT_RECEIPT_LEDGER = "provider-execution-attempt-receipts-v1.jsonl"
PROGRESS_FILE = "provider-execution-progress-v1.json"
RESULT_DIR = "provider-execution-results-v1"
ATTEMPT_NAMESPACE = uuid.UUID("a59b91a1-4c0d-4b4e-87a5-3c3fdb0dd87e")


class DesktopProviderExecutionError(DesktopResumePolicyError):
    """Fail-closed provider execution error."""


class ProviderExecutionStaleStateError(DesktopProviderExecutionError):
    """The reviewed state changed before the paid boundary."""


class ProviderGateway(Protocol):
    """One and only one paid gateway entry used by the executor."""

    def submit(
        self,
        *,
        request: PaidOperationRequest,
        unit: Mapping[str, Any],
        attempt_id: str,
    ) -> Any: ...


@dataclass(frozen=True, slots=True)
class ProviderExecutionBinding:
    episode_id: str
    stage: str
    preflight_file_sha256: str
    preflight_payload_sha256: str
    media_plan_sha256: str
    provider_request_plan_sha256: str
    pricing_registry_sha256: str
    pricing_registry_version: str
    reack_receipt_id: str
    maximum_cost: float
    currency: str
    ledger_head_sha256: str
    creative_overlay_sha256: str
    structural_fingerprint: str
    request_plan_hash: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "stage": self.stage,
            "preflight_file_sha256": self.preflight_file_sha256,
            "preflight_payload_sha256": self.preflight_payload_sha256,
            "media_plan_sha256": self.media_plan_sha256,
            "provider_request_plan_sha256": self.provider_request_plan_sha256,
            "pricing_registry_sha256": self.pricing_registry_sha256,
            "pricing_registry_version": self.pricing_registry_version,
            "reack_receipt_id": self.reack_receipt_id,
            "maximum_cost": self.maximum_cost,
            "currency": self.currency,
            "ledger_head_sha256": self.ledger_head_sha256,
            "creative_overlay_sha256": self.creative_overlay_sha256,
            "structural_fingerprint": self.structural_fingerprint,
            "request_plan_hash": self.request_plan_hash,
        }


@dataclass(frozen=True, slots=True)
class ProviderExecutionOutcome:
    status: str
    episode_id: str
    stage: str
    session_id: str
    completed_requests: int
    planned_requests: int
    video_requests: int
    still_requests: int
    local_units: int
    failed_requests: int
    unknown_requests: int
    estimated_spent_usd: float
    maximum_cost_envelope_usd: float
    next_stage: str | None
    stage_receipt_path: str
    progress_path: str
    transition_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "episode_id": self.episode_id,
            "stage": self.stage,
            "session_id": self.session_id,
            "completed_requests": self.completed_requests,
            "planned_requests": self.planned_requests,
            "video_requests": self.video_requests,
            "still_requests": self.still_requests,
            "local_units": self.local_units,
            "failed_requests": self.failed_requests,
            "unknown_requests": self.unknown_requests,
            "estimated_spent_usd": self.estimated_spent_usd,
            "maximum_cost_envelope_usd": self.maximum_cost_envelope_usd,
            "next_stage": self.next_stage,
            "stage_receipt_path": self.stage_receipt_path,
            "progress_path": self.progress_path,
            "transition_id": self.transition_id,
        }


def _execution_root(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / "provider-execution-v1"
    )


def _stage_receipt_path(repo_root: Path, episode_id: str) -> Path:
    return _execution_root(repo_root, episode_id) / STAGE_RECEIPT_LEDGER


def _attempt_receipt_path(repo_root: Path, episode_id: str) -> Path:
    return _execution_root(repo_root, episode_id) / ATTEMPT_RECEIPT_LEDGER


def _progress_path(repo_root: Path, episode_id: str) -> Path:
    return _execution_root(repo_root, episode_id) / PROGRESS_FILE


def _result_path(repo_root: Path, episode_id: str, attempt_id: str) -> Path:
    return _execution_root(repo_root, episode_id) / RESULT_DIR / f"{attempt_id}.json"


def _persist_provider_operation_id(
    *,
    repo_root: Path,
    episode_id: str,
    attempt_id: str,
    unit: Mapping[str, Any],
    request: PaidOperationRequest,
    provider_operation_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Write the provider operation identity before polling or retrieval.

    The receipt is intentionally separate from the attempt-completion receipt.
    A process can therefore restart after provider acknowledgement and resume
    read-only polling of the same operation without creating another paid
    submission.
    """

    path = _attempt_receipt_path(repo_root, episode_id)
    return _append_hashed(
        path,
        {
            "status": SUBMITTED_PENDING,
            "episode_id": episode_id,
            "stage": STAGE,
            "session_id": session_id,
            "attempt_id": attempt_id,
            "unit_id": unit.get("unit_id"),
            "request_id": unit.get("request_id"),
            "provider_request_id": unit.get("request_id"),
            "shot_id": unit.get("shot_id"),
            "provider": unit.get("provider"),
            "model": unit.get("model"),
            "provider_operation_id": provider_operation_id,
            "payload_sha256": request.payload_sha256,
            "request_plan_hash": request.input_artifact_hashes.get(
                "provider_request_plan"
            ),
            "submission_status": SUBMITTED_PENDING,
            "submission_certainty": "PROVEN_SUBMITTED_PENDING_OR_ACCEPTED",
            "provider_acknowledged": True,
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
        },
        hash_key="receipt_sha256",
    )


def _append_hashed(path: Path, payload: Mapping[str, Any], *, hash_key: str) -> dict[str, Any]:
    value = dict(payload)
    value.setdefault("schema_version", SCHEMA_VERSION)
    value.setdefault("event_id", str(uuid.uuid4()))
    value.setdefault("timestamp_utc", utc_now())
    value[hash_key] = canonical_sha256(value)
    append_jsonl(path, value)
    return value


def _relative(repo: Path, path: Path) -> str:
    return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")


def _read_mapping(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DesktopProviderExecutionError("EXECUTION_INPUT_UNREADABLE:" + str(path)) from exc
    if not isinstance(value, dict):
        raise DesktopProviderExecutionError("EXECUTION_INPUT_OBJECT_REQUIRED:" + str(path))
    return value


def _resolve_input(repo: Path, reference: Mapping[str, Any]) -> Path:
    raw = Path(str(reference.get("path") or ""))
    path = (raw if raw.is_absolute() else repo / raw).resolve()
    try:
        path.relative_to(repo)
    except ValueError as exc:
        raise DesktopProviderExecutionError("EXECUTION_INPUT_OUTSIDE_REPOSITORY") from exc
    expected = str(reference.get("sha256") or "").lower()
    if not path.is_file() or len(expected) != 64 or sha256_file(path) != expected:
        raise DesktopProviderExecutionError("EXECUTION_INPUT_HASH_MISMATCH:" + str(reference.get("path")))
    return path


def _provider_api_key() -> str:
    import os

    value = os.environ.get("RUNWARE_API_KEY", "").strip() or os.environ.get(
        "SIRAJ_RUNWARE_API_KEY", ""
    ).strip()
    if value:
        return value
    try:
        from src.application.windows_credentials_v1 import read_runware_api_key

        value = str(read_runware_api_key() or "").strip()
    except Exception as exc:
        raise DesktopProviderExecutionError("RUNWARE_CREDENTIAL_MANAGER_READ_FAILED") from exc
    if not value:
        raise DesktopProviderExecutionError("RUNWARE_API_KEY_REQUIRED")
    return value



# SIRAJ_RUNWARE_HTTP400_TERMINAL_REJECTION_BRIDGE_V2
def _siraj_runware_terminal_http_error_v1(
    *,
    repo_root: Path,
    episode_id: str,
    poll_attempt_id: str,
    task: Mapping[str, Any],
    expected_task_uuid: str,
    provider_operation_id: str,
) -> dict[str, Any] | None:
    # Classify an already-persisted Runware HTTP error body, fail-closed.
    # Return a replacement-eligible terminal classification only when SIRAJ's
    # canonical moderation classifier, empty data, matching task UUID, and the
    # provider's explicit no-charge statement all agree.
    error_path = (
        Path(repo_root).resolve()
        / "projects"
        / str(episode_id)
        / "orchestration"
        / "paid-operation-attempts-v1"
        / str(poll_attempt_id)
        / "http-error-response.bin"
    )
    if not error_path.is_file():
        return None

    try:
        value = json.loads(error_path.read_bytes().decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(value, Mapping):
        return None

    rejection = classify_runware_terminal_provider_rejection_v2(value, task)
    if not isinstance(rejection, Mapping):
        return None
    if rejection.get("terminal") is not True:
        return None
    if rejection.get("safe_to_reauthorize") is not True:
        return None
    if bool(rejection.get("billable_output_detected")):
        return None

    data = value.get("data")
    if not isinstance(data, list) or data:
        return None

    errors = value.get("errors")
    if not isinstance(errors, list) or not errors:
        return None

    provider_error: Mapping[str, Any] | None = None
    for candidate in errors:
        if isinstance(candidate, Mapping):
            provider_error = candidate
            break
    if provider_error is None:
        return None

    code = str(provider_error.get("code") or rejection.get("code") or "").strip()
    error_task_uuid = str(provider_error.get("taskUUID") or "").strip()
    expected_uuid = str(expected_task_uuid or "").strip()
    if not code:
        return None
    if not error_task_uuid or not expected_uuid or error_task_uuid != expected_uuid:
        return None

    text = json.dumps(value, ensure_ascii=False, sort_keys=True).lower()
    explicit_no_charge = (
        "you will not be charged" in text
        or "will not be charged for blocked videos" in text
    )
    if not explicit_no_charge:
        return None

    return {
        "status": "FAILED",
        "submission_status": "PROVIDER_REJECTED_TERMINAL",
        "provider_operation_id": str(provider_operation_id or expected_uuid),
        "response": dict(value),
        "error": (
            "RUNWARE_TERMINAL_PROVIDER_REJECTION_REAUTHORIZATION_REQUIRED:"
            + code
        ),
        "provider_rejection_code": code,
        "terminal_provider_rejection": True,
        "safe_to_reauthorize": True,
        "billable_output_detected": False,
        "explicit_no_charge_statement": True,
        "provider_error_task_uuid": error_task_uuid,
        "http_error_response_path": _relative(
            Path(repo_root).resolve(),
            error_path,
        ),
        "http_error_response_sha256": sha256_file(error_path),
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
    }


class CanonicalRunwarePaidGateway:
    """Production adapter; all network submission remains in paid gateway."""

    # Historical/fake fixtures may still contain planning-only identities, but
    # the real Runware boundary must reject them before transport.
    requires_uuid4 = True

    def __init__(
        self,
        *,
        read_only_transport: Callable[[Mapping[str, Any]], Mapping[str, Any]] | None = None,
    ) -> None:
        # Tests inject a deterministic read-only transport.  The production
        # default uses the same Runware endpoint but only sends getResponse /
        # getTaskDetails payloads; it never constructs a generation request.
        self._read_only_transport = read_only_transport

    @staticmethod
    def _read_only_evidence_path(
        repo_root: Path,
        episode_id: str,
        attempt_id: str,
        operation: str,
        task_uuid: str,
    ) -> Path:
        safe_operation = operation.replace("/", "_")
        safe_uuid = task_uuid.replace("/", "_")
        return (
            Path(repo_root).resolve()
            / "projects"
            / episode_id
            / "orchestration"
            / "paid-operation-attempts-v1"
            / attempt_id
            / "runware-read-only-reconciliation-v1"
            / f"{safe_operation}-{safe_uuid}.json"
        )

    @staticmethod
    def _persist_read_only_raw(path: Path, raw: bytes) -> None:
        """Persist lookup bytes immutably before response interpretation."""

        raw_path = Path(str(path) + ".raw")
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(
                raw_path,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                0o600,
            )
        except FileExistsError:
            if sha256_file(raw_path) != hashlib.sha256(raw).hexdigest():
                raise DesktopProviderExecutionError(
                    "RUNWARE_READ_ONLY_RAW_EVIDENCE_HASH_CONFLICT"
                )
            return
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            try:
                os.close(descriptor)
            except OSError:
                pass

    def _read_only_json(
        self,
        payload: Mapping[str, Any],
        *,
        repo_root: Path | None = None,
        episode_id: str | None = None,
        attempt_id: str | None = None,
    ) -> Mapping[str, Any]:
        validated = validate_runware_task(payload, require_uuid_v4=True)
        request_payload = dict(validated.payload)
        evidence: Path | None = None
        if repo_root is not None and episode_id and attempt_id:
            evidence = self._read_only_evidence_path(
                repo_root,
                episode_id,
                attempt_id,
                str(request_payload.get("taskType") or "lookup"),
                str(request_payload.get("taskUUID") or ""),
            )
            evidence.parent.mkdir(parents=True, exist_ok=True)
        if self._read_only_transport is not None:
            response = self._read_only_transport(request_payload)
            if not isinstance(response, Mapping):
                raise DesktopProviderExecutionError(
                    "RUNWARE_READ_ONLY_RESPONSE_OBJECT_REQUIRED"
                )
            value = dict(response)
            if evidence is not None:
                self._persist_read_only_raw(evidence, canonical_json_bytes(value))
        else:
            raw = http_json_transport(
                url="https://api.runware.ai/v1",
                method="POST",
                payload=[request_payload],
                headers={
                    "Authorization": "Bearer " + _provider_api_key(),
                    "Content-Type": "application/json",
                },
                timeout_seconds=120,
            )(lambda _status, _details: None)
            if evidence is not None:
                self._persist_read_only_raw(evidence, raw)
            try:
                decoded = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise DesktopProviderExecutionError(
                    "RUNWARE_READ_ONLY_RESPONSE_INVALID_JSON"
                ) from exc
            if not isinstance(decoded, Mapping):
                raise DesktopProviderExecutionError(
                    "RUNWARE_READ_ONLY_RESPONSE_OBJECT_REQUIRED"
                )
            value = dict(decoded)

        # Preserve the raw interpreted JSON before callers classify it.  The
        # write is optional for isolated callers but mandatory whenever an
        # original SIRAJ attempt context is supplied.
        if evidence is not None:
            if evidence.is_file():
                existing = json.loads(evidence.read_text(encoding="utf-8-sig"))
                if canonical_sha256(existing) != canonical_sha256(value):
                    raise DesktopProviderExecutionError(
                        "RUNWARE_READ_ONLY_EVIDENCE_HASH_CONFLICT"
                    )
            else:
                write_new_json(evidence, value)
        return value

    def get_task_details(
        self,
        *,
        task_uuid: str,
        repo_root: Path | None = None,
        episode_id: str | None = None,
        attempt_id: str | None = None,
    ) -> Mapping[str, Any]:
        """Read historical Runware task details for one UUID only."""

        if not is_uuid4(task_uuid):
            raise DesktopProviderExecutionError(
                "RUNWARE_TASK_UUID_UUID4_REQUIRED_FOR_LOOKUP"
            )
        return self._read_only_json(
            {"taskType": "getTaskDetails", "taskUUID": task_uuid},
            repo_root=repo_root,
            episode_id=episode_id,
            attempt_id=attempt_id,
        )

    def get_response(
        self,
        *,
        task_uuid: str,
        repo_root: Path | None = None,
        episode_id: str | None = None,
        attempt_id: str | None = None,
    ) -> Mapping[str, Any]:
        """Read the asynchronous result for the original UUID only."""

        if not is_uuid4(task_uuid):
            raise DesktopProviderExecutionError(
                "RUNWARE_TASK_UUID_UUID4_REQUIRED_FOR_LOOKUP"
            )
        return self._read_only_json(
            {"taskType": "getResponse", "taskUUID": task_uuid},
            repo_root=repo_root,
            episode_id=episode_id,
            attempt_id=attempt_id,
        )

    @staticmethod
    def _matching_item(
        payload: Mapping[str, Any],
        task_uuid: str,
        *,
        allow_singleton_fallback: bool = True,
    ) -> Mapping[str, Any] | None:
        data = payload.get("data")
        if not isinstance(data, list):
            return None
        matches = [
            row
            for row in data
            if isinstance(row, Mapping) and str(row.get("taskUUID") or "") == task_uuid
        ]
        if not matches:
            if not allow_singleton_fallback:
                return None
            # A provider may return a server-side operation ID that differs
            # from the client planning UUID.  Each SIRAJ submission contains
            # one task, so the sole returned row is still attributable to
            # this request and becomes the durable operation identity.
            rows = [row for row in data if isinstance(row, Mapping)]
            return rows[-1] if len(rows) == 1 else None
        for row in reversed(matches):
            if row.get("status") == "success" or row.get("imageURL") or row.get("videoURL"):
                return row
        return matches[-1]

    @staticmethod
    def _provider_operation_id(
        payload: Mapping[str, Any], item: Mapping[str, Any] | None,
    ) -> str | None:
        """Return only an identifier actually returned by the provider.

        The planning ``taskUUID`` sent in the request is not evidence of
        submission.  An operation identity is accepted only when it appears
        in the provider acknowledgement/result payload.
        """

        candidates: list[Any] = []
        if isinstance(item, Mapping):
            candidates.extend(
                item.get(key)
                for key in ("taskUUID", "taskUuid", "job_id", "jobId", "request_id")
            )
        data = payload.get("data")
        if isinstance(data, Mapping):
            candidates.extend(
                data.get(key)
                for key in ("taskUUID", "taskUuid", "job_id", "jobId", "request_id")
            )
        candidates.extend(
            payload.get(key)
            for key in ("taskUUID", "taskUuid", "job_id", "jobId", "request_id")
        )
        for value in candidates:
            value_text = str(value or "").strip()
            # Runware's client task identity is UUID v4.  Do not persist a
            # server field that merely looks like an operation label; an
            # invalid identifier cannot support safe historical lookup.
            if value_text and is_uuid4(value_text):
                return value_text
        return None

    @staticmethod
    def _write_asset(path: Path, payload: bytes) -> str:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            if sha256_file(path) != hashlib.sha256(payload).hexdigest():
                raise DesktopProviderExecutionError("PROVIDER_ASSET_HASH_CONFLICT")
            return sha256_file(path)
        try:
            with os.fdopen(descriptor, "wb", closefd=True) as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
        finally:
            # fdopen owns the descriptor on the normal path.  The guard is
            # intentionally best-effort for an exception before fdopen.
            try:
                os.close(descriptor)
            except OSError:
                pass
        digest = sha256_file(path)
        if not digest:
            raise DesktopProviderExecutionError("PROVIDER_ASSET_HASH_MISSING")
        return digest

    def _download_asset(
        self,
        request: PaidOperationRequest,
        unit: Mapping[str, Any],
        attempt_id: str,
        url: str,
    ) -> tuple[str, str]:
        url_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        download_request = PaidOperationRequest(
            repo_root=request.repo_root,
            episode_id=request.episode_id,
            stage=request.stage,
            operation_type="RUNWARE_ASSET_DOWNLOAD",
            provider="RUNWARE",
            model="ASSET_DOWNLOAD",
            provider_contract_version=request.provider_contract_version,
            payload={"url_sha256": url_hash},
            input_artifact_hashes={
                **dict(request.input_artifact_hashes),
                "provider_attempt_id": attempt_id,
                "asset_url_sha256": url_hash,
            },
            master_authorization_reference=request.master_authorization_reference,
            operation_nonce=attempt_id + ":download",
        )
        downloaded = execute_paid_bytes(
            download_request,
            http_download_transport(
                url=url,
                headers={"User-Agent": "SIRAJ-Desktop-Canonical-Provider-Execution/1"},
                timeout_seconds=240,
            ),
        )
        raw = downloaded.raw_response_path.read_bytes()
        extension = ".mp4" if unit.get("media_kind") == "RUNWARE_VIDEO" else ".jpg"
        asset = (
            Path(request.repo_root).resolve()
            / "projects"
            / request.episode_id
            / "orchestration"
            / "provider-execution-assets-v1"
            / (str(unit.get("unit_id") or attempt_id) + extension)
        )
        return _relative(Path(request.repo_root).resolve(), asset), self._write_asset(asset, raw)

    def submit(
        self,
        *,
        request: PaidOperationRequest,
        unit: Mapping[str, Any],
        attempt_id: str,
    ) -> tuple[PaidOperationResult, dict[str, Any]]:
        task = validate_runware_task(
            request.payload,
            require_uuid_v4=True,
        ).payload
        from src.application.pr01_production_readiness_v1 import (
            enforce_pr01_desktop_paid_gate,
        )

        enforce_pr01_desktop_paid_gate(request=request, unit=unit)
        # The contract validator rejects Veo negativePrompt before transport.
        if unit.get("model", "").startswith("google:veo@3.1") and "negativePrompt" in task:
            raise DesktopProviderExecutionError("VEO31_NEGATIVE_PROMPT_FIELD_FORBIDDEN")
        paid_result, payload = execute_paid_json(
            request,
            http_json_transport(
                url="https://api.runware.ai/v1",
                method="POST",
                payload=[task],
                headers={
                    "Authorization": "Bearer " + _provider_api_key(),
                    "Content-Type": "application/json",
                },
                timeout_seconds=240,
            ),
        )
        task_uuid = str(task.get("taskUUID") or "")
        item = self._matching_item(payload, task_uuid)
        provider_operation_id = self._provider_operation_id(payload, item)
        if provider_operation_id:
            # This is the first durable provider-side identity.  It is
            # written before any polling or asset retrieval begins.
            record_provider_operation_id(
                request,
                provider_operation_id,
                details={
                    "provider": request.provider,
                    "model": request.model,
                    "operation_type": request.operation_type,
                },
            )
            _persist_provider_operation_id(
                repo_root=request.repo_root,
                episode_id=request.episode_id,
                attempt_id=attempt_id,
                unit=unit,
                request=request,
                provider_operation_id=provider_operation_id,
            )
        if provider_operation_id is None and not isinstance(payload.get("data"), list):
            # Do not turn an unrecognisable response into a 20-minute polling
            # loop.  There is no durable operation identity to reconcile.
            return {
                "status": "UNKNOWN",
                "response": dict(payload),
                "error": "PROVIDER_RESPONSE_SCHEMA_MISMATCH",
                "submission_status": "UNKNOWN",
            }
        if provider_operation_id is None and item is None:
            return {
                "status": "UNKNOWN",
                "response": dict(payload),
                "error": "PROVIDER_OPERATION_ID_MISSING",
                "submission_status": "UNKNOWN",
            }
        poll_index = 0
        poll_task_uuid = provider_operation_id or task_uuid
        # Runware generation is asynchronous.  Polling this same task UUID is
        # recovery of the already-submitted operation, not a retry or a new
        # generation request.  Every poll still crosses the same paid gateway.
        while item is None or not (item.get("status") == "success" or item.get("imageURL") or item.get("videoURL")):
            if item is not None and str(item.get("status") or "").lower() == "error":
                return {
                    "status": "FAILED",
                    "response": dict(payload),
                    "error": str(item.get("message") or "RUNWARE_TASK_ERROR"),
                    "provider_operation_id": provider_operation_id,
                }
            poll_index += 1
            if poll_index > 240:
                return {
                    "status": "UNKNOWN",
                    "response": dict(payload),
                    "error": "RUNWARE_POLLING_TIMEOUT_NO_AUTOMATIC_RESUBMISSION",
                    "provider_operation_id": provider_operation_id,
                    "submission_status": SUBMITTED_PENDING
                    if provider_operation_id
                    else "UNKNOWN",
                }
            time.sleep(5)
            poll_payload = {"taskType": "getResponse", "taskUUID": poll_task_uuid}
            poll_request = PaidOperationRequest(
                repo_root=request.repo_root,
                episode_id=request.episode_id,
                stage=request.stage,
                operation_type="RUNWARE_POLL",
                provider="RUNWARE",
                model="getResponse",
                provider_contract_version=request.provider_contract_version,
                payload=poll_payload,
                input_artifact_hashes={
                    **dict(request.input_artifact_hashes),
                    "provider_attempt_id": attempt_id,
                },
                master_authorization_reference=request.master_authorization_reference,
                operation_nonce=attempt_id + f":poll:{poll_index}",
            )
            try:
                _, payload = execute_paid_json(
                    poll_request,
                    http_json_transport(
                        url="https://api.runware.ai/v1",
                        method="POST",
                        payload=[poll_payload],
                        headers={
                            "Authorization": "Bearer " + _provider_api_key(),
                            "Content-Type": "application/json",
                        },
                        timeout_seconds=240,
                    ),
                )
            except Exception:
                terminal_rejection = _siraj_runware_terminal_http_error_v1(
                    repo_root=request.repo_root,
                    episode_id=request.episode_id,
                    poll_attempt_id=poll_request.immutable_attempt_id,
                    task=task,
                    expected_task_uuid=poll_task_uuid,
                    provider_operation_id=provider_operation_id,
                )
                if terminal_rejection is not None:
                    return terminal_rejection
                raise

            item = self._matching_item(payload, poll_task_uuid)
            provider_operation_id = provider_operation_id or self._provider_operation_id(
                payload, item
            )
            poll_task_uuid = provider_operation_id or poll_task_uuid
            if item is None and not isinstance(payload.get("data"), list):
                return {
                    "status": "UNKNOWN",
                    "response": dict(payload),
                    "error": "RUNWARE_POLL_RESPONSE_SCHEMA_MISMATCH",
                    "provider_operation_id": provider_operation_id,
                    "submission_status": SUBMITTED_PENDING
                    if provider_operation_id
                    else "UNKNOWN",
                }
        url_key = "videoURL" if unit.get("media_kind") == "RUNWARE_VIDEO" else "imageURL"
        url = str(item.get(url_key) or "").strip()
        if not url:
            return {
                "status": "UNKNOWN",
                "response": dict(payload),
                "error": "PROVIDER_ASSET_URL_MISSING",
                "provider_operation_id": provider_operation_id,
                "submission_status": SUBMITTED_PENDING
                if provider_operation_id
                else "UNKNOWN",
            }
        asset_path, asset_sha = self._download_asset(request, unit, attempt_id, url)
        return {
            "status": "COMPLETE",
            "response": dict(payload),
            "asset_url": url,
            "asset_path": asset_path,
            "asset_sha256": asset_sha,
            "actual_cost_usd": item.get("cost"),
            "poll_count": poll_index,
            "initial_attempt_id": paid_result.attempt_id,
            "provider_operation_id": provider_operation_id,
            "submission_status": "COMPLETE",
        }

    def reconcile_submitted_operation(
        self,
        *,
        request: PaidOperationRequest,
        unit: Mapping[str, Any],
        attempt_id: str,
        provider_operation_id: str,
        max_polls: int = 240,
        poll_interval_seconds: float = 5.0,
    ) -> Mapping[str, Any]:
        """Poll one already-acknowledged operation without submitting it.

        This method is intentionally separate from :meth:`submit`.  A caller
        must supply a durable operation ID from the original attempt; there
        is no path that constructs a generation task or silently falls back
        to a new submission.
        """

        operation_id = str(provider_operation_id or "").strip()
        if not operation_id:
            raise DesktopProviderExecutionError(
                "PROVIDER_OPERATION_ID_REQUIRED_FOR_RECONCILIATION"
            )
        expected_operation_id = str(request.payload.get("taskUUID") or "").strip()
        if expected_operation_id != operation_id or not is_uuid4(expected_operation_id):
            raise DesktopProviderExecutionError(
                "RUNWARE_OPERATION_ID_BINDING_MISMATCH"
            )
        polls = max(1, int(max_polls))
        for poll_index in range(1, polls + 1):
            try:
                payload = self.get_response(
                    task_uuid=operation_id,
                    repo_root=request.repo_root,
                    episode_id=request.episode_id,
                    attempt_id=attempt_id,
                )
            except Exception as exc:
                return {
                    "status": "UNKNOWN",
                    "submission_status": SUBMITTED_PENDING,
                    "provider_operation_id": operation_id,
                    "poll_count": poll_index,
                    "error": str(exc),
                    "automatic_paid_retry": False,
                    "automatic_paid_resubmission": False,
                }
            # Historical reconciliation must never attribute a singleton
            # response to the original task when its UUID does not match.
            item = self._matching_item(
                payload,
                operation_id,
                allow_singleton_fallback=False,
            )
            if item is not None and str(item.get("status") or "").lower() == "error":
                return {
                    "status": "FAILED",
                    "submission_status": "FAILED",
                    "provider_operation_id": operation_id,
                    "poll_count": poll_index,
                    "response": dict(payload),
                    "error": str(item.get("message") or "RUNWARE_TASK_ERROR"),
                }
            url_key = "videoURL" if unit.get("media_kind") == "RUNWARE_VIDEO" else "imageURL"
            url = str(item.get(url_key) or "").strip() if item is not None else ""
            if url:
                try:
                    asset_path, asset_sha = self._download_asset(
                        request, unit, attempt_id, url
                    )
                except Exception as exc:
                    return {
                        "status": "FAILED",
                        "submission_status": "FAILED",
                        "provider_operation_id": operation_id,
                        "poll_count": poll_index,
                        "response": dict(payload),
                        "error": "RESULT_DOWNLOAD_FAILURE:" + str(exc),
                    }
                return {
                    "status": "COMPLETE",
                    "submission_status": "COMPLETE",
                    "provider_operation_id": operation_id,
                    "poll_count": poll_index,
                    "response": dict(payload),
                    "asset_url": url,
                    "asset_path": asset_path,
                    "asset_sha256": asset_sha,
                }
            if poll_index < polls and poll_interval_seconds > 0:
                time.sleep(float(poll_interval_seconds))
        return {
            "status": "UNKNOWN",
            "submission_status": SUBMITTED_PENDING,
            "provider_operation_id": operation_id,
            "poll_count": polls,
            "error": "RUNWARE_RECONCILIATION_POLLING_TIMEOUT",
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
        }


class FakePaidProviderGateway:
    """Deterministic offline gateway used by readiness/E2E tests only."""

    requires_uuid4 = False

    def __init__(
        self,
        *,
        fail_at: int | None = None,
        unknown_at: int | None = None,
        response_factory: Callable[[Mapping[str, Any], int], Mapping[str, Any]] | None = None,
    ) -> None:
        self.fail_at = fail_at
        self.unknown_at = unknown_at
        self.response_factory = response_factory
        self.calls: list[dict[str, Any]] = []

    @property
    def provider_calls(self) -> int:
        return len(self.calls)

    def submit(
        self,
        *,
        request: PaidOperationRequest,
        unit: Mapping[str, Any],
        attempt_id: str,
    ) -> Mapping[str, Any]:
        ordinal = len(self.calls) + 1
        self.calls.append(
            {
                "ordinal": ordinal,
                "attempt_id": attempt_id,
                "unit_id": unit.get("unit_id"),
                "request_id": unit.get("request_id"),
                "provider": request.provider,
                "model": request.model,
            }
        )
        if self.fail_at == ordinal:
            return {"status": "FAILED", "error": "FAKE_PROVIDER_FAILURE"}
        if self.unknown_at == ordinal:
            return {"status": "UNKNOWN", "error": "FAKE_NETWORK_RESULT_UNKNOWN"}
        if self.response_factory is not None:
            return dict(self.response_factory(unit, ordinal))
        return {
            "status": "COMPLETE",
            "response": {
                "data": [
                    {
                        "taskUUID": str(request.payload.get("taskUUID") or ""),
                        "mediaKind": unit.get("media_kind"),
                        "fake": True,
                    }
                ]
            },
        }


class FakeAsyncPaidProviderGateway(FakePaidProviderGateway):
    """Offline async provider with exactly one submission per operation.

    The fake records an acknowledged operation ID before returning a pending
    or completed result.  Its ``poll_calls`` counter models read-only polling
    of that same operation and never increments ``provider_calls``.
    """

    def __init__(
        self,
        *,
        polls_before_complete: int = 1,
        polling_timeout: bool = False,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.polls_before_complete = max(0, int(polls_before_complete))
        self.polling_timeout = bool(polling_timeout)
        self.poll_calls = 0
        self.operation_ids: dict[str, str] = {}

    def submit(
        self,
        *,
        request: PaidOperationRequest,
        unit: Mapping[str, Any],
        attempt_id: str,
    ) -> Mapping[str, Any]:
        ordinal = len(self.calls) + 1
        self.calls.append(
            {
                "ordinal": ordinal,
                "attempt_id": attempt_id,
                "unit_id": unit.get("unit_id"),
                "request_id": unit.get("request_id"),
                "provider": request.provider,
                "model": request.model,
            }
        )
        operation_id = "fake-operation-" + attempt_id
        self.operation_ids[attempt_id] = operation_id
        record_provider_operation_id(
            request,
            operation_id,
            details={
                "provider": request.provider,
                "model": request.model,
                "operation_type": request.operation_type,
                "fake_provider": True,
            },
        )
        _persist_provider_operation_id(
            repo_root=request.repo_root,
            episode_id=request.episode_id,
            attempt_id=attempt_id,
            unit=unit,
            request=request,
            provider_operation_id=operation_id,
        )
        if self.polling_timeout:
            self.poll_calls += 1
            return {
                "status": "UNKNOWN",
                "submission_status": SUBMITTED_PENDING,
                "provider_operation_id": operation_id,
                "error": "FAKE_POLLING_TIMEOUT",
            }
        for _ in range(self.polls_before_complete):
            self.poll_calls += 1
        return {
            "status": "COMPLETE",
            "submission_status": "COMPLETE",
            "provider_operation_id": operation_id,
            "poll_count": self.polls_before_complete,
            "response": {
                "data": [
                    {
                        "taskUUID": operation_id,
                        "status": "success",
                        "mediaKind": unit.get("media_kind"),
                        "fake": True,
                    }
                ]
            },
        }


def _attempt_id(
    binding: ProviderExecutionBinding,
    unit: Mapping[str, Any],
    *,
    first_submission_reconciliation_id: str | None = None,
) -> str:
    identity = canonical_sha256(
        {
            "episode_id": binding.episode_id,
            "stage": binding.stage,
            "request_plan_hash": binding.request_plan_hash,
            "unit_id": unit.get("unit_id"),
            "request_id": unit.get("request_id"),
            "provider": unit.get("provider"),
            "model": unit.get("model"),
            "payload_sha256": unit.get("payload_sha256"),
            # A human evidence reconciliation explicitly clears one false
            # UNKNOWN.  The next valid submission is a new first attempt and
            # must not reuse the historical attempt identity.
            "first_submission_reconciliation_id": first_submission_reconciliation_id,
        }
    )
    return str(uuid.uuid5(ATTEMPT_NAMESPACE, identity))


def _normalise_gateway_result(value: Any) -> tuple[str, Mapping[str, Any]]:
    if isinstance(value, PaidOperationResult):
        if value.status != "COMPLETE":
            return str(value.status), value.as_dict()
        return "COMPLETE", value.as_dict()
    if isinstance(value, Mapping):
        status = str(value.get("status") or "COMPLETE").upper()
        return status, value
    raise DesktopProviderExecutionError("PROVIDER_GATEWAY_RESULT_INVALID")



# SIRAJ_PROVIDER_EXECUTION_STAGE_RECOVERY_V3
def _siraj_recovery_jsonl_rows_v2(path: Path) -> list[dict[str, Any]]:
    import json as _siraj_json_v2

    target = Path(path)
    if not target.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for raw in target.read_text(encoding="utf-8-sig").splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            value = _siraj_json_v2.loads(raw)
        except Exception:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def append_jsonl(
    path: Path,
    value: Mapping[str, Any],
    *args: Any,
    **kwargs: Any,
) -> Any:
    # Preserve append-only receipts while suppressing one duplicate stage start.
    if isinstance(value, Mapping) and str(value.get("status") or "") == "STAGE_STARTED":
        episode_id = str(value.get("episode_id") or "")
        stage = str(value.get("stage") or "")
        session_id = str(value.get("session_id") or "")
        if episode_id and stage and session_id:
            for existing in _siraj_recovery_jsonl_rows_v2(Path(path)):
                if (
                    str(existing.get("status") or "") == "STAGE_STARTED"
                    and str(existing.get("episode_id") or "") == episode_id
                    and str(existing.get("stage") or "") == stage
                    and str(existing.get("session_id") or "") == session_id
                ):
                    return existing
    return _siraj_base_append_jsonl_v2(path, value, *args, **kwargs)


def _siraj_recovery_request_id_v2(value: Any) -> str:
    if isinstance(value, Mapping):
        return str(
            value.get("request_id")
            or value.get("unit_id")
            or value.get("queue_id")
            or ""
        ).strip()
    return str(value or "").strip()


def _siraj_provider_execution_recovery_session_v2(
    repo_root: Path,
    episode_id: str,
    reconciliation: Mapping[str, Any],
) -> str | None:
    # Return the newest unfinished session only when reconciliation is safe.
    root = (
        Path(repo_root)
        / "projects"
        / episode_id
        / "orchestration"
        / "provider-execution-v1"
    )
    rows = _siraj_recovery_jsonl_rows_v2(root / STAGE_RECEIPT_LEDGER)

    starts = [
        row
        for row in rows
        if str(row.get("stage") or "") == STAGE
        and str(row.get("status") or "") == "STAGE_STARTED"
        and str(row.get("session_id") or "").strip()
    ]
    if not starts:
        return None

    pending = reconciliation.get("pending_attempts") or []
    provider_operation_ids = reconciliation.get("provider_operation_ids") or {}
    request_attempts = reconciliation.get("request_attempts") or {}
    pending_ids: set[str] = set()
    for item in pending:
        request_id = _siraj_recovery_request_id_v2(item)
        if request_id:
            pending_ids.add(request_id)
        if isinstance(item, Mapping):
            if not str(item.get("provider_operation_id") or "").strip():
                return None
        elif not str(provider_operation_ids.get(request_id) or "").strip():
            return None

    unsafe_blocked: list[Any] = []
    for item in reconciliation.get("blocked_requests") or []:
        request_id = _siraj_recovery_request_id_v2(item)
        pending_attempt_id = str(request_attempts.get(request_id) or "")
        if request_id and (
            request_id in pending_ids or pending_attempt_id in pending_ids
        ):
            continue
        unsafe_blocked.append(item)
    if unsafe_blocked:
        return None

    if reconciliation.get("unknown_blocking_requests"):
        return None

    completed_statuses = {
        "STAGE_COMPLETED",
        "COMPLETED",
        "COMPLETE",
    }
    for start in reversed(starts):
        session_id = str(start.get("session_id") or "").strip()
        session_rows = [
            row
            for row in rows
            if str(row.get("session_id") or "") == session_id
        ]
        if any(
            str(row.get("status") or "") in completed_statuses
            for row in session_rows
        ):
            continue
        return session_id
    return None


# SIRAJ_EP002_ONE_UNIT_PAID_SCOPE_PAUSE_GUARD_V2
def _siraj_scope_receipt_valid_v2(row: Mapping[str, Any]) -> bool:
    if not isinstance(row, Mapping):
        return False
    stored = str(row.get("receipt_sha256") or "")
    if not stored:
        return False
    unsigned = dict(row)
    unsigned.pop("receipt_sha256", None)
    return stored == canonical_sha256(unsigned)


def _siraj_scope_result_valid_v2(
    repo_root: Path,
    result_path_value: Any,
    *,
    attempt_id: str,
    unit_id: str,
    provider: str,
    model: str,
    request_plan_hash: str,
    expected_result_sha256: str,
) -> bool:
    repo = Path(repo_root).resolve()
    raw = Path(str(result_path_value or ""))
    if not str(raw):
        return False
    candidate = raw.resolve() if raw.is_absolute() else (repo / raw).resolve()
    try:
        candidate.relative_to(repo)
    except ValueError:
        return False
    if not candidate.is_file():
        return False
    try:
        value = json.loads(candidate.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(value, Mapping):
        return False
    if str(value.get("status") or "") != "RESULT_PERSISTED":
        return False
    if str(value.get("attempt_id") or "") != attempt_id:
        return False
    if str(value.get("unit_id") or "") != unit_id:
        return False
    if str(value.get("provider") or "") != provider:
        return False
    if str(value.get("model") or "") != model:
        return False
    binding_value = value.get("binding")
    if not isinstance(binding_value, Mapping):
        return False
    if str(binding_value.get("request_plan_hash") or "") != request_plan_hash:
        return False

    stored_result_hash = str(value.get("result_sha256") or "")
    if not stored_result_hash or stored_result_hash != expected_result_sha256:
        return False
    unsigned_result = dict(value)
    unsigned_result.pop("result_sha256", None)
    if canonical_sha256(unsigned_result) != stored_result_hash:
        return False
    return True


def _siraj_durable_completed_provider_units_v2(
    repo_root: Path,
    episode_id: str,
    provider_units: list[Mapping[str, Any]],
    binding: Any,
) -> dict[str, str]:
    """
    Return only provider units whose CURRENT approved-plan success is proven by
    an append-only intent -> result -> completion chain plus the persisted,
    canonically hashed result object.

    Historical UNKNOWN/FAILED rows do not defeat a later proven success, and
    conversely a bare ATTEMPT_COMPLETED row is not enough by itself.
    """
    repo = Path(repo_root).resolve()
    binding_dict = (
        dict(binding.as_dict())
        if hasattr(binding, "as_dict")
        else dict(binding)
    )
    request_plan_hash = str(binding_dict.get("request_plan_hash") or "")
    if not request_plan_hash:
        raise DesktopProviderExecutionError(
            "PAID_SCOPE_BINDING_REQUEST_PLAN_HASH_REQUIRED"
        )

    current_units: dict[str, Mapping[str, Any]] = {}
    for raw_unit in provider_units:
        unit = dict(raw_unit)
        unit_id = str(unit.get("request_id") or unit.get("unit_id") or "")
        if not unit_id:
            raise DesktopProviderExecutionError(
                "PAID_SCOPE_PROVIDER_UNIT_ID_REQUIRED"
            )
        if unit_id in current_units:
            raise DesktopProviderExecutionError(
                "PAID_SCOPE_DUPLICATE_PROVIDER_UNIT:" + unit_id
            )
        current_units[unit_id] = unit

    ledger_path = (
        repo
        / "projects"
        / str(episode_id)
        / "orchestration"
        / "provider-execution-v1"
        / "provider-execution-attempt-receipts-v1.jsonl"
    )
    rows = read_jsonl(ledger_path)
    interesting = {
        "ATTEMPT_INTENT_PERSISTED",
        "RESULT_PERSISTED",
        "ATTEMPT_COMPLETED",
    }
    grouped: dict[str, dict[str, dict[str, list[dict[str, Any]]]]] = {}

    for raw_row in rows:
        if not isinstance(raw_row, Mapping):
            continue
        status = str(raw_row.get("status") or "")
        if status not in interesting:
            continue
        unit_id = str(
            raw_row.get("request_id")
            or raw_row.get("unit_id")
            or raw_row.get("provider_request_id")
            or ""
        )
        if unit_id not in current_units:
            continue
        if not _siraj_scope_receipt_valid_v2(raw_row):
            raise DesktopProviderExecutionError(
                "PAID_SCOPE_RECEIPT_HASH_INVALID:"
                + unit_id
                + ":"
                + status
            )
        attempt_id = str(raw_row.get("attempt_id") or "")
        if not attempt_id:
            raise DesktopProviderExecutionError(
                "PAID_SCOPE_RECEIPT_ATTEMPT_ID_REQUIRED:"
                + unit_id
                + ":"
                + status
            )
        grouped.setdefault(unit_id, {}).setdefault(attempt_id, {}).setdefault(
            status, []
        ).append(dict(raw_row))

    proven: dict[str, str] = {}
    for unit_id, unit in current_units.items():
        provider = str(unit.get("provider") or "")
        model = str(unit.get("model") or "")
        planned_payload = str(unit.get("payload_sha256") or "")
        successful_attempts: list[str] = []

        for attempt_id, statuses in grouped.get(unit_id, {}).items():
            intents = statuses.get("ATTEMPT_INTENT_PERSISTED", [])
            results = statuses.get("RESULT_PERSISTED", [])
            completions = statuses.get("ATTEMPT_COMPLETED", [])
            if len(intents) != 1 or len(results) != 1 or len(completions) != 1:
                continue

            intent = intents[0]
            result_receipt = results[0]
            completion = completions[0]

            intent_planned_payload = str(
                intent.get("planned_payload_sha256")
                or (intent.get("settings") or {}).get("payload_sha256")
                or ""
            )
            if (
                str(intent.get("request_plan_hash") or "")
                != request_plan_hash
            ):
                continue
            if str(intent.get("provider") or "") != provider:
                continue
            if str(intent.get("model") or "") != model:
                continue
            if not planned_payload or intent_planned_payload != planned_payload:
                continue

            result_path_value = str(result_receipt.get("result_path") or "")
            result_sha = str(result_receipt.get("result_sha256") or "")
            if not result_path_value or not result_sha:
                continue
            if str(completion.get("result_path") or "") != result_path_value:
                continue
            if str(completion.get("result_sha256") or "") != result_sha:
                continue

            if not _siraj_scope_result_valid_v2(
                repo,
                result_path_value,
                attempt_id=attempt_id,
                unit_id=unit_id,
                provider=provider,
                model=model,
                request_plan_hash=request_plan_hash,
                expected_result_sha256=result_sha,
            ):
                continue
            successful_attempts.append(attempt_id)

        if len(successful_attempts) > 1:
            raise DesktopProviderExecutionError(
                "PAID_SCOPE_MULTIPLE_CURRENT_PLAN_SUCCESSES:"
                + unit_id
                + ":"
                + ",".join(sorted(successful_attempts))
            )
        if len(successful_attempts) == 1:
            proven[unit_id] = successful_attempts[0]

    return proven


# SIRAJ_EP002_VEO_MENA_ALLOW_ADULT_RUNTIME_POLICY_V1
def _siraj_ep002_veo_mena_allow_adult_runtime_policy_v1(
    episode_id,
    unit,
    task,
):
    """
    Runtime-only provider compatibility transform for EP002 Veo 3.1 Lite.

    It deliberately does NOT mutate the persisted preflight/request-plan
    artifacts or their hashes. The transform is applied immediately before
    PaidOperationRequest construction and is recorded in the durable intent
    receipt.

    Current production evidence established that Google rejects
    personGeneration=dont_allow for this effective MENA execution context,
    while the exact same target succeeded with allow_adult.
    """
    if str(episode_id) != "episode-002-adam-temptation-fall-repentance":
        return task, None
    if str(unit.get("provider") or "").upper() != "RUNWARE":
        return task, None
    if str(unit.get("model") or "") != "google:veo@3.1-lite":
        return task, None
    if not isinstance(task, dict):
        raise DesktopProviderExecutionError(
            "EP002_VEO_MENA_POLICY_TASK_OBJECT_REQUIRED"
        )

    provider_settings = task.get("providerSettings")
    if not isinstance(provider_settings, dict):
        raise DesktopProviderExecutionError(
            "EP002_VEO_MENA_POLICY_PROVIDER_SETTINGS_REQUIRED"
        )
    google = provider_settings.get("google")
    if not isinstance(google, dict):
        raise DesktopProviderExecutionError(
            "EP002_VEO_MENA_POLICY_GOOGLE_SETTINGS_REQUIRED"
        )

    current = str(google.get("personGeneration") or "")
    if current not in {"dont_allow", "allow_adult"}:
        raise DesktopProviderExecutionError(
            "EP002_VEO_MENA_POLICY_UNEXPECTED_PERSON_GENERATION:"
            + (current or "MISSING")
        )

    metadata = {
        "policy_id": "SIRAJ_EP002_VEO_MENA_ALLOW_ADULT_RUNTIME_POLICY_V1",
        "episode_id": str(episode_id),
        "provider": "RUNWARE",
        "model": "google:veo@3.1-lite",
        "path": "providerSettings.google.personGeneration",
        "from": current,
        "to": "allow_adult",
        "applied": current == "dont_allow",
        "preflight_artifact_mutated": False,
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
    }

    if current == "allow_adult":
        return task, metadata

    revised = dict(task)
    revised_provider_settings = dict(provider_settings)
    revised_google = dict(google)
    revised_google["personGeneration"] = "allow_adult"
    revised_provider_settings["google"] = revised_google
    revised["providerSettings"] = revised_provider_settings

    observed = str(
        (
            revised.get("providerSettings", {})
            .get("google", {})
            .get("personGeneration")
            or ""
        )
    )
    if observed != "allow_adult":
        raise DesktopProviderExecutionError(
            "EP002_VEO_MENA_POLICY_OVERRIDE_FAILED"
        )
    return revised, metadata


from src.application.provider_remaining_stage_authorization_v1 import (
    remaining_stage_authorization_for_episode,
    validate_remaining_stage_authorization_current,
)

# SIRAJ_EP002_REMAINING_STAGE_AUTHORIZATION_V1
class CanonicalDesktopProviderExecutionExecutor:
    """Execute the exact persisted provider plan after Desktop review."""

    def __init__(
        self,
        repo_root: Path,
        episode_id: str = EPISODE_002,
        *,
        gateway: ProviderGateway | None = None,
        fault_injector: Callable[[str], None] | None = None,
        progress_callback: Callable[[Mapping[str, Any]], None] | None = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.episode_id = episode_id
        self.gateway = gateway or CanonicalRunwarePaidGateway()
        self.fault_injector = fault_injector
        self.progress_callback = progress_callback

    def _fault(self, point: str) -> None:
        if self.fault_injector is not None:
            self.fault_injector(point)

    def _binding(self, review: MediaCostPreflightReview) -> ProviderExecutionBinding:
        try:
            expected = review_binding(review, self.repo_root)
        except Exception as exc:
            raise DesktopProviderExecutionError("EXECUTION_REVIEW_BINDING_INVALID") from exc
        receipt = read_latest_reack_receipt(
            self.repo_root,
            self.episode_id,
            binding=expected,
        )
        if not receipt or receipt.get("resulting_authorization_status") != VALID_STATUS:
            raise DesktopProviderExecutionError("COST_ENVELOPE_REACK_REQUIRED")
        envelope = expected["maximum_cost_envelope"]
        return ProviderExecutionBinding(
            episode_id=self.episode_id,
            stage=STAGE,
            preflight_file_sha256=str(expected["preflight_result"]["file_sha256"]),
            preflight_payload_sha256=str(expected["preflight_result"]["payload_sha256"]),
            media_plan_sha256=str(expected["media_plan_sha256"]),
            provider_request_plan_sha256=str(expected["provider_request_plan_sha256"]),
            pricing_registry_sha256=str(expected["pricing_registry_sha256"]),
            pricing_registry_version=str(expected["pricing_registry_version"]),
            reack_receipt_id=str(receipt.get("receipt_id") or ""),
            maximum_cost=float(envelope["amount"]),
            currency=str(envelope["currency"]),
            ledger_head_sha256=str(expected["ledger_head_sha256"]),
            creative_overlay_sha256=str(expected["creative_overlay_sha256"]),
            structural_fingerprint=str(expected["structural_fingerprint"]),
            request_plan_hash=str(expected["provider_request_plan_sha256"]),
        )

    def _validate_reviewed_state(
        self,
        intent: DesktopResumeIntent,
        review: MediaCostPreflightReview,
        binding: ProviderExecutionBinding,
    ) -> None:
        state = read_desktop_episode_state(self.repo_root, self.episode_id)
        if state.current_stage != STAGE:
            raise DesktopProviderExecutionError("INVALID_CURRENT_STAGE:" + state.current_stage)
        if intent.episode_id != self.episode_id or intent.first_stage != STAGE:
            raise DesktopProviderExecutionError("RESUME_INTENT_BINDING_INVALID")
        if intent.source != DESKTOP_SOURCE:
            raise DesktopProviderExecutionError("PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY")
        if intent.ledger_head_sha256 != state.ledger_head_sha256:
            raise ProviderExecutionStaleStateError("STALE_STATE_REVIEW_REQUIRED")
        if intent.promoted_overlay_sha256 != binding.creative_overlay_sha256:
            raise ProviderExecutionStaleStateError("STALE_STATE_REVIEW_REQUIRED")
        if intent.structural_fingerprint != binding.structural_fingerprint:
            raise ProviderExecutionStaleStateError("STALE_STATE_REVIEW_REQUIRED")
        if binding.ledger_head_sha256 != state.ledger_head_sha256:
            raise ProviderExecutionStaleStateError("STALE_STATE_REVIEW_REQUIRED")
        if review.production_authorization != VALID_STATUS or not review.provider_execution_allowed:
            raise DesktopProviderExecutionError("COST_ENVELOPE_REACK_REQUIRED")

    def _prompt_items(self, review: MediaCostPreflightReview) -> dict[str, dict[str, Any]]:
        ref = review.input_artifacts.get("legacy_provider_ready_prompt_plan")
        if not isinstance(ref, Mapping):
            raise DesktopProviderExecutionError("PROMPT_PLAN_REFERENCE_MISSING")
        path = _resolve_input(self.repo_root, ref)
        value = _read_mapping(path)
        items = value.get("items")
        if not isinstance(items, list):
            raise DesktopProviderExecutionError("PROMPT_PLAN_ITEMS_REQUIRED")
        result: dict[str, dict[str, Any]] = {}
        for item in items:
            if not isinstance(item, Mapping) or not str(item.get("shot_id") or ""):
                raise DesktopProviderExecutionError("PROMPT_PLAN_ITEM_INVALID")
            result[str(item["shot_id"])] = dict(item)
        return result

    @staticmethod
    def _runtime_runware_task_uuid(
        attempt_id: str,
        unit: Mapping[str, Any],
    ) -> str:
        # Provider identity is separate from the persisted planning identity.
        # Derive a stable UUID-v4-shaped value from the immutable SIRAJ attempt
        # so restart/reconciliation resolves to the same Runware task UUID.
        value = str(attempt_id or "").strip()
        if not value:
            raise DesktopProviderExecutionError(
                "RUNWARE_RUNTIME_ATTEMPT_ID_REQUIRED"
            )
        material = canonical_sha256(
            {
                "schema_version": "siraj-runware-runtime-taskuuid-v2",
                "attempt_id": value,
                "unit_id": unit.get("unit_id"),
                "request_id": unit.get("request_id"),
                "provider": unit.get("provider"),
                "model": unit.get("model"),
                "planned_payload_sha256": unit.get("payload_sha256"),
            }
        )
        raw = bytearray(bytes.fromhex(material[:32]))
        raw[6] = (raw[6] & 0x0F) | 0x40
        raw[8] = (raw[8] & 0x3F) | 0x80
        task_uuid = str(uuid.UUID(bytes=bytes(raw)))
        if not is_uuid4(task_uuid):
            raise DesktopProviderExecutionError(
                "RUNWARE_RUNTIME_TASK_UUID_MATERIALIZATION_FAILED"
            )
        return task_uuid

    def _task_for_unit(
        self,
        unit: Mapping[str, Any],
        prompt_items: Mapping[str, Mapping[str, Any]],
    ) -> Mapping[str, Any] | None:
        kind = str(unit.get("media_kind") or "")
        if kind == "LOCAL_GRAPHICS":
            return None
        shot_id = str(unit.get("shot_id") or "")
        item = prompt_items.get(shot_id)
        if item is None:
            raise DesktopProviderExecutionError("PROMPT_PLAN_SHOT_MISSING:" + shot_id)
        planning_identity = str(unit.get("planning_identity") or "")
        if not planning_identity:
            raise DesktopProviderExecutionError("PROVIDER_REQUEST_IDENTITY_MISSING:" + shot_id)
        if kind == "RUNWARE_VIDEO":
            prompt = str(item.get("runware_positive_prompt_en") or "").strip()
            if not prompt:
                raise DesktopProviderExecutionError("VIDEO_PROMPT_REQUIRED:" + shot_id)
            task: dict[str, Any] = {
                "taskType": "videoInference",
                "taskUUID": planning_identity,
                "model": str(unit.get("model") or ""),
                "positivePrompt": prompt,
                "width": int(unit.get("width") or 0),
                "height": int(unit.get("height") or 0),
                "duration": int(unit.get("requested_seconds") or 0),
                "numberResults": 1,
                "deliveryMethod": "async",
                "includeCost": True,
                "providerSettings": {
                    "google": {
                        "generateAudio": False,
                        "personGeneration": (
                            "allow_adult" if item.get("contains_people") else "dont_allow"
                        ),
                    }
                },
            }
        elif kind == "RUNWARE_IMAGE":
            item_for_route = dict(item)
            item_for_route["final_budget_treatment"] = "ANIMATED_STILL_COMPOSITING"
            task = build_runware_image_task(item_for_route, planning_identity)
            # The approved provider unit, not the route helper, is authority
            # for the model/dimensions.  A mismatch is a stale-plan failure.
            if task.get("model") != unit.get("model"):
                raise DesktopProviderExecutionError("REQUEST_PLAN_MODEL_MISMATCH:" + str(unit.get("unit_id")))
            if task.get("width") != unit.get("width") or task.get("height") != unit.get("height"):
                raise DesktopProviderExecutionError("REQUEST_PLAN_DIMENSIONS_MISMATCH:" + str(unit.get("unit_id")))
        else:
            raise DesktopProviderExecutionError("UNSUPPORTED_MEDIA_KIND:" + kind)
        validated = validate_runware_task(
            task,
            require_uuid_v4=False,
        )
        expected_hash = str(unit.get("payload_sha256") or "")
        if expected_hash and validated.payload_sha256 != expected_hash:
            raise DesktopProviderExecutionError("REQUEST_PLAN_PAYLOAD_HASH_MISMATCH:" + str(unit.get("unit_id")))
        return dict(validated.payload)

    def _write_progress(self, value: Mapping[str, Any]) -> Path:
        path = _progress_path(self.repo_root, self.episode_id)
        atomic_write_json(path, dict(value), preserve_previous=True)
        if self.progress_callback is not None:
            try:
                self.progress_callback(dict(value))
            except Exception:
                # Progress presentation is advisory; it must never change
                # provider-result classification or transaction state.
                pass
        return path

    def _existing_stage(self, binding: ProviderExecutionBinding) -> dict[str, Any] | None:
        rows = read_jsonl(_stage_receipt_path(self.repo_root, self.episode_id))
        for row in reversed(rows):
            if row.get("binding", {}).get("request_plan_hash") != binding.request_plan_hash:
                continue
            if row.get("status") in {"STAGE_COMPLETED", "STAGE_STARTED", "RESULTS_PERSISTED", "STAGE_FAILED"}:
                return row
        return None

    def _new_outcome(
        self,
        *,
        status: str,
        session_id: str,
        completed: int,
        planned: int,
        video: int,
        still: int,
        local: int,
        failed: int,
        unknown: int,
        spent: float,
        envelope: float,
        next_stage: str | None,
        transition_id: str | None = None,
    ) -> ProviderExecutionOutcome:
        return ProviderExecutionOutcome(
            status=status,
            episode_id=self.episode_id,
            stage=STAGE,
            session_id=session_id,
            completed_requests=completed,
            planned_requests=planned,
            video_requests=video,
            still_requests=still,
            local_units=local,
            failed_requests=failed,
            unknown_requests=unknown,
            estimated_spent_usd=round(spent, 8),
            maximum_cost_envelope_usd=round(envelope, 8),
            next_stage=next_stage,
            stage_receipt_path=_relative(self.repo_root, _stage_receipt_path(self.repo_root, self.episode_id)),
            progress_path=_relative(self.repo_root, _progress_path(self.repo_root, self.episode_id)),
            transition_id=transition_id,
        )

    def execute(
        self,
        intent: DesktopResumeIntent,
        *,
        authorization: Mapping[str, Any],
    ) -> ProviderExecutionOutcome:
        if authorization.get("source") != DESKTOP_SOURCE:
            raise DesktopProviderExecutionError("PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY")
        if authorization.get("execution_token") != getattr(intent, "execution_token", ""):
            raise DesktopProviderExecutionError("DESKTOP_EXECUTION_CONTEXT_REQUIRED")
        try:
            review = read_persisted_media_cost_preflight(self.repo_root, self.episode_id)
        except MediaCostPreflightError as exc:
            raise DesktopProviderExecutionError("PREFLIGHT_BINDING_UNREADABLE") from exc
        binding = self._binding(review)
        self._validate_reviewed_state(intent, review, binding)
        reviewed_binding = authorization.get("provider_execution_binding")
        if not isinstance(reviewed_binding, Mapping) or canonical_sha256(
            dict(reviewed_binding)
        ) != canonical_sha256(binding.as_dict()):
            raise ProviderExecutionStaleStateError("STALE_STATE_REVIEW_REQUIRED")
        self._fault("before_stage_start_receipt")

        stage_path = _stage_receipt_path(self.repo_root, self.episode_id)
        attempt_path = _attempt_receipt_path(self.repo_root, self.episode_id)
        stage_path.parent.mkdir(parents=True, exist_ok=True)
        existing = self._existing_stage(binding)
        if existing and existing.get("status") == "STAGE_COMPLETED":
            return self._new_outcome(
                status="ALREADY_COMPLETED",
                session_id=str(existing.get("session_id") or ""),
                completed=int(existing.get("completed_requests") or 0),
                planned=int(existing.get("planned_requests") or 0),
                video=int(existing.get("video_requests") or 0),
                still=int(existing.get("still_requests") or 0),
                local=int(existing.get("local_units") or 0),
                failed=0,
                unknown=0,
                spent=float(existing.get("estimated_spent_usd") or 0.0),
                envelope=binding.maximum_cost,
                next_stage=NEXT_STAGE,
                transition_id=str(existing.get("transition_id") or "") or None,
            )
        recovery_mode = False
        if existing and existing.get('status') in {'STAGE_STARTED', 'RESULTS_PERSISTED', 'STAGE_FAILED'}:
            recovery_snapshot = self.reconcile()
            recovered_session_id = _siraj_provider_execution_recovery_session_v2(
                self.repo_root,
                self.episode_id,
                recovery_snapshot,
            )
            if not recovered_session_id:
                raise DesktopProviderExecutionError(
                    "EXECUTION_ALREADY_STARTED_RECOVERY_REQUIRED"
                )
            session_id = recovered_session_id
            recovery_mode = True

        if not recovery_mode:
            session_id = str(uuid.uuid4())
        units = [dict(unit) for unit in review.units]
        provider_units = [unit for unit in units if str(unit.get("media_kind")) != "LOCAL_GRAPHICS"]
        video_count = sum(str(unit.get("media_kind")) == "RUNWARE_VIDEO" for unit in units)
        still_count = sum(str(unit.get("media_kind")) == "RUNWARE_IMAGE" for unit in units)
        local_count = len(units) - len(provider_units)
        expected_total = float(review.summary.get("planned_provider_requests") or len(provider_units))
        if int(expected_total) != len(provider_units):
            raise DesktopProviderExecutionError("REQUEST_PLAN_COUNT_MISMATCH")
        # Hash binding is checked against the active result before the first
        # receipt.  This also ensures the user cannot execute a stale proposal.
        if binding.preflight_file_sha256 != sha256_file(Path(review.result_path)):
            raise ProviderExecutionStaleStateError("STALE_STATE_REVIEW_REQUIRED")

        stage_started = _append_hashed(
            stage_path,
            {
                "status": "STAGE_STARTED",
                "episode_id": self.episode_id,
                "stage": STAGE,
                "session_id": session_id,
                "binding": binding.as_dict(),
                "input_hashes": {
                    "preflight_result": binding.preflight_file_sha256,
                    "preflight_payload": binding.preflight_payload_sha256,
                    "media_plan": binding.media_plan_sha256,
                    "provider_request_plan": binding.provider_request_plan_sha256,
                    "pricing_registry": binding.pricing_registry_sha256,
                    "creative_overlay": binding.creative_overlay_sha256,
                    "structural_fingerprint": binding.structural_fingerprint,
                    "ledger_head": binding.ledger_head_sha256,
                },
                "request_plan_hash": binding.request_plan_hash,
                "cost_envelope": {"amount": binding.maximum_cost, "currency": binding.currency},
                "authorization_receipt_id": binding.reack_receipt_id,
                "ledger_head_sha256": binding.ledger_head_sha256,
                "execution_session_id": session_id,
                "completed_requests": 0,
                "planned_requests": len(provider_units),
                "video_requests": video_count,
                "still_requests": still_count,
                "local_units": local_count,
                "estimated_spent_usd": 0.0,
                "automatic_paid_retry": False,
                "automatic_paid_resubmission": False,
            },
            hash_key="receipt_sha256",
        )
        self._fault("after_stage_start_receipt")
        prompt_items = self._prompt_items(review)
        spent = 0.0
        completed = 0
        failed = 0
        unknown = 0
        result_refs: list[dict[str, Any]] = []
        attempt_refs: list[dict[str, Any]] = []
        # Local graphics are part of the approved media plan but are not paid
        # provider requests.  Record their deterministic completion explicitly
        # so the stage cannot later infer completion from a file count.
        for local_unit in sorted(
            (unit for unit in units if str(unit.get("media_kind")) == "LOCAL_GRAPHICS"),
            key=lambda row: int(row.get("queue_index") or 0),
        ):
            local_receipt = _append_hashed(
                attempt_path,
                {
                    "status": "LOCAL_UNIT_COMPLETED",
                    "episode_id": self.episode_id,
                    "stage": STAGE,
                    "session_id": session_id,
                    "unit_id": local_unit.get("unit_id"),
                    "shot_id": local_unit.get("shot_id"),
                    "media_kind": "LOCAL_GRAPHICS",
                    "provider_calls": 0,
                    "paid_attempt_created": False,
                },
                hash_key="receipt_sha256",
            )
            attempt_refs.append(
                {
                    "unit_id": local_unit.get("unit_id"),
                    "receipt_sha256": local_receipt["receipt_sha256"],
                    "local": True,
                }
            )
        progress = {
            "schema_version": SCHEMA_VERSION,
            "status": "PROVIDER_EXECUTION_RUNNING",
            "episode_id": self.episode_id,
            "stage": STAGE,
            "session_id": session_id,
            "planned_requests": len(provider_units),
            "completed_requests": 0,
            "pending_requests": len(provider_units),
            "failed_requests": 0,
            "unknown_requests": 0,
            "estimated_spent_usd": 0.0,
            "remaining_authorized_usd": binding.maximum_cost,
            "maximum_cost_envelope_usd": binding.maximum_cost,
            "currency": binding.currency,
            "next_stage": NEXT_STAGE,
            "provider_calls": 0,
            "paid_attempts_created": 0,
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
            "binding": binding.as_dict(),
        }
        self._write_progress(progress)

        # SIRAJ_EP002_ONE_UNIT_PAID_SCOPE_PAUSE_GUARD_V2
        # SIRAJ_EP002_REMAINING_STAGE_AUTHORIZATION_V1
        _siraj_remaining_stage_guard_active_v1 = False
        _siraj_remaining_stage_authorization_v1 = None
        _siraj_remaining_stage_snapshot_v1 = None
        _siraj_remaining_stage_authorized_ids_v1: set[str] = set()
        _siraj_remaining_stage_submission_count_v1 = 0
        _siraj_remaining_stage_exposure_usd_v1 = 0.0
        _siraj_paid_scope_guard_active_v2 = False
        _siraj_paid_scope_target_v2 = ""
        _siraj_paid_scope_authorization_v2 = None
        _siraj_durable_completed_units_v2: dict[str, str] = {}

        if recovery_mode:
            _siraj_prior_scope_pauses_v2 = [
                row
                for row in read_jsonl(stage_path)
                if str(row.get("status") or "")
                == "STAGE_PAUSED_AUTHORIZATION_SCOPE"
                and row.get("remaining_stage_not_authorized") is True
            ]
            if _siraj_prior_scope_pauses_v2:
                _siraj_remaining_stage_authorization_v1 = (
                    remaining_stage_authorization_for_episode(
                        self.repo_root,
                        self.episode_id,
                    )
                )
                if _siraj_remaining_stage_authorization_v1 is None:
                    raise DesktopProviderExecutionError(
                        "REMAINING_STAGE_REQUIRES_SEPARATE_AUTHORIZATION"
                    )

            _siraj_durable_completed_units_v2 = (
                _siraj_durable_completed_provider_units_v2(
                    self.repo_root,
                    self.episode_id,
                    list(provider_units),
                    binding,
                )
            )

            if _siraj_prior_scope_pauses_v2:
                _siraj_remaining_stage_snapshot_v1 = (
                    validate_remaining_stage_authorization_current(
                        _siraj_remaining_stage_authorization_v1,
                        episode_id=self.episode_id,
                        binding=binding.as_dict(),
                        provider_units=list(provider_units),
                        durable_completed=_siraj_durable_completed_units_v2,
                        prior_scope_pause=_siraj_prior_scope_pauses_v2[-1],
                    )
                )
                _siraj_remaining_stage_guard_active_v1 = True
                _siraj_remaining_stage_authorized_ids_v1 = set(
                    _siraj_remaining_stage_snapshot_v1[
                        "authorized_unit_ids"
                    ]
                )
                _siraj_remaining_stage_auth_id_v1 = str(
                    _siraj_remaining_stage_authorization_v1.get(
                        "authorization_id"
                    )
                    or ""
                )
                _siraj_remaining_stage_attempt_ledger_v1 = (
                    Path(self.repo_root).resolve()
                    / "projects"
                    / str(self.episode_id)
                    / "orchestration"
                    / "provider-execution-v1"
                    / "provider-execution-attempt-receipts-v1.jsonl"
                )
                _siraj_remaining_stage_tagged_intents_v1 = [
                    row
                    for row in read_jsonl(
                        _siraj_remaining_stage_attempt_ledger_v1
                    )
                    if str(row.get("status") or "")
                    == "ATTEMPT_INTENT_PERSISTED"
                    and str(
                        row.get("remaining_stage_authorization_id") or ""
                    )
                    == _siraj_remaining_stage_auth_id_v1
                ]

                _siraj_remaining_stage_seen_units_v1: set[str] = set()
                _siraj_remaining_stage_submission_count_v1 = 0
                _siraj_remaining_stage_exposure_usd_v1 = 0.0
                for _siraj_remaining_stage_intent_v1 in (
                    _siraj_remaining_stage_tagged_intents_v1
                ):
                    _siraj_remaining_stage_intent_unit_v1 = str(
                        _siraj_remaining_stage_intent_v1.get("request_id")
                        or _siraj_remaining_stage_intent_v1.get("unit_id")
                        or _siraj_remaining_stage_intent_v1.get(
                            "provider_request_id"
                        )
                        or ""
                    )
                    if (
                        _siraj_remaining_stage_intent_unit_v1
                        not in _siraj_remaining_stage_authorized_ids_v1
                    ):
                        raise DesktopProviderExecutionError(
                            "REMAINING_STAGE_AUTHORIZATION_TAGGED_UNIT_OUTSIDE_SCOPE:"
                            + _siraj_remaining_stage_intent_unit_v1
                        )
                    if (
                        _siraj_remaining_stage_intent_unit_v1
                        in _siraj_remaining_stage_seen_units_v1
                    ):
                        raise DesktopProviderExecutionError(
                            "REMAINING_STAGE_AUTHORIZATION_DUPLICATE_INTENT:"
                            + _siraj_remaining_stage_intent_unit_v1
                        )
                    _siraj_remaining_stage_seen_units_v1.add(
                        _siraj_remaining_stage_intent_unit_v1
                    )

                    if (
                        _siraj_remaining_stage_intent_unit_v1
                        not in _siraj_durable_completed_units_v2
                    ):
                        raise DesktopProviderExecutionError(
                            "REMAINING_STAGE_AUTHORIZATION_PARTIAL_ATTEMPT_"
                            "REQUIRES_REAUTHORIZATION:"
                            + _siraj_remaining_stage_intent_unit_v1
                        )

                    _siraj_remaining_stage_intent_cost_v1 = (
                        _siraj_remaining_stage_intent_v1.get(
                            "remaining_stage_planned_cost_usd"
                        )
                    )
                    if (
                        not isinstance(
                            _siraj_remaining_stage_intent_cost_v1,
                            (int, float),
                        )
                        or isinstance(
                            _siraj_remaining_stage_intent_cost_v1,
                            bool,
                        )
                    ):
                        raise DesktopProviderExecutionError(
                            "REMAINING_STAGE_AUTHORIZATION_INTENT_COST_INVALID:"
                            + _siraj_remaining_stage_intent_unit_v1
                        )
                    _siraj_remaining_stage_submission_count_v1 += 1
                    _siraj_remaining_stage_exposure_usd_v1 += float(
                        _siraj_remaining_stage_intent_cost_v1
                    )

                if _siraj_remaining_stage_submission_count_v1 > int(
                    _siraj_remaining_stage_authorization_v1.get(
                        "maximum_provider_submissions"
                    )
                    or 0
                ):
                    raise DesktopProviderExecutionError(
                        "REMAINING_STAGE_AUTHORIZATION_SUBMISSION_CAP_ALREADY_EXCEEDED"
                    )
                if _siraj_remaining_stage_exposure_usd_v1 > float(
                    _siraj_remaining_stage_authorization_v1.get(
                        "maximum_total_usd"
                    )
                    or 0.0
                ) + 1e-9:
                    raise DesktopProviderExecutionError(
                        "REMAINING_STAGE_AUTHORIZATION_TOTAL_COST_CAP_ALREADY_EXCEEDED"
                    )
            _siraj_ordered_provider_units_v2 = sorted(
                provider_units,
                key=lambda row: int(row.get("queue_index") or 0),
            )
            _siraj_first_remaining_unit_v2 = next(
                (
                    row
                    for row in _siraj_ordered_provider_units_v2
                    if str(row.get("request_id") or row.get("unit_id") or "")
                    not in _siraj_durable_completed_units_v2
                ),
                None,
            )

            if (
                _siraj_first_remaining_unit_v2 is not None
                and not _siraj_remaining_stage_guard_active_v1
            ):
                _siraj_first_remaining_id_v2 = str(
                    _siraj_first_remaining_unit_v2.get("request_id")
                    or _siraj_first_remaining_unit_v2.get("unit_id")
                    or ""
                )
                _siraj_scope_auth_v2 = (
                    terminal_replacement_authorization_for_request(
                        self.repo_root,
                        self.episode_id,
                        _siraj_first_remaining_id_v2,
                    )
                )
                if _siraj_scope_auth_v2 is not None:
                    if (
                        consumption_for_authorization(
                            self.repo_root,
                            self.episode_id,
                            str(_siraj_scope_auth_v2.get("authorization_id") or ""),
                        )
                        is not None
                    ):
                        raise DesktopProviderExecutionError(
                            "EXPLICIT_REPLACEMENT_AUTHORIZATION_ALREADY_CONSUMED:"
                            + _siraj_first_remaining_id_v2
                        )

                    if int(
                        _siraj_scope_auth_v2.get("maximum_provider_requests") or 0
                    ) != 1:
                        raise DesktopProviderExecutionError(
                            "EXPLICIT_REPLACEMENT_SCOPE_REQUEST_COUNT_INVALID:"
                            + _siraj_first_remaining_id_v2
                        )
                    if _siraj_scope_auth_v2.get("automatic_paid_retry") is not False:
                        raise DesktopProviderExecutionError(
                            "EXPLICIT_REPLACEMENT_AUTOMATIC_RETRY_FORBIDDEN"
                        )
                    if (
                        _siraj_scope_auth_v2.get("automatic_paid_resubmission")
                        is not False
                    ):
                        raise DesktopProviderExecutionError(
                            "EXPLICIT_REPLACEMENT_AUTOMATIC_RESUBMISSION_FORBIDDEN"
                        )

                    _siraj_current_planned_payload_v2 = str(
                        _siraj_first_remaining_unit_v2.get("payload_sha256") or ""
                    )
                    if (
                        str(
                            _siraj_scope_auth_v2.get("planned_payload_sha256")
                            or ""
                        )
                        != _siraj_current_planned_payload_v2
                    ):
                        raise DesktopProviderExecutionError(
                            "EXPLICIT_REPLACEMENT_PLANNED_PAYLOAD_MISMATCH:"
                            + _siraj_first_remaining_id_v2
                        )

                    _siraj_auth_binding_v2 = _siraj_scope_auth_v2.get("binding")
                    if not isinstance(_siraj_auth_binding_v2, Mapping):
                        raise DesktopProviderExecutionError(
                            "EXPLICIT_REPLACEMENT_BINDING_MISSING"
                        )
                    if canonical_sha256(dict(_siraj_auth_binding_v2)) != canonical_sha256(
                        binding.as_dict()
                    ):
                        raise DesktopProviderExecutionError(
                            "EXPLICIT_REPLACEMENT_BINDING_CHANGED"
                        )
                    _siraj_auth_binding_sha_v2 = str(
                        _siraj_scope_auth_v2.get("binding_sha256") or ""
                    )
                    if (
                        _siraj_auth_binding_sha_v2
                        and _siraj_auth_binding_sha_v2
                        != canonical_sha256(dict(_siraj_auth_binding_v2))
                    ):
                        raise DesktopProviderExecutionError(
                            "EXPLICIT_REPLACEMENT_BINDING_HASH_INVALID"
                        )

                    _siraj_scope_planned_cost_v2 = float(
                        _siraj_scope_auth_v2.get("planned_cost_usd") or -1.0
                    )
                    _siraj_scope_max_cost_v2 = float(
                        _siraj_scope_auth_v2.get("maximum_cost_usd") or -1.0
                    )
                    _siraj_current_cost_v2 = _siraj_first_remaining_unit_v2.get(
                        "expected_cost_usd"
                    )
                    if (
                        not isinstance(_siraj_current_cost_v2, (int, float))
                        or isinstance(_siraj_current_cost_v2, bool)
                    ):
                        raise DesktopProviderExecutionError(
                            "EXPLICIT_REPLACEMENT_CURRENT_COST_INVALID"
                        )
                    _siraj_current_cost_v2 = float(_siraj_current_cost_v2)
                    if abs(
                        _siraj_scope_planned_cost_v2 - _siraj_current_cost_v2
                    ) > 1e-9:
                        raise DesktopProviderExecutionError(
                            "EXPLICIT_REPLACEMENT_PLANNED_COST_MISMATCH"
                        )
                    if (
                        _siraj_current_cost_v2
                        > _siraj_scope_max_cost_v2 + 1e-9
                    ):
                        raise DesktopProviderExecutionError(
                            "EXPLICIT_REPLACEMENT_COST_CAP_EXCEEDED"
                        )

                    _siraj_paid_scope_guard_active_v2 = True
                    _siraj_paid_scope_target_v2 = _siraj_first_remaining_id_v2
                    _siraj_paid_scope_authorization_v2 = _siraj_scope_auth_v2
        for ordinal, unit in enumerate(sorted(provider_units, key=lambda row: int(row.get("queue_index") or 0)), 1):
            if recovery_mode and _siraj_remaining_stage_guard_active_v1:
                _siraj_remaining_stage_unit_id_v1 = str(
                    unit.get("request_id") or unit.get("unit_id") or ""
                )
                if (
                    _siraj_remaining_stage_unit_id_v1
                    in _siraj_durable_completed_units_v2
                ):
                    continue
                if (
                    _siraj_remaining_stage_unit_id_v1
                    not in _siraj_remaining_stage_authorized_ids_v1
                ):
                    raise DesktopProviderExecutionError(
                        "REMAINING_STAGE_UNIT_OUTSIDE_AUTHORIZATION:"
                        + _siraj_remaining_stage_unit_id_v1
                    )
            if recovery_mode and _siraj_paid_scope_guard_active_v2:
                _siraj_scope_current_unit_v2 = str(
                    unit.get("request_id") or unit.get("unit_id") or ""
                )
                if _siraj_scope_current_unit_v2 in _siraj_durable_completed_units_v2:
                    continue
                if _siraj_scope_current_unit_v2 != _siraj_paid_scope_target_v2:
                    raise DesktopProviderExecutionError(
                        "RECOVERY_NEXT_PAID_UNIT_OUTSIDE_EXPLICIT_AUTHORIZATION:"
                        + _siraj_scope_current_unit_v2
                    )
            self._fault("before_attempt_intent")
            expected_cost = unit.get("expected_cost_usd")
            if not isinstance(expected_cost, (int, float)) or isinstance(expected_cost, bool):
                raise DesktopProviderExecutionError("UNPRICED_REQUEST:" + str(unit.get("unit_id")))
            expected_cost = float(expected_cost)
            if spent + expected_cost > binding.maximum_cost + 1e-9:
                raise DesktopProviderExecutionError("COST_ENVELOPE_EXCEEDED_BEFORE_SUBMISSION")
            human_reconciliation = reconciliation_for_request(
                self.repo_root,
                self.episode_id,
                str(unit.get("request_id") or unit.get("unit_id") or ""),
            )
            task = self._task_for_unit(unit, prompt_items)
            if task is None:
                raise DesktopProviderExecutionError("PROVIDER_TASK_REQUIRED")
            reconciliation_id = (
                str(human_reconciliation.get("receipt_id") or "")
                if human_reconciliation
                else None
            )
            attempt_id = _attempt_id(
                binding,
                unit,
                first_submission_reconciliation_id=reconciliation_id,
            )
            if task is not None and bool(getattr(self.gateway, "requires_uuid4", False)):
                # The persisted unit hash describes the approved PLANNING payload.
                # Validate that exact payload before changing only its provider identity.
                planned_runtime = validate_runware_task(
                    task,
                    require_uuid_v4=False,
                )
                planned_payload_sha256 = str(unit.get("payload_sha256") or "")
                if (
                    planned_payload_sha256
                    and planned_runtime.payload_sha256 != planned_payload_sha256
                ):
                    raise DesktopProviderExecutionError(
                        "REQUEST_PLAN_PAYLOAD_HASH_MISMATCH:"
                        + str(unit.get("unit_id"))
                    )
                provider_task_uuid = self._runtime_runware_task_uuid(
                    attempt_id,
                    unit,
                )
                runtime_task = dict(planned_runtime.payload)
                runtime_task["taskUUID"] = provider_task_uuid
                task = dict(
                    validate_runware_task(
                        runtime_task,
                        require_uuid_v4=True,
                    ).payload
                )
            operation_nonce = str(unit.get("unit_id") or "")
            if reconciliation_id:
                operation_nonce += ":first-valid-submission:" + reconciliation_id
            replacement_authorization = None
            if (
                human_reconciliation
                and str(
                    human_reconciliation.get("original_submission_status") or ""
                )
                == PROVEN_SUBMITTED_TERMINAL_REJECTED
            ):
                replacement_authorization = (
                    terminal_replacement_authorization_for_request(
                        self.repo_root,
                        self.episode_id,
                        str(unit.get("request_id") or unit.get("unit_id") or ""),
                    )
                )
                if replacement_authorization is None:
                    raise DesktopProviderExecutionError(
                        "TERMINAL_REPLACEMENT_AUTHORIZATION_REQUIRED:"
                        + str(unit.get("unit_id"))
                    )
                if not terminal_replacement_authorization_matches_reconciliation(
                    replacement_authorization,
                    human_reconciliation,
                ):
                    raise DesktopProviderExecutionError(
                        "TERMINAL_REPLACEMENT_AUTHORIZATION_RECONCILIATION_MISMATCH:"
                        + str(unit.get("unit_id"))
                    )
                replacement_maximum = float(
                    replacement_authorization.get("maximum_cost_usd") or 0.0
                )
                if expected_cost > replacement_maximum + 1e-9:
                    raise DesktopProviderExecutionError(
                        "TERMINAL_REPLACEMENT_COST_CAP_EXCEEDED:"
                        + str(unit.get("unit_id"))
                    )
                if int(
                    replacement_authorization.get("maximum_provider_requests") or 0
                ) != 1:
                    raise DesktopProviderExecutionError(
                        "TERMINAL_REPLACEMENT_SINGLE_REQUEST_REQUIRED:"
                        + str(unit.get("unit_id"))
                    )
                if (
                    str(replacement_authorization.get("replacement_attempt_id") or "")
                    != attempt_id
                ):
                    raise DesktopProviderExecutionError(
                        "TERMINAL_REPLACEMENT_ATTEMPT_ID_MISMATCH:"
                        + str(unit.get("unit_id"))
                    )
                task = apply_terminal_replacement_prompt(
                    task,
                    replacement_authorization,
                )
            _siraj_ep002_veo_mena_policy_v1 = None
            if bool(getattr(self.gateway, "requires_uuid4", False)):
                task, _siraj_ep002_veo_mena_policy_v1 = (
                    _siraj_ep002_veo_mena_allow_adult_runtime_policy_v1(
                        self.episode_id,
                        unit,
                        task,
                    )
                )
            if recovery_mode and _siraj_remaining_stage_guard_active_v1:
                _siraj_remaining_stage_budget_unit_id_v1 = str(
                    unit.get("request_id") or unit.get("unit_id") or ""
                )
                _siraj_remaining_stage_entry_v1 = (
                    _siraj_remaining_stage_snapshot_v1[
                        "authorized_unit_entries"
                    ].get(_siraj_remaining_stage_budget_unit_id_v1)
                )
                if not isinstance(_siraj_remaining_stage_entry_v1, Mapping):
                    raise DesktopProviderExecutionError(
                        "REMAINING_STAGE_AUTHORIZATION_ENTRY_MISSING:"
                        + _siraj_remaining_stage_budget_unit_id_v1
                    )
                _siraj_remaining_stage_entry_cost_v1 = float(
                    _siraj_remaining_stage_entry_v1.get(
                        "expected_cost_usd"
                    )
                    or 0.0
                )
                if abs(
                    _siraj_remaining_stage_entry_cost_v1
                    - float(expected_cost)
                ) > 1e-9:
                    raise DesktopProviderExecutionError(
                        "REMAINING_STAGE_AUTHORIZATION_UNIT_COST_MISMATCH:"
                        + _siraj_remaining_stage_budget_unit_id_v1
                    )

                _siraj_remaining_stage_next_count_v1 = (
                    _siraj_remaining_stage_submission_count_v1 + 1
                )
                _siraj_remaining_stage_next_exposure_v1 = (
                    _siraj_remaining_stage_exposure_usd_v1
                    + float(expected_cost)
                )
                if _siraj_remaining_stage_next_count_v1 > int(
                    _siraj_remaining_stage_authorization_v1.get(
                        "maximum_provider_submissions"
                    )
                    or 0
                ):
                    raise DesktopProviderExecutionError(
                        "REMAINING_STAGE_AUTHORIZATION_SUBMISSION_CAP_EXCEEDED:"
                        + _siraj_remaining_stage_budget_unit_id_v1
                    )
                if _siraj_remaining_stage_next_exposure_v1 > float(
                    _siraj_remaining_stage_authorization_v1.get(
                        "maximum_total_usd"
                    )
                    or 0.0
                ) + 1e-9:
                    raise DesktopProviderExecutionError(
                        "REMAINING_STAGE_AUTHORIZATION_TOTAL_COST_CAP_EXCEEDED:"
                        + _siraj_remaining_stage_budget_unit_id_v1
                    )

                _siraj_remaining_stage_submission_count_v1 = (
                    _siraj_remaining_stage_next_count_v1
                )
                _siraj_remaining_stage_exposure_usd_v1 = (
                    _siraj_remaining_stage_next_exposure_v1
                )
            request = PaidOperationRequest(
                repo_root=self.repo_root,
                episode_id=self.episode_id,
                stage=STAGE,
                operation_type=(
                    "RUNWARE_VIDEO_GENERATION"
                    if unit.get("media_kind") == "RUNWARE_VIDEO"
                    else "RUNWARE_IMAGE_GENERATION"
                ),
                provider=str(unit.get("provider") or "RUNWARE"),
                model=str(unit.get("model") or ""),
                provider_contract_version=PROVIDER_CONTRACT_VERSION,
                payload=task,
                input_artifact_hashes={
                    "preflight_result": binding.preflight_file_sha256,
                    "media_plan": binding.media_plan_sha256,
                    "provider_request_plan": binding.provider_request_plan_sha256,
                    "pricing_registry": binding.pricing_registry_sha256,
                    "creative_overlay": binding.creative_overlay_sha256,
                    "structural_fingerprint": binding.structural_fingerprint,
                    "ledger_head": binding.ledger_head_sha256,
                },
                master_authorization_reference=master_authorization_reference(
                    self.repo_root, self.episode_id
                ),
                operation_nonce=operation_nonce,
                attempt_id=attempt_id,
            )
            planned_payload_sha256 = str(unit.get("payload_sha256") or "")
            if bool(getattr(self.gateway, "requires_uuid4", False)):
                observed_runtime_uuid = str(request.payload.get("taskUUID") or "")
                expected_runtime_uuid = self._runtime_runware_task_uuid(
                    attempt_id,
                    unit,
                )
                if observed_runtime_uuid != expected_runtime_uuid:
                    raise DesktopProviderExecutionError(
                        "RUNWARE_RUNTIME_TASK_UUID_BINDING_MISMATCH:"
                        + str(unit.get("unit_id"))
                    )
                if not is_uuid4(observed_runtime_uuid):
                    raise DesktopProviderExecutionError(
                        "RUNWARE_TASK_UUID_UUID4_REQUIRED:"
                        + str(unit.get("unit_id"))
                    )
            elif request.payload_sha256 != planned_payload_sha256:
                raise DesktopProviderExecutionError(
                    "REQUEST_PLAN_PAYLOAD_HASH_MISMATCH:"
                    + str(unit.get("unit_id"))
                )
            intent_row = _append_hashed(
                attempt_path,
                {
                    "status": "ATTEMPT_INTENT_PERSISTED",
                    "episode_id": self.episode_id,
                    "stage": STAGE,
                    "session_id": session_id,
                    "attempt_id": attempt_id,
                    "ordinal": ordinal,
                    "unit_id": unit.get("unit_id"),
                    "request_id": unit.get("request_id"),
                    "provider_request_id": unit.get("request_id"),
                    "shot_id": unit.get("shot_id"),
                    "provider": unit.get("provider"),
                    "model": unit.get("model"),
                    "duration_seconds": unit.get("requested_seconds"),
                    "settings": dict(unit.get("provider_request_contract") or {}),
                    "payload_sha256": request.payload_sha256,
                    "planned_payload_sha256": str(unit.get("payload_sha256") or ""),
                    "planning_identity": str(unit.get("planning_identity") or ""),
                    "provider_task_uuid": str(task.get("taskUUID") or ""),
                    "provider_payload_sha256": request.payload_sha256,
                    "task_uuid_durable_before_submission": True,
                    "historical_reconciliation_receipt_id": reconciliation_id,
                    "runtime_person_generation_policy": (
                        dict(_siraj_ep002_veo_mena_policy_v1)
                        if _siraj_ep002_veo_mena_policy_v1 else None
                    ),
                    "remaining_stage_authorization_id": (
                        str(_siraj_remaining_stage_authorization_v1.get("authorization_id") or "")
                        if _siraj_remaining_stage_guard_active_v1 else None
                    ),
                    "remaining_stage_authorization_sha256": (
                        str(_siraj_remaining_stage_authorization_v1.get("authorization_sha256") or "")
                        if _siraj_remaining_stage_guard_active_v1 else None
                    ),
                    "remaining_stage_submission_ordinal": (
                        _siraj_remaining_stage_submission_count_v1
                        if _siraj_remaining_stage_guard_active_v1 else None
                    ),
                    "remaining_stage_planned_cost_usd": (
                        float(expected_cost)
                        if _siraj_remaining_stage_guard_active_v1 else None
                    ),
                    "remaining_stage_authorized_exposure_usd_after_intent": (
                        round(_siraj_remaining_stage_exposure_usd_v1, 8)
                        if _siraj_remaining_stage_guard_active_v1 else None
                    ),
                    "remaining_stage_maximum_total_cost_usd": (
                        float(_siraj_remaining_stage_authorization_v1.get("maximum_total_usd") or 0.0)
                        if _siraj_remaining_stage_guard_active_v1 else None
                    ),
                    "replacement_authorization_id": (
                        str(replacement_authorization.get("authorization_id") or "")
                        if replacement_authorization else None
                    ),
                    "replacement_authorization_sha256": (
                        str(replacement_authorization.get("authorization_sha256") or "")
                        if replacement_authorization else None
                    ),
                    "replacement_parent_attempt_id": (
                        str(replacement_authorization.get("historical_attempt_id") or "")
                        if replacement_authorization else None
                    ),
                    "replacement_prompt_override_sha256": (
                        str(replacement_authorization.get("replacement_positive_prompt_sha256") or "")
                        if replacement_authorization else None
                    ),
                    "historical_attempt_reconciled_as": (
                        PROVEN_NOT_SUBMITTED if human_reconciliation else None
                    ),
                    "future_submission_status": (
                        NOT_SUBMITTED_ELIGIBLE if human_reconciliation else None
                    ),
                    "request_plan_hash": binding.request_plan_hash,
                    "cost_estimate_usd": expected_cost,
                    "maximum_cost_envelope_usd": binding.maximum_cost,
                    "automatic_paid_retry": False,
                    "automatic_paid_resubmission": False,
                    "provider_submission_started": False,
                },
                hash_key="receipt_sha256",
            )
            attempt_refs.append({"attempt_id": attempt_id, "receipt_sha256": intent_row["receipt_sha256"]})
            if replacement_authorization is not None:
                consume_terminal_replacement_authorization(
                    self.repo_root,
                    self.episode_id,
                    replacement_authorization,
                    attempt_id=attempt_id,
                )
            self._fault("after_attempt_intent")
            try:
                gateway_result = self.gateway.submit(
                    request=request,
                    unit=unit,
                    attempt_id=attempt_id,
                )
            except Exception as exc:
                status = "UNKNOWN" if "UNKNOWN" in str(exc).upper() else "FAILED"
                _append_hashed(
                    attempt_path,
                    {
                        "status": status,
                        "episode_id": self.episode_id,
                        "stage": STAGE,
                        "session_id": session_id,
                        "attempt_id": attempt_id,
                        "unit_id": unit.get("unit_id"),
                        "error": str(exc),
                        "automatic_paid_retry": False,
                        "automatic_paid_resubmission": False,
                    },
                    hash_key="receipt_sha256",
                )
                if status == "UNKNOWN":
                    unknown += 1
                else:
                    failed += 1
                progress.update(
                    {
                        "status": "PROVIDER_EXECUTION_PAUSED_FAILURE",
                        "failed_requests": failed,
                        "unknown_requests": unknown,
                        "pending_requests": len(provider_units) - completed - failed - unknown,
                        "provider_calls": ordinal,
                        "paid_attempts_created": ordinal,
                    }
                )
                self._write_progress(progress)
                _append_hashed(
                    stage_path,
                    {
                        "status": "STAGE_FAILED",
                        "episode_id": self.episode_id,
                        "stage": STAGE,
                        "session_id": session_id,
                        "binding": binding.as_dict(),
                        "failure_classification": status,
                        "failed_requests": failed,
                        "unknown_requests": unknown,
                        "completed_requests": completed,
                        "automatic_paid_retry": False,
                        "automatic_paid_resubmission": False,
                    },
                    hash_key="receipt_sha256",
                )
                raise DesktopProviderExecutionError(
                    "PAID_PROVIDER_ATTEMPT_" + status + "_NO_AUTOMATIC_RETRY:" + attempt_id
                ) from exc

            self._fault("after_provider_submission")
            status, response = _normalise_gateway_result(gateway_result)
            provider_operation_id = str(
                response.get("provider_operation_id") or ""
            ).strip()
            if provider_operation_id:
                # Gateways normally persist this before returning.  The
                # executor verifies the invariant and repairs the receipt if
                # an injected/test gateway only returned the identifier.
                attempt_rows = read_jsonl(attempt_path)
                already_persisted = any(
                    row.get("attempt_id") == attempt_id
                    and row.get("status") == SUBMITTED_PENDING
                    and str(row.get("provider_operation_id") or "")
                    == provider_operation_id
                    for row in attempt_rows
                )
                if not already_persisted:
                    _persist_provider_operation_id(
                        repo_root=self.repo_root,
                        episode_id=self.episode_id,
                        attempt_id=attempt_id,
                        unit=unit,
                        request=request,
                        provider_operation_id=provider_operation_id,
                        session_id=session_id,
                    )
                self._fault("after_provider_operation_id_persistence")
            if status != "COMPLETE":
                pending = (
                    status == SUBMITTED_PENDING
                    or str(response.get("submission_status") or "").upper()
                    == SUBMITTED_PENDING
                )
                receipt_status = SUBMITTED_PENDING if pending else (
                    status if status in {"FAILED", "UNKNOWN"} else "FAILED"
                )
                _append_hashed(
                    attempt_path,
                    {
                        "status": receipt_status,
                        "episode_id": self.episode_id,
                        "stage": STAGE,
                        "session_id": session_id,
                        "attempt_id": attempt_id,
                        "unit_id": unit.get("unit_id"),
                        "response": dict(response),
                        "provider_operation_id": provider_operation_id or None,
                        "submission_status": SUBMITTED_PENDING if pending else status,
                        "automatic_paid_retry": False,
                        "automatic_paid_resubmission": False,
                    },
                    hash_key="receipt_sha256",
                )
                if status == "UNKNOWN" or pending:
                    unknown += 1
                else:
                    failed += 1
                progress.update(
                    {
                        "status": "PROVIDER_EXECUTION_PAUSED_FAILURE",
                        "failed_requests": failed,
                        "unknown_requests": unknown,
                        "pending_requests": len(provider_units) - completed - failed - unknown,
                        "provider_calls": ordinal,
                        "paid_attempts_created": ordinal,
                    }
                )
                self._write_progress(progress)
                _append_hashed(
                    stage_path,
                    {
                        "status": "STAGE_FAILED",
                        "episode_id": self.episode_id,
                        "stage": STAGE,
                        "session_id": session_id,
                        "binding": binding.as_dict(),
                        "failure_classification": receipt_status,
                        "failed_requests": failed,
                        "unknown_requests": unknown,
                        "completed_requests": completed,
                        "automatic_paid_retry": False,
                        "automatic_paid_resubmission": False,
                    },
                    hash_key="receipt_sha256",
                )
                provider_rejection_code = str(
                    response.get("provider_rejection_code") or ""
                ).strip()
                if (
                    receipt_status == "FAILED"
                    and response.get("terminal_provider_rejection") is True
                    and response.get("safe_to_reauthorize") is True
                    and response.get("billable_output_detected") is False
                    and provider_rejection_code
                ):
                    raise DesktopProviderExecutionError(
                        "RUNWARE_TERMINAL_PROVIDER_REJECTION_"
                        "REAUTHORIZATION_REQUIRED:"
                        + provider_rejection_code
                        + ":"
                        + attempt_id
                    )
                raise DesktopProviderExecutionError(
                    "PAID_PROVIDER_ATTEMPT_" + receipt_status
                    + "_NO_AUTOMATIC_RETRY:" + attempt_id
                )

            response_payload = dict(response)
            result_path = _result_path(self.repo_root, self.episode_id, attempt_id)
            result_value = {
                "schema_version": SCHEMA_VERSION,
                "status": "RESULT_PERSISTED",
                "episode_id": self.episode_id,
                "stage": STAGE,
                "session_id": session_id,
                "attempt_id": attempt_id,
                "unit_id": unit.get("unit_id"),
                "request_id": unit.get("request_id"),
                "provider_request_id": unit.get("request_id"),
                "shot_id": unit.get("shot_id"),
                "provider": unit.get("provider"),
                "model": unit.get("model"),
                "duration_seconds": unit.get("requested_seconds"),
                "settings": dict(unit.get("provider_request_contract") or {}),
                "payload_sha256": request.payload_sha256,
                "response": response_payload,
                "response_sha256": canonical_sha256(response_payload),
                "provider_operation_id": provider_operation_id or None,
                # Production gateway responses carry the immutable downloaded
                # asset hash; retain that as content identity.  Offline fake
                # responses fall back to their canonical response hash.
                "content_hash": str(
                    response_payload.get("asset_sha256")
                    or canonical_sha256(response_payload)
                ),
                "cost_estimate_usd": expected_cost,
                "binding": binding.as_dict(),
            }
            result_value["result_sha256"] = canonical_sha256(result_value)
            write_new_json(result_path, result_value)
            self._fault("after_result_persistence")
            _append_hashed(
                attempt_path,
                {
                    "status": "RESULT_PERSISTED",
                    "episode_id": self.episode_id,
                    "stage": STAGE,
                    "session_id": session_id,
                    "attempt_id": attempt_id,
                    "unit_id": unit.get("unit_id"),
                    "result_path": _relative(self.repo_root, result_path),
                    "result_sha256": result_value["result_sha256"],
                    "response_sha256": result_value["response_sha256"],
                    "provider_operation_id": provider_operation_id or None,
                    "automatic_paid_retry": False,
                    "automatic_paid_resubmission": False,
                },
                hash_key="receipt_sha256",
            )
            self._fault("after_attempt_completion")
            _append_hashed(
                attempt_path,
                {
                    "status": "ATTEMPT_COMPLETED",
                    "episode_id": self.episode_id,
                    "stage": STAGE,
                    "session_id": session_id,
                    "attempt_id": attempt_id,
                    "unit_id": unit.get("unit_id"),
                    "result_path": _relative(self.repo_root, result_path),
                    "result_sha256": result_value["result_sha256"],
                    "cost_estimate_usd": expected_cost,
                    "provider_operation_id": provider_operation_id or None,
                    "automatic_paid_retry": False,
                    "automatic_paid_resubmission": False,
                },
                hash_key="receipt_sha256",
            )
            result_refs.append(artifact_reference(result_path, base=self.repo_root))
            completed += 1
            spent += expected_cost
            progress.update(
                {
                    "completed_requests": completed,
                    "pending_requests": len(provider_units) - completed,
                    "estimated_spent_usd": round(spent, 8),
                    "remaining_authorized_usd": round(binding.maximum_cost - spent, 8),
                    "provider_calls": completed,
                    "paid_attempts_created": completed,
                }
            )
            self._write_progress(progress)

            if _siraj_paid_scope_guard_active_v2:
                _siraj_scope_unit_id_v2 = str(
                    unit.get("request_id") or unit.get("unit_id") or ""
                )
                if _siraj_scope_unit_id_v2 != _siraj_paid_scope_target_v2:
                    raise DesktopProviderExecutionError(
                        "SCOPED_SUCCESS_TARGET_MISMATCH:" + _siraj_scope_unit_id_v2
                    )
                if replacement_authorization is None:
                    raise DesktopProviderExecutionError(
                        "SCOPED_SUCCESS_REPLACEMENT_AUTHORIZATION_MISSING:"
                        + _siraj_scope_unit_id_v2
                    )
                if (
                    str(replacement_authorization.get("authorization_id") or "")
                    != str(
                        _siraj_paid_scope_authorization_v2.get("authorization_id") or ""
                    )
                ):
                    raise DesktopProviderExecutionError(
                        "SCOPED_SUCCESS_AUTHORIZATION_ID_MISMATCH"
                    )
                if (
                    str(replacement_authorization.get("replacement_attempt_id") or "")
                    != attempt_id
                ):
                    raise DesktopProviderExecutionError(
                        "SCOPED_SUCCESS_ATTEMPT_ID_MISMATCH"
                    )

                _siraj_scope_consumption_v2 = consumption_for_authorization(
                    self.repo_root,
                    self.episode_id,
                    str(replacement_authorization.get("authorization_id") or ""),
                )
                if _siraj_scope_consumption_v2 is None:
                    raise DesktopProviderExecutionError(
                        "SCOPED_SUCCESS_AUTHORIZATION_CONSUMPTION_MISSING"
                    )
                if (
                    str(_siraj_scope_consumption_v2.get("replacement_attempt_id") or "")
                    != attempt_id
                ):
                    raise DesktopProviderExecutionError(
                        "SCOPED_SUCCESS_CONSUMPTION_ATTEMPT_MISMATCH"
                    )

                _siraj_scope_max_requests_v2 = int(
                    replacement_authorization.get("maximum_provider_requests") or 0
                )
                _siraj_scope_max_cost_v2 = float(
                    replacement_authorization.get("maximum_cost_usd") or 0.0
                )
                if _siraj_scope_max_requests_v2 != 1:
                    raise DesktopProviderExecutionError(
                        "SCOPED_SUCCESS_REQUEST_CAP_INVALID"
                    )
                if expected_cost > _siraj_scope_max_cost_v2 + 1e-9:
                    raise DesktopProviderExecutionError(
                        "SCOPED_SUCCESS_COST_CAP_EXCEEDED"
                    )

                _siraj_historical_completed_v2 = len(
                    _siraj_durable_completed_units_v2
                )
                progress.update(
                    {
                        "status": "PROVIDER_EXECUTION_PAUSED_AUTHORIZATION_SCOPE",
                        "scope_completed_unit_id": _siraj_scope_unit_id_v2,
                        "scope_authorization_id": str(
                            replacement_authorization.get("authorization_id") or ""
                        ),
                        "scope_provider_requests_completed": 1,
                        "scope_maximum_provider_requests": 1,
                        "scope_planned_cost_usd": expected_cost,
                        "scope_maximum_cost_usd": _siraj_scope_max_cost_v2,
                        "historical_durable_completed_requests": (
                            _siraj_historical_completed_v2
                        ),
                        "total_durable_completed_after_scope": (
                            _siraj_historical_completed_v2 + 1
                        ),
                        "remaining_stage_not_authorized": True,
                        "automatic_paid_retry": False,
                        "automatic_paid_resubmission": False,
                    }
                )
                self._write_progress(progress)
                _append_hashed(
                    stage_path,
                    {
                        "status": "STAGE_PAUSED_AUTHORIZATION_SCOPE",
                        "episode_id": self.episode_id,
                        "stage": STAGE,
                        "session_id": session_id,
                        "binding": binding.as_dict(),
                        "scope_completed_unit_id": _siraj_scope_unit_id_v2,
                        "scope_authorization_id": str(
                            replacement_authorization.get("authorization_id") or ""
                        ),
                        "scope_replacement_attempt_id": attempt_id,
                        "scope_provider_operation_id": provider_operation_id or None,
                        "scope_provider_requests_completed": 1,
                        "scope_maximum_provider_requests": 1,
                        "scope_planned_cost_usd": expected_cost,
                        "scope_maximum_cost_usd": _siraj_scope_max_cost_v2,
                        "historical_durable_completed_requests": (
                            _siraj_historical_completed_v2
                        ),
                        "total_durable_completed_after_scope": (
                            _siraj_historical_completed_v2 + 1
                        ),
                        "remaining_stage_not_authorized": True,
                        "automatic_paid_retry": False,
                        "automatic_paid_resubmission": False,
                    },
                    hash_key="receipt_sha256",
                )
                raise DesktopProviderExecutionError(
                    "EXPLICIT_REPLACEMENT_COMPLETED_"
                    "REMAINING_STAGE_REQUIRES_SEPARATE_AUTHORIZATION:"
                    + _siraj_scope_unit_id_v2
                )

        # All durable per-request results exist before this receipt is written.
        _append_hashed(
            stage_path,
            {
                "status": "RESULTS_PERSISTED",
                "episode_id": self.episode_id,
                "stage": STAGE,
                "session_id": session_id,
                "binding": binding.as_dict(),
                "completed_requests": completed,
                "planned_requests": len(provider_units),
                "video_requests": video_count,
                "still_requests": still_count,
                "local_units": local_count,
                "estimated_spent_usd": spent,
                "result_references": result_refs,
                "attempt_references": attempt_refs,
            },
            hash_key="receipt_sha256",
        )
        ledger_before = binding.ledger_head_sha256
        try:
            self._fault("before_transition_commit")
            transition = append_transition_if_head(
                self.repo_root,
                self.episode_id,
                expected_ledger_sha256=ledger_before,
                stage=STAGE,
                previous_stage="MEDIA_COST_PREFLIGHT",
                status="COMPLETED",
                input_artifacts=[
                    {
                        "logical_output": "MEDIA_COST_PREFLIGHT_RESULT",
                        "path": review.result_path,
                        "sha256": binding.preflight_file_sha256,
                    },
                ],
                output_artifacts=result_refs,
                schema_versions=(SCHEMA_VERSION,),
                authorization_references=[
                    {
                        "receipt_id": binding.reack_receipt_id,
                        "status": VALID_STATUS,
                        "maximum_cost": binding.maximum_cost,
                        "currency": binding.currency,
                    }
                ],
                attempt_references=attempt_refs,
                metadata={
                    "execution_session_id": session_id,
                    "request_plan_hash": binding.request_plan_hash,
                    "cost_envelope": {"amount": binding.maximum_cost, "currency": binding.currency},
                    "automatic_paid_retry": False,
                    "automatic_paid_resubmission": False,
                    "provider_execution_started": True,
                    "provider_calls": completed,
                    "paid_attempts_created": completed,
                },
            )
        except Exception as exc:
            progress["status"] = "RESULT_PERSISTED_BUT_TRANSITION_NOT_COMMITTED"
            self._write_progress(progress)
            raise DesktopProviderExecutionError("RESULT_PERSISTED_BUT_TRANSITION_NOT_COMMITTED") from exc
        new_head = sha256_file(ledger_path(self.repo_root, self.episode_id))
        _append_hashed(
            stage_path,
            {
                "status": "STAGE_COMPLETED",
                "episode_id": self.episode_id,
                "stage": STAGE,
                "session_id": session_id,
                "binding": binding.as_dict(),
                "completed_requests": completed,
                "planned_requests": len(provider_units),
                "video_requests": video_count,
                "still_requests": still_count,
                "local_units": local_count,
                "estimated_spent_usd": spent,
                "next_stage": NEXT_STAGE,
                "transition_id": transition["transition_id"],
                "ledger_head_before_sha256": ledger_before,
                "ledger_head_after_sha256": new_head,
                "result_references": result_refs,
                "attempt_references": attempt_refs,
                "provider_execution_started": True,
                "automatic_paid_retry": False,
                "automatic_paid_resubmission": False,
            },
            hash_key="receipt_sha256",
        )
        progress.update(
            {
                "status": "PROVIDER_EXECUTION_COMPLETED",
                "completed_requests": completed,
                "pending_requests": 0,
                "remaining_authorized_usd": round(binding.maximum_cost - spent, 8),
                "next_stage": NEXT_STAGE,
                "ledger_head_after_sha256": new_head,
                "transition_id": transition["transition_id"],
            }
        )
        progress_path = self._write_progress(progress)
        return self._new_outcome(
            status="COMPLETED",
            session_id=session_id,
            completed=completed,
            planned=len(provider_units),
            video=video_count,
            still=still_count,
            local=local_count,
            failed=failed,
            unknown=unknown,
            spent=spent,
            envelope=binding.maximum_cost,
            next_stage=NEXT_STAGE,
            transition_id=str(transition["transition_id"]),
        )

    def reconcile(self) -> dict[str, Any]:
        """Read durable execution evidence without resubmitting anything."""

        attempts = read_jsonl(_attempt_receipt_path(self.repo_root, self.episode_id))
        statuses: dict[str, str] = {}
        provider_operation_ids: dict[str, str] = {}
        request_states: dict[str, str] = {}
        request_attempts: dict[str, str] = {}
        for row in attempts:
            attempt_id = str(row.get("attempt_id") or "")
            if attempt_id:
                statuses[attempt_id] = str(row.get("status") or "")
                unit_id = str(row.get("unit_id") or "")
                if unit_id:
                    request_attempts[unit_id] = attempt_id
                operation_id = str(row.get("provider_operation_id") or "").strip()
                if operation_id:
                    provider_operation_ids[attempt_id] = operation_id
        for unit_id, attempt_id in request_attempts.items():
            status = statuses.get(attempt_id, "")
            if status in {"ATTEMPT_COMPLETED", "LOCAL_UNIT_COMPLETED"}:
                request_states[unit_id] = "SUCCESS"
            elif status == SUBMITTED_PENDING or (
                status == "UNKNOWN" and attempt_id in provider_operation_ids
            ):
                request_states[unit_id] = SUBMITTED_PENDING
            elif status == "FAILED":
                request_states[unit_id] = "FAILED"
            elif status == "UNKNOWN":
                request_states[unit_id] = "UNKNOWN"
            else:
                request_states[unit_id] = "NOT_SUBMITTED"
        # SIRAJ_TERMINAL_PROVIDER_REJECTION_RECONCILE_GATE_V1
        # Legacy evidence can prove a prior UNKNOWN was never submitted.
        # Durable provider evidence can prove a real submission ended in a
        # terminal no-charge rejection. The latter stays blocked until a
        # separate explicit human replacement authorization.
        human_reconciliations: list[dict[str, Any]] = []
        for row in current_reconciliation_receipts(self.repo_root, self.episode_id):
            request_id = str(
                row.get("provider_request_id") or row.get("media_unit_id") or ""
            )
            if not request_id:
                continue
            original_submission_status = str(
                row.get("original_submission_status") or ""
            )
            request_status = str(row.get("request_status") or "")

            if original_submission_status == PROVEN_NOT_SUBMITTED:
                if request_status not in {"", NOT_SUBMITTED_ELIGIBLE}:
                    continue
                request_states[request_id] = NOT_SUBMITTED_ELIGIBLE
                request_attempts.pop(request_id, None)
                human_reconciliations.append(row)
                continue

            if (
                original_submission_status
                == PROVEN_SUBMITTED_TERMINAL_REJECTED
                and request_status
                == TERMINAL_REJECTION_REAUTHORIZATION_REQUIRED
                and row.get("original_charge_status") == PROVEN_NOT_CHARGED
                and row.get("terminal_provider_rejection") is True
                and row.get("safe_to_reauthorize") is True
                and row.get("explicit_no_charge_statement") is True
                and row.get("billable_output_detected") is False
                and row.get("historical_attempt_reusable") is False
                and row.get("new_attempt_required_for_future_submission") is True
                and row.get("replacement_authorized") is False
                and row.get("automatic_paid_retry") is False
                and row.get("automatic_paid_resubmission") is False
            ):
                # SIRAJ_EXPLICIT_TERMINAL_REPLACEMENT_AUTHORIZATION_V1
                replacement_authorization = (
                    terminal_replacement_authorization_for_request(
                        self.repo_root,
                        self.episode_id,
                        request_id,
                    )
                )
                if (
                    replacement_authorization is not None
                    and terminal_replacement_authorization_matches_reconciliation(
                        replacement_authorization,
                        row,
                    )
                ):
                    replacement_attempt_id = str(
                        replacement_authorization.get("replacement_attempt_id") or ""
                    )
                    historical_attempt_id = str(
                        replacement_authorization.get("historical_attempt_id") or ""
                    )
                    current_attempt_id = str(
                        request_attempts.get(request_id) or ""
                    )
                    current_state = str(
                        request_states.get(request_id) or ""
                    )

                    if current_attempt_id == replacement_attempt_id:
                        if current_state in {
                            "SUCCESS",
                            SUBMITTED_PENDING,
                            "FAILED",
                            "UNKNOWN",
                        }:
                            human_reconciliations.append(row)
                            continue

                        request_states[request_id] = NOT_SUBMITTED_ELIGIBLE
                        human_reconciliations.append(row)
                        continue

                    if (
                        current_attempt_id
                        and current_attempt_id != historical_attempt_id
                    ):
                        request_states[request_id] = "UNKNOWN"
                        human_reconciliations.append(row)
                        continue

                    request_states[request_id] = NOT_SUBMITTED_ELIGIBLE
                    request_attempts.pop(request_id, None)
                    human_reconciliations.append(row)
                    continue

                request_states[request_id] = (
                    TERMINAL_REJECTION_REAUTHORIZATION_REQUIRED
                )
                request_attempts.pop(request_id, None)
                human_reconciliations.append(row)
        stage_rows = read_jsonl(_stage_receipt_path(self.repo_root, self.episode_id))
        latest = stage_rows[-1] if stage_rows else None
        if latest and latest.get("status") == "RESULTS_PERSISTED":
            state = "RESULT_PERSISTED_BUT_TRANSITION_NOT_COMMITTED"
        elif latest and latest.get("status") == "STAGE_COMPLETED":
            state = "COMPLETED"
        else:
            state = str(latest.get("status") if latest else "NOT_STARTED")
        return {
            "schema_version": SCHEMA_VERSION,
            "episode_id": self.episode_id,
            "stage": STAGE,
            "state": state,
            "attempt_statuses": statuses,
            "provider_operation_ids": provider_operation_ids,
            "request_states": request_states,
            "request_attempts": request_attempts,
            "success_requests_skipped_on_resume": [
                unit_id for unit_id, status in request_states.items() if status == "SUCCESS"
            ],
            "not_submitted_requests_eligible": [
                unit_id
                for unit_id, status in request_states.items()
                if status in {"NOT_SUBMITTED", NOT_SUBMITTED_ELIGIBLE}
            ],
            "blocked_requests": [
                unit_id
                for unit_id, status in request_states.items()
                if status in {
                    "FAILED",
                    "UNKNOWN",
                    SUBMITTED_PENDING,
                    TERMINAL_REJECTION_REAUTHORIZATION_REQUIRED,
                }
            ],
            "terminal_rejection_reauthorization_required": [
                unit_id
                for unit_id, status in request_states.items()
                if status == TERMINAL_REJECTION_REAUTHORIZATION_REQUIRED
            ],
            "pending_attempts": [
                attempt_id
                for attempt_id, status in statuses.items()
                if status == SUBMITTED_PENDING or (
                    status == "UNKNOWN" and attempt_id in provider_operation_ids
                )
            ],
            "unknown_attempts": [
                attempt_id
                for attempt_id, status in statuses.items()
                if status == "UNKNOWN"
                and not any(
                    str(row.get("historical_attempt_id") or "") == attempt_id
                    for row in human_reconciliations
                )
            ],
            "human_provider_reconciliations": [
                {
                    "receipt_id": row.get("receipt_id"),
                    "historical_attempt_id": row.get("historical_attempt_id"),
                    "provider_request_id": row.get("provider_request_id"),
                    "request_status": row.get("request_status"),
                    "original_charge_status": row.get("original_charge_status"),
                }
                for row in human_reconciliations
            ],
            "reconciled_attempts": [
                str(row.get("historical_attempt_id") or "")
                for row in human_reconciliations
            ],
            "unknown_blocking_requests": [
                unit_id
                for unit_id, status in request_states.items()
                if status == "UNKNOWN"
            ],
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
            "provider_resubmission": False,
        }


def reconcile_unknown_attempt(
    repo_root: Path,
    episode_id: str,
    attempt_id: str,
    *,
    read_only_lookup: Callable[[str], Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Reconcile one durable attempt without ever submitting a new request.

    ``read_only_lookup`` is intentionally dependency-injected.  The real
    application does not provide one automatically: a provider-side query is
    allowed only when a durable provider operation ID exists and the caller
    can prove the query is read-only.  With no such ID this function returns
    ``SUBMISSION_STATUS_UNKNOWN`` and leaves the attempt blocked.
    """

    repo = Path(repo_root).resolve()
    path = _attempt_receipt_path(repo, episode_id)
    rows = [
        row for row in read_jsonl(path) if str(row.get("attempt_id") or "") == attempt_id
    ]
    human_receipt = reconciliation_for_attempt(repo, episode_id, attempt_id)
    if human_receipt is not None:
        # Human evidence is only allowed to clear an ambiguous historical
        # attempt. A conflicting local terminal receipt is a fail-closed
        # state conflict, never something to overwrite.
        if rows and str(rows[-1].get("status") or "") not in {
            "UNKNOWN",
            "SUBMISSION_STATUS_UNKNOWN",
            "NETWORK_RESULT_UNKNOWN",
        }:
            raise DesktopProviderExecutionError(
                "RECONCILIATION_CONFLICT_WITH_TERMINAL_ATTEMPT"
            )
        return {
            "attempt_id": attempt_id,
            "status": PROVEN_NOT_SUBMITTED,
            "charge_status": PROVEN_NOT_CHARGED,
            "request_status": NOT_SUBMITTED_ELIGIBLE,
            "provider_operation_id": None,
            "lookup_performed": False,
            "lookup_result": {},
            "latest_receipt": rows[-1] if rows else None,
            "reconciliation_receipt": human_receipt,
            "human_evidence_source": human_receipt.get("evidence_source"),
            "historical_unknown_preserved": bool(
                human_receipt.get("historical_unknown_preserved")
            ),
            "historical_attempt_spend_usd": float(
                human_receipt.get("historical_attempt_spend_usd") or 0.0
            ),
            "planned_future_request_cost_usd": float(
                human_receipt.get("planned_future_request_cost_usd") or 0.0
            ),
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
        }
    if not rows:
        return {
            "attempt_id": attempt_id,
            "status": "NOT_FOUND_IN_LOCAL_FORENSIC_EVIDENCE",
            "provider_operation_id": None,
            "lookup_performed": False,
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
        }
    operation_id = next(
        (
            str(row.get("provider_operation_id") or "").strip()
            for row in reversed(rows)
            if str(row.get("provider_operation_id") or "").strip()
        ),
        None,
    )
    latest_status = str(rows[-1].get("status") or "")
    if latest_status == "ATTEMPT_COMPLETED":
        status = "PROVEN_SUBMITTED_SUCCEEDED"
    elif operation_id:
        status = "PROVEN_SUBMITTED_PENDING_OR_ACCEPTED"
    else:
        status = "SUBMISSION_STATUS_UNKNOWN"

    lookup_result: Mapping[str, Any] | None = None
    if operation_id and read_only_lookup is not None:
        lookup_result = dict(read_only_lookup(operation_id))
        provider_status = str(lookup_result.get("status") or "").upper()
        if provider_status == "SUCCEEDED":
            status = "PROVEN_SUBMITTED_SUCCEEDED"
        elif provider_status == "FAILED":
            status = "PROVEN_SUBMITTED_FAILED"
        elif provider_status == "PENDING":
            status = "PROVEN_SUBMITTED_PENDING_OR_ACCEPTED"
        elif provider_status == "NOT_FOUND":
            # A provider NOT_FOUND response is not proof of non-submission
            # unless that provider's contract explicitly guarantees it.
            status = "SUBMISSION_STATUS_UNKNOWN"

    return {
        "attempt_id": attempt_id,
        "status": status,
        "provider_operation_id": operation_id,
        "lookup_performed": lookup_result is not None,
        "lookup_result": dict(lookup_result or {}),
        "latest_receipt": rows[-1],
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
    }


__all__ = [
    "CanonicalDesktopProviderExecutionExecutor",
    "CanonicalRunwarePaidGateway",
    "DesktopProviderExecutionError",
    "FakeAsyncPaidProviderGateway",
    "FakePaidProviderGateway",
    "ProviderExecutionBinding",
    "ProviderExecutionOutcome",
    "ProviderExecutionStaleStateError",
    "ProviderGateway",
    "reconcile_unknown_attempt",
    "STAGE_RECEIPT_LEDGER",
]
