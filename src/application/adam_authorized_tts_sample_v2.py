"""Execute one explicitly authorized ElevenLabs sample for Adam episode V2."""

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

RELEASE = "SIRAJ_ADAM_AUTHORIZED_TTS_SAMPLE_V2"
API_ROOT = "https://api.elevenlabs.io/v1"

EXPECTED_EPISODE_ID = "episode-001-adam"
EXPECTED_QUEUE_ID = "TTS-SAMPLE-VB-001-01"
EXPECTED_BLOCK_ID = "VB-001-01"
EXPECTED_SEGMENT_ID = "ADAM-SEQUENCE-01"
EXPECTED_VOICE_ID = "XdoLPWNt7ytn6BtU4FBf"
EXPECTED_MODEL_ID = "eleven_multilingual_v2"
EXPECTED_OUTPUT_FORMAT = "mp3_44100_128"
EXPECTED_CHARACTER_COUNT = 263
EXPECTED_AUTHORIZED_MAXIMUM_USD = 0.07
EXPECTED_INTERNAL_RESERVE_SHARE_USD = 0.069399
EXPECTED_TEXT = (
    "اِنْخَفَضَ كُلُّ شَيْءٍ فِي حَرَكَةٍ وَاحِدَةٍ. "
    "اِمْتِثَالٌ كَامِلٌ... ثُمَّ بَقِيَ مَوْضِعٌ وَاحِدٌ قَائِمًا. "
    "لَمْ يَكُنِ الْعَجْزُ هُوَ مَا مَنَعَهُ، وَلَا غُمُوضُ الْأَمْرِ. "
    "كَانَ يَرَى، وَيَفْهَمُ، ثُمَّ اخْتَارَ أَنْ يَرْفَعَ نَفْسَهُ "
    "فَوْقَ مَا أُمِرَ بِهِ."
)

AUTHORIZATION = {
    "schema_version": "siraj-explicit-paid-authorization-v2",
    "episode_id": EXPECTED_EPISODE_ID,
    "queue_id": EXPECTED_QUEUE_ID,
    "block_id": EXPECTED_BLOCK_ID,
    "decision": "AUTHORIZED_ONE_SAMPLE_ATTEMPT_ONLY",
    "authorization_source": "USER_EXPLICIT_YES_IN_CHAT",
    "authorized_at_local": "2026-08-06T13:47:00+03:00",
    "maximum_authorized_usd": EXPECTED_AUTHORIZED_MAXIMUM_USD,
    "maximum_provider_requests": 1,
    "hidden_paid_retry": "FORBIDDEN",
    "automatic_resubmission": "FORBIDDEN",
    "full_episode_tts_authorized": False,
}


class AuthorizedTtsSampleError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SampleExecutionResult:
    status: str
    output_path: Path
    receipt_path: Path
    lock_path: Path
    request_id: str | None
    provider_requests_this_run: int
    idempotent_reuse: bool

    def as_dict(self, repo: Path) -> dict[str, Any]:
        return {
            "status": self.status,
            "output_path_relative": str(
                self.output_path.relative_to(repo)
            ).replace("\\", "/"),
            "receipt_path_relative": str(
                self.receipt_path.relative_to(repo)
            ).replace("\\", "/"),
            "lock_path_relative": str(
                self.lock_path.relative_to(repo)
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
        raise AuthorizedTtsSampleError(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise AuthorizedTtsSampleError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_file(path: Path) -> str:
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
    return _sha256_bytes(encoded)


def validate_authorization_request(
    request: Mapping[str, Any],
    *,
    confirmed_maximum_usd: float,
) -> None:
    expected = {
        "episode_id": EXPECTED_EPISODE_ID,
        "queue_id": EXPECTED_QUEUE_ID,
        "block_id": EXPECTED_BLOCK_ID,
        "segment_id": EXPECTED_SEGMENT_ID,
        "voice_id": EXPECTED_VOICE_ID,
        "model_id": EXPECTED_MODEL_ID,
        "output_format": EXPECTED_OUTPUT_FORMAT,
    }
    for key, value in expected.items():
        if str(request.get(key) or "") != value:
            raise AuthorizedTtsSampleError(
                f"AUTHORIZATION_REQUEST_FIELD_MISMATCH:{key}"
            )

    if request.get("sample_generation_authorized") is not False:
        raise AuthorizedTtsSampleError(
            "PREFLIGHT_REQUEST_MUST_START_UNAUTHORIZED"
        )
    if str(request.get("status") or "") != (
        "READY_FOR_EXPLICIT_SAMPLE_AUTHORIZATION"
    ):
        raise AuthorizedTtsSampleError(
            "PREFLIGHT_REQUEST_NOT_READY_FOR_AUTHORIZATION"
        )
    if str(request.get("text_ar") or "") != EXPECTED_TEXT:
        raise AuthorizedTtsSampleError("AUTHORIZED_SAMPLE_TEXT_CHANGED")
    if len(EXPECTED_TEXT) != EXPECTED_CHARACTER_COUNT:
        raise AuthorizedTtsSampleError(
            f"EMBEDDED_CHARACTER_COUNT_CHANGED:{len(EXPECTED_TEXT)}"
        )
    if int(request.get("character_count_unicode", -1)) != (
        EXPECTED_CHARACTER_COUNT
    ):
        raise AuthorizedTtsSampleError(
            "AUTHORIZED_SAMPLE_CHARACTER_COUNT_CHANGED"
        )
    ceiling = float(
        request.get("suggested_authorization_ceiling_usd", -1)
    )
    if abs(ceiling - EXPECTED_AUTHORIZED_MAXIMUM_USD) > 1e-9:
        raise AuthorizedTtsSampleError(
            "AUTHORIZED_SAMPLE_CEILING_CHANGED"
        )
    if abs(
        float(confirmed_maximum_usd)
        - EXPECTED_AUTHORIZED_MAXIMUM_USD
    ) > 1e-9:
        raise AuthorizedTtsSampleError(
            "EXPLICIT_AUTHORIZATION_MAXIMUM_MISMATCH"
        )
    if str(request.get("hidden_paid_retry") or "") != "FORBIDDEN":
        raise AuthorizedTtsSampleError("HIDDEN_PAID_RETRY_MUST_BE_FORBIDDEN")
    if str(request.get("automatic_resubmission") or "") != "FORBIDDEN":
        raise AuthorizedTtsSampleError(
            "AUTOMATIC_RESUBMISSION_MUST_BE_FORBIDDEN"
        )

    settings = request.get("voice_settings")
    if not isinstance(settings, Mapping):
        raise AuthorizedTtsSampleError("VOICE_SETTINGS_REQUIRED")


def _audio_looks_valid(audio: bytes, content_type: str) -> bool:
    if len(audio) < 1024:
        return False
    lowered = content_type.lower()
    if "audio" in lowered or "mpeg" in lowered or "mp3" in lowered:
        return True
    return (
        audio.startswith(b"ID3")
        or audio.startswith(b"\xff\xfb")
        or audio.startswith(b"\xff\xf3")
        or audio.startswith(b"\xff\xf2")
    )


def _probe_duration_seconds(path: Path) -> float | None:
    ffprobe = shutil.which("ffprobe")
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
    )
    if process.returncode != 0:
        return None
    try:
        value = float(process.stdout.strip())
    except ValueError:
        return None
    return round(value, 3) if value > 0 else None


def execute_authorized_sample(
    repo: Path,
    *,
    confirmed_maximum_usd: float,
) -> SampleExecutionResult:
    repo = repo.resolve()
    episode = repo / "projects" / EXPECTED_EPISODE_ID
    request_path = (
        episode
        / "audio"
        / "tts"
        / "tts-sample-authorization-request-v2.json"
    )
    authorization_path = (
        episode
        / "evidence"
        / "tts-sample-explicit-authorization-v2.json"
    )
    execution_root = (
        episode
        / "orchestration"
        / "tts-sample-execution-v2"
    )
    lock_path = (
        execution_root
        / "locks"
        / "TTS-SAMPLE-VB-001-01-attempt-01.json"
    )
    receipt_path = (
        execution_root
        / "receipts"
        / "TTS-SAMPLE-VB-001-01-attempt-01-receipt.json"
    )

    request = _read_json(request_path)
    validate_authorization_request(
        request,
        confirmed_maximum_usd=confirmed_maximum_usd,
    )

    output_path = repo / str(request.get("output_path_relative") or "")
    if not output_path.is_relative_to(repo):
        raise AuthorizedTtsSampleError("OUTPUT_PATH_MUST_BE_INSIDE_REPOSITORY")

    if lock_path.is_file():
        lock = _read_json(lock_path)
        if (
            str(lock.get("status") or "") == "COMPLETE"
            and receipt_path.is_file()
            and output_path.is_file()
            and output_path.stat().st_size > 0
        ):
            receipt = _read_json(receipt_path)
            return SampleExecutionResult(
                status="COMPLETE_EXISTING_RESULT_REUSED",
                output_path=output_path,
                receipt_path=receipt_path,
                lock_path=lock_path,
                request_id=str(receipt.get("request_id") or "") or None,
                provider_requests_this_run=0,
                idempotent_reuse=True,
            )
        raise AuthorizedTtsSampleError(
            "SAMPLE_ATTEMPT_ALREADY_LOCKED_NO_AUTOMATIC_RETRY"
        )

    authorization = dict(AUTHORIZATION)
    authorization["request_path_relative"] = str(
        request_path.relative_to(repo)
    ).replace("\\", "/")
    authorization["request_sha256"] = _canonical_sha256(request)
    authorization["recorded_at_utc"] = _now()
    _write_json(authorization_path, authorization)

    try:
        api_key = read_elevenlabs_api_key()
    except ProviderCredentialError as exc:
        raise AuthorizedTtsSampleError(str(exc)) from exc
    if not api_key:
        raise AuthorizedTtsSampleError("ELEVENLABS_API_KEY_REQUIRED")

    request_body = {
        "text": EXPECTED_TEXT,
        "model_id": EXPECTED_MODEL_ID,
        "voice_settings": dict(request["voice_settings"]),
    }
    local_request_id = str(uuid.uuid4())
    lock = {
        "schema_version": "siraj-authorized-tts-sample-lock-v2",
        "release": RELEASE,
        "episode_id": EXPECTED_EPISODE_ID,
        "queue_id": EXPECTED_QUEUE_ID,
        "block_id": EXPECTED_BLOCK_ID,
        "status": "LOCKED_BEFORE_NETWORK",
        "attempt": 1,
        "maximum_authorized_usd": EXPECTED_AUTHORIZED_MAXIMUM_USD,
        "internal_reserve_share_usd": (
            EXPECTED_INTERNAL_RESERVE_SHARE_USD
        ),
        "maximum_provider_requests": 1,
        "provider_requests_made": 0,
        "local_request_id": local_request_id,
        "request_payload_sha256": _canonical_sha256(request_body),
        "authorization_path_relative": str(
            authorization_path.relative_to(repo)
        ).replace("\\", "/"),
        "api_key_persisted": False,
        "hidden_paid_retry": "FORBIDDEN",
        "automatic_resubmission": "FORBIDDEN",
        "full_episode_tts_authorized": False,
        "created_at_utc": _now(),
    }
    _write_json(lock_path, lock)

    endpoint = (
        API_ROOT
        + "/text-to-speech/"
        + urllib.parse.quote(EXPECTED_VOICE_ID, safe="")
        + "?output_format="
        + urllib.parse.quote(EXPECTED_OUTPUT_FORMAT, safe="")
    )
    http_request = urllib.request.Request(
        endpoint,
        data=json.dumps(
            request_body,
            ensure_ascii=False,
        ).encode("utf-8"),
        method="POST",
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "Accept": "audio/mpeg",
            "User-Agent": "SIRAJ-Authorized-TTS-Sample/2.0",
        },
    )

    lock["status"] = "NETWORK_REQUEST_STARTED"
    lock["provider_requests_made"] = 1
    lock["network_started_at_utc"] = _now()
    _write_json(lock_path, lock)

    try:
        with urllib.request.urlopen(http_request, timeout=240.0) as response:
            audio = response.read()
            headers = {
                key.lower(): value
                for key, value in response.headers.items()
            }
            http_status = int(getattr(response, "status", 200))
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        lock.update(
            {
                "status": "PROVIDER_REJECTED_NO_AUTOMATIC_RETRY",
                "http_status": exc.code,
                "last_error": body,
                "updated_at_utc": _now(),
            }
        )
        _write_json(lock_path, lock)
        raise AuthorizedTtsSampleError(
            f"ELEVENLABS_HTTP_ERROR:{exc.code}:{body}"
        ) from exc
    except urllib.error.URLError as exc:
        lock.update(
            {
                "status": (
                    "NETWORK_RESULT_UNKNOWN_NO_AUTOMATIC_RETRY"
                ),
                "last_error": str(exc.reason),
                "updated_at_utc": _now(),
            }
        )
        _write_json(lock_path, lock)
        raise AuthorizedTtsSampleError(
            f"ELEVENLABS_NETWORK_ERROR:{exc.reason}"
        ) from exc

    content_type = str(headers.get("content-type") or "")
    if not _audio_looks_valid(audio, content_type):
        lock.update(
            {
                "status": "INVALID_AUDIO_RESPONSE_NO_AUTOMATIC_RETRY",
                "http_status": http_status,
                "response_bytes": len(audio),
                "content_type": content_type,
                "response_sha256": _sha256_bytes(audio),
                "updated_at_utc": _now(),
            }
        )
        _write_json(lock_path, lock)
        raise AuthorizedTtsSampleError("ELEVENLABS_AUDIO_RESPONSE_INVALID")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    partial = output_path.with_suffix(output_path.suffix + ".part")
    partial.write_bytes(audio)
    os.replace(partial, output_path)

    duration_seconds = _probe_duration_seconds(output_path)
    provider_request_id = (
        headers.get("request-id")
        or headers.get("x-request-id")
        or local_request_id
    )
    receipt = {
        "schema_version": "siraj-authorized-tts-sample-receipt-v2",
        "release": RELEASE,
        "episode_id": EXPECTED_EPISODE_ID,
        "queue_id": EXPECTED_QUEUE_ID,
        "block_id": EXPECTED_BLOCK_ID,
        "status": "COMPLETE_AWAITING_HUMAN_AUDIO_REVIEW",
        "provider": "ELEVENLABS",
        "service": "text-to-speech",
        "voice_id": EXPECTED_VOICE_ID,
        "model_id": EXPECTED_MODEL_ID,
        "output_format": EXPECTED_OUTPUT_FORMAT,
        "request_id": provider_request_id,
        "trace_id": headers.get("x-trace-id"),
        "character_cost": headers.get("character-cost"),
        "character_count_unicode": EXPECTED_CHARACTER_COUNT,
        "maximum_authorized_usd": EXPECTED_AUTHORIZED_MAXIMUM_USD,
        "internal_reserve_share_usd": (
            EXPECTED_INTERNAL_RESERVE_SHARE_USD
        ),
        "actual_cost_usd": None,
        "cost_note": (
            "ElevenLabs reports character cost in response headers; "
            "USD 0.07 is the Siraj internal authorization ceiling."
        ),
        "provider_requests": 1,
        "hidden_paid_retry": "FORBIDDEN",
        "automatic_resubmission": "FORBIDDEN",
        "output_path_relative": str(
            output_path.relative_to(repo)
        ).replace("\\", "/"),
        "output_sha256": _sha256_file(output_path),
        "output_bytes": output_path.stat().st_size,
        "duration_seconds": duration_seconds,
        "content_type": content_type,
        "completed_at_utc": _now(),
        "full_episode_tts_authorized": False,
    }
    _write_json(receipt_path, receipt)

    lock.update(
        {
            "status": "COMPLETE",
            "request_id": provider_request_id,
            "receipt_path_relative": str(
                receipt_path.relative_to(repo)
            ).replace("\\", "/"),
            "output_path_relative": str(
                output_path.relative_to(repo)
            ).replace("\\", "/"),
            "output_sha256": receipt["output_sha256"],
            "completed_at_utc": _now(),
        }
    )
    _write_json(lock_path, lock)

    request["status"] = "SAMPLE_GENERATED_AWAITING_HUMAN_REVIEW"
    request["sample_generation_authorized"] = True
    request["authorization"] = authorization
    request["execution_receipt_path_relative"] = str(
        receipt_path.relative_to(repo)
    ).replace("\\", "/")
    request["full_episode_tts_authorized"] = False
    _write_json(request_path, request)

    review_path = (
        episode
        / "audio"
        / "tts"
        / "samples"
        / "VB-001-01-human-review-v2.json"
    )
    _write_json(
        review_path,
        {
            "schema_version": "siraj-tts-sample-human-review-v2",
            "episode_id": EXPECTED_EPISODE_ID,
            "block_id": EXPECTED_BLOCK_ID,
            "status": "AWAITING_HUMAN_AUDIO_REVIEW",
            "audio_path_relative": str(
                output_path.relative_to(repo)
            ).replace("\\", "/"),
            "review_dimensions": [
                "ARABIC_PRONUNCIATION",
                "DIACRITIC_REALIZATION",
                "DELIBERATE_PACING",
                "PAUSE_QUALITY",
                "MEASURED_AWE",
                "DRAMATIC_RESTRAINT",
                "AUDIO_ARTIFACTS",
            ],
            "decision": None,
            "full_episode_tts_authorized": False,
        },
    )

    return SampleExecutionResult(
        status="COMPLETE_AWAITING_HUMAN_AUDIO_REVIEW",
        output_path=output_path,
        receipt_path=receipt_path,
        lock_path=lock_path,
        request_id=provider_request_id,
        provider_requests_this_run=1,
        idempotent_reuse=False,
    )
