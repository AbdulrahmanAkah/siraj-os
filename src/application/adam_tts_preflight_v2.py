"""Offline ElevenLabs TTS preflight for Adam episode V2.

This module performs no network request and no paid provider action.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
from typing import Any, Mapping

from src.application.elevenlabs_voice_casting_v1 import (
    MODEL_ID,
    PRIMARY_VOICE_ID,
    VOICE_ROSTER,
    VOICE_SETTINGS,
    build_episode_voice_cast_plan,
)
from src.application.provider_credentials_v1 import (
    ProviderCredentialError,
    read_elevenlabs_api_key,
)

RELEASE = "SIRAJ_ADAM_TTS_PREFLIGHT_V2"
SCHEMA_VERSION = "siraj-adam-tts-preflight-v2"

SAMPLE_BLOCK_ID = "VB-001-01"
TTS_TOTAL_INTERNAL_RESERVE_USD = 3.0
TARGET_WORDS_PER_MINUTE = 110.415
OUTPUT_FORMAT = "mp3_44100_128"

_ARABIC_WORD = re.compile(r"[\u0621-\u064A\u064B-\u0652\u0670]+")


class AdamTtsPreflightError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CredentialProbe:
    status: str
    present: bool
    format_valid: bool
    source: str
    detail: str | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "present": self.present,
            "format_valid": self.format_valid,
            "source": self.source,
            "detail": self.detail,
            "secret_recorded": False,
        }


def _sequence(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AdamTtsPreflightError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise AdamTtsPreflightError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _probe_credential() -> CredentialProbe:
    source = (
        "ELEVENLABS_API_KEY_ENVIRONMENT"
        if os.environ.get("ELEVENLABS_API_KEY", "").strip()
        else "WINDOWS_CREDENTIAL_MANAGER"
    )
    try:
        secret = read_elevenlabs_api_key()
    except ProviderCredentialError as exc:
        return CredentialProbe(
            status="INVALID_LOCAL_CREDENTIAL",
            present=True,
            format_valid=False,
            source=source,
            detail=str(exc),
        )
    if secret is None:
        return CredentialProbe(
            status="CREDENTIAL_REQUIRED",
            present=False,
            format_valid=False,
            source="NONE",
            detail=None,
        )
    return CredentialProbe(
        status="PRESENT_FORMAT_VALID",
        present=True,
        format_valid=True,
        source=source,
        detail=None,
    )


def _stale_tts_locks(repo: Path, episode_id: str) -> list[dict[str, str]]:
    root = (
        repo
        / "projects"
        / episode_id
        / "orchestration"
        / "media-execution"
        / "locks"
    )
    if not root.is_dir():
        return []
    output: list[dict[str, str]] = []
    for path in sorted(root.glob("*.json")):
        try:
            payload = _read_json(path)
        except AdamTtsPreflightError:
            continue
        if str(payload.get("media_kind") or "") != "ELEVENLABS_TTS":
            continue
        output.append(
            {
                "path_relative": str(path.relative_to(repo)).replace("\\", "/"),
                "status": str(payload.get("status") or ""),
                "queue_id": str(payload.get("queue_id") or ""),
            }
        )
    return output


def _estimate_sample_seconds(queue_item: Mapping[str, Any]) -> float:
    text = str(queue_item.get("text_ar") or "")
    words = len(_ARABIC_WORD.findall(text))
    pause_before = int(queue_item.get("pause_before_ms", 0) or 0)
    pause_after = int(queue_item.get("pause_after_ms", 0) or 0)
    spoken = words * 60.0 / TARGET_WORDS_PER_MINUTE
    return round(spoken + (pause_before + pause_after) / 1000.0, 3)


def _queue_item_by_block(
    queue_items: list[dict[str, Any]],
    block_id: str,
) -> dict[str, Any]:
    matches = [
        item for item in queue_items
        if str(item.get("block_id") or "") == block_id
    ]
    if len(matches) != 1:
        raise AdamTtsPreflightError(
            f"SAMPLE_BLOCK_MATCH_COUNT:{block_id}:{len(matches)}"
        )
    return matches[0]


def _attach_pause_metadata(
    queue_items: list[dict[str, Any]],
    script: Mapping[str, Any],
) -> None:
    block_meta: dict[str, tuple[int, int]] = {}
    for segment in _sequence(script.get("segments")):
        if not isinstance(segment, Mapping):
            continue
        for block in _sequence(segment.get("performance_blocks")):
            if not isinstance(block, Mapping):
                continue
            block_id = str(block.get("block_id") or "")
            if block_id:
                block_meta[block_id] = (
                    int(block.get("pause_before_ms", 0) or 0),
                    int(block.get("pause_after_ms", 0) or 0),
                )
    for item in queue_items:
        before, after = block_meta.get(
            str(item.get("block_id") or ""),
            (0, 0),
        )
        item["pause_before_ms"] = before
        item["pause_after_ms"] = after


def build_preflight(
    *,
    repo: Path,
    episode_id: str,
    script: Mapping[str, Any],
    storyboard: Mapping[str, Any],
) -> dict[str, Any]:
    cast = build_episode_voice_cast_plan(episode_id, script, storyboard)
    cast_payload = cast.as_dict()
    queue_items = [
        dict(item)
        for item in _sequence(cast_payload.get("queue_items"))
        if isinstance(item, Mapping)
    ]
    _attach_pause_metadata(queue_items, script)

    if len(queue_items) != 43:
        raise AdamTtsPreflightError(
            f"EXPECTED_43_TTS_BLOCKS:{len(queue_items)}"
        )
    if cast.performer_slots_used != ("PRIMARY",):
        raise AdamTtsPreflightError(
            "ADAM_EPISODE_EXPECTED_PRIMARY_NARRATOR_ONLY:"
            + ",".join(cast.performer_slots_used)
        )

    sample = _queue_item_by_block(queue_items, SAMPLE_BLOCK_ID)
    if str(sample.get("voice_slot") or "") != "PRIMARY":
        raise AdamTtsPreflightError("SAMPLE_MUST_USE_PRIMARY_VOICE")

    full_character_count = sum(
        len(str(item.get("text_ar") or ""))
        for item in queue_items
    )
    sample_character_count = len(str(sample.get("text_ar") or ""))
    if full_character_count <= 0 or sample_character_count <= 0:
        raise AdamTtsPreflightError("TTS_CHARACTER_COUNTS_INVALID")

    sample_reserve = round(
        TTS_TOTAL_INTERNAL_RESERVE_USD
        * sample_character_count
        / full_character_count,
        6,
    )
    suggested_ceiling = round(
        max(0.01, math.ceil(sample_reserve * 100.0) / 100.0),
        2,
    )

    credential = _probe_credential()
    stale_locks = _stale_tts_locks(repo, episode_id)

    if credential.format_valid:
        readiness = "READY_FOR_EXPLICIT_SAMPLE_AUTHORIZATION"
        next_stage = "EXPLICIT_SAMPLE_AUTHORIZATION"
    elif credential.present:
        readiness = "BLOCKED_INVALID_LOCAL_CREDENTIAL"
        next_stage = "REPLACE_ELEVENLABS_CREDENTIAL_AND_RERUN_PREFLIGHT"
    else:
        readiness = "BLOCKED_CREDENTIAL_REQUIRED"
        next_stage = "CONFIGURE_ELEVENLABS_CREDENTIAL_AND_RERUN_PREFLIGHT"

    sample_request = {
        "schema_version": "siraj-elevenlabs-sample-authorization-request-v2",
        "release": RELEASE,
        "episode_id": episode_id,
        "status": readiness,
        "sample_generation_authorized": False,
        "explicit_paid_authorization_required": True,
        "provider_requests_during_preflight": 0,
        "paid_provider_requests_during_preflight": 0,
        "queue_id": "TTS-SAMPLE-VB-001-01",
        "block_id": SAMPLE_BLOCK_ID,
        "segment_id": str(sample.get("segment_id") or ""),
        "voice_slot": "PRIMARY",
        "voice_id": PRIMARY_VOICE_ID,
        "model_id": MODEL_ID,
        "voice_settings": dict(VOICE_SETTINGS),
        "output_format": OUTPUT_FORMAT,
        "text_ar": str(sample.get("text_ar") or ""),
        "character_count_unicode": sample_character_count,
        "word_count": len(
            _ARABIC_WORD.findall(str(sample.get("text_ar") or ""))
        ),
        "estimated_sample_seconds": _estimate_sample_seconds(sample),
        "internal_reserve_basis_usd": TTS_TOTAL_INTERNAL_RESERVE_USD,
        "internal_reserve_share_usd": sample_reserve,
        "suggested_authorization_ceiling_usd": suggested_ceiling,
        "provider_price_queried": False,
        "output_path_relative": (
            f"projects/{episode_id}/audio/tts/samples/"
            "VB-001-01-primary-narrator-sample.mp3"
        ),
        "selection_reason": (
            "Cold-open narration tests measured awe, deliberate pauses, "
            "Arabic consonant clarity, and the primary narrator's dramatic restraint."
        ),
        "credential": credential.as_dict(),
        "hidden_paid_retry": "FORBIDDEN",
        "automatic_resubmission": "FORBIDDEN",
    }

    cast_payload["queue_items"] = queue_items
    cast_payload["status"] = "PREFLIGHT_CAST_LOCKED_NO_PROVIDER_EXECUTION"
    cast_payload["provider_requests"] = 0
    cast_payload["paid_provider_requests"] = 0

    preflight = {
        "schema_version": SCHEMA_VERSION,
        "release": RELEASE,
        "episode_id": episode_id,
        "status": readiness,
        "credential": credential.as_dict(),
        "voice_cast": {
            "performer_slots_used": list(cast.performer_slots_used),
            "performer_count": cast.performer_count,
            "primary_voice_id": PRIMARY_VOICE_ID,
            "model_id": MODEL_ID,
            "voice_settings": dict(VOICE_SETTINGS),
            "roster": [dict(item) for item in VOICE_ROSTER],
        },
        "script": {
            "segment_count": len(_sequence(script.get("segments"))),
            "performance_block_count": len(queue_items),
            "full_character_count_unicode": full_character_count,
        },
        "sample": {
            "block_id": SAMPLE_BLOCK_ID,
            "segment_id": str(sample.get("segment_id") or ""),
            "character_count_unicode": sample_character_count,
            "estimated_seconds": _estimate_sample_seconds(sample),
            "suggested_authorization_ceiling_usd": suggested_ceiling,
        },
        "stale_tts_locks": stale_locks,
        "stale_tts_lock_count": len(stale_locks),
        "network_requests": 0,
        "provider_requests": 0,
        "paid_provider_requests": 0,
        "sample_generation_authorized": False,
        "full_episode_tts_authorized": False,
        "next_stage": next_stage,
    }

    return {
        "preflight": preflight,
        "cast_plan": cast_payload,
        "sample_request": sample_request,
    }


def write_preflight_outputs(
    *,
    repo: Path,
    episode_id: str,
    result: Mapping[str, Any],
) -> dict[str, str]:
    root = repo / "projects" / episode_id
    report_path = root / "orchestration/tts-preflight-v2-report.json"
    cast_path = root / "orchestration/elevenlabs-voice-cast-plan-v2.json"
    request_path = root / "audio/tts/tts-sample-authorization-request-v2.json"
    sample_text_path = root / "audio/tts/tts-sample-text-v2.txt"

    _write_json(report_path, result["preflight"])
    _write_json(cast_path, result["cast_plan"])
    _write_json(request_path, result["sample_request"])
    _write_text(
        sample_text_path,
        (
            "سراج — عينة الراوي المقترحة\n"
            "الحالة: غير مصرح بإرسالها إلى ElevenLabs بعد\n"
            f"BLOCK_ID={result['sample_request']['block_id']}\n"
            f"VOICE_ID={result['sample_request']['voice_id']}\n"
            f"MODEL_ID={result['sample_request']['model_id']}\n\n"
            f"{result['sample_request']['text_ar']}\n"
        ),
    )

    return {
        "preflight_report": str(report_path.relative_to(repo)).replace("\\", "/"),
        "voice_cast_plan": str(cast_path.relative_to(repo)).replace("\\", "/"),
        "sample_authorization_request": str(
            request_path.relative_to(repo)
        ).replace("\\", "/"),
        "sample_text": str(sample_text_path.relative_to(repo)).replace("\\", "/"),
    }
