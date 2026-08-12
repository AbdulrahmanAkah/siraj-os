"""Single auditable gateway for every paid/provider network operation.

Adapters provide a model-specific payload and an explicit transport.  The
gateway owns immutable attempt identity, authorization binding, transport
boundary states, raw-result persistence, retry law, and telemetry ordering.
It never retries or resubmits automatically.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import socket
from typing import Any, Callable, Mapping, Protocol, Sequence
import urllib.error
import urllib.request
import uuid

from src.application.artifact_provenance_v1 import (
    append_jsonl,
    canonical_json_bytes,
    canonical_sha256,
    read_jsonl,
    sha256_file,
    utc_now,
    write_new_json,
)
from src.application.paid_retry_ledger_v1 import (
    record_retry_required,
    record_retry_transport_state,
)
from src.application.paid_operation_identity_v1 import (
    build_paid_operation_identity,
    provider_payload_sha256,
)
from src.application.provider_model_contracts import validate_runware_task


SCHEMA_VERSION = "siraj-paid-operation-attempt-v1"
ATTEMPT_NAMESPACE = uuid.UUID("fcf7a385-926a-4a9e-a190-d1dfb30acdb8")
CONTROLLED_ALIGNMENT_AUTHORIZATION_SCHEMA = (
    "siraj-controlled-alignment-validation-authorization-v1"
)

PLANNED = "PLANNED"
AUTHORIZED = "AUTHORIZED"
RESERVED = "RESERVED"
TRANSPORT_STARTING = "TRANSPORT_STARTING"
REQUEST_BYTES_HANDED_TO_TRANSPORT = "REQUEST_BYTES_HANDED_TO_TRANSPORT"
RESPONSE_HEADERS_RECEIVED = "RESPONSE_HEADERS_RECEIVED"
PROVIDER_TASK_ACCEPTED = "PROVIDER_TASK_ACCEPTED"
PROVIDER_OPERATION_ID_PERSISTED = "PROVIDER_OPERATION_ID_PERSISTED"
PROVIDER_SUBMISSION_INTENT_PERSISTED = "PROVIDER_SUBMISSION_INTENT_PERSISTED"
SUBMITTED_PENDING = "SUBMITTED_PENDING"
RESULT_RECEIVED = "RESULT_RECEIVED"
RESULT_PERSISTED = "RESULT_PERSISTED"
COMPLETE = "COMPLETE"
FAILED = "FAILED"
NETWORK_RESULT_UNKNOWN = "NETWORK_RESULT_UNKNOWN"
ABANDONED_NOT_RETRIED = "ABANDONED_NOT_RETRIED"

TERMINAL_FAILURES = {FAILED, NETWORK_RESULT_UNKNOWN, ABANDONED_NOT_RETRIED}


class PaidOperationGatewayError(RuntimeError):
    pass


class Transport(Protocol):
    def __call__(
        self,
        boundary: Callable[[str, Mapping[str, Any] | None], None],
    ) -> bytes: ...


TelemetryCallback = Callable[[str, Mapping[str, Any]], bool | None]


@dataclass(frozen=True, slots=True)
class PaidOperationRequest:
    repo_root: Path
    episode_id: str
    stage: str
    operation_type: str
    provider: str
    model: str
    provider_contract_version: str
    payload: Mapping[str, Any]
    input_artifact_hashes: Mapping[str, str]
    master_authorization_reference: Mapping[str, Any]
    authorization_mode: str = "EPISODE_MASTER"
    retry_authorization_reference: Mapping[str, Any] | None = None
    prior_attempt_id: str | None = None
    operation_nonce: str | None = None
    attempt_id: str | None = None

    @property
    def payload_sha256(self) -> str:
        return provider_payload_sha256(self.payload)

    @property
    def request_identity_sha256(self) -> str:
        return build_paid_operation_identity(
            episode_id=self.episode_id,
            stage=self.stage,
            operation_type=self.operation_type,
            provider=self.provider,
            model=self.model,
            provider_contract_version=self.provider_contract_version,
            payload=self.payload,
            input_artifact_hashes=self.input_artifact_hashes,
            operation_nonce=self.operation_nonce,
            authorization_mode=self.authorization_mode,
        )

    @property
    def canonical_request_identity_sha256(self) -> str:
        """The retry-binding identity for this immutable paid request."""

        return self.request_identity_sha256

    @property
    def immutable_attempt_id(self) -> str:
        if self.attempt_id:
            return self.attempt_id
        return str(uuid.uuid5(ATTEMPT_NAMESPACE, self.request_identity_sha256))


@dataclass(frozen=True, slots=True)
class PaidOperationResult:
    attempt_id: str
    request_identity_sha256: str
    payload_sha256: str
    status: str
    raw_response_path: Path
    response_sha256: str
    recovered_existing_attempt: bool

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["raw_response_path"] = str(self.raw_response_path)
        return value


class UrllibGatewayTransport:
    """The only production urllib transport used by remediated adapters."""

    def __init__(
        self,
        *,
        url: str,
        method: str,
        body: bytes | None,
        headers: Mapping[str, str],
        timeout_seconds: float,
    ) -> None:
        self.url = url
        self.method = method
        self.body = body
        self.headers = dict(headers)
        self.timeout_seconds = float(timeout_seconds)

    def __call__(
        self,
        boundary: Callable[[str, Mapping[str, Any] | None], None],
    ) -> bytes:
        request = urllib.request.Request(
            self.url,
            data=self.body,
            method=self.method,
            headers=self.headers,
        )
        boundary(
            REQUEST_BYTES_HANDED_TO_TRANSPORT,
            {
                "url_origin": urllib.request.urlparse(self.url).netloc
                if hasattr(urllib.request, "urlparse")
                else self.url.split("/", 3)[2],
                "method": self.method,
                "body_size": len(self.body or b""),
            },
        )
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            boundary(
                RESPONSE_HEADERS_RECEIVED,
                {
                    "http_status": getattr(response, "status", None),
                    "content_type": response.headers.get("Content-Type")
                    if getattr(response, "headers", None)
                    else None,
                },
            )
            return response.read()


def _attempt_root(request: PaidOperationRequest) -> Path:
    return (
        Path(request.repo_root).resolve()
        / "projects"
        / request.episode_id
        / "orchestration"
        / "paid-operation-attempts-v1"
        / request.immutable_attempt_id
    )


def _attempt_ledger(request: PaidOperationRequest) -> Path:
    return (
        Path(request.repo_root).resolve()
        / "projects"
        / request.episode_id
        / "orchestration"
        / "paid-operation-attempt-ledger-v1.jsonl"
    )


def _validate_reference(repo: Path, reference: Mapping[str, Any], label: str) -> None:
    path_text = str(reference.get("path") or "").strip()
    expected = str(reference.get("sha256") or "").strip().lower()
    if not path_text or len(expected) != 64:
        raise PaidOperationGatewayError(label + "_REFERENCE_INVALID")
    path = Path(path_text)
    if not path.is_absolute():
        path = repo / path
    path = path.resolve()
    try:
        path.relative_to(repo)
    except ValueError as exc:
        raise PaidOperationGatewayError(label + "_REFERENCE_OUTSIDE_REPOSITORY") from exc
    if not path.is_file() or sha256_file(path) != expected:
        raise PaidOperationGatewayError(label + "_REFERENCE_HASH_MISMATCH")


def _validate_master_authorization_content(
    repo: Path, reference: Mapping[str, Any], episode_id: str,
) -> None:
    path = Path(str(reference["path"]))
    if not path.is_absolute():
        path = repo / path
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaidOperationGatewayError("MASTER_AUTHORIZATION_CONTENT_INVALID") from exc
    if not isinstance(value, dict):
        raise PaidOperationGatewayError("MASTER_AUTHORIZATION_OBJECT_REQUIRED")
    signature = value.get("authorization_sha256")
    unsigned = {key: val for key, val in value.items() if key != "authorization_sha256"}
    expected_episode = (
        "NEXT_NEW_EPISODE" if episode_id == "episode-bootstrap-next" else episode_id
    )
    if (
        value.get("status") != "ACTIVE"
        or value.get("episode_id") != expected_episode
        or signature != canonical_sha256(unsigned)
        or value.get("automatic_paid_retry") is not False
        or value.get("automatic_paid_resubmission") is not False
        or value.get("publishing") != "HUMAN_ONLY"
    ):
        raise PaidOperationGatewayError("MASTER_AUTHORIZATION_CONTENT_INVALID")


def _validate_controlled_alignment_authorization_content(
    repo: Path,
    reference: Mapping[str, Any],
    request: PaidOperationRequest,
) -> None:
    """Validate the one-attempt post-migration alignment test authority.

    This is intentionally not interchangeable with an episode-wide master
    authorization.  It is bound to exactly one planned request identity and
    explicitly cannot authorize retries, resubmissions, other stages, or
    another provider.
    """

    path = Path(str(reference["path"]))
    if not path.is_absolute():
        path = repo / path
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PaidOperationGatewayError(
            "CONTROLLED_ALIGNMENT_AUTHORIZATION_CONTENT_INVALID"
        ) from exc
    if not isinstance(value, dict):
        raise PaidOperationGatewayError(
            "CONTROLLED_ALIGNMENT_AUTHORIZATION_OBJECT_REQUIRED"
        )
    signature = value.get("authorization_sha256")
    unsigned = {
        key: val for key, val in value.items() if key != "authorization_sha256"
    }
    required = {
        "schema_version": CONTROLLED_ALIGNMENT_AUTHORIZATION_SCHEMA,
        "status": "ACTIVE",
        "episode_id": request.episode_id,
        "scope": "CONTROLLED_ALIGNMENT_VALIDATION_ONLY",
        "allowed_stage": "NARRATION_VISUAL_ALIGNMENT_GATE",
        "allowed_provider": "OPENAI",
        "allowed_operation_type": "OPENAI_RESPONSES",
        "allowed_model": request.model,
        "maximum_real_luna_attempts": 1,
        "planned_attempt_id": request.immutable_attempt_id,
        "payload_sha256": request.payload_sha256,
        "request_identity_sha256": request.request_identity_sha256,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "authorizes_downstream_continuation": False,
        "authorizes_paid_retry": False,
        "authorizes_media_generation": False,
    }
    for key, expected in required.items():
        if value.get(key) != expected:
            raise PaidOperationGatewayError(
                "CONTROLLED_ALIGNMENT_AUTHORIZATION_BINDING_INVALID:" + key
            )
    if (
        request.stage != value["allowed_stage"]
        or request.provider != value["allowed_provider"]
        or request.operation_type != value["allowed_operation_type"]
        or signature != canonical_sha256(unsigned)
    ):
        raise PaidOperationGatewayError(
            "CONTROLLED_ALIGNMENT_AUTHORIZATION_CONTENT_INVALID"
        )


def _validate_authorization(
    repo: Path,
    request: PaidOperationRequest,
) -> None:
    _validate_reference(repo, request.master_authorization_reference, "AUTHORIZATION")
    if request.authorization_mode == "EPISODE_MASTER":
        _validate_master_authorization_content(
            repo, request.master_authorization_reference, request.episode_id
        )
        # Episode 002's V2 plan materially changed the paid request/cost
        # envelope.  The old episode-wide grant remains active as historical
        # authority, but it is not sufficient for PROVIDER_EXECUTION until a
        # Desktop cost-envelope re-ack receipt binds the exact preflight.
        if request.stage == "PROVIDER_EXECUTION":
            from src.application.desktop_resume_readiness_v1 import EPISODE_002
            if request.episode_id == EPISODE_002:
                from src.application.desktop_media_cost_preflight_v1 import (
                    MediaCostPreflightError,
                    read_persisted_media_cost_preflight,
                )

                try:
                    review = read_persisted_media_cost_preflight(
                        repo,
                        request.episode_id,
                    )
                except MediaCostPreflightError as exc:
                    raise PaidOperationGatewayError(
                        "COST_ENVELOPE_REACK_REQUIRED"
                    ) from exc
                if not review.provider_execution_allowed:
                    raise PaidOperationGatewayError(
                        "COST_ENVELOPE_REACK_REQUIRED"
                    )
        return
    if request.authorization_mode == "CONTROLLED_ALIGNMENT_VALIDATION":
        _validate_controlled_alignment_authorization_content(
            repo, request.master_authorization_reference, request
        )
        return
    raise PaidOperationGatewayError(
        "AUTHORIZATION_MODE_UNSUPPORTED:" + request.authorization_mode
    )


def _validate_retry_authorization(request: PaidOperationRequest) -> None:
    reference = request.retry_authorization_reference
    if reference is None:
        raise PaidOperationGatewayError(
            "SEPARATE_HUMAN_RETRY_AUTHORIZATION_REQUIRED:"
            + str(request.prior_attempt_id or "UNKNOWN_PRIOR_ATTEMPT")
        )
    required = {
        "status": "ACTIVE",
        "prior_attempt_id": request.prior_attempt_id,
        "new_attempt_id": request.immutable_attempt_id,
        "canonical_request_identity_sha256": (
            request.canonical_request_identity_sha256
        ),
        "provider_payload_sha256": request.payload_sha256,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "one_shot": True,
    }
    for key, expected in required.items():
        if reference.get(key) != expected:
            raise PaidOperationGatewayError(
                "RETRY_AUTHORIZATION_BINDING_INVALID:" + key
            )
    if not str(reference.get("reason") or "").strip():
        raise PaidOperationGatewayError("RETRY_AUTHORIZATION_REASON_REQUIRED")


def _attempt_events(request: PaidOperationRequest) -> list[dict[str, Any]]:
    return read_jsonl(_attempt_root(request) / "attempt-events.jsonl")


def _append_attempt_event(
    request: PaidOperationRequest,
    status: str,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    event: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "event_id": str(uuid.uuid4()),
        "attempt_id": request.immutable_attempt_id,
        "request_identity_sha256": request.request_identity_sha256,
        "payload_sha256": request.payload_sha256,
        "episode_id": request.episode_id,
        "stage": request.stage,
        "operation_type": request.operation_type,
        "provider": request.provider,
        "model": request.model,
        "provider_contract_version": request.provider_contract_version,
        "status": status,
        "prior_attempt_id": request.prior_attempt_id,
        "timestamp_utc": utc_now(),
        "details": dict(details or {}),
        "automatic_retry": False,
        "automatic_resubmission": False,
    }
    event["event_sha256"] = canonical_sha256(event)
    append_jsonl(_attempt_root(request) / "attempt-events.jsonl", event)
    append_jsonl(_attempt_ledger(request), event)
    return event


def record_provider_operation_id(
    request: PaidOperationRequest,
    provider_operation_id: str,
    *,
    details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Persist an acknowledged provider operation before any polling.

    This is deliberately an append-only, idempotent receipt.  It records the
    provider-side operation returned by the original submission; it never
    submits a payload and it is not a retry.  Adapters call it immediately
    after parsing an acknowledgement and before polling or downloading.
    """

    operation_id = str(provider_operation_id or "").strip()
    if not operation_id:
        raise PaidOperationGatewayError("PROVIDER_OPERATION_ID_REQUIRED")
    existing = _attempt_events(request)
    for row in existing:
        if (
            row.get("status") == PROVIDER_OPERATION_ID_PERSISTED
            and str(row.get("details", {}).get("provider_operation_id") or "")
            == operation_id
        ):
            return row
    payload = dict(details or {})
    payload.update(
        {
            "provider_operation_id": operation_id,
            "submission_status": SUBMITTED_PENDING,
            "submission_certainty": "PROVEN_SUBMITTED_PENDING_OR_ACCEPTED",
            "provider_acknowledged": True,
            "automatic_retry": False,
            "automatic_resubmission": False,
        }
    )
    return _append_attempt_event(request, PROVIDER_OPERATION_ID_PERSISTED, payload)


def _write_request_once(request: PaidOperationRequest) -> None:
    root = _attempt_root(request)
    target = root / "request.json"
    value: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "attempt_id": request.immutable_attempt_id,
        "request_identity_sha256": request.request_identity_sha256,
        "episode_id": request.episode_id,
        "stage": request.stage,
        "operation_type": request.operation_type,
        "provider": request.provider,
        "model": request.model,
        "provider_contract_version": request.provider_contract_version,
        "payload": request.payload,
        "payload_sha256": request.payload_sha256,
        "input_artifact_hashes": dict(sorted(request.input_artifact_hashes.items())),
        "master_authorization_reference": dict(request.master_authorization_reference),
        "retry_authorization_reference": dict(request.retry_authorization_reference or {}),
        "prior_attempt_id": request.prior_attempt_id,
        "operation_nonce": request.operation_nonce,
        # Runware taskUUID is a client-created provider identity.  Keep it as
        # a first-class field so recovery can audit the exact pre-send
        # identity without reconstructing the payload after a crash.
        "provider_task_uuid": (
            str(request.payload.get("taskUUID") or "")
            if request.provider.upper() == "RUNWARE"
            else None
        ),
        "created_at_utc": utc_now(),
    }
    value["request_record_sha256"] = canonical_sha256(value)
    if target.is_file():
        existing = json.loads(target.read_text(encoding="utf-8-sig"))
        if existing.get("request_identity_sha256") != request.request_identity_sha256:
            raise PaidOperationGatewayError("ATTEMPT_IDENTITY_COLLISION")
        return
    write_new_json(target, value)


def _validate_runware_submission_identity(request: PaidOperationRequest) -> None:
    """Fail closed before a Runware generation reaches transport.

    Historical planning artifacts remain readable through the permissive
    validator.  The paid gateway is stricter: every Runware generation must
    carry a client-created UUID v4 that can be used for later reconciliation.
    """

    if request.provider.upper() != "RUNWARE":
        return
    task_type = str(request.payload.get("taskType") or "")
    if task_type not in {"videoInference", "imageInference"}:
        return
    validate_runware_task(request.payload, require_uuid_v4=True)


def _safe_telemetry(
    callback: TelemetryCallback | None,
    event_type: str,
    payload: Mapping[str, Any],
) -> bool:
    if callback is None:
        return True
    try:
        result = callback(event_type, payload)
        return result is not False
    except Exception:
        return False


def execute_bytes(
    request: PaidOperationRequest,
    transport: Transport,
    *,
    telemetry: TelemetryCallback | None = None,
) -> PaidOperationResult:
    repo = Path(request.repo_root).resolve()
    _validate_authorization(repo, request)
    _validate_runware_submission_identity(request)
    root = _attempt_root(request)
    raw_path = root / "raw-response.bin"
    events = _attempt_events(request)
    if events:
        last_status = str(events[-1].get("status") or "")
        if any(
            str(row.get("status") or "") in {RESULT_PERSISTED, COMPLETE}
            for row in events
        ) and raw_path.is_file():
            return PaidOperationResult(
                attempt_id=request.immutable_attempt_id,
                request_identity_sha256=request.request_identity_sha256,
                payload_sha256=request.payload_sha256,
                status=COMPLETE,
                raw_response_path=raw_path,
                response_sha256=sha256_file(raw_path),
                recovered_existing_attempt=True,
            )
        if last_status == PROVIDER_OPERATION_ID_PERSISTED:
            raise PaidOperationGatewayError(
                "EXISTING_ATTEMPT_SUBMITTED_PENDING_NO_AUTOMATIC_RESUBMISSION:"
                + request.immutable_attempt_id
            )
        if last_status in TERMINAL_FAILURES:
            _validate_retry_authorization(request)
        if any(row.get("status") == REQUEST_BYTES_HANDED_TO_TRANSPORT for row in events):
            if not raw_path.is_file():
                raise PaidOperationGatewayError(
                    "EXISTING_ATTEMPT_POSSIBLY_SUBMITTED_NO_AUTOMATIC_RETRY:"
                    + request.immutable_attempt_id
                )

    if request.prior_attempt_id:
        _validate_retry_authorization(request)

    _write_request_once(request)
    if not events:
        _append_attempt_event(request, PLANNED)
        _append_attempt_event(request, AUTHORIZED)
        _append_attempt_event(request, RESERVED)
        if request.prior_attempt_id:
            record_retry_transport_state(
                repo, request.episode_id, prior_attempt_id=request.prior_attempt_id,
                new_attempt_id=request.immutable_attempt_id, event_type="RETRY_RESERVED",
            )
    if (
        request.provider.upper() == "RUNWARE"
        and str(request.payload.get("taskType") or "")
        in {"videoInference", "imageInference"}
        and not any(
            row.get("status") == PROVIDER_SUBMISSION_INTENT_PERSISTED
            for row in _attempt_events(request)
        )
    ):
        # The immutable request record has already been fsync'ed by
        # _write_request_once.  This receipt makes the exact task identity
        # explicit before TRANSPORT_STARTING and before any request bytes can
        # leave the process.
        _append_attempt_event(
            request,
            PROVIDER_SUBMISSION_INTENT_PERSISTED,
            {
                "provider_task_uuid": str(request.payload.get("taskUUID") or ""),
                "payload_sha256": request.payload_sha256,
                "request_record_durable": True,
                "automatic_retry": False,
                "automatic_resubmission": False,
            },
        )
    _append_attempt_event(request, TRANSPORT_STARTING)
    boundaries: list[str] = []

    def boundary(status: str, details: Mapping[str, Any] | None = None) -> None:
        if status not in {
            REQUEST_BYTES_HANDED_TO_TRANSPORT,
            RESPONSE_HEADERS_RECEIVED,
            PROVIDER_TASK_ACCEPTED,
        }:
            raise PaidOperationGatewayError("TRANSPORT_BOUNDARY_INVALID:" + status)
        boundaries.append(status)
        _append_attempt_event(request, status, details)
        if request.prior_attempt_id and status == REQUEST_BYTES_HANDED_TO_TRANSPORT:
            record_retry_transport_state(
                repo, request.episode_id, prior_attempt_id=request.prior_attempt_id,
                new_attempt_id=request.immutable_attempt_id,
                event_type="RETRY_REQUEST_BYTES_HANDED_TO_TRANSPORT",
            )

    try:
        raw = transport(boundary)
        if not isinstance(raw, bytes):
            raise PaidOperationGatewayError("TRANSPORT_BYTES_REQUIRED")
        _append_attempt_event(request, RESULT_RECEIVED, {"response_size": len(raw)})
        root.mkdir(parents=True, exist_ok=True)
        try:
            descriptor = raw_path.open("xb")
        except FileExistsError:
            if sha256_file(raw_path) != hashlib.sha256(raw).hexdigest():
                raise PaidOperationGatewayError("RAW_RESPONSE_HASH_CONFLICT")
        else:
            with descriptor:
                descriptor.write(raw)
                descriptor.flush()
                import os

                os.fsync(descriptor.fileno())
        response_hash = sha256_file(raw_path)
        _append_attempt_event(
            request,
            RESULT_PERSISTED,
            {
                "raw_response_path": str(raw_path.relative_to(repo)).replace("\\", "/"),
                "response_sha256": response_hash,
            },
        )
    except urllib.error.HTTPError as exc:
        body = exc.read()
        error_path = root / "http-error-response.bin"
        if not error_path.exists():
            error_path.parent.mkdir(parents=True, exist_ok=True)
            with error_path.open("xb") as handle:
                handle.write(body)
                handle.flush()
                import os

                os.fsync(handle.fileno())
        _append_attempt_event(
            request,
            FAILED,
            {"http_status": exc.code, "error_response_sha256": sha256_file(error_path)},
        )
        record_retry_required(
            repo, request.episode_id, stage=request.stage,
            prior_attempt_id=request.immutable_attempt_id, prior_status=FAILED,
            prior_payload_hash=request.payload_sha256,
            failure_classification=f"HTTP_{exc.code}",
        )
        raise PaidOperationGatewayError(
            f"PAID_PROVIDER_FAILED_NO_AUTOMATIC_RETRY:HTTP_{exc.code}:"
            f"{request.immutable_attempt_id}"
        ) from exc
    except Exception as exc:
        status = (
            NETWORK_RESULT_UNKNOWN
            if REQUEST_BYTES_HANDED_TO_TRANSPORT in boundaries
            else FAILED
        )
        _append_attempt_event(
            request,
            status,
            {
                "error_type": type(exc).__name__,
                "error": str(exc),
                "request_bytes_handed": REQUEST_BYTES_HANDED_TO_TRANSPORT in boundaries,
                "root_cause_classification": (
                    "TRANSPORT_RESULT_UNKNOWN_AFTER_REQUEST_BYTES_HANDOFF"
                    if REQUEST_BYTES_HANDED_TO_TRANSPORT in boundaries
                    else "LOCAL_PRE_SUBMISSION_FAILURE"
                ),
                "provider_operation_id_persisted": False,
            },
        )
        record_retry_required(
            repo, request.episode_id, stage=request.stage,
            prior_attempt_id=request.immutable_attempt_id, prior_status=status,
            prior_payload_hash=request.payload_sha256,
            failure_classification=type(exc).__name__,
        )
        if request.prior_attempt_id:
            record_retry_transport_state(
                repo, request.episode_id, prior_attempt_id=request.prior_attempt_id,
                new_attempt_id=request.immutable_attempt_id,
                event_type="RETRY_FAILED_OR_UNKNOWN",
            )
        label = (
            "NETWORK_RESULT_UNKNOWN_NO_AUTOMATIC_RETRY"
            if status == NETWORK_RESULT_UNKNOWN
            else "NOT_SUBMITTED_FAILED_NO_AUTOMATIC_RETRY"
        )
        raise PaidOperationGatewayError(
            label + ":" + request.immutable_attempt_id
        ) from exc

    telemetry_ok = _safe_telemetry(
        telemetry,
        "TASK_COMPLETED",
        {
            "attempt_id": request.immutable_attempt_id,
            "episode_id": request.episode_id,
            "stage": request.stage,
            "provider": request.provider,
            "model": request.model,
            "response_sha256": response_hash,
        },
    )
    _append_attempt_event(
        request,
        COMPLETE,
        {"telemetry_projected": telemetry_ok},
    )
    if request.prior_attempt_id:
        record_retry_transport_state(
            repo, request.episode_id, prior_attempt_id=request.prior_attempt_id,
            new_attempt_id=request.immutable_attempt_id,
            event_type="RETRY_RESULT_PERSISTED",
        )
    return PaidOperationResult(
        attempt_id=request.immutable_attempt_id,
        request_identity_sha256=request.request_identity_sha256,
        payload_sha256=request.payload_sha256,
        status=COMPLETE,
        raw_response_path=raw_path,
        response_sha256=response_hash,
        recovered_existing_attempt=False,
    )


def execute_json(
    request: PaidOperationRequest,
    transport: Transport,
    *,
    telemetry: TelemetryCallback | None = None,
) -> tuple[PaidOperationResult, dict[str, Any]]:
    result = execute_bytes(request, transport, telemetry=telemetry)
    raw = result.raw_response_path.read_bytes()
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        _append_attempt_event(
            request,
            FAILED,
            {
                "classification": "PROVIDER_RESPONSE_INVALID_JSON",
                "raw_response_preserved": True,
            },
        )
        raise PaidOperationGatewayError(
            "PROVIDER_RESPONSE_INVALID_JSON_NO_AUTOMATIC_RETRY:"
            + request.immutable_attempt_id
        ) from exc
    if not isinstance(value, dict):
        raise PaidOperationGatewayError("PROVIDER_RESPONSE_OBJECT_REQUIRED")
    return result, value


def http_json_transport(
    *,
    url: str,
    method: str,
    payload: Mapping[str, Any] | Sequence[Any] | None,
    headers: Mapping[str, str],
    timeout_seconds: float,
) -> UrllibGatewayTransport:
    body = None if payload is None else canonical_json_bytes(payload)
    return UrllibGatewayTransport(
        url=url,
        method=method,
        body=body,
        headers=headers,
        timeout_seconds=timeout_seconds,
    )


def http_download_transport(
    *,
    url: str,
    headers: Mapping[str, str],
    timeout_seconds: float,
) -> UrllibGatewayTransport:
    return UrllibGatewayTransport(
        url=url,
        method="GET",
        body=None,
        headers=headers,
        timeout_seconds=timeout_seconds,
    )


def is_network_ambiguity(error: BaseException) -> bool:
    return isinstance(error, (TimeoutError, socket.timeout, ConnectionError))
