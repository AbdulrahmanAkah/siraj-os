from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping
import urllib.error
import urllib.parse
import urllib.request
import uuid

from src.application.provider_credentials_v1 import (
    ProviderCredentialError,
    read_elevenlabs_api_key,
)
from src.application.paid_operation_gateway import (
    PaidOperationRequest,
    execute_bytes as execute_paid_bytes,
    http_json_transport,
)
from src.application.provider_model_contracts import (
    CONTRACT_VERSION as PROVIDER_CONTRACT_VERSION,
    validate_elevenlabs_payload,
)
from src.application.siraj_episode_master_authorization_v6_6 import master_authorization_reference

EP2_ID = "episode-002-adam-temptation-fall-repentance"

PROVIDER = "ELEVENLABS"
VOICE_ID = "XdoLPWNt7ytn6BtU4FBf"
MODEL_ID = "eleven_multilingual_v2"
OUTPUT_FORMAT = "mp3_44100_128"
VOICE_SETTINGS = {
    "stability": 0.38,
    "similarity_boost": 0.75,
    "style": 0.42,
    "use_speaker_boost": True,
}
API_ROOT = "https://api.elevenlabs.io/v1"
CONFIRMATION_PHRASE = "أوافق على توليد الصوت النهائي"

NARRATOR_LOCK_REL = Path(
    "projects/_series/siraj-primary-narrator-lock-v5.4.1.json"
)
PRONUNCIATION_LAW_REL = Path(
    "projects/_series/siraj-global-arabic-pronunciation-law-v5.3.json"
)


class GenericFinalTtsV632Error(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GenericTtsResult:
    queue_id: str
    status: str
    output_path: Path
    receipt_path: Path
    provider_requests_this_run: int


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise GenericFinalTtsV632Error("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temp, path)


def _append(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _file_sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _probe_duration(path: Path) -> float | None:
    # SIRAJ_PURE_PYTHON_MP3_DURATION_V6_5_2
    from src.application.siraj_mp3_duration_v6_5_2 import (
        probe_audio_duration_seconds,
    )

    value = probe_audio_duration_seconds(path)
    if value is not None:
        return round(float(value), 3)

    ffprobe = os.environ.get("SIRAJ_FFPROBE_EXE", "").strip()
    if not ffprobe:
        return None

    process = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if process.returncode:
        return None
    try:
        value = float(process.stdout.strip())
    except ValueError:
        return None
    return round(value, 3) if value > 0 else None


def _validate_series_locks(repo: Path) -> None:
    narrator = _read(repo / NARRATOR_LOCK_REL)
    if narrator.get("voice_id") != VOICE_ID:
        raise GenericFinalTtsV632Error("PRIMARY_NARRATOR_VOICE_CHANGED")

    model_resolution = narrator.get("model_resolution")
    if isinstance(model_resolution, Mapping):
        resolved = str(model_resolution.get("resolved_model_id") or "").strip()
        if resolved and resolved != MODEL_ID:
            raise GenericFinalTtsV632Error(
                "PRIMARY_NARRATOR_MODEL_CHANGED:" + resolved
            )

    law = _read(repo / PRONUNCIATION_LAW_REL)
    if str(law.get("status") or "").upper() not in {"ACTIVE", "PASS"}:
        raise GenericFinalTtsV632Error("GLOBAL_PRONUNCIATION_LAW_NOT_ACTIVE")


def queue_path(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration/final-tts-queue-v6-3-2.json"
    )


def auth_path(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration/final-tts-paid-authorization-v6-3-2.json"
    )


def execution_root(repo_root: Path, episode_id: str) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "orchestration/final-tts-execution-v6-3-2"
    )


def build_future_tts_queue(repo_root: Path, episode_id: str) -> Path:
    if episode_id == EP2_ID:
        raise GenericFinalTtsV632Error(
            "EPISODE_002_MUST_KEEP_CANONICAL_V5_4_3_FINAL_TTS"
        )

    repo = Path(repo_root).resolve()
    _validate_series_locks(repo)
    ep = repo / "projects" / episode_id

    pronunciation = _read(
        ep / "preproduction/pronunciation-performance-gate-v6-3.json"
    )
    if pronunciation.get("status") != "PASS":
        raise GenericFinalTtsV632Error("PRONUNCIATION_GATE_NOT_PASS")

    audit = _read(ep / "orchestration/pronunciation-audit-v6-3.json")
    if audit.get("status") != "PASS":
        raise GenericFinalTtsV632Error("PRONUNCIATION_LOCAL_AUDIT_NOT_PASS")

    segments = pronunciation.get("segments")
    if not isinstance(segments, list) or not segments:
        raise GenericFinalTtsV632Error("PRONUNCIATION_SEGMENTS_REQUIRED")

    items = []
    total_chars = 0
    for index, segment in enumerate(segments, 1):
        if not isinstance(segment, Mapping):
            raise GenericFinalTtsV632Error(
                "PRONUNCIATION_SEGMENT_OBJECT_REQUIRED"
            )
        segment_id = str(segment.get("segment_id") or f"SEG-{index:03d}")
        text = str(segment.get("tts_text_ar") or "").strip()
        if not text:
            raise GenericFinalTtsV632Error("TTS_TEXT_EMPTY:" + segment_id)
        pause = float(segment.get("pause_after_seconds", 0) or 0)
        total_chars += len(text)
        items.append(
            {
                "queue_id": f"TTS-{index:03d}-{segment_id}",
                "queue_index": index,
                "segment_id": segment_id,
                "status": "AWAITING_EXPLICIT_PAID_AUTHORIZATION",
                "provider": PROVIDER,
                "voice_id": VOICE_ID,
                "model_id": MODEL_ID,
                "output_format": OUTPUT_FORMAT,
                "voice_settings": VOICE_SETTINGS,
                "text_ar": text,
                "pause_after_seconds": pause,
                "output_path_relative": (
                    f"projects/{episode_id}/audio/tts/final-v6-3-2/"
                    f"{index:03d}-{segment_id}.mp3"
                ),
                "automatic_retry": False,
                "automatic_resubmission": False,
            }
        )

    immutable = {
        "episode_id": episode_id,
        "provider": PROVIDER,
        "voice_id": VOICE_ID,
        "model_id": MODEL_ID,
        "output_format": OUTPUT_FORMAT,
        "voice_settings": VOICE_SETTINGS,
        "items": [
            {
                "queue_id": item["queue_id"],
                "segment_id": item["segment_id"],
                "text_ar": item["text_ar"],
                "pause_after_seconds": item["pause_after_seconds"],
                "output_path_relative": item["output_path_relative"],
            }
            for item in items
        ],
    }

    queue = {
        "schema_version": "siraj-final-tts-queue-v6.3.2",
        "status": "AWAITING_EXPLICIT_PAID_AUTHORIZATION",
        "episode_id": episode_id,
        "stage": "FINAL_TTS",
        "provider": PROVIDER,
        "voice_id": VOICE_ID,
        "model_id": MODEL_ID,
        "output_format": OUTPUT_FORMAT,
        "voice_settings": VOICE_SETTINGS,
        "planned_provider_requests": len(items),
        "total_character_count_unicode": total_chars,
        "assistant_authored_cost_cap_usd": None,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "immutable_manifest_sha256": _canonical_sha(immutable),
        "items": items,
        "next_stage": "FINAL_TTS_PAID_AUTHORIZATION",
        "created_at_utc": _now(),
    }

    path = queue_path(repo, episode_id)
    if path.exists():
        existing = _read(path)
        if existing.get("immutable_manifest_sha256") == queue[
            "immutable_manifest_sha256"
        ]:
            return path
        raise GenericFinalTtsV632Error("EXISTING_FUTURE_TTS_QUEUE_CONFLICT")

    _write(path, queue)
    return path


def authorize_future_tts_queue(
    repo_root: Path,
    episode_id: str,
    confirmation_phrase: str,
) -> Path:
    if episode_id == EP2_ID:
        raise GenericFinalTtsV632Error(
            "EPISODE_002_AUTHORIZATION_MUST_USE_V5_4_4_STUDIO_CONTROLLER"
        )
    if confirmation_phrase.strip() != CONFIRMATION_PHRASE:
        raise GenericFinalTtsV632Error(
            "EXPLICIT_FINAL_TTS_CONFIRMATION_PHRASE_MISMATCH"
        )

    repo = Path(repo_root).resolve()
    path = queue_path(repo, episode_id)
    if not path.is_file():
        build_future_tts_queue(repo, episode_id)
    queue = _read(path)

    auth = auth_path(repo, episode_id)
    if auth.exists():
        existing = _read(auth)
        if (
            existing.get("status") == "ACTIVE"
            and existing.get("immutable_manifest_sha256")
            == queue.get("immutable_manifest_sha256")
        ):
            return auth
        raise GenericFinalTtsV632Error(
            "EXISTING_FINAL_TTS_AUTHORIZATION_CONFLICT"
        )

    _write(
        auth,
        {
            "schema_version": "siraj-final-tts-paid-authorization-v6.3.2",
            "status": "ACTIVE",
            "episode_id": episode_id,
            "stage": "FINAL_TTS",
            "provider": PROVIDER,
            "voice_id": VOICE_ID,
            "model_id": MODEL_ID,
            "output_format": OUTPUT_FORMAT,
            "voice_settings": VOICE_SETTINGS,
            "immutable_manifest_sha256": queue.get("immutable_manifest_sha256"),
            "maximum_provider_requests": queue.get("planned_provider_requests"),
            "authorization_source": "EXPLICIT_HUMAN_DESKTOP_CONFIRMATION",
            "confirmation_phrase": CONFIRMATION_PHRASE,
            "assistant_authored_cost_cap_usd": None,
            "automatic_retry": False,
            "automatic_resubmission": False,
            "authorized_at_utc": _now(),
        },
    )

    for item in queue["items"]:
        if item.get("status") == "AWAITING_EXPLICIT_PAID_AUTHORIZATION":
            item["status"] = "AUTHORIZED"
        elif item.get("status") != "COMPLETE":
            raise GenericFinalTtsV632Error(
                "CANNOT_AUTHORIZE_TTS_ITEM:"
                + str(item.get("queue_id"))
                + ":"
                + str(item.get("status"))
            )
    queue["status"] = "AUTHORIZED"
    queue["next_stage"] = "FINAL_TTS_EXECUTION"
    _write(path, queue)
    return auth


def _authorization(
    repo: Path,
    episode_id: str,
    queue: Mapping[str, Any],
) -> dict[str, Any]:
    path = auth_path(repo, episode_id)
    if not path.is_file():
        raise GenericFinalTtsV632Error(
            "EXPLICIT_FINAL_TTS_PAID_AUTHORIZATION_REQUIRED"
        )
    auth = _read(path)
    if (
        auth.get("status") != "ACTIVE"
        or auth.get("episode_id") != episode_id
        or auth.get("voice_id") != VOICE_ID
        or auth.get("model_id") != MODEL_ID
        or auth.get("immutable_manifest_sha256")
        != queue.get("immutable_manifest_sha256")
        or auth.get("automatic_retry") is not False
    ):
        raise GenericFinalTtsV632Error("FINAL_TTS_AUTHORIZATION_INVALID")
    return auth


def _exclusive_lock(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise GenericFinalTtsV632Error(
            "FINAL_TTS_ATTEMPT_ALREADY_LOCKED_"
            "EXPLICIT_RETRY_AUTHORIZATION_REQUIRED"
        ) from exc
    try:
        os.write(
            descriptor,
            (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode(
                "utf-8"
            ),
        )
    finally:
        os.close(descriptor)


def re_safe(value: str) -> str:
    return "".join(
        character
        for character in value
        if character.isalnum() or character in "-_"
    )


def execute_future_tts_item(
    repo_root: Path,
    episode_id: str,
    queue_id: str,
) -> GenericTtsResult:
    if episode_id == EP2_ID:
        raise GenericFinalTtsV632Error(
            "EPISODE_002_EXECUTION_MUST_USE_CANONICAL_V5_4_3"
        )

    repo = Path(repo_root).resolve()
    _validate_series_locks(repo)
    qpath = queue_path(repo, episode_id)
    queue = _read(qpath)
    _authorization(repo, episode_id, queue)

    items = queue.get("items")
    if not isinstance(items, list):
        raise GenericFinalTtsV632Error("FINAL_TTS_QUEUE_ITEMS_REQUIRED")

    item = next(
        (
            value
            for value in items
            if isinstance(value, dict)
            and value.get("queue_id") == queue_id
        ),
        None,
    )
    if item is None:
        raise GenericFinalTtsV632Error(
            "FINAL_TTS_QUEUE_ITEM_NOT_FOUND:" + queue_id
        )

    root = execution_root(repo, episode_id)
    safe_id = re_safe(queue_id)
    lock = root / "locks" / f"{safe_id}-attempt-01.json"
    receipt = root / "receipts" / f"{safe_id}-attempt-01.json"
    output = repo / str(item.get("output_path_relative") or "")

    if item.get("status") == "COMPLETE":
        if output.is_file() and receipt.is_file():
            return GenericTtsResult(
                queue_id,
                "COMPLETE_EXISTING_RESULT_REUSED",
                output,
                receipt,
                0,
            )
        raise GenericFinalTtsV632Error("COMPLETE_TTS_ARTIFACT_MISSING")

    if item.get("status") not in {"AUTHORIZED", "READY_AUTHORIZED"}:
        raise GenericFinalTtsV632Error(
            "FINAL_TTS_ITEM_NOT_AUTHORIZED:" + str(item.get("status"))
        )
    if lock.exists():
        raise GenericFinalTtsV632Error(
            "FINAL_TTS_ITEM_ATTEMPT_ALREADY_LOCKED_"
            "EXPLICIT_RETRY_AUTHORIZATION_REQUIRED"
        )

    if (
        item.get("voice_id") != VOICE_ID
        or item.get("model_id") != MODEL_ID
        or item.get("output_format") != OUTPUT_FORMAT
        or item.get("voice_settings") != VOICE_SETTINGS
    ):
        raise GenericFinalTtsV632Error(
            "FINAL_TTS_LOCKED_CONFIGURATION_CHANGED"
        )

    text = str(item.get("text_ar") or "").strip()
    if not text:
        raise GenericFinalTtsV632Error("FINAL_TTS_TEXT_EMPTY")

    request_body = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": VOICE_SETTINGS,
    }
    request_id = str(uuid.uuid4())
    lock_payload = {
        "schema_version": "siraj-final-tts-attempt-lock-v6.3.2",
        "episode_id": episode_id,
        "queue_id": queue_id,
        "request_id": request_id,
        "status": "LOCKED_BEFORE_NETWORK",
        "request_payload_sha256": _canonical_sha(request_body),
        "provider_requests_made": 0,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "created_at_utc": _now(),
    }
    _exclusive_lock(lock, lock_payload)

    item["status"] = "SUBMISSION_LOCKED"
    item["request_id"] = request_id
    _write(qpath, queue)

    ledger = root / "attempt-ledger.jsonl"
    _append(
        ledger,
        {
            "event": "LOCKED_BEFORE_NETWORK",
            "queue_id": queue_id,
            "request_id": request_id,
            "timestamp_utc": _now(),
        },
    )

    try:
        key = read_elevenlabs_api_key()
    except ProviderCredentialError as exc:
        lock_payload["status"] = "CREDENTIAL_LOAD_FAILED_NO_NETWORK"
        lock_payload["last_error"] = str(exc)
        _write(lock, lock_payload)
        item["status"] = "BLOCKED_CREDENTIAL_NO_NETWORK"
        _write(qpath, queue)
        raise GenericFinalTtsV632Error(str(exc)) from exc

    if not key:
        lock_payload["status"] = "CREDENTIAL_EMPTY_NO_NETWORK"
        _write(lock, lock_payload)
        item["status"] = "BLOCKED_CREDENTIAL_NO_NETWORK"
        _write(qpath, queue)
        raise GenericFinalTtsV632Error("ELEVENLABS_API_KEY_REQUIRED")

    endpoint = (
        API_ROOT
        + "/text-to-speech/"
        + urllib.parse.quote(VOICE_ID, safe="")
        + "?output_format="
        + urllib.parse.quote(OUTPUT_FORMAT, safe="")
    )
    lock_payload["status"] = "NETWORK_REQUEST_STARTED"
    lock_payload["provider_requests_made"] = 1
    lock_payload["network_started_at_utc"] = _now()
    _write(lock, lock_payload)

    provider_payload = {"voice_id": VOICE_ID, **request_body}
    validate_elevenlabs_payload(provider_payload)
    paid_request = PaidOperationRequest(
        repo_root=repo, episode_id=episode_id, stage="FINAL_TTS",
        operation_type="ELEVENLABS_TTS", provider="ELEVENLABS", model=MODEL_ID,
        provider_contract_version=PROVIDER_CONTRACT_VERSION,
        payload=provider_payload,
        input_artifact_hashes={"tts_queue": str(queue.get("queue_sha256") or _canonical_sha(queue))},
        master_authorization_reference=master_authorization_reference(repo, episode_id),
        operation_nonce=request_id, attempt_id=request_id,
    )
    try:
        paid_result = execute_paid_bytes(
            paid_request,
            http_json_transport(
                url=endpoint, method="POST", payload=request_body,
                headers={"xi-api-key": key, "Content-Type": "application/json",
                         "Accept": "audio/mpeg", "User-Agent": "SIRAJ-Final-TTS-V6.3.2"},
                timeout_seconds=240,
            ),
        )
        audio = paid_result.raw_response_path.read_bytes()
        headers = {"content-type": "audio/mpeg"}
        status = 200
    except Exception as exc:
        lock_payload["status"] = (
            "NETWORK_RESULT_UNKNOWN_NO_AUTOMATIC_RESUBMISSION"
        )
        lock_payload["last_error"] = str(exc)
        _write(lock, lock_payload)
        item["status"] = "NETWORK_RESULT_UNKNOWN_RETRY_AUTH_REQUIRED"
        _write(qpath, queue)
        raise GenericFinalTtsV632Error(
            "ELEVENLABS_NETWORK_RESULT_UNKNOWN_"
            "EXPLICIT_RETRY_AUTH_REQUIRED"
        ) from exc

    content_type = str(headers.get("content-type") or "")
    if len(audio) < 512 or "audio" not in content_type.lower():
        lock_payload["status"] = (
            "INVALID_AUDIO_RESPONSE_NO_AUTOMATIC_RETRY"
        )
        lock_payload["http_status"] = status
        _write(lock, lock_payload)
        item["status"] = "FAILED_INVALID_AUDIO_RETRY_AUTH_REQUIRED"
        _write(qpath, queue)
        raise GenericFinalTtsV632Error("ELEVENLABS_AUDIO_INVALID")

    output.parent.mkdir(parents=True, exist_ok=True)
    partial = output.with_suffix(output.suffix + ".part")
    partial.write_bytes(audio)
    os.replace(partial, output)
    duration = _probe_duration(output)

    receipt_payload = {
        "schema_version": "siraj-final-tts-receipt-v6.3.2",
        "status": "PASS",
        "episode_id": episode_id,
        "queue_id": queue_id,
        "request_id": request_id,
        "provider_request_id": (
            headers.get("request-id")
            or headers.get("x-request-id")
            or headers.get("xi-request-id")
        ),
        "provider": PROVIDER,
        "voice_id": VOICE_ID,
        "model_id": MODEL_ID,
        "output_format": OUTPUT_FORMAT,
        "voice_settings": VOICE_SETTINGS,
        "character_count_unicode": len(text),
        "http_status": status,
        "content_type": content_type,
        "output_path_relative": str(output.relative_to(repo)).replace("\\", "/"),
        "output_sha256": _file_sha(output),
        "output_bytes": output.stat().st_size,
        "duration_seconds": duration,
        "automatic_retry": False,
        "provider_requests_this_attempt": 1,
        "completed_at_utc": _now(),
    }
    _write(receipt, receipt_payload)
    lock_payload["status"] = "COMPLETE"
    lock_payload["receipt_path_relative"] = str(
        receipt.relative_to(repo)
    ).replace("\\", "/")
    lock_payload["completed_at_utc"] = _now()
    _write(lock, lock_payload)

    item["status"] = "COMPLETE"
    item["duration_seconds"] = duration
    item["output_sha256"] = receipt_payload["output_sha256"]
    item["receipt_path_relative"] = lock_payload["receipt_path_relative"]

    if all(
        isinstance(candidate, Mapping)
        and candidate.get("status") == "COMPLETE"
        for candidate in items
    ):
        queue["status"] = "COMPLETE"
        queue["next_stage"] = "AUDIO_TIMESTAMPS_AND_BEATS"
    else:
        queue["status"] = "IN_PROGRESS"
    queue["updated_at_utc"] = _now()
    _write(qpath, queue)

    return GenericTtsResult(queue_id, "COMPLETE", output, receipt, 1)


def execute_future_tts_queue(
    repo_root: Path,
    episode_id: str,
) -> tuple[GenericTtsResult, ...]:
    repo = Path(repo_root).resolve()
    queue = _read(queue_path(repo, episode_id))
    items = queue.get("items")
    if not isinstance(items, list):
        raise GenericFinalTtsV632Error("FINAL_TTS_QUEUE_ITEMS_REQUIRED")

    results = []
    for item in items:
        if not isinstance(item, Mapping):
            raise GenericFinalTtsV632Error(
                "FINAL_TTS_QUEUE_ITEM_OBJECT_REQUIRED"
            )
        status = str(item.get("status") or "")
        queue_id = str(item.get("queue_id") or "")
        if status in {"COMPLETE", "AUTHORIZED", "READY_AUTHORIZED"}:
            results.append(
                execute_future_tts_item(repo, episode_id, queue_id)
            )
        else:
            raise GenericFinalTtsV632Error(
                "FINAL_TTS_QUEUE_STOPPED_AT_NON_EXECUTABLE_ITEM:"
                + queue_id
                + ":"
                + status
            )
    return tuple(results)


def final_tts_backend_kind(episode_id: str) -> str:
    return (
        "EPISODE_002_CANONICAL_V5_4_3"
        if episode_id == EP2_ID
        else "GENERIC_V6_3_2"
    )


def build_or_prepare_final_tts(repo_root: Path, episode_id: str):
    if episode_id == EP2_ID:
        path = (
            Path(repo_root).resolve()
            / "projects"
            / EP2_ID
            / "orchestration/final-tts-queue-v5-4-3.json"
        )
        if not path.is_file():
            raise GenericFinalTtsV632Error(
                "EPISODE_002_CANONICAL_TTS_QUEUE_MISSING"
            )
        return path
    return build_future_tts_queue(repo_root, episode_id)
