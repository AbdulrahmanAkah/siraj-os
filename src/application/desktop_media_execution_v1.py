from __future__ import annotations

import hashlib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from src.application.episode_cost_ledger_v1 import HARD_CAP_USD, scan_episode_costs
from src.application.local_graphics_renderer_v1 import render_graphic
from src.application.runware_execution_v1 import (
    ProductionGateError,
    _matching_data,
    _post_json,
    _response_error,
)

RELEASE = "DESKTOP_MEDIA_EXECUTION_V1"
ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
MEDIA_QUEUE_REL = Path("orchestration/media-production-queue-v1.json")
EXECUTION_ROOT_REL = Path("orchestration/media-execution")
RUNWARE_POLL_INTERVAL_SECONDS = 5.0
RUNWARE_POLL_TIMEOUT_SECONDS = 900.0
ELEVENLABS_API_ROOT = "https://api.elevenlabs.io/v1"
TTS_TOTAL_RESERVE_USD = 3.0

ProgressCallback = Callable[[str, int | None], None]


class DesktopMediaExecutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class MediaQueueRow:
    queue_id: str
    queue_index: int
    media_kind: str
    source_id: str
    provider: str
    model_or_voice: str
    status: str
    maximum_authorized_usd: float
    output_path_relative: str


@dataclass(frozen=True, slots=True)
class MediaExecutionResult:
    queue_id: str
    media_kind: str
    status: str
    output_path: Path
    receipt_path: Path
    task_uuid: str | None
    actual_cost_usd: float | None
    estimated_cost_usd: float | None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DesktopMediaExecutionError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise DesktopMediaExecutionError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return value
    return ()


def _active_episode(
    repo_root: Path,
) -> tuple[str, Path, Path, dict[str, Any], dict[str, Any]]:
    repo = repo_root.resolve()
    state_path = repo / ORCHESTRATOR_STATE_REL
    state = _read(state_path)
    episode_id = state.get("current_episode_id")
    if not isinstance(episode_id, str) or not episode_id.strip():
        raise DesktopMediaExecutionError("CURRENT_EPISODE_REQUIRED_FOR_MEDIA_EXECUTION")
    episode_root = repo / "projects" / episode_id.strip()
    queue_path = episode_root / MEDIA_QUEUE_REL
    if not queue_path.is_file():
        raise DesktopMediaExecutionError("MEDIA_PRODUCTION_QUEUE_NOT_FOUND")
    queue = _read(queue_path)
    allowed = {
        "MEDIA_QUEUE_READY",
        "DESKTOP_MEDIA_EXECUTION_ACTIVE",
        "MEDIA_ASSETS_COMPLETE",
    }
    if str(state.get("status", "")) not in allowed:
        raise DesktopMediaExecutionError(
            "DESKTOP_MEDIA_EXECUTION_NOT_ALLOWED:" + str(state.get("status", ""))
        )
    return episode_id.strip(), episode_root, queue_path, state, queue


def _queue_collections(
    queue: Mapping[str, Any],
) -> tuple[tuple[str, list[dict[str, Any]]], ...]:
    queues = queue.get("queues")
    if not isinstance(queues, Mapping):
        raise DesktopMediaExecutionError("MEDIA_QUEUE_COLLECTIONS_REQUIRED")
    result: list[tuple[str, list[dict[str, Any]]]] = []
    for key in (
        "runware_images",
        "runware_videos",
        "local_graphics",
        "elevenlabs_tts",
    ):
        raw = queues.get(key)
        if not isinstance(raw, list):
            raise DesktopMediaExecutionError(f"MEDIA_QUEUE_LIST_REQUIRED:{key}")
        values: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                raise DesktopMediaExecutionError(
                    f"MEDIA_QUEUE_ITEM_OBJECT_REQUIRED:{key}"
                )
            values.append(item)
        result.append((key, values))
    return tuple(result)


def _kind_for_collection(collection: str) -> str:
    return {
        "runware_images": "RUNWARE_IMAGE",
        "runware_videos": "RUNWARE_VIDEO",
        "local_graphics": "LOCAL_GRAPHICS",
        "elevenlabs_tts": "ELEVENLABS_TTS",
    }[collection]


def _provider_for_kind(kind: str) -> str:
    if kind in {"RUNWARE_IMAGE", "RUNWARE_VIDEO"}:
        return "RUNWARE"
    if kind == "ELEVENLABS_TTS":
        return "ELEVENLABS"
    return "LOCAL"


def _tts_maximum(queue: Mapping[str, Any], item: Mapping[str, Any]) -> float:
    tts_items = queue["queues"]["elevenlabs_tts"]
    total_chars = sum(
        len(str(value.get("text_ar", "")))
        for value in tts_items
        if isinstance(value, Mapping)
    )
    item_chars = len(str(item.get("text_ar", "")))
    if total_chars <= 0 or item_chars <= 0:
        raise DesktopMediaExecutionError("TTS_CHARACTER_BUDGET_INVALID")
    return round(TTS_TOTAL_RESERVE_USD * item_chars / total_chars, 6)


def media_queue_rows(repo_root: Path) -> tuple[MediaQueueRow, ...]:
    _, _, _, _, queue = _active_episode(repo_root)
    rows: list[MediaQueueRow] = []
    for collection, items in _queue_collections(queue):
        kind = _kind_for_collection(collection)
        for item in items:
            if kind == "ELEVENLABS_TTS":
                model = f"{item.get('voice_slot', '')} / {item.get('model_id', '')}"
                source_id = str(item.get("segment_id", ""))
                maximum = _tts_maximum(queue, item)
            elif kind == "LOCAL_GRAPHICS":
                model = str(item.get("graphic_type", ""))
                source_id = str(item.get("shot_id", ""))
                maximum = 0.0
            else:
                model = str(item.get("selected_model", ""))
                source_id = str(item.get("shot_id", ""))
                maximum = float(item.get("maximum_authorized_usd", 0.0))
            rows.append(
                MediaQueueRow(
                    queue_id=str(item.get("queue_id", "")),
                    queue_index=int(item.get("queue_index", 0)),
                    media_kind=kind,
                    source_id=source_id,
                    provider=_provider_for_kind(kind),
                    model_or_voice=model,
                    status=str(item.get("status", "")),
                    maximum_authorized_usd=maximum,
                    output_path_relative=str(item.get("output_path_relative", "")),
                )
            )
    return tuple(sorted(rows, key=lambda value: (value.queue_index, value.queue_id)))


def _find_item(
    queue: Mapping[str, Any],
    queue_id: str,
) -> tuple[str, dict[str, Any]]:
    for collection, items in _queue_collections(queue):
        for item in items:
            if str(item.get("queue_id", "")) == queue_id:
                return collection, item
    raise DesktopMediaExecutionError(f"MEDIA_QUEUE_ITEM_NOT_FOUND:{queue_id}")


def _paths(episode_root: Path, queue_id: str) -> tuple[Path, Path]:
    safe = "".join(
        character
        for character in queue_id
        if character.isalnum() or character in "-_"
    )
    root = episode_root / EXECUTION_ROOT_REL
    return (
        root / "locks" / f"{safe}-attempt-01.json",
        root / "receipts" / f"{safe}-attempt-01-receipt.json",
    )


def _exclusive_lock(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    ).encode("utf-8")
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise DesktopMediaExecutionError(
            "ATTEMPT_ALREADY_LOCKED_USE_RECOVERY"
        ) from exc
    try:
        os.write(descriptor, raw)
    finally:
        os.close(descriptor)


def _budget_preflight(
    repo_root: Path,
    episode_id: str,
    maximum_authorized_usd: float,
) -> dict[str, Any]:
    maximum = float(maximum_authorized_usd)
    if maximum <= 0:
        raise DesktopMediaExecutionError("POSITIVE_MAXIMUM_AUTHORIZED_COST_REQUIRED")
    snapshot = scan_episode_costs(repo_root, episode_id)
    projected = snapshot.recorded_total_usd + maximum
    if projected > HARD_CAP_USD + 1e-9:
        raise DesktopMediaExecutionError(
            "EPISODE_BUDGET_HARD_CAP_BLOCKED:"
            f"recorded={snapshot.recorded_total_usd:.4f}:"
            f"maximum={maximum:.4f}:projected={projected:.4f}:"
            f"cap={HARD_CAP_USD:.2f}"
        )
    return {
        "recorded_total_usd": snapshot.recorded_total_usd,
        "maximum_authorized_usd": maximum,
        "projected_total_usd": round(projected, 8),
        "hard_cap_usd": HARD_CAP_USD,
        "remaining_after_maximum_usd": round(HARD_CAP_USD - projected, 8),
    }


def _download_url(url: str, destination: Path, *, timeout: float = 240.0) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SIRAJ-Desktop-Media-Execution/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response, partial.open(
            "wb"
        ) as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
    except (urllib.error.HTTPError, urllib.error.URLError) as exc:
        partial.unlink(missing_ok=True)
        raise DesktopMediaExecutionError(f"MEDIA_DOWNLOAD_FAILED:{exc}") from exc
    if not partial.is_file() or partial.stat().st_size <= 0:
        partial.unlink(missing_ok=True)
        raise DesktopMediaExecutionError("MEDIA_DOWNLOAD_EMPTY")
    os.replace(partial, destination)


def _runware_result(
    payload: Mapping[str, Any],
    task_uuid: str,
    kind: str,
) -> Mapping[str, Any] | None:
    error = _response_error(payload)
    if error:
        raise DesktopMediaExecutionError("RUNWARE_PROVIDER_ERROR:" + error)
    result = _matching_data(payload, task_uuid)
    if result is None:
        return None
    output_key = "imageURL" if kind == "RUNWARE_IMAGE" else "videoURL"
    return result if result.get(output_key) else None


def _poll_runware(
    api_key: str,
    task_uuid: str,
    kind: str,
    *,
    progress: ProgressCallback | None,
) -> Mapping[str, Any]:
    started = time.monotonic()
    while True:
        if time.monotonic() - started > RUNWARE_POLL_TIMEOUT_SECONDS:
            raise DesktopMediaExecutionError("RUNWARE_POLL_TIMEOUT_USE_RECOVERY")
        if progress:
            progress(
                f"استعادة/انتظار مهمة Runware — {int(time.monotonic() - started)} ثانية",
                None,
            )
        payload = _post_json(
            api_key,
            [{"taskType": "getResponse", "taskUUID": task_uuid}],
        )
        result = _runware_result(payload, task_uuid, kind)
        if result is not None:
            return result
        time.sleep(RUNWARE_POLL_INTERVAL_SECONDS)


def _write_receipt_and_complete(
    repo_root: Path,
    queue_path: Path,
    state_path: Path,
    state: dict[str, Any],
    queue: dict[str, Any],
    item: dict[str, Any],
    receipt_path: Path,
    receipt: dict[str, Any],
) -> None:
    _write(receipt_path, receipt)
    item.update(
        {
            "status": "COMPLETE",
            "receipt_path_relative": str(
                receipt_path.relative_to(repo_root.resolve())
            ).replace("\\", "/"),
            "completed_at_utc": _now(),
            "actual_cost_usd": receipt.get("actual_cost_usd"),
            "estimated_cost_usd": receipt.get("estimated_cost_usd"),
            "output_sha256": receipt.get("output_sha256"),
        }
    )
    _write(queue_path, queue)
    all_complete = all(
        str(candidate.get("status", "")) == "COMPLETE"
        for _, items in _queue_collections(queue)
        for candidate in items
    )
    state.update(
        {
            "status": (
                "MEDIA_ASSETS_COMPLETE"
                if all_complete
                else "DESKTOP_MEDIA_EXECUTION_ACTIVE"
            ),
            "stage": (
                "STRUCTURAL_MONTAGE" if all_complete else "DESKTOP_MEDIA_EXECUTION"
            ),
            "next_stage": (
                "STRUCTURAL_MONTAGE_V1"
                if all_complete
                else "DESKTOP_MEDIA_EXECUTION_V1"
            ),
            "last_error": None,
            "updated_at_utc": _now(),
        }
    )
    _write(state_path, state)


def execute_runware_item(
    repo_root: Path,
    queue_id: str,
    api_key: str,
    *,
    confirmed_maximum_usd: float,
    recovery_only: bool = False,
    progress: ProgressCallback | None = None,
) -> MediaExecutionResult:
    repo = repo_root.resolve()
    episode_id, episode_root, queue_path, state, queue = _active_episode(repo)
    collection, item = _find_item(queue, queue_id)
    kind = _kind_for_collection(collection)
    if kind not in {"RUNWARE_IMAGE", "RUNWARE_VIDEO"}:
        raise DesktopMediaExecutionError("RUNWARE_ITEM_REQUIRED")
    if str(item.get("status", "")) == "COMPLETE":
        raise DesktopMediaExecutionError("MEDIA_QUEUE_ITEM_ALREADY_COMPLETE")

    maximum = float(item.get("maximum_authorized_usd", 0.0))
    if abs(float(confirmed_maximum_usd) - maximum) > 1e-9:
        raise DesktopMediaExecutionError("EXPLICIT_AUTHORIZATION_MAXIMUM_MISMATCH")
    budget = _budget_preflight(repo, episode_id, maximum)
    lock_path, receipt_path = _paths(episode_root, queue_id)
    state_path = repo / ORCHESTRATOR_STATE_REL

    if recovery_only:
        if not lock_path.is_file():
            raise DesktopMediaExecutionError("RUNWARE_RECOVERY_LOCK_NOT_FOUND")
        lock = _read(lock_path)
        task_uuid = str(lock.get("task_uuid", ""))
        if not task_uuid:
            raise DesktopMediaExecutionError("RUNWARE_RECOVERY_TASK_UUID_MISSING")
        result = _poll_runware(api_key, task_uuid, kind, progress=progress)
    else:
        if lock_path.exists():
            raise DesktopMediaExecutionError("ATTEMPT_ALREADY_LOCKED_USE_RECOVERY")
        task_uuid = str(uuid.uuid4())
        task = dict(item.get("task_draft") or {})
        task["taskUUID"] = task_uuid
        task["deliveryMethod"] = "async"
        task["includeCost"] = True
        task.setdefault("outputType", "URL")
        task.setdefault(
            "outputFormat",
            "JPG" if kind == "RUNWARE_IMAGE" else "MP4",
        )
        if kind == "RUNWARE_VIDEO":
            google = task.setdefault("providerSettings", {}).setdefault(
                "google", {}
            )
            google["generateAudio"] = False
            google["personGeneration"] = (
                "allow_adult"
                if item.get("person_generation_resolution_required")
                else "dont_allow"
            )
        lock = {
            "schema_version": "siraj-desktop-media-submission-lock-v1",
            "release": RELEASE,
            "episode_id": episode_id,
            "queue_id": queue_id,
            "media_kind": kind,
            "task_uuid": task_uuid,
            "status": "LOCKED_BEFORE_NETWORK",
            "maximum_authorized_usd": maximum,
            "budget_preflight": budget,
            "request_payload_sha256": _canonical_sha256({"tasks": [task]}),
            "request_payload": [task],
            "explicit_desktop_authorization": True,
            "paid_submission_trigger": (
                "ONE_EXPLICIT_DESKTOP_AUTHORIZATION_PER_ATTEMPT"
            ),
            "hidden_paid_retry": "FORBIDDEN",
            "api_key_persisted": False,
            "created_at_utc": _now(),
        }
        _exclusive_lock(lock_path, lock)
        item["status"] = "SUBMISSION_LOCKED"
        item["task_uuid"] = task_uuid
        _write(queue_path, queue)
        if progress:
            progress("تم قفل المحاولة قبل الاتصال بـRunware.", 5)
        try:
            response = _post_json(api_key, [task])
        except ProductionGateError as exc:
            lock["status"] = "NETWORK_RESULT_UNKNOWN_USE_RECOVERY"
            lock["last_error"] = str(exc)
            lock["updated_at_utc"] = _now()
            _write(lock_path, lock)
            raise DesktopMediaExecutionError(str(exc)) from exc
        lock["status"] = "SUBMITTED_POLLING"
        lock["provider_acknowledgement"] = response
        lock["updated_at_utc"] = _now()
        _write(lock_path, lock)
        result = _runware_result(response, task_uuid, kind)
        if result is None:
            result = _poll_runware(api_key, task_uuid, kind, progress=progress)

    output_key = "imageURL" if kind == "RUNWARE_IMAGE" else "videoURL"
    uuid_key = "imageUUID" if kind == "RUNWARE_IMAGE" else "videoUUID"
    output_url = str(result.get(output_key, "")).strip()
    if not output_url:
        raise DesktopMediaExecutionError("RUNWARE_OUTPUT_URL_MISSING")
    output_path = repo / str(item.get("output_path_relative", ""))
    if progress:
        progress("تنزيل ملف Runware وحساب البصمة.", 92)
    _download_url(output_url, output_path)
    actual_cost = result.get("cost")
    if not isinstance(actual_cost, (int, float)):
        actual_cost = None
    receipt = {
        "schema_version": "siraj-desktop-media-receipt-v1",
        "release": RELEASE,
        "episode_id": episode_id,
        "queue_id": queue_id,
        "media_type": kind,
        "provider": "RUNWARE",
        "cost_category": (
            "RUNWARE_IMAGES" if kind == "RUNWARE_IMAGE" else "RUNWARE_VIDEO"
        ),
        "task_uuid": task_uuid,
        "provider_output_uuid": result.get(uuid_key),
        "provider_output_url": output_url,
        "actual_cost_usd": actual_cost,
        "maximum_authorized_usd": maximum,
        "provider_cost_within_authorized_maximum": (
            actual_cost is None or float(actual_cost) <= maximum + 1e-9
        ),
        "output_path_relative": str(output_path.relative_to(repo)).replace(
            "\\", "/"
        ),
        "output_sha256": _sha256(output_path),
        "output_bytes": output_path.stat().st_size,
        "hidden_paid_retry": "FORBIDDEN",
        "completed_at_utc": _now(),
    }
    _write_receipt_and_complete(
        repo,
        queue_path,
        state_path,
        state,
        queue,
        item,
        receipt_path,
        receipt,
    )
    if progress:
        progress("اكتمل تنفيذ العنصر وحُفظ الإيصال.", 100)
    return MediaExecutionResult(
        queue_id=queue_id,
        media_kind=kind,
        status="COMPLETE",
        output_path=output_path,
        receipt_path=receipt_path,
        task_uuid=task_uuid,
        actual_cost_usd=actual_cost,
        estimated_cost_usd=None,
    )


def execute_elevenlabs_item(
    repo_root: Path,
    queue_id: str,
    api_key: str,
    *,
    confirmed_maximum_usd: float,
    progress: ProgressCallback | None = None,
) -> MediaExecutionResult:
    repo = repo_root.resolve()
    episode_id, episode_root, queue_path, state, queue = _active_episode(repo)
    collection, item = _find_item(queue, queue_id)
    kind = _kind_for_collection(collection)
    if kind != "ELEVENLABS_TTS":
        raise DesktopMediaExecutionError("ELEVENLABS_TTS_ITEM_REQUIRED")
    maximum = _tts_maximum(queue, item)
    if abs(float(confirmed_maximum_usd) - maximum) > 1e-6:
        raise DesktopMediaExecutionError("EXPLICIT_AUTHORIZATION_MAXIMUM_MISMATCH")
    budget = _budget_preflight(repo, episode_id, maximum)
    lock_path, receipt_path = _paths(episode_root, queue_id)
    if lock_path.exists():
        raise DesktopMediaExecutionError(
            "ELEVENLABS_ATTEMPT_LOCKED_NO_AUTOMATIC_RESUBMISSION"
        )

    voice_id = str(item.get("voice_id", "")).strip()
    model_id = str(item.get("model_id", "")).strip()
    text = str(item.get("text_ar", "")).strip()
    settings = item.get("voice_settings")
    if not voice_id or not model_id or not text:
        raise DesktopMediaExecutionError("ELEVENLABS_TASK_DRAFT_INCOMPLETE")
    if not isinstance(settings, Mapping):
        raise DesktopMediaExecutionError("ELEVENLABS_VOICE_SETTINGS_REQUIRED")
    request_body = {
        "text": text,
        "model_id": model_id,
        "voice_settings": dict(settings),
    }
    request_id = str(uuid.uuid4())
    lock = {
        "schema_version": "siraj-desktop-media-submission-lock-v1",
        "release": RELEASE,
        "episode_id": episode_id,
        "queue_id": queue_id,
        "media_kind": kind,
        "request_id": request_id,
        "status": "LOCKED_BEFORE_NETWORK",
        "maximum_authorized_usd": maximum,
        "budget_preflight": budget,
        "request_payload_sha256": _canonical_sha256(request_body),
        "explicit_desktop_authorization": True,
        "paid_submission_trigger": (
            "ONE_EXPLICIT_DESKTOP_AUTHORIZATION_PER_ATTEMPT"
        ),
        "hidden_paid_retry": "FORBIDDEN",
        "api_key_persisted": False,
        "created_at_utc": _now(),
    }
    _exclusive_lock(lock_path, lock)
    item["status"] = "SUBMISSION_LOCKED"
    _write(queue_path, queue)

    endpoint = (
        ELEVENLABS_API_ROOT
        + "/text-to-speech/"
        + urllib.parse.quote(voice_id, safe="")
        + "?output_format=mp3_44100_128"
    )
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "xi-api-key": api_key.strip(),
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
            "User-Agent": "SIRAJ-Desktop-Media-Execution/1.0",
        },
    )
    if progress:
        progress("تم قفل محاولة ElevenLabs قبل الاتصال.", 10)
    try:
        with urllib.request.urlopen(request, timeout=240.0) as response:
            audio = response.read()
            headers = {key.lower(): value for key, value in response.headers.items()}
    except urllib.error.HTTPError as exc:
        message = exc.read(2048).decode("utf-8", errors="replace")
        lock["status"] = "PROVIDER_REJECTED"
        lock["last_error"] = f"ELEVENLABS_HTTP_ERROR:{exc.code}:{message}"
        lock["updated_at_utc"] = _now()
        _write(lock_path, lock)
        raise DesktopMediaExecutionError(lock["last_error"]) from exc
    except urllib.error.URLError as exc:
        lock["status"] = "NETWORK_RESULT_UNKNOWN_NO_AUTOMATIC_RESUBMISSION"
        lock["last_error"] = f"ELEVENLABS_NETWORK_ERROR:{exc.reason}"
        lock["updated_at_utc"] = _now()
        _write(lock_path, lock)
        raise DesktopMediaExecutionError(lock["last_error"]) from exc

    if not audio:
        raise DesktopMediaExecutionError("ELEVENLABS_AUDIO_EMPTY")
    output_path = repo / str(item.get("output_path_relative", ""))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_suffix(output_path.suffix + ".part")
    partial.write_bytes(audio)
    os.replace(partial, output_path)

    receipt = {
        "schema_version": "siraj-desktop-media-receipt-v1",
        "release": RELEASE,
        "episode_id": episode_id,
        "queue_id": queue_id,
        "media_type": kind,
        "provider": "ELEVENLABS",
        "service": "text-to-speech",
        "cost_category": "ELEVENLABS_TTS",
        "request_id": headers.get("request-id", request_id),
        "trace_id": headers.get("x-trace-id"),
        "character_cost": headers.get("character-cost"),
        "actual_cost_usd": None,
        "estimated_cost_usd": maximum,
        "maximum_authorized_usd": maximum,
        "voice_id": voice_id,
        "voice_slot": item.get("voice_slot"),
        "model_id": model_id,
        "output_path_relative": str(output_path.relative_to(repo)).replace(
            "\\", "/"
        ),
        "output_sha256": _sha256(output_path),
        "output_bytes": output_path.stat().st_size,
        "hidden_paid_retry": "FORBIDDEN",
        "completed_at_utc": _now(),
    }
    _write_receipt_and_complete(
        repo,
        queue_path,
        repo / ORCHESTRATOR_STATE_REL,
        state,
        queue,
        item,
        receipt_path,
        receipt,
    )
    if progress:
        progress("اكتمل ملف التعليق الصوتي وحُفظ الإيصال.", 100)
    return MediaExecutionResult(
        queue_id=queue_id,
        media_kind=kind,
        status="COMPLETE",
        output_path=output_path,
        receipt_path=receipt_path,
        task_uuid=None,
        actual_cost_usd=None,
        estimated_cost_usd=maximum,
    )


def render_local_graphics_item(
    repo_root: Path,
    queue_id: str,
    *,
    progress: ProgressCallback | None = None,
) -> MediaExecutionResult:
    repo = repo_root.resolve()
    episode_id, episode_root, queue_path, state, queue = _active_episode(repo)
    collection, item = _find_item(queue, queue_id)
    kind = _kind_for_collection(collection)
    if kind != "LOCAL_GRAPHICS":
        raise DesktopMediaExecutionError("LOCAL_GRAPHICS_ITEM_REQUIRED")
    if str(item.get("status", "")) == "COMPLETE":
        raise DesktopMediaExecutionError("MEDIA_QUEUE_ITEM_ALREADY_COMPLETE")
    spec_path = repo / str(item.get("spec_path_relative", ""))
    output_path = repo / str(item.get("output_path_relative", ""))
    _, receipt_path = _paths(episode_root, queue_id)
    if progress:
        progress("بدء رندر الجرافيك المحلي.", 5)
    result = render_graphic(
        repo,
        spec_path,
        output_path,
        receipt_path=receipt_path,
    )
    receipt = _read(receipt_path)
    receipt.update(
        {
            "queue_id": queue_id,
            "provider": "LOCAL",
            "cost_category": "OTHER",
            "actual_cost_usd": 0.0,
            "estimated_cost_usd": 0.0,
        }
    )
    _write_receipt_and_complete(
        repo,
        queue_path,
        repo / ORCHESTRATOR_STATE_REL,
        state,
        queue,
        item,
        receipt_path,
        receipt,
    )
    if progress:
        progress("اكتمل رندر الجرافيك المحلي.", 100)
    return MediaExecutionResult(
        queue_id=queue_id,
        media_kind=kind,
        status="COMPLETE",
        output_path=result.output_path,
        receipt_path=receipt_path,
        task_uuid=None,
        actual_cost_usd=0.0,
        estimated_cost_usd=0.0,
    )


def render_all_pending_local_graphics(
    repo_root: Path,
    *,
    progress: ProgressCallback | None = None,
) -> tuple[MediaExecutionResult, ...]:
    rows = [
        row
        for row in media_queue_rows(repo_root)
        if row.media_kind == "LOCAL_GRAPHICS" and row.status != "COMPLETE"
    ]
    results = []
    total = max(1, len(rows))
    for index, row in enumerate(rows, start=1):
        if progress:
            progress(
                f"رندر الجرافيك المحلي {index}/{len(rows)}",
                int((index - 1) * 100 / total),
            )
        results.append(render_local_graphics_item(repo_root, row.queue_id))
    if progress:
        progress("اكتملت جميع عناصر الجرافيك المحلية.", 100)
    return tuple(results)
