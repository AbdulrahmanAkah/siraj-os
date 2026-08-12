"""V6.2.1 provider execution with perceptual duplicate stop."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
from typing import Mapping

from src.application.artifact_provenance_v1 import (
    atomic_write_json,
    preserve_existing,
    record_invalidation,
)

from src.application.local_graphics_renderer_v1 import render_graphic
# SIRAJ_STATIC_BLACK_HOLD_LOCAL_RENDERER_V6_6_R8
from src.application.siraj_visual_treatment_normalization_v6_6_r8 import (
    is_static_black_hold_spec,
    render_static_black_hold,
)
from src.application.runware_execution_v1 import (
    _matching_data,
    _response_error,
)
from src.application.paid_operation_gateway import (
    PaidOperationRequest,
    execute_bytes as execute_paid_bytes,
    execute_json as execute_paid_json,
    http_download_transport,
    http_json_transport,
)
from src.application.provider_model_contracts import (
    CONTRACT_VERSION as PROVIDER_CONTRACT_VERSION,
    validate_runware_task,
)
from src.application.siraj_episode_master_authorization_v6_6 import master_authorization_reference
from src.application.runware_seedream_negative_prompt_recovery_v1 import (
    prepare_runware_task_for_submission,
)
# SIRAJ_VEO31_REQUEST_CONTRACT_AND_TRUE_TELEMETRY_V6_6_R9
from src.application.siraj_live_telemetry_v6_6_r9 import emit_event
from src.application.siraj_runware_provider_contract_v6_6_r9 import (
    sanitize_runware_task_for_submission,
)
from src.application.siraj_duplicate_gates_v6_2_1 import (
    audit_completed_assets,
)
from src.application.media_cost_authority_v2 import (
    CostAuthorityError,
    require_complete_pricing_for_provider_execution,
)


class ProviderExecutionV621Error(RuntimeError):
    pass


def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path):
    value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ProviderExecutionV621Error(
            "JSON_OBJECT_REQUIRED:" + str(path)
        )
    return value


def _write(path, value):
    atomic_write_json(Path(path), value, preserve_previous=True)


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)
    return digest.hexdigest()


def _runware_key():
    value = (
        os.environ.get("RUNWARE_API_KEY", "").strip()
        or os.environ.get("SIRAJ_RUNWARE_API_KEY", "").strip()
    )
    if value:
        return value

    try:
        from src.application.windows_credentials_v1 import (
            read_runware_api_key,
        )
        value = str(read_runware_api_key() or "").strip()
    except Exception as exc:
        raise ProviderExecutionV621Error(
            "RUNWARE_CREDENTIAL_MANAGER_READ_FAILED:" + str(exc)
        ) from exc

    if not value:
        raise ProviderExecutionV621Error(
            "RUNWARE_API_KEY_REQUIRED:"
            "STORE_SECURELY_IN_SIRAJ_RUNWARE_API_KEY_CREDENTIAL"
        )
    return value


def _queue(repo, episode_id):
    path = (
        Path(repo).resolve()
        / "projects"
        / episode_id
        / "orchestration/media-production-queue-v6-2-1.json"
    )
    return path, _read(path)


def _auth(repo, episode_id, queue):
    path = (
        Path(repo).resolve()
        / "projects"
        / episode_id
        / "orchestration/media-production-paid-authorization-v6-2-1.json"
    )
    if not path.is_file():
        raise ProviderExecutionV621Error(
            "EXPLICIT_PAID_AUTHORIZATION_REQUIRED:"
            "PROVIDER_EXECUTION"
        )
    auth = _read(path)
    if (
        auth.get("status") != "ACTIVE"
        or auth.get("immutable_manifest_sha256")
        != queue.get("immutable_manifest_sha256")
        or auth.get("automatic_retry") is not False
    ):
        raise ProviderExecutionV621Error(
            "MEDIA_AUTHORIZATION_INVALID"
        )
    return auth


def authorize_media_queue(
    repo_root: Path,
    episode_id: str,
    confirmation_phrase: str,
):
    phrase = "أوافق على إنتاج الوسائط المدفوع"
    if confirmation_phrase.strip() != phrase:
        raise ProviderExecutionV621Error(
            "EXPLICIT_MEDIA_AUTHORIZATION_PHRASE_MISMATCH"
        )

    repo = Path(repo_root).resolve()
    queue_path, queue = _queue(repo, episode_id)
    auth_path = (
        repo
        / "projects"
        / episode_id
        / "orchestration/media-production-paid-authorization-v6-2-1.json"
    )

    if auth_path.exists():
        existing = _read(auth_path)
        if (
            existing.get("status") == "ACTIVE"
            and existing.get("immutable_manifest_sha256")
            == queue.get("immutable_manifest_sha256")
        ):
            return auth_path
        raise ProviderExecutionV621Error(
            "MEDIA_AUTHORIZATION_CONFLICT"
        )

    _write(
        auth_path,
        {
            "schema_version": (
                "siraj-media-paid-authorization-v6.2.1"
            ),
            "status": "ACTIVE",
            "episode_id": episode_id,
            "immutable_manifest_sha256": queue.get(
                "immutable_manifest_sha256"
            ),
            "authorization_source": (
                "EXPLICIT_HUMAN_DESKTOP_CONFIRMATION"
            ),
            "confirmation_phrase": phrase,
            "assistant_authored_cost_cap_usd": None,
            "automatic_retry": False,
            "automatic_resubmission": False,
            "authorized_at_utc": _now(),
        },
    )

    for item in queue.get("items", []):
        if (
            isinstance(item, dict)
            and item.get("status")
            == "AWAITING_EXPLICIT_PAID_AUTHORIZATION"
        ):
            item["status"] = "AUTHORIZED"
    queue["status"] = "AUTHORIZED"
    _write(queue_path, queue)
    return auth_path


def _result(payload, task_uuid, kind):
    error = _response_error(payload)
    if error:
        raise ProviderExecutionV621Error(
            "RUNWARE_PROVIDER_ERROR:" + error
        )
    value = _matching_data(payload, task_uuid)
    if value is None:
        return None
    key = (
        "imageURL"
        if kind == "RUNWARE_IMAGE"
        else "videoURL"
    )
    return value if value.get(key) else None


def _runware_json(repo, episode_id, task, *, operation, nonce, input_hashes):
    task = dict(validate_runware_task(task).payload)
    model = str(task.get("model") or "RUNWARE_CONTROL")
    request = PaidOperationRequest(
        repo_root=repo, episode_id=episode_id, stage="PROVIDER_EXECUTION",
        operation_type=operation, provider="RUNWARE", model=model,
        provider_contract_version=PROVIDER_CONTRACT_VERSION,
        payload=[task], input_artifact_hashes=input_hashes,
        master_authorization_reference=master_authorization_reference(repo, episode_id),
        operation_nonce=nonce,
    )
    return execute_paid_json(
        request,
        http_json_transport(
            url="https://api.runware.ai/v1", method="POST", payload=[task],
            headers={"Authorization": "Bearer " + _runware_key(),
                     "Content-Type": "application/json"}, timeout_seconds=240,
        ),
    )[1]


def _poll(repo, episode_id, api_key, task_uuid, kind):
    started = time.monotonic()
    poll_index = 0
    while True:
        if time.monotonic() - started > 1200:
            raise ProviderExecutionV621Error(
                "RUNWARE_POLL_TIMEOUT_RECOVERY_ONLY_"
                "NO_RESUBMISSION"
            )
        poll_index += 1
        poll_task = {"taskType": "getResponse", "taskUUID": task_uuid}
        value = _result(
            _runware_json(repo, episode_id, poll_task, operation="RUNWARE_POLL",
                          nonce=f"{task_uuid}:poll:{poll_index}",
                          input_hashes={"provider_task_uuid": task_uuid}),
            task_uuid,
            kind,
        )
        if value is not None:
            return value
        time.sleep(5)


def _download(url, destination, repo, episode_id):
    destination = Path(destination)
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    partial = destination.with_suffix(
        destination.suffix + ".part"
    )
    try:
        paid_request = PaidOperationRequest(
            repo_root=repo, episode_id=episode_id, stage="PROVIDER_EXECUTION",
            operation_type="RUNWARE_ASSET_DOWNLOAD", provider="RUNWARE",
            model="ASSET_DOWNLOAD", provider_contract_version=PROVIDER_CONTRACT_VERSION,
            payload={"url_sha256": hashlib.sha256(url.encode("utf-8")).hexdigest()},
            input_artifact_hashes={},
            master_authorization_reference=master_authorization_reference(repo, episode_id),
            operation_nonce=hashlib.sha256(url.encode("utf-8")).hexdigest(),
        )
        paid_result = execute_paid_bytes(
            paid_request,
            http_download_transport(url=url, headers={"User-Agent": "SIRAJ-V6.2.1"},
                                    timeout_seconds=240),
        )
        partial.write_bytes(paid_result.raw_response_path.read_bytes())
    except Exception as exc:
        if partial.is_file():
            record_invalidation(
                Path(repo).resolve(),
                episode_id,
                partial,
                reason="MEDIA_DOWNLOAD_FAILED_PARTIAL_PRESERVED",
                classification="FORENSIC",
            )
        raise ProviderExecutionV621Error(
            "MEDIA_DOWNLOAD_FAILED:" + str(exc)
        ) from exc

    if (
        not partial.is_file()
        or partial.stat().st_size <= 0
    ):
        raise ProviderExecutionV621Error(
            "MEDIA_DOWNLOAD_EMPTY"
        )
    preserve_existing(destination)
    os.replace(partial, destination)


def _duplicate_audit_or_stop(repo, queue_path, queue, item):
    problems = audit_completed_assets(
        repo,
        queue.get("items") or [],
    )
    if not problems:
        return

    item["status"] = (
        "COMPLETE_BUT_DUPLICATE_"
        "PAID_REPAIR_AUTH_REQUIRED"
    )
    queue["status"] = (
        "STOPPED_DUPLICATE_PAID_REPAIR_AUTH_REQUIRED"
    )
    queue["duplicate_problems"] = problems
    _write(queue_path, queue)

    raise ProviderExecutionV621Error(
        "POST_GENERATION_DUPLICATE_DETECTED_"
        "NO_AUTOMATIC_PAID_REGENERATION:"
        + json.dumps(
            problems,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )


def execute_item(
    repo_root: Path,
    episode_id: str,
    queue_id: str,
):
    # This V6 queue executor is retained as historical implementation
    # evidence.  Production execution for the migrated Desktop path must go
    # through ``CanonicalDesktopProviderExecutionExecutor`` and its single
    # paid gateway; allowing this function to be called directly would create
    # a legacy provider bypass.
    raise ProviderExecutionV621Error(
        "PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY:LEGACY_PROVIDER_EXECUTION_BLOCKED"
    )

    repo = Path(repo_root).resolve()
    try:
        require_complete_pricing_for_provider_execution(repo, episode_id)
    except CostAuthorityError as exc:
        raise ProviderExecutionV621Error(str(exc)) from exc
    queue_path, queue = _queue(repo, episode_id)
    items = queue.get("items")
    if not isinstance(items, list):
        raise ProviderExecutionV621Error(
            "MEDIA_QUEUE_ITEMS_REQUIRED"
        )

    item = next(
        (
            x
            for x in items
            if isinstance(x, dict)
            and x.get("queue_id") == queue_id
        ),
        None,
    )
    if item is None:
        raise ProviderExecutionV621Error(
            "QUEUE_ITEM_NOT_FOUND:" + queue_id
        )

    output = repo / str(
        item.get("output_path_relative") or ""
    )
    execution_root = (
        repo
        / "projects"
        / episode_id
        / "orchestration/provider-execution-v6-2-1"
    )
    lock = (
        execution_root
        / "locks"
        / (queue_id + "-attempt-01.json")
    )
    receipt = (
        execution_root
        / "receipts"
        / (queue_id + "-attempt-01.json")
    )

    if item.get("status") == "COMPLETE":
        if output.is_file() and receipt.is_file():
            return receipt
        raise ProviderExecutionV621Error(
            "COMPLETE_ITEM_ARTIFACT_MISSING:"
            + queue_id
        )

    kind = str(item.get("media_kind") or "")

    if kind == "LOCAL_GRAPHICS":
        spec_path = (
            repo
            / str(item.get("spec_path_relative") or "")
        )
        spec = _read(spec_path)
        if is_static_black_hold_spec(spec):
            result = render_static_black_hold(
                spec_path,
                output,
                receipt_path=receipt,
            )
        else:
            result = render_graphic(
                repo,
                spec_path,
                output,
                receipt_path=receipt,
            )
        item["status"] = "COMPLETE"
        item["output_sha256"] = result.output_sha256
        item["completed_at_utc"] = _now()
        _write(queue_path, queue)
        _duplicate_audit_or_stop(
            repo,
            queue_path,
            queue,
            item,
        )
        return receipt

    _auth(repo, episode_id, queue)

    if kind not in {
        "RUNWARE_IMAGE",
        "RUNWARE_VIDEO",
    }:
        raise ProviderExecutionV621Error(
            "UNSUPPORTED_MEDIA_KIND:" + kind
        )

    task_uuid = str(item.get("task_uuid") or "")
    task = dict(item.get("task_draft") or {})
    if not task_uuid or not task:
        raise ProviderExecutionV621Error(
            "RUNWARE_TASK_REQUIRED:" + queue_id
        )

    api_key = _runware_key()

    if lock.exists():
        locked = _read(lock)
        if (
            locked.get("status") == "COMPLETE"
            and output.is_file()
        ):
            return receipt
        if locked.get("task_uuid") != task_uuid:
            raise ProviderExecutionV621Error(
                "LOCKED_TASK_UUID_CHANGED_"
                "STRUCTURAL_STOP"
            )
        if (
            locked.get("provider_submission_started")
            is not True
        ):
            raise ProviderExecutionV621Error(
                "LOCK_EXISTS_BEFORE_KNOWN_SUBMISSION:"
                "EXPLICIT_REVIEW_REQUIRED"
            )

        # Safe recovery: query the same provider task UUID.
        # This is NOT a new paid generation request.
        result = _poll(
            repo,
            episode_id,
            api_key,
            task_uuid,
            kind,
        )
    else:
        lock.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        lock_payload = {
            "schema_version": (
                "siraj-provider-attempt-lock-v6.2.1"
            ),
            "episode_id": episode_id,
            "queue_id": queue_id,
            "task_uuid": task_uuid,
            "status": "LOCKED_BEFORE_NETWORK",
            "provider_submission_started": False,
            "automatic_paid_retry": False,
            "automatic_resubmission": False,
            "created_at_utc": _now(),
        }

        try:
            descriptor = os.open(
                lock,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL,
                0o600,
            )
        except FileExistsError as exc:
            raise ProviderExecutionV621Error(
                "ATTEMPT_ALREADY_LOCKED_RECOVERY_ONLY"
            ) from exc
        try:
            os.write(
                descriptor,
                (
                    json.dumps(
                        lock_payload,
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n"
                ).encode("utf-8"),
            )
        finally:
            os.close(descriptor)

        task = prepare_runware_task_for_submission(
            task
        )
        task = sanitize_runware_task_for_submission(task)
        task = dict(validate_runware_task(task).payload)
        lock_payload[
            "provider_submission_started"
        ] = True
        lock_payload[
            "status"
        ] = "NETWORK_REQUEST_STARTED"
        _write(lock, lock_payload)

        emit_event(
            repo,
            episode_id,
            "RUNWARE_TASK_SUBMISSION_STARTED",
            stage="PROVIDER_EXECUTION",
            message_ar="بدأ إرسال مهمة Runware",
            operation="إرسال طلب التوليد إلى Runware",
            output_path=str(output.relative_to(repo)).replace("\\", "/"),
            provider="RUNWARE",
            model=str(task.get("model") or item.get("selected_model") or ""),
            task_uuid=task_uuid,
            request_current=(items.index(item) + 1),
            request_total=len(items),
            status="SUBMITTING",
        )
        try:
            response = _runware_json(
                repo, episode_id, task, operation="RUNWARE_SUBMIT",
                nonce=task_uuid,
                input_hashes={
                    "queue_manifest": str(queue.get("immutable_manifest_sha256") or ""),
                    "provider_task_uuid": task_uuid,
                },
            )
        except Exception as exc:
            lock_payload["status"] = (
                "NETWORK_OR_PROVIDER_RESULT_UNKNOWN_"
                "NO_AUTOMATIC_RESUBMISSION"
            )
            lock_payload["last_error"] = str(exc)
            _write(lock, lock_payload)
            item["status"] = (
                "FAILED_OR_UNKNOWN_RETRY_AUTH_REQUIRED"
            )
            _write(queue_path, queue)
            raise ProviderExecutionV621Error(
                "PAID_PROVIDER_ATTEMPT_FAILED_"
                "RETRY_AUTH_REQUIRED:"
                + queue_id
                + ":"
                + str(exc)
            ) from exc

        result = _result(
            response,
            task_uuid,
            kind,
        )
        if result is None:
            emit_event(
                repo,
                episode_id,
                "RUNWARE_TASK_POLLING",
                stage="PROVIDER_EXECUTION",
                message_ar="Runware قبل المهمة ويجري انتظار النتيجة",
                operation="Polling لنفس task UUID دون إعادة إرسال",
                output_path=str(output.relative_to(repo)).replace("\\", "/"),
                provider="RUNWARE",
                model=str(task.get("model") or item.get("selected_model") or ""),
                task_uuid=task_uuid,
                request_current=(items.index(item) + 1),
                request_total=len(items),
                status="POLLING",
            )
            result = _poll(
                repo,
                episode_id,
                api_key,
                task_uuid,
                kind,
            )

    url_key = (
        "imageURL"
        if kind == "RUNWARE_IMAGE"
        else "videoURL"
    )
    output_url = str(
        result.get(url_key) or ""
    ).strip()
    if not output_url:
        raise ProviderExecutionV621Error(
            "RUNWARE_OUTPUT_URL_MISSING"
        )

    _download(
        output_url,
        output,
        repo,
        episode_id,
    )
    emit_event(
        repo,
        episode_id,
        "ASSET_DOWNLOADED",
        stage="PROVIDER_EXECUTION",
        message_ar="تم تنزيل الأصل المولد",
        operation="التحقق من الأصل وحفظ الإيصال",
        output_path=str(output.relative_to(repo)).replace("\\", "/"),
        last_completed_file=str(output.relative_to(repo)).replace("\\", "/"),
        provider="RUNWARE",
        model=str(task.get("model") or item.get("selected_model") or ""),
        task_uuid=task_uuid,
        request_current=(items.index(item) + 1),
        request_total=len(items),
        status="DOWNLOADED",
    )

    actual_cost = result.get("cost")
    receipt_payload = {
        "schema_version": (
            "siraj-provider-receipt-v6.2.1"
        ),
        "status": "PASS",
        "episode_id": episode_id,
        "queue_id": queue_id,
        "provider": "RUNWARE",
        "media_kind": kind,
        "task_uuid": task_uuid,
        "actual_cost_usd": (
            float(actual_cost)
            if isinstance(actual_cost, (int, float))
            else None
        ),
        "assistant_authored_cost_cap_usd": None,
        "output_path_relative": str(
            output.relative_to(repo)
        ).replace("\\", "/"),
        "output_sha256": _sha(output),
        "completed_at_utc": _now(),
    }
    _write(receipt, receipt_payload)
    _write(
        lock,
        {
            **_read(lock),
            "status": "COMPLETE",
            "completed_at_utc": _now(),
        },
    )

    item["status"] = "COMPLETE"
    item["actual_cost_usd"] = receipt_payload[
        "actual_cost_usd"
    ]
    item["output_sha256"] = receipt_payload[
        "output_sha256"
    ]
    item["completed_at_utc"] = _now()
    _write(queue_path, queue)

    # Paid duplicate failures are intentionally detected AFTER the completed
    # receipt has been preserved. Regeneration never happens automatically.
    _duplicate_audit_or_stop(
        repo,
        queue_path,
        queue,
        item,
    )

    if all(
        isinstance(candidate, Mapping)
        and candidate.get("status") == "COMPLETE"
        for candidate in items
    ):
        queue["status"] = "COMPLETE"
        queue["next_stage"] = (
            "LOCAL_ASSEMBLY_AND_MONTAGE"
        )
    else:
        queue["status"] = "IN_PROGRESS"
    _write(queue_path, queue)
    emit_event(
        repo,
        episode_id,
        "RUNWARE_TASK_COMPLETED",
        stage="PROVIDER_EXECUTION",
        message_ar="اكتملت مهمة Runware",
        operation="انتقال إلى عنصر الوسائط التالي",
        output_path=str(output.relative_to(repo)).replace("\\", "/"),
        last_completed_file=str(output.relative_to(repo)).replace("\\", "/"),
        provider="RUNWARE",
        model=str(task.get("model") or item.get("selected_model") or ""),
        task_uuid=task_uuid,
        request_current=(items.index(item) + 1),
        request_total=len(items),
        actual_cost_usd=receipt_payload.get("actual_cost_usd"),
        status="COMPLETE",
    )
    return receipt


def execute_queue(
    repo_root: Path,
    episode_id: str,
):
    raise ProviderExecutionV621Error(
        "PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY:LEGACY_PROVIDER_EXECUTION_BLOCKED"
    )

    repo = Path(repo_root).resolve()
    try:
        # Cost authority is a pre-network fail-closed boundary.  The legacy
        # queue remains a compatibility adapter, but it cannot bypass the
        # current V2 pricing and true-coverage contract.
        require_complete_pricing_for_provider_execution(repo, episode_id)
    except CostAuthorityError as exc:
        raise ProviderExecutionV621Error(str(exc)) from exc
    _, queue = _queue(repo, episode_id)
    items = queue.get("items")
    if not isinstance(items, list):
        raise ProviderExecutionV621Error(
            "MEDIA_QUEUE_ITEMS_REQUIRED"
        )

    results = []
    for item in sorted(
        items,
        key=lambda x: int(
            x.get("queue_index", 0) or 0
        ),
    ):
        status = str(item.get("status") or "")
        kind = str(item.get("media_kind") or "")

        if status == "COMPLETE":
            results.append(
                execute_item(
                    repo,
                    episode_id,
                    item["queue_id"],
                )
            )
        elif (
            kind == "LOCAL_GRAPHICS"
            and status == "READY_LOCAL_RENDER"
        ):
            results.append(
                execute_item(
                    repo,
                    episode_id,
                    item["queue_id"],
                )
            )
        elif status == "AUTHORIZED":
            results.append(
                execute_item(
                    repo,
                    episode_id,
                    item["queue_id"],
                )
            )
        else:
            raise ProviderExecutionV621Error(
                "QUEUE_STOPPED_NON_EXECUTABLE_ITEM:"
                + str(item.get("queue_id"))
                + ":"
                + status
            )

    return tuple(results)
