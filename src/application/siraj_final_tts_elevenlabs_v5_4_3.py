"""SIRAJ V5.4.3 — Hardened ElevenLabs FINAL_TTS transport.

Series invariants:
- provider/voice/model/output/settings are locked to the approved Episode 001 narrator.
- no assistant-authored cost/call/output-token caps.
- no network occurs without a separate explicit paid authorization artifact.
- one immutable provider attempt per queue item.
- lock is persisted before network.
- no automatic resubmission after timeout/rejection/unknown result.
- completed items are idempotently reused.
- API key is loaded through the existing SIRAJ credential provider and never persisted.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import argparse
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
    PaidOperationGatewayError,
    PaidOperationRequest,
    execute_bytes as execute_paid_bytes,
    http_json_transport,
)
from src.application.provider_model_contracts import (
    CONTRACT_VERSION as PROVIDER_CONTRACT_VERSION,
    validate_elevenlabs_payload,
)
from src.application.siraj_episode_master_authorization_v6_6 import master_authorization_reference

RELEASE = "SIRAJ_FINAL_TTS_ELEVENLABS_V5_4_3"
STAGE = "FINAL_TTS"

EPISODE_ID = "episode-002-adam-temptation-fall-repentance"

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

QUEUE_REL = Path(
    "projects/episode-002-adam-temptation-fall-repentance/"
    "orchestration/final-tts-queue-v5-4-3.json"
)
AUTH_REL = Path(
    "projects/episode-002-adam-temptation-fall-repentance/"
    "orchestration/final-tts-paid-authorization-v5-4-3.json"
)
EXEC_ROOT_REL = Path(
    "projects/episode-002-adam-temptation-fall-repentance/"
    "orchestration/final-tts-execution-v5-4-3"
)
LEDGER_REL = EXEC_ROOT_REL / "attempt-ledger.jsonl"

NARRATOR_LOCK_REL = Path(
    "projects/_series/siraj-primary-narrator-lock-v5.4.1.json"
)
PRONUNCIATION_LAW_REL = Path(
    "projects/_series/siraj-global-arabic-pronunciation-law-v5.3.json"
)


class FinalTtsError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class FinalTtsItemResult:
    queue_id: str
    status: str
    output_path: Path
    receipt_path: Path
    request_id: str | None
    provider_requests_this_run: int
    idempotent_reuse: bool

    def as_dict(self, repo: Path) -> dict[str, Any]:
        return {
            "queue_id": self.queue_id,
            "status": self.status,
            "output_path_relative": str(
                self.output_path.relative_to(repo)
            ).replace("\\", "/"),
            "receipt_path_relative": str(
                self.receipt_path.relative_to(repo)
            ).replace("\\", "/"),
            "request_id": self.request_id,
            "provider_requests_this_run": self.provider_requests_this_run,
            "idempotent_reuse": self.idempotent_reuse,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FinalTtsError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise FinalTtsError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def _append_jsonl(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
            )
            + "\n"
        )
        handle.flush()
        os.fsync(handle.fileno())


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _probe_duration_seconds(path: Path) -> float | None:
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
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if process.returncode != 0:
        return None
    try:
        value = float(process.stdout.strip())
    except ValueError:
        return None
    return round(value, 3) if value > 0 else None


def _audio_looks_valid(audio: bytes, content_type: str) -> bool:
    if len(audio) < 1024:
        return False
    lower = content_type.lower()
    if "audio" in lower or "mpeg" in lower or "mp3" in lower:
        return True
    return (
        audio.startswith(b"ID3")
        or audio.startswith(b"\xff\xfb")
        or audio.startswith(b"\xff\xf3")
        or audio.startswith(b"\xff\xf2")
    )


def _exclusive_json_lock(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = (
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    try:
        fd = os.open(
            path,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL,
            0o600,
        )
    except FileExistsError as exc:
        raise FinalTtsError(
            "ATTEMPT_ALREADY_LOCKED_NO_AUTOMATIC_RESUBMISSION"
        ) from exc
    try:
        os.write(fd, raw)
    finally:
        os.close(fd)


def _lock_paths(repo: Path, queue_id: str) -> tuple[Path, Path]:
    safe = "".join(
        ch
        for ch in queue_id
        if ch.isalnum() or ch in "-_"
    )
    root = repo / EXEC_ROOT_REL
    return (
        root / "locks" / f"{safe}-attempt-01.json",
        root / "receipts" / f"{safe}-attempt-01-receipt.json",
    )


def _validate_series_locks(repo: Path) -> None:
    narrator = _read_json(repo / NARRATOR_LOCK_REL)
    if narrator.get("status") != "ACTIVE":
        raise FinalTtsError("PRIMARY_NARRATOR_LOCK_NOT_ACTIVE")
    if narrator.get("provider") != PROVIDER:
        raise FinalTtsError("PRIMARY_NARRATOR_PROVIDER_CHANGED")
    if narrator.get("voice_id") != VOICE_ID:
        raise FinalTtsError("PRIMARY_NARRATOR_VOICE_CHANGED")

    model = narrator.get("model_resolution")
    if not isinstance(model, Mapping):
        raise FinalTtsError("PRIMARY_NARRATOR_MODEL_LOCK_MISSING")
    if model.get("resolved_model_id") != MODEL_ID:
        raise FinalTtsError("PRIMARY_NARRATOR_MODEL_CHANGED")

    law = _read_json(repo / PRONUNCIATION_LAW_REL)
    if law.get("status") != "ACTIVE":
        raise FinalTtsError("GLOBAL_PRONUNCIATION_LAW_NOT_ACTIVE")


def _queue(repo: Path) -> dict[str, Any]:
    queue = _read_json(repo / QUEUE_REL)
    if queue.get("status") not in {
        "AWAITING_EXPLICIT_PAID_AUTHORIZATION",
        "AUTHORIZED",
        "IN_PROGRESS",
        "COMPLETE",
        "BLOCKED_RETRY_AUTH_REQUIRED",
    }:
        raise FinalTtsError("FINAL_TTS_QUEUE_STATUS_INVALID")

    if queue.get("provider") != PROVIDER:
        raise FinalTtsError("FINAL_TTS_PROVIDER_CHANGED")
    if queue.get("voice_id") != VOICE_ID:
        raise FinalTtsError("FINAL_TTS_VOICE_CHANGED")
    if queue.get("model_id") != MODEL_ID:
        raise FinalTtsError("FINAL_TTS_MODEL_CHANGED")
    if queue.get("output_format") != OUTPUT_FORMAT:
        raise FinalTtsError("FINAL_TTS_OUTPUT_FORMAT_CHANGED")
    if queue.get("voice_settings") != VOICE_SETTINGS:
        raise FinalTtsError("FINAL_TTS_VOICE_SETTINGS_CHANGED")
    return queue


def _authorization(repo: Path, queue: Mapping[str, Any]) -> dict[str, Any]:
    path = repo / AUTH_REL
    if not path.is_file():
        raise FinalTtsError(
            "EXPLICIT_FINAL_TTS_PAID_AUTHORIZATION_REQUIRED"
        )
    auth = _read_json(path)
    if auth.get("status") != "ACTIVE":
        raise FinalTtsError(
            "EXPLICIT_FINAL_TTS_PAID_AUTHORIZATION_NOT_ACTIVE"
        )
    if auth.get("stage") != STAGE:
        raise FinalTtsError("FINAL_TTS_AUTHORIZATION_STAGE_MISMATCH")
    if auth.get("episode_id") != EPISODE_ID:
        raise FinalTtsError("FINAL_TTS_AUTHORIZATION_EPISODE_MISMATCH")
    if auth.get("provider") != PROVIDER:
        raise FinalTtsError("FINAL_TTS_AUTHORIZATION_PROVIDER_MISMATCH")
    if auth.get("voice_id") != VOICE_ID:
        raise FinalTtsError("FINAL_TTS_AUTHORIZATION_VOICE_MISMATCH")
    if auth.get("model_id") != MODEL_ID:
        raise FinalTtsError("FINAL_TTS_AUTHORIZATION_MODEL_MISMATCH")
    if auth.get("queue_sha256") != queue.get("queue_sha256"):
        raise FinalTtsError("FINAL_TTS_AUTHORIZATION_QUEUE_HASH_MISMATCH")
    if auth.get("automatic_retry") is not False:
        raise FinalTtsError("FINAL_TTS_AUTOMATIC_RETRY_MUST_BE_FALSE")
    if auth.get("maximum_provider_requests") != queue.get(
        "planned_provider_requests"
    ):
        raise FinalTtsError(
            "FINAL_TTS_AUTHORIZED_REQUEST_COUNT_MISMATCH"
        )
    return auth


def _find_item(
    queue: Mapping[str, Any],
    queue_id: str,
) -> dict[str, Any]:
    items = queue.get("items")
    if not isinstance(items, list):
        raise FinalTtsError("FINAL_TTS_QUEUE_ITEMS_REQUIRED")
    for item in items:
        if (
            isinstance(item, dict)
            and str(item.get("queue_id") or "") == queue_id
        ):
            return item
    raise FinalTtsError("FINAL_TTS_QUEUE_ITEM_NOT_FOUND:" + queue_id)


def _persist_queue(repo: Path, queue: Mapping[str, Any]) -> None:
    _write_json(repo / QUEUE_REL, queue)


def execute_authorized_item(
    repo: Path,
    queue_id: str,
) -> FinalTtsItemResult:
    repo = repo.resolve()
    _validate_series_locks(repo)
    queue = _queue(repo)
    _authorization(repo, queue)
    item = _find_item(queue, queue_id)

    status = str(item.get("status") or "")
    output_path = repo / str(
        item.get("output_path_relative") or ""
    )
    lock_path, receipt_path = _lock_paths(repo, queue_id)

    if status == "COMPLETE":
        if (
            output_path.is_file()
            and output_path.stat().st_size > 0
            and receipt_path.is_file()
        ):
            receipt = _read_json(receipt_path)
            return FinalTtsItemResult(
                queue_id=queue_id,
                status="COMPLETE_EXISTING_RESULT_REUSED",
                output_path=output_path,
                receipt_path=receipt_path,
                request_id=str(receipt.get("request_id") or "") or None,
                provider_requests_this_run=0,
                idempotent_reuse=True,
            )
        raise FinalTtsError(
            "COMPLETE_ITEM_ARTIFACT_OR_RECEIPT_MISSING"
        )

    if status not in {
        "AUTHORIZED",
        "READY_AUTHORIZED",
    }:
        raise FinalTtsError(
            "FINAL_TTS_ITEM_NOT_AUTHORIZED:" + status
        )

    if lock_path.exists():
        raise FinalTtsError(
            "FINAL_TTS_ITEM_ATTEMPT_ALREADY_LOCKED_"
            "EXPLICIT_RETRY_AUTHORIZATION_REQUIRED"
        )

    text = str(item.get("text_ar") or "").strip()
    if not text:
        raise FinalTtsError("FINAL_TTS_TEXT_EMPTY")

    if item.get("voice_id") != VOICE_ID:
        raise FinalTtsError("ITEM_VOICE_CHANGED")
    if item.get("model_id") != MODEL_ID:
        raise FinalTtsError("ITEM_MODEL_CHANGED")
    if item.get("output_format") != OUTPUT_FORMAT:
        raise FinalTtsError("ITEM_OUTPUT_FORMAT_CHANGED")
    if item.get("voice_settings") != VOICE_SETTINGS:
        raise FinalTtsError("ITEM_VOICE_SETTINGS_CHANGED")

    request_body = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": VOICE_SETTINGS,
    }
    request_id = str(uuid.uuid4())

    lock = {
        "schema_version": "siraj-final-tts-attempt-lock-v5.4.3",
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "stage": STAGE,
        "queue_id": queue_id,
        "request_id": request_id,
        "attempt": 1,
        "status": "LOCKED_BEFORE_NETWORK",
        "request_payload_sha256": _canonical_sha256(
            request_body
        ),
        "provider_requests_made": 0,
        "api_key_persisted": False,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "explicit_retry_authorization_required_after_failure": True,
        "created_at_utc": _now(),
    }
    _exclusive_json_lock(lock_path, lock)

    item["status"] = "SUBMISSION_LOCKED"
    item["request_id"] = request_id
    _persist_queue(repo, queue)

    _append_jsonl(
        repo / LEDGER_REL,
        {
            "event": "LOCKED_BEFORE_NETWORK",
            "queue_id": queue_id,
            "request_id": request_id,
            "timestamp_utc": _now(),
        },
    )

    try:
        api_key = read_elevenlabs_api_key()
    except ProviderCredentialError as exc:
        lock["status"] = "CREDENTIAL_LOAD_FAILED_NO_NETWORK"
        lock["last_error"] = str(exc)
        lock["updated_at_utc"] = _now()
        _write_json(lock_path, lock)
        item["status"] = "BLOCKED_CREDENTIAL_NO_NETWORK"
        _persist_queue(repo, queue)
        raise FinalTtsError(str(exc)) from exc

    if not api_key:
        lock["status"] = "CREDENTIAL_EMPTY_NO_NETWORK"
        lock["updated_at_utc"] = _now()
        _write_json(lock_path, lock)
        item["status"] = "BLOCKED_CREDENTIAL_NO_NETWORK"
        _persist_queue(repo, queue)
        raise FinalTtsError("ELEVENLABS_API_KEY_REQUIRED")

    endpoint = (
        API_ROOT
        + "/text-to-speech/"
        + urllib.parse.quote(VOICE_ID, safe="")
        + "?output_format="
        + urllib.parse.quote(OUTPUT_FORMAT, safe="")
    )

    lock["status"] = "NETWORK_REQUEST_STARTED"
    lock["provider_requests_made"] = 1
    lock["network_started_at_utc"] = _now()
    _write_json(lock_path, lock)

    _append_jsonl(
        repo / LEDGER_REL,
        {
            "event": "NETWORK_REQUEST_STARTED",
            "queue_id": queue_id,
            "request_id": request_id,
            "timestamp_utc": _now(),
        },
    )

    provider_payload = {
        "voice_id": VOICE_ID, "output_format": OUTPUT_FORMAT, **request_body,
    }
    validate_elevenlabs_payload(provider_payload)
    paid_request = PaidOperationRequest(
        repo_root=repo, episode_id=EPISODE_ID, stage=STAGE,
        operation_type="ELEVENLABS_TTS", provider=PROVIDER, model=MODEL_ID,
        provider_contract_version=PROVIDER_CONTRACT_VERSION,
        payload=provider_payload,
        input_artifact_hashes={"queue_item": str(lock["request_payload_sha256"])},
        master_authorization_reference=master_authorization_reference(repo, EPISODE_ID),
        operation_nonce=request_id, attempt_id=request_id,
    )
    try:
        paid_result = execute_paid_bytes(
            paid_request,
            http_json_transport(
                url=endpoint, method="POST", payload=request_body,
                headers={"xi-api-key": api_key, "Content-Type": "application/json",
                         "Accept": "audio/mpeg", "User-Agent": "SIRAJ-Final-TTS-V5.4.3"},
                timeout_seconds=240,
            ),
        )
        audio = paid_result.raw_response_path.read_bytes()
        headers = {"content-type": "audio/mpeg"}
        http_status = 200
    except urllib.error.HTTPError as exc:
        message = exc.read(4096).decode(
            "utf-8",
            errors="replace",
        )
        lock.update(
            {
                "status": (
                    "PROVIDER_REJECTED_NO_AUTOMATIC_RETRY"
                ),
                "http_status": exc.code,
                "last_error": message,
                "updated_at_utc": _now(),
            }
        )
        _write_json(lock_path, lock)
        item["status"] = (
            "FAILED_PROVIDER_REJECTED_RETRY_AUTH_REQUIRED"
        )
        _persist_queue(repo, queue)
        _append_jsonl(
            repo / LEDGER_REL,
            {
                "event": "PROVIDER_REJECTED",
                "queue_id": queue_id,
                "request_id": request_id,
                "http_status": exc.code,
                "timestamp_utc": _now(),
            },
        )
        raise FinalTtsError(
            f"ELEVENLABS_HTTP_ERROR:{exc.code}:{message}"
        ) from exc
    except urllib.error.URLError as exc:
        lock.update(
            {
                "status": (
                    "NETWORK_RESULT_UNKNOWN_NO_AUTOMATIC_RESUBMISSION"
                ),
                "last_error": str(exc.reason),
                "updated_at_utc": _now(),
            }
        )
        _write_json(lock_path, lock)
        item["status"] = (
            "NETWORK_RESULT_UNKNOWN_RETRY_AUTH_REQUIRED"
        )
        _persist_queue(repo, queue)
        _append_jsonl(
            repo / LEDGER_REL,
            {
                "event": "NETWORK_RESULT_UNKNOWN",
                "queue_id": queue_id,
                "request_id": request_id,
                "timestamp_utc": _now(),
            },
        )
        raise FinalTtsError(
            f"ELEVENLABS_NETWORK_ERROR:{exc.reason}"
        ) from exc
    except PaidOperationGatewayError as exc:
        lock.update({
            "status": "FAILED_OR_UNKNOWN_RETRY_AUTH_REQUIRED",
            "last_error": str(exc), "updated_at_utc": _now(),
        })
        _write_json(lock_path, lock)
        item["status"] = "FAILED_OR_UNKNOWN_RETRY_AUTH_REQUIRED"
        _persist_queue(repo, queue)
        raise FinalTtsError(str(exc)) from exc

    content_type = str(headers.get("content-type") or "")
    if not _audio_looks_valid(audio, content_type):
        lock.update(
            {
                "status": (
                    "INVALID_AUDIO_RESPONSE_NO_AUTOMATIC_RETRY"
                ),
                "http_status": http_status,
                "response_bytes": len(audio),
                "content_type": content_type,
                "updated_at_utc": _now(),
            }
        )
        _write_json(lock_path, lock)
        item["status"] = (
            "FAILED_INVALID_AUDIO_RETRY_AUTH_REQUIRED"
        )
        _persist_queue(repo, queue)
        raise FinalTtsError("ELEVENLABS_AUDIO_INVALID")

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    partial = output_path.with_suffix(
        output_path.suffix + ".part"
    )
    partial.write_bytes(audio)
    os.replace(partial, output_path)

    duration = _probe_duration_seconds(output_path)

    provider_request_id = (
        headers.get("request-id")
        or headers.get("x-request-id")
        or headers.get("xi-request-id")
    )

    receipt = {
        "schema_version": "siraj-final-tts-receipt-v5.4.3",
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "stage": STAGE,
        "queue_id": queue_id,
        "request_id": request_id,
        "provider_request_id": provider_request_id,
        "provider": PROVIDER,
        "voice_id": VOICE_ID,
        "model_id": MODEL_ID,
        "output_format": OUTPUT_FORMAT,
        "voice_settings": VOICE_SETTINGS,
        "character_count_unicode": len(text),
        "http_status": http_status,
        "content_type": content_type,
        "output_path_relative": str(
            output_path.relative_to(repo)
        ).replace("\\", "/"),
        "output_sha256": _sha256_file(output_path),
        "output_bytes": output_path.stat().st_size,
        "duration_seconds": duration,
        "automatic_retry": False,
        "provider_requests_this_attempt": 1,
        "completed_at_utc": _now(),
    }
    _write_json(receipt_path, receipt)

    lock.update(
        {
            "status": "COMPLETE",
            "provider_request_id": provider_request_id,
            "output_sha256": receipt["output_sha256"],
            "receipt_path_relative": str(
                receipt_path.relative_to(repo)
            ).replace("\\", "/"),
            "completed_at_utc": _now(),
        }
    )
    _write_json(lock_path, lock)

    item.update(
        {
            "status": "COMPLETE",
            "request_id": request_id,
            "provider_request_id": provider_request_id,
            "receipt_path_relative": str(
                receipt_path.relative_to(repo)
            ).replace("\\", "/"),
            "output_sha256": receipt["output_sha256"],
            "duration_seconds": duration,
            "completed_at_utc": _now(),
        }
    )

    items = queue.get("items")
    if isinstance(items, list) and all(
        isinstance(candidate, Mapping)
        and candidate.get("status") == "COMPLETE"
        for candidate in items
    ):
        queue["status"] = "COMPLETE"
        queue["next_stage"] = "AUDIO_TIMESTAMPS_AND_BEATS"
    else:
        queue["status"] = "IN_PROGRESS"

    queue["updated_at_utc"] = _now()
    _persist_queue(repo, queue)

    _append_jsonl(
        repo / LEDGER_REL,
        {
            "event": "COMPLETE",
            "queue_id": queue_id,
            "request_id": request_id,
            "provider_request_id": provider_request_id,
            "output_sha256": receipt["output_sha256"],
            "timestamp_utc": _now(),
        },
    )

    return FinalTtsItemResult(
        queue_id=queue_id,
        status="COMPLETE",
        output_path=output_path,
        receipt_path=receipt_path,
        request_id=request_id,
        provider_requests_this_run=1,
        idempotent_reuse=False,
    )


def execute_authorized_queue(repo: Path) -> list[FinalTtsItemResult]:
    repo = repo.resolve()
    _validate_series_locks(repo)
    queue = _queue(repo)
    _authorization(repo, queue)

    results: list[FinalTtsItemResult] = []
    items = queue.get("items")
    if not isinstance(items, list):
        raise FinalTtsError("FINAL_TTS_QUEUE_ITEMS_REQUIRED")

    for item in items:
        if not isinstance(item, dict):
            raise FinalTtsError("FINAL_TTS_QUEUE_ITEM_OBJECT_REQUIRED")
        queue_id = str(item.get("queue_id") or "")
        status = str(item.get("status") or "")

        if status == "COMPLETE":
            results.append(
                execute_authorized_item(repo, queue_id)
            )
            continue

        if status in {"AUTHORIZED", "READY_AUTHORIZED"}:
            results.append(
                execute_authorized_item(repo, queue_id)
            )
            continue

        # Stop immediately. Never skip around an ambiguous or failed
        # billable attempt because that could make accounting opaque.
        raise FinalTtsError(
            "FINAL_TTS_QUEUE_STOPPED_AT_NON_EXECUTABLE_ITEM:"
            f"{queue_id}:{status}"
        )

    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--queue-id")
    parser.add_argument(
        "--execute-authorized-queue",
        action="store_true",
    )
    args = parser.parse_args()

    repo = Path(args.repo).resolve()

    if args.execute_authorized_queue:
        results = execute_authorized_queue(repo)
        print("SIRAJ_FINAL_TTS_AUTHORIZED_QUEUE_EXECUTION_COMPLETE")
        for result in results:
            print(
                f"{result.queue_id}:{result.status}:"
                f"provider_requests_this_run="
                f"{result.provider_requests_this_run}"
            )
        return

    if args.queue_id:
        result = execute_authorized_item(
            repo,
            args.queue_id,
        )
        print(
            json.dumps(
                result.as_dict(repo),
                ensure_ascii=False,
                indent=2,
            )
        )
        return

    raise SystemExit(
        "USE_--queue-id_OR_--execute-authorized-queue"
    )


if __name__ == "__main__":
    main()
