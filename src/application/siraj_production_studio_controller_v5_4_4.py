"""SIRAJ Production Studio V5.4.4 controller.

Bridges the V5.3/V5.4 production state into the desktop UI without falling
back to the legacy paid-execution path.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Mapping

from src.application.siraj_final_tts_elevenlabs_v5_4_3 import (
    execute_authorized_item,
)

EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
EP = Path("projects") / EPISODE_ID

QUEUE_REL = EP / "orchestration/final-tts-queue-v5-4-3.json"
PLAN_REL = EP / "orchestration/final-tts-plan-v5-4-3.json"
AUTH_REL = EP / "orchestration/final-tts-paid-authorization-v5-4-3.json"
MARKER_REL = EP / "orchestration/luna-runtime-v5-active.json"
PRON_REPORT_REL = EP / "orchestration/pronunciation-local-recovery-v5-3-4r2.json"
NARRATOR_LOCK_REL = Path(
    "projects/_series/siraj-primary-narrator-lock-v5.4.1.json"
)
LAW_REL = Path(
    "projects/_series/siraj-global-arabic-pronunciation-law-v5.3.json"
)

EXPLICIT_CONFIRMATION_PHRASE = "أوافق على توليد الصوت النهائي"

EXPECTED_PROVIDER = "ELEVENLABS"
EXPECTED_VOICE_ID = "XdoLPWNt7ytn6BtU4FBf"
EXPECTED_MODEL_ID = "eleven_multilingual_v2"
EXPECTED_OUTPUT_FORMAT = "mp3_44100_128"
EXPECTED_SETTINGS = {
    "stability": 0.38,
    "similarity_boost": 0.75,
    "style": 0.42,
    "use_speaker_boost": True,
}


class ProductionStudioError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DashboardState:
    episode_id: str
    current_stage: str
    next_stage: str
    final_tts_status: str
    pronunciation_status: str
    global_pronunciation_law: str
    narrator_lock_status: str
    provider: str
    voice_id: str
    model_id: str
    output_format: str
    planned_requests: int
    total_characters: int
    queue_sha256: str
    historical_reference_usd: float | None
    authorized: bool
    completed_items: int
    total_items: int
    failed_items: int
    queue_items: tuple[dict[str, Any], ...]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionStudioError(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ProductionStudioError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
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


def _canonical_sha(value: Mapping[str, Any]) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def immutable_request_manifest(queue: Mapping[str, Any]) -> dict[str, Any]:
    items = queue.get("items")
    if not isinstance(items, list):
        raise ProductionStudioError("FINAL_TTS_QUEUE_ITEMS_REQUIRED")

    immutable_items = []
    for item in items:
        if not isinstance(item, Mapping):
            raise ProductionStudioError("FINAL_TTS_QUEUE_ITEM_OBJECT_REQUIRED")
        immutable_items.append(
            {
                "queue_id": item.get("queue_id"),
                "queue_index": item.get("queue_index"),
                "source_kind": item.get("source_kind"),
                "segment_id": item.get("segment_id"),
                "beat_id": item.get("beat_id"),
                "order": item.get("order"),
                "text_ar": item.get("text_ar"),
                "character_count_unicode": item.get(
                    "character_count_unicode"
                ),
                "provider": item.get("provider"),
                "voice_id": item.get("voice_id"),
                "model_id": item.get("model_id"),
                "output_format": item.get("output_format"),
                "voice_settings": item.get("voice_settings"),
                "output_path_relative": item.get(
                    "output_path_relative"
                ),
            }
        )

    return {
        "episode_id": queue.get("episode_id"),
        "stage": queue.get("stage"),
        "provider": queue.get("provider"),
        "voice_id": queue.get("voice_id"),
        "model_id": queue.get("model_id"),
        "output_format": queue.get("output_format"),
        "voice_settings": queue.get("voice_settings"),
        "planned_provider_requests": queue.get(
            "planned_provider_requests"
        ),
        "total_character_count_unicode": queue.get(
            "total_character_count_unicode"
        ),
        "items": immutable_items,
    }


def immutable_request_manifest_sha256(
    queue: Mapping[str, Any],
) -> str:
    return _canonical_sha(immutable_request_manifest(queue))


def _validate_series_contract(repo: Path, queue: Mapping[str, Any]) -> None:
    narrator = _read(repo / NARRATOR_LOCK_REL)
    if narrator.get("status") != "ACTIVE":
        raise ProductionStudioError("PRIMARY_NARRATOR_LOCK_NOT_ACTIVE")
    if narrator.get("provider") != EXPECTED_PROVIDER:
        raise ProductionStudioError("PRIMARY_NARRATOR_PROVIDER_MISMATCH")
    if narrator.get("voice_id") != EXPECTED_VOICE_ID:
        raise ProductionStudioError("PRIMARY_NARRATOR_VOICE_MISMATCH")

    resolution = narrator.get("model_resolution")
    if (
        not isinstance(resolution, Mapping)
        or resolution.get("resolved_model_id") != EXPECTED_MODEL_ID
    ):
        raise ProductionStudioError("PRIMARY_NARRATOR_MODEL_MISMATCH")

    law = _read(repo / LAW_REL)
    if law.get("status") != "ACTIVE":
        raise ProductionStudioError("GLOBAL_PRONUNCIATION_LAW_NOT_ACTIVE")

    if queue.get("provider") != EXPECTED_PROVIDER:
        raise ProductionStudioError("QUEUE_PROVIDER_MISMATCH")
    if queue.get("voice_id") != EXPECTED_VOICE_ID:
        raise ProductionStudioError("QUEUE_VOICE_MISMATCH")
    if queue.get("model_id") != EXPECTED_MODEL_ID:
        raise ProductionStudioError("QUEUE_MODEL_MISMATCH")
    if queue.get("output_format") != EXPECTED_OUTPUT_FORMAT:
        raise ProductionStudioError("QUEUE_OUTPUT_FORMAT_MISMATCH")
    if queue.get("voice_settings") != EXPECTED_SETTINGS:
        raise ProductionStudioError("QUEUE_VOICE_SETTINGS_MISMATCH")
    if queue.get("automatic_retry") is not False:
        raise ProductionStudioError("AUTOMATIC_RETRY_MUST_BE_FALSE")


def load_dashboard_state(repo_root: Path) -> DashboardState:
    repo = repo_root.resolve()
    queue = _read(repo / QUEUE_REL)
    plan = _read(repo / PLAN_REL)
    marker = _read(repo / MARKER_REL)
    pron = _read(repo / PRON_REPORT_REL)
    narrator = _read(repo / NARRATOR_LOCK_REL)
    law = _read(repo / LAW_REL)

    _validate_series_contract(repo, queue)

    items = queue.get("items")
    if not isinstance(items, list):
        raise ProductionStudioError("FINAL_TTS_QUEUE_ITEMS_REQUIRED")

    completed = sum(
        1
        for item in items
        if isinstance(item, Mapping)
        and item.get("status") == "COMPLETE"
    )
    failed = sum(
        1
        for item in items
        if isinstance(item, Mapping)
        and (
            "FAILED" in str(item.get("status") or "")
            or "UNKNOWN" in str(item.get("status") or "")
            or "BLOCKED" in str(item.get("status") or "")
        )
    )

    auth_path = repo / AUTH_REL
    authorized = False
    if auth_path.is_file():
        auth = _read(auth_path)
        authorized = (
            auth.get("status") == "ACTIVE"
            and auth.get("immutable_manifest_sha256")
            == immutable_request_manifest_sha256(queue)
        )

    history = plan.get("historical_episode1_reference")
    historical = None
    if isinstance(history, Mapping):
        value = history.get(
            "equivalent_reference_for_current_character_count_usd"
        )
        if isinstance(value, (int, float)):
            historical = float(value)

    return DashboardState(
        episode_id=EPISODE_ID,
        current_stage="FINAL_TTS",
        next_stage=str(
            marker.get("next_stage")
            or queue.get("next_stage")
            or ""
        ),
        final_tts_status=str(
            marker.get("final_tts_status")
            or queue.get("status")
            or "UNKNOWN"
        ),
        pronunciation_status=str(pron.get("status") or "UNKNOWN"),
        global_pronunciation_law=(
            "ACTIVE" if law.get("status") == "ACTIVE" else "INACTIVE"
        ),
        narrator_lock_status=str(narrator.get("status") or "UNKNOWN"),
        provider=str(queue.get("provider") or ""),
        voice_id=str(queue.get("voice_id") or ""),
        model_id=str(queue.get("model_id") or ""),
        output_format=str(queue.get("output_format") or ""),
        planned_requests=int(
            queue.get("planned_provider_requests", 0) or 0
        ),
        total_characters=int(
            queue.get("total_character_count_unicode", 0) or 0
        ),
        queue_sha256=str(queue.get("queue_sha256") or ""),
        historical_reference_usd=historical,
        authorized=authorized,
        completed_items=completed,
        total_items=len(items),
        failed_items=failed,
        queue_items=tuple(
            dict(item)
            for item in items
            if isinstance(item, Mapping)
        ),
    )


def authorize_final_tts(
    repo_root: Path,
    confirmation_phrase: str,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    if confirmation_phrase.strip() != EXPLICIT_CONFIRMATION_PHRASE:
        raise ProductionStudioError(
            "EXPLICIT_DESKTOP_CONFIRMATION_PHRASE_MISMATCH"
        )

    queue = _read(repo / QUEUE_REL)
    _validate_series_contract(repo, queue)

    if queue.get("status") == "COMPLETE":
        raise ProductionStudioError("FINAL_TTS_ALREADY_COMPLETE")

    items = queue.get("items")
    if not isinstance(items, list) or not items:
        raise ProductionStudioError("FINAL_TTS_QUEUE_ITEMS_REQUIRED")

    manifest_sha = immutable_request_manifest_sha256(queue)

    existing_path = repo / AUTH_REL
    if existing_path.is_file():
        existing = _read(existing_path)
        if (
            existing.get("status") == "ACTIVE"
            and existing.get("immutable_manifest_sha256") == manifest_sha
        ):
            return existing
        raise ProductionStudioError(
            "EXISTING_FINAL_TTS_AUTHORIZATION_CONFLICT"
        )

    authorization = {
        "schema_version": "siraj-final-tts-paid-authorization-v5.4.4",
        "status": "ACTIVE",
        "episode_id": EPISODE_ID,
        "stage": "FINAL_TTS",
        "provider": EXPECTED_PROVIDER,
        "voice_id": EXPECTED_VOICE_ID,
        "model_id": EXPECTED_MODEL_ID,
        "output_format": EXPECTED_OUTPUT_FORMAT,
        "voice_settings": EXPECTED_SETTINGS,
        "queue_sha256": queue.get("queue_sha256"),
        "immutable_manifest_sha256": manifest_sha,
        "authorization_source": (
            "EXPLICIT_HUMAN_DESKTOP_CONFIRMATION"
        ),
        "confirmation_phrase": EXPLICIT_CONFIRMATION_PHRASE,
        "maximum_provider_requests": int(
            queue.get("planned_provider_requests", 0) or 0
        ),
        "user_defined_cost_cap_usd": None,
        "assistant_authored_cost_cap_usd": None,
        "automatic_retry": False,
        "automatic_resubmission": False,
        "failed_or_unknown_attempt_requires_new_explicit_authorization": True,
        "authorized_at_utc": _now(),
    }
    _atomic_write(existing_path, authorization)

    for item in items:
        if not isinstance(item, dict):
            raise ProductionStudioError(
                "FINAL_TTS_QUEUE_ITEM_OBJECT_REQUIRED"
            )
        status = str(item.get("status") or "")
        if status == "AWAITING_EXPLICIT_PAID_AUTHORIZATION":
            item["status"] = "AUTHORIZED"
            item["authorized_at_utc"] = _now()
        elif status == "COMPLETE":
            continue
        else:
            raise ProductionStudioError(
                "CANNOT_AUTHORIZE_ITEM_IN_STATUS:"
                f"{item.get('queue_id')}:{status}"
            )

    queue["status"] = "AUTHORIZED"
    queue["authorization_path_relative"] = str(
        AUTH_REL
    ).replace("\\", "/")
    queue["authorization_manifest_sha256"] = manifest_sha
    queue["next_stage"] = "FINAL_TTS_EXECUTION"
    queue["updated_at_utc"] = _now()
    _atomic_write(repo / QUEUE_REL, queue)

    marker = _read(repo / MARKER_REL)
    marker["final_tts_status"] = "AUTHORIZED"
    marker["final_tts_authorization"] = "V5.4.4_ACTIVE"
    marker["next_stage"] = "FINAL_TTS_EXECUTION"
    marker["updated_at_utc"] = _now()
    _atomic_write(repo / MARKER_REL, marker)

    return authorization


def verify_authorization_integrity(repo_root: Path) -> None:
    repo = repo_root.resolve()
    queue = _read(repo / QUEUE_REL)
    auth = _read(repo / AUTH_REL)
    _validate_series_contract(repo, queue)

    current = immutable_request_manifest_sha256(queue)
    if auth.get("status") != "ACTIVE":
        raise ProductionStudioError("FINAL_TTS_AUTHORIZATION_NOT_ACTIVE")
    if auth.get("immutable_manifest_sha256") != current:
        raise ProductionStudioError(
            "FINAL_TTS_IMMUTABLE_MANIFEST_CHANGED_AFTER_AUTHORIZATION"
        )
    if auth.get("queue_sha256") != queue.get("queue_sha256"):
        raise ProductionStudioError(
            "FINAL_TTS_QUEUE_HASH_CHANGED_AFTER_AUTHORIZATION"
        )


def execute_one_authorized_item(
    repo_root: Path,
    queue_id: str,
):
    verify_authorization_integrity(repo_root)
    return execute_authorized_item(
        repo_root.resolve(),
        queue_id,
    )


def pending_authorized_queue_ids(repo_root: Path) -> tuple[str, ...]:
    repo = repo_root.resolve()
    queue = _read(repo / QUEUE_REL)
    items = queue.get("items")
    if not isinstance(items, list):
        raise ProductionStudioError("FINAL_TTS_QUEUE_ITEMS_REQUIRED")
    result = []
    for item in items:
        if not isinstance(item, Mapping):
            continue
        if item.get("status") in {
            "AUTHORIZED",
            "READY_AUTHORIZED",
            "COMPLETE",
        }:
            result.append(str(item.get("queue_id") or ""))
        else:
            raise ProductionStudioError(
                "QUEUE_CONTAINS_NON_EXECUTABLE_STATUS:"
                f"{item.get('queue_id')}:{item.get('status')}"
            )
    return tuple(result)
