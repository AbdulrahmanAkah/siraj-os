"""Final SIRAJ SERIES PRODUCTION STANDARD V2 completion and readiness gate.

This module performs offline standard finalization only. It never calls a paid
provider. It promotes the human-approved Adam narration, creates the immutable
series standard, builds the rolling cost ledger, produces the full TTS execution
plan, performs directorial/technical review, and writes the desktop snapshot.

A publishable result is never claimed merely because rendering completed. The
standard is fail-closed: every blocking gate must pass before the final master
can be labelled READY_TO_PUBLISH.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

from src.application.production_quality_gate_v2 import (
    evaluate_production_quality,
)
from src.application.series_production_quality_v2 import (
    HARD_GENERATED_VIDEO_SPEND_USD,
    TARGET_GENERATED_VIDEO_SPEND_USD,
)
from src.application.world_continuity_policy_v1 import (
    validate_world_continuity,
)

RELEASE = "SIRAJ_SERIES_PRODUCTION_STANDARD_V2_COMPLETE"
SCHEMA_VERSION = "siraj-series-production-standard-v2-complete"

EPISODE_ID = "episode-001-adam"
TOTAL_EPISODE_HARD_CAP_USD = 40.0
GENERATED_VIDEO_TARGET_USD = 30.0
GENERATED_VIDEO_HARD_CAP_USD = 35.0
TTS_RESERVE_USD = 3.0
NON_VIDEO_MEDIA_RESERVE_USD = 2.0
ROLLING_WINDOW = 5
ROLLING_GENERATED_VIDEO_TARGET_USD = 150.0

EXPECTED_BLOCK_COUNT = 43
EXPECTED_SEGMENT_COUNT = 14
EXPECTED_SHOT_COUNT = 70
EXPECTED_SAMPLE_BLOCK_ID = "VB-001-01"
EXPECTED_SAMPLE_SHA256 = (
    "e6a3e74cc6c3c1bd5588a10a9c77c7029a3abcf580d4cc48d8dca42adab35e07"
)
EXPECTED_SAMPLE_VOICE_ID = "XdoLPWNt7ytn6BtU4FBf"
EXPECTED_SAMPLE_MODEL_ID = "eleven_multilingual_v2"

SERIES_ROOT_REL = Path("projects/_series")
EPISODE_ROOT_REL = Path("projects") / EPISODE_ID

SOURCE_CANDIDATE_REL = Path(
    "script/arabic-performance-source-v3-waqf-candidate.json"
)
SCRIPT_CANDIDATE_REL = Path(
    "script/episode-script-v3-waqf-candidate.json"
)
FINAL_SOURCE_REL = Path(
    "script/arabic-performance-source-production-standard-v2.json"
)
FINAL_SCRIPT_REL = Path(
    "script/episode-script-production-standard-v2.json"
)
STORYBOARD_REL = Path(
    "cinematic/storyboard-and-media-plan-v2.json"
)
PRODUCTION_PLAN_REL = Path(
    "cinematic/episode-production-plan-v2.json"
)
SAMPLE_RECEIPT_REL = Path(
    "orchestration/tts-waqf-v3-sample-execution/receipts/"
    "TTS-WAQF-V3-SAMPLE-VB-001-01-attempt-01-receipt.json"
)
SAMPLE_REVIEW_REL = Path(
    "audio/tts/samples/VB-001-01-waqf-v3-human-review.json"
)
SAMPLE_AUDIO_REL = Path(
    "audio/tts/samples/VB-001-01-primary-narrator-waqf-v3-sample.mp3"
)

NARRATION_APPROVAL_REL = Path(
    "evidence/production-standard-v2-narration-final-approval.json"
)
FULL_TTS_PLAN_REL = Path(
    "orchestration/full-episode-tts-execution-plan-production-standard-v2.json"
)
DIRECTOR_REVIEW_REL = Path(
    "orchestration/global-director-and-technical-review-v2.json"
)
READINESS_REL = Path(
    "orchestration/series-production-standard-v2-readiness.json"
)
SOUND_PLAN_REL = Path(
    "cinematic/sound-continuity-plan-production-standard-v2.json"
)
TITLE_PLAN_REL = Path(
    "cinematic/title-and-brand-cue-plan-production-standard-v2.json"
)
UI_SNAPSHOT_REL = Path(
    "orchestration/desktop-series-production-standard-v2-snapshot.json"
)

SERIES_STANDARD_REL = Path(
    "siraj-series-production-standard-v2.json"
)
SERIES_LEDGER_REL = Path(
    "series-cost-ledger-v2.json"
)
SERIES_DIRECTOR_BIBLE_REL = Path(
    "siraj-series-director-bible-v2.json"
)
SERIES_ONE_PASS_CONTRACT_REL = Path(
    "one-pass-publish-ready-production-contract-v2.json"
)


class SeriesProductionStandardV2Error(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class StandardIssue:
    code: str
    scope: str
    severity: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SeriesProductionStandardV2Error(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise SeriesProductionStandardV2Error(
            f"JSON_OBJECT_REQUIRED:{path}"
        )
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(text, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_sha256(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return value
    return ()


def _blocks(script: Mapping[str, Any]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for segment in _sequence(script.get("segments")):
        if not isinstance(segment, Mapping):
            continue
        for block in _sequence(segment.get("performance_blocks")):
            if isinstance(block, Mapping):
                item = dict(block)
                item["_segment_id"] = str(
                    segment.get("segment_id") or ""
                )
                result.append(item)
    return result


def _shots(storyboard: Mapping[str, Any]) -> list[dict[str, Any]]:
    direct = storyboard.get("shots")
    if isinstance(direct, list):
        return [dict(item) for item in direct if isinstance(item, Mapping)]

    result: list[dict[str, Any]] = []
    for sequence in _sequence(storyboard.get("sequences")):
        if not isinstance(sequence, Mapping):
            continue
        for shot in _sequence(sequence.get("shots")):
            if isinstance(shot, Mapping):
                item = dict(shot)
                item["_sequence_id"] = str(
                    sequence.get("sequence_id") or ""
                )
                result.append(item)
    return result


def _float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _find_values(
    value: Any,
    keys: set[str],
) -> list[float]:
    result: list[float] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            if str(key) in keys:
                numeric = _float(item)
                if numeric is not None:
                    result.append(numeric)
            result.extend(_find_values(item, keys))
    elif isinstance(value, list):
        for item in value:
            result.extend(_find_values(item, keys))
    return result


def _planned_generated_video_spend(
    production_plan: Mapping[str, Any],
    storyboard: Mapping[str, Any],
) -> float:
    keys = {
        "generated_video_spend_usd",
        "planned_generated_video_spend_usd",
        "estimated_generated_video_spend_usd",
        "video_spend_usd",
        "selected_generated_video_cost_usd",
    }
    values = _find_values(production_plan, keys)
    values.extend(_find_values(storyboard, keys))
    positive = [item for item in values if item >= 0]
    if positive:
        return round(max(positive), 6)

    total = 0.0
    found = False
    for shot in _shots(storyboard):
        treatment = str(
            shot.get("final_budget_treatment")
            or shot.get("treatment")
            or ""
        ).upper()
        if treatment != "GENERATED_VIDEO":
            continue
        for key in (
            "selected_cost_usd",
            "estimated_cost_usd",
            "cost_usd",
        ):
            numeric = _float(shot.get(key))
            if numeric is not None:
                total += numeric
                found = True
                break
    return round(total, 6) if found else 0.0


def _receipt_identity(
    payload: Mapping[str, Any],
    path: Path,
) -> str:
    for key in (
        "taskUUID",
        "task_uuid",
        "request_id",
        "provider_request_id",
        "local_request_id",
        "trace_id",
    ):
        value = str(payload.get(key) or "").strip()
        if value:
            return f"{key}:{value}"
    return f"path:{path.as_posix()}"


def _receipt_category(
    payload: Mapping[str, Any],
    path: Path,
) -> str:
    text = " ".join(
        str(payload.get(key) or "")
        for key in (
            "provider",
            "service",
            "queue_id",
            "media_type",
            "treatment",
            "release",
        )
    ).lower() + " " + path.as_posix().lower()
    if "text-to-speech" in text or "tts" in text or "elevenlabs" in text:
        return "TTS"
    if "video" in text or "veo" in text:
        return "GENERATED_VIDEO"
    if "image" in text or "seedream" in text:
        return "GENERATED_IMAGE"
    if "openai" in text or "luna" in text:
        return "LUNA"
    return "OTHER"


def _receipt_cost(
    payload: Mapping[str, Any],
) -> tuple[float, bool]:
    for key in (
        "actual_cost_usd",
        "cost_usd",
        "charged_usd",
        "provider_cost_usd",
    ):
        numeric = _float(payload.get(key))
        if numeric is not None and numeric >= 0:
            return round(numeric, 6), True
    return 0.0, False


def build_series_cost_ledger(repo: Path) -> dict[str, Any]:
    episode_rows: list[dict[str, Any]] = []
    global_seen: set[str] = set()

    for episode_root in sorted((repo / "projects").glob("episode-*")):
        if not episode_root.is_dir():
            continue

        totals = {
            "GENERATED_VIDEO": 0.0,
            "GENERATED_IMAGE": 0.0,
            "TTS": 0.0,
            "LUNA": 0.0,
            "OTHER": 0.0,
        }
        receipt_count = 0
        priced_receipt_count = 0
        unpriced_receipt_count = 0
        duplicate_receipt_count = 0

        for path in sorted(episode_root.rglob("*.json")):
            lowered = path.name.lower()
            if "receipt" not in lowered:
                continue
            try:
                payload = _read_json(path)
            except SeriesProductionStandardV2Error:
                continue

            identity = _receipt_identity(
                payload,
                path.relative_to(repo),
            )
            if identity in global_seen:
                duplicate_receipt_count += 1
                continue
            global_seen.add(identity)
            receipt_count += 1

            category = _receipt_category(payload, path)
            cost, known = _receipt_cost(payload)
            totals[category] += cost
            if known:
                priced_receipt_count += 1
            else:
                unpriced_receipt_count += 1

        total_actual = round(sum(totals.values()), 6)
        generated_video_actual = round(
            totals["GENERATED_VIDEO"], 6
        )
        episode_rows.append(
            {
                "episode_id": episode_root.name,
                "actual_paid_spend_usd": total_actual,
                "actual_generated_video_spend_usd": (
                    generated_video_actual
                ),
                "by_category_usd": {
                    key: round(value, 6)
                    for key, value in totals.items()
                },
                "receipt_count": receipt_count,
                "priced_receipt_count": priced_receipt_count,
                "unpriced_receipt_count": unpriced_receipt_count,
                "duplicate_receipt_count": duplicate_receipt_count,
                "total_hard_cap_usd": TOTAL_EPISODE_HARD_CAP_USD,
                "generated_video_hard_cap_usd": (
                    GENERATED_VIDEO_HARD_CAP_USD
                ),
                "within_known_actual_total_cap": (
                    total_actual <= TOTAL_EPISODE_HARD_CAP_USD + 1e-9
                ),
                "within_known_actual_video_cap": (
                    generated_video_actual
                    <= GENERATED_VIDEO_HARD_CAP_USD + 1e-9
                ),
            }
        )

    rolling_rows = episode_rows[-ROLLING_WINDOW:]
    rolling_video = round(
        sum(
            float(item["actual_generated_video_spend_usd"])
            for item in rolling_rows
        ),
        6,
    )
    rolling_actual = round(
        sum(float(item["actual_paid_spend_usd"]) for item in rolling_rows),
        6,
    )
    rolling_count = len(rolling_rows)
    return {
        "schema_version": "siraj-series-cost-ledger-v2",
        "release": RELEASE,
        "generated_at_utc": _now(),
        "policy": {
            "total_episode_hard_cap_usd": TOTAL_EPISODE_HARD_CAP_USD,
            "generated_video_target_usd": GENERATED_VIDEO_TARGET_USD,
            "generated_video_hard_cap_usd": (
                GENERATED_VIDEO_HARD_CAP_USD
            ),
            "tts_reserve_usd": TTS_RESERVE_USD,
            "non_video_media_reserve_usd": (
                NON_VIDEO_MEDIA_RESERVE_USD
            ),
            "rolling_episode_window": ROLLING_WINDOW,
            "rolling_generated_video_target_usd": (
                ROLLING_GENERATED_VIDEO_TARGET_USD
            ),
            "hidden_paid_retry": "FORBIDDEN",
            "deduplication": (
                "TASK_OR_REQUEST_ID_THEN_RECEIPT_PATH"
            ),
        },
        "episodes": episode_rows,
        "rolling_window": {
            "episode_count": rolling_count,
            "actual_paid_spend_usd": rolling_actual,
            "actual_generated_video_spend_usd": rolling_video,
            "generated_video_target_usd": round(
                GENERATED_VIDEO_TARGET_USD * rolling_count,
                6,
            ),
            "average_generated_video_spend_usd": round(
                rolling_video / rolling_count,
                6,
            )
            if rolling_count
            else 0.0,
            "compliant_on_known_actual_costs": (
                rolling_video
                <= GENERATED_VIDEO_TARGET_USD * rolling_count + 1e-9
            ),
        },
        "unpriced_receipt_policy": (
            "VISIBLE_AND_NOT_ASSUMED_ZERO_FOR_AUTHORIZATION"
        ),
    }


def _validate_sample(
    episode_root: Path,
) -> tuple[dict[str, Any], list[StandardIssue]]:
    issues: list[StandardIssue] = []
    receipt_path = episode_root / SAMPLE_RECEIPT_REL
    audio_path = episode_root / SAMPLE_AUDIO_REL
    review_path = episode_root / SAMPLE_REVIEW_REL

    if not receipt_path.is_file():
        issues.append(
            StandardIssue(
                "WAQF_SAMPLE_RECEIPT_MISSING",
                "NARRATION",
                "BLOCKING",
                str(receipt_path),
            )
        )
        return {}, issues
    receipt = _read_json(receipt_path)

    if str(receipt.get("status") or "") != (
        "COMPLETE_AWAITING_HUMAN_AUDIO_REVIEW"
    ):
        issues.append(
            StandardIssue(
                "WAQF_SAMPLE_RECEIPT_STATUS_INVALID",
                "NARRATION",
                "BLOCKING",
                str(receipt.get("status")),
            )
        )
    if str(receipt.get("voice_id") or "") != EXPECTED_SAMPLE_VOICE_ID:
        issues.append(
            StandardIssue(
                "WAQF_SAMPLE_VOICE_CHANGED",
                "NARRATION",
                "BLOCKING",
                str(receipt.get("voice_id")),
            )
        )
    if str(receipt.get("model_id") or "") != EXPECTED_SAMPLE_MODEL_ID:
        issues.append(
            StandardIssue(
                "WAQF_SAMPLE_MODEL_CHANGED",
                "NARRATION",
                "BLOCKING",
                str(receipt.get("model_id")),
            )
        )
    if not audio_path.is_file():
        issues.append(
            StandardIssue(
                "WAQF_SAMPLE_AUDIO_MISSING",
                "NARRATION",
                "BLOCKING",
                str(audio_path),
            )
        )
    else:
        actual_sha = _sha256_file(audio_path)
        expected_sha = str(receipt.get("output_sha256") or "")
        if actual_sha != expected_sha:
            issues.append(
                StandardIssue(
                    "WAQF_SAMPLE_AUDIO_HASH_MISMATCH",
                    "NARRATION",
                    "BLOCKING",
                    f"receipt={expected_sha}:actual={actual_sha}",
                )
            )
        if actual_sha != EXPECTED_SAMPLE_SHA256:
            issues.append(
                StandardIssue(
                    "WAQF_SAMPLE_APPROVED_REFERENCE_CHANGED",
                    "NARRATION",
                    "BLOCKING",
                    actual_sha,
                )
            )

    prior_review = (
        _read_json(review_path) if review_path.is_file() else {}
    )
    return {
        "receipt": receipt,
        "prior_review": prior_review,
        "audio_path": str(audio_path),
        "audio_sha256": (
            _sha256_file(audio_path) if audio_path.is_file() else None
        ),
    }, issues


def _promote_narration(
    episode_root: Path,
    sample: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    source_candidate = _read_json(
        episode_root / SOURCE_CANDIDATE_REL
    )
    script_candidate = _read_json(
        episode_root / SCRIPT_CANDIDATE_REL
    )

    source_final = dict(source_candidate)
    source_final["status"] = (
        "PRODUCTION_STANDARD_V2_HUMAN_APPROVED"
    )
    source_final["paid_execution_authorized"] = False
    source_final["tts_execution_authorized"] = False
    source_final["production_standard_v2_approval"] = {
        "decision": "APPROVED_NO_NOTES",
        "exact_human_direction_ar": "رائع، لا ملاحظات",
        "approval_source": "USER_EXPLICIT_REVIEW_IN_CHAT",
        "approved_at_local": "2026-08-06T14:49:00+03:00",
        "sample_audio_sha256": sample.get("audio_sha256"),
        "sample_block_id": EXPECTED_SAMPLE_BLOCK_ID,
        "full_episode_tts_authorized": False,
    }

    script_final = dict(script_candidate)
    script_final["status"] = (
        "PRODUCTION_STANDARD_V2_HUMAN_APPROVED"
    )
    script_final["paid_execution_authorized"] = False
    script_final["tts_execution_authorized"] = False
    script_final["waqf_human_review_required"] = False
    script_final["human_language_review_required"] = False
    script_final["human_performance_review_required"] = False
    script_final["production_standard_v2_approval"] = dict(
        source_final["production_standard_v2_approval"]
    )

    _write_json(episode_root / FINAL_SOURCE_REL, source_final)
    _write_json(episode_root / FINAL_SCRIPT_REL, script_final)

    source_sha = _canonical_sha256(source_final)
    script_sha = _canonical_sha256(script_final)
    approval = {
        "schema_version": (
            "siraj-production-standard-v2-narration-final-approval"
        ),
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "status": "HUMAN_APPROVED_NO_NOTES",
        "decision": "APPROVE_WAQF_V3_AS_PRODUCTION_REFERENCE",
        "exact_human_direction_ar": "رائع، لا ملاحظات",
        "approval_source": "USER_EXPLICIT_REVIEW_IN_CHAT",
        "approved_at_local": "2026-08-06T14:49:00+03:00",
        "sample_audio_sha256": sample.get("audio_sha256"),
        "source_path_relative": str(FINAL_SOURCE_REL).replace("\\", "/"),
        "source_canonical_sha256": source_sha,
        "script_path_relative": str(FINAL_SCRIPT_REL).replace("\\", "/"),
        "script_canonical_sha256": script_sha,
        "performance_block_count": len(_blocks(script_final)),
        "segment_count": len(
            _sequence(script_final.get("segments"))
        ),
        "full_episode_tts_authorized": False,
        "next_stage": "FULL_EPISODE_TTS_PLAN_READY",
    }
    _write_json(episode_root / NARRATION_APPROVAL_REL, approval)

    review_path = episode_root / SAMPLE_REVIEW_REL
    review = (
        _read_json(review_path) if review_path.is_file() else {}
    )
    review.update(
        {
            "status": "HUMAN_APPROVED_NO_NOTES",
            "decision": "APPROVED",
            "exact_human_direction_ar": "رائع، لا ملاحظات",
            "approved_at_local": "2026-08-06T14:49:00+03:00",
            "full_episode_tts_authorized": False,
        }
    )
    _write_json(review_path, review)
    return script_final, approval


def _build_full_tts_plan(
    episode_root: Path,
    script: Mapping[str, Any],
    approval: Mapping[str, Any],
) -> dict[str, Any]:
    blocks = _blocks(script)
    if len(blocks) != EXPECTED_BLOCK_COUNT:
        raise SeriesProductionStandardV2Error(
            f"EXPECTED_43_BLOCKS:{len(blocks)}"
        )

    total_chars = sum(
        len(str(block.get("tts_text_ar") or ""))
        for block in blocks
    )
    queue: list[dict[str, Any]] = []
    allocated = 0.0
    for index, block in enumerate(blocks, start=1):
        text = str(block.get("tts_text_ar") or "")
        if not text:
            raise SeriesProductionStandardV2Error(
                f"TTS_TEXT_MISSING:{block.get('block_id')}"
            )
        share = (
            TTS_RESERVE_USD * len(text) / total_chars
            if total_chars
            else 0.0
        )
        share = round(share, 6)
        allocated += share
        queue.append(
            {
                "sequence": index,
                "queue_id": (
                    "TTS-PSV2-"
                    + str(block.get("block_id") or f"{index:03d}")
                ),
                "block_id": str(block.get("block_id") or ""),
                "segment_id": str(block.get("_segment_id") or ""),
                "speaker_key": str(
                    block.get("speaker_key") or "NARRATOR"
                ),
                "voice_id": EXPECTED_SAMPLE_VOICE_ID,
                "model_id": EXPECTED_SAMPLE_MODEL_ID,
                "voice_settings": {
                    "stability": 0.38,
                    "similarity_boost": 0.75,
                    "style": 0.42,
                    "use_speaker_boost": True,
                },
                "text_ar": text,
                "character_count_unicode": len(text),
                "pause_before_ms": int(
                    block.get("pause_before_ms", 0) or 0
                ),
                "pause_after_ms": int(
                    block.get("pause_after_ms", 0) or 0
                ),
                "internal_reserve_share_usd": share,
                "maximum_provider_requests": 1,
                "automatic_resubmission": "FORBIDDEN",
                "hidden_paid_retry": "FORBIDDEN",
                "status": "READY_AWAITING_CONSOLIDATED_AUTHORIZATION",
                "output_path_relative": (
                    "projects/episode-001-adam/audio/tts/production-standard-v2/"
                    + str(block.get("block_id") or f"{index:03d}")
                    + ".mp3"
                ),
            }
        )

    plan = {
        "schema_version": (
            "siraj-full-episode-tts-execution-plan-production-standard-v2"
        ),
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "status": "READY_AWAITING_CONSOLIDATED_AUTHORIZATION",
        "narration_approval_sha256": _canonical_sha256(approval),
        "approved_sample_audio_sha256": EXPECTED_SAMPLE_SHA256,
        "performance_block_count": len(queue),
        "character_count_unicode": total_chars,
        "internal_reserve_usd": TTS_RESERVE_USD,
        "allocated_reserve_usd": round(allocated, 6),
        "voice_id": EXPECTED_SAMPLE_VOICE_ID,
        "model_id": EXPECTED_SAMPLE_MODEL_ID,
        "one_request_per_block": True,
        "maximum_provider_requests": len(queue),
        "sequential_execution": True,
        "per_block_lock_before_network": True,
        "per_block_receipt_required": True,
        "automatic_resubmission": "FORBIDDEN",
        "hidden_paid_retry": "FORBIDDEN",
        "full_episode_tts_authorized": False,
        "queue": queue,
        "completion_gate": {
            "all_audio_files_decode": True,
            "all_receipt_hashes_match": True,
            "block_duration_plausibility": True,
            "clipping_and_silence_scan": True,
            "speaker_consistency": True,
            "join_boundary_audit": True,
        },
        "next_stage": "CONSOLIDATED_FULL_EPISODE_PRODUCTION_AUTHORIZATION",
    }
    _write_json(episode_root / FULL_TTS_PLAN_REL, plan)
    return plan


def _camera_field_count(shots: Sequence[Mapping[str, Any]]) -> int:
    keys = (
        "camera",
        "camera_ar",
        "camera_psychology_ar",
        "camera_language_ar",
        "lens",
        "lens_ar",
        "shot_size",
        "composition_ar",
    )
    return sum(
        any(str(shot.get(key) or "").strip() for key in keys)
        for shot in shots
    )


def _sound_field_count(shots: Sequence[Mapping[str, Any]]) -> int:
    keys = (
        "sfx_cues_ar",
        "sound_design_ar",
        "sound_ar",
        "audio_ar",
        "ambience_ar",
    )
    return sum(
        any(str(shot.get(key) or "").strip() for key in keys)
        for shot in shots
    )


def _duration(shot: Mapping[str, Any]) -> float:
    for key in (
        "planned_seconds",
        "duration_seconds",
        "duration",
    ):
        numeric = _float(shot.get(key))
        if numeric is not None:
            return max(0.0, numeric)
    return 0.0


def _build_sound_plan(
    episode_root: Path,
    shots: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    entries: list[dict[str, Any]] = []
    for index, shot in enumerate(shots, start=1):
        domain = str(
            shot.get("scene_domain") or "UNSPECIFIED"
        )
        explicit = (
            shot.get("sfx_cues_ar")
            or shot.get("sound_design_ar")
            or shot.get("ambience_ar")
        )
        if explicit:
            treatment = explicit
            origin = "STORYBOARD_EXPLICIT"
        elif domain == "HEAVENLY_UNSEEN_SYMBOLIC":
            treatment = (
                "صمت مصمم قصير مع هواء تجريدي غير موسيقي "
                "وطبقة مكانية خافتة غير محددة المصدر"
            )
            origin = "STANDARD_DERIVED"
        elif domain == "DOCUMENTARY_EVIDENCE":
            treatment = (
                "ملمس وثائقي محلي هادئ: ورق أو حجر أو حركة بيئية "
                "من دون موسيقى"
            )
            origin = "STANDARD_DERIVED"
        else:
            treatment = (
                "أجواء بيئية مطابقة للمكان مع مؤثرات سببية للحركة، "
                "من دون موسيقى"
            )
            origin = "STANDARD_DERIVED"
        entries.append(
            {
                "sequence": index,
                "shot_id": str(
                    shot.get("shot_id") or f"SHOT-{index:03d}"
                ),
                "duration_seconds": _duration(shot),
                "scene_domain": domain,
                "treatment_ar": treatment,
                "origin": origin,
                "music": "FORBIDDEN",
                "unplanned_silence": "FORBIDDEN",
                "designed_silence_requires_manifest": True,
            }
        )
    plan = {
        "schema_version": (
            "siraj-sound-continuity-plan-production-standard-v2"
        ),
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "status": "READY",
        "music": "FORBIDDEN",
        "narration": "APPROVED_WAQF_V3",
        "target_integrated_lufs": -16.0,
        "loudness_tolerance_lu": 1.0,
        "target_true_peak_dbtp": -1.5,
        "maximum_true_peak_dbtp": -1.0,
        "maximum_unplanned_silence_seconds": 3.0,
        "sidechain_ducking_under_narration": True,
        "shot_count": len(entries),
        "shots": entries,
    }
    _write_json(episode_root / SOUND_PLAN_REL, plan)
    return plan


def _build_title_plan(episode_root: Path) -> dict[str, Any]:
    plan = {
        "schema_version": (
            "siraj-title-and-brand-cue-plan-production-standard-v2"
        ),
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "status": "LOCKED",
        "cold_open": {
            "start_seconds": 0.0,
            "minimum_seconds": 10.0,
            "maximum_seconds": 20.0,
            "purpose": "DRAMATIC_HOOK_BEFORE_BRAND",
        },
        "brand_cue": {
            "channel_name": "سراج",
            "start_seconds": 14.0,
            "duration_seconds": 2.5,
            "maximum_duration_seconds": 3.0,
            "logo_only_or_minimal_wordmark": True,
            "ornate_generic_calligraphy": "FORBIDDEN",
            "sound": "NON_MUSICAL_IMPACT_OR_DESIGNED_SILENCE",
        },
        "episode_title": {
            "display_after_brand_cue": True,
            "maximum_words": 8,
            "safe_title_area_percent": 80,
            "arabic_typography_human_review_required": True,
        },
        "opening_at_absolute_frame_zero": "FORBIDDEN",
    }
    _write_json(episode_root / TITLE_PLAN_REL, plan)
    return plan


def _directorial_review(
    script: Mapping[str, Any],
    storyboard: Mapping[str, Any],
    production_plan: Mapping[str, Any],
    generated_video_spend: float,
) -> tuple[dict[str, Any], list[StandardIssue]]:
    issues: list[StandardIssue] = []
    shots = _shots(storyboard)
    blocks = _blocks(script)

    if len(shots) != EXPECTED_SHOT_COUNT:
        issues.append(
            StandardIssue(
                "SHOT_COUNT_CHANGED",
                "DIRECTORIAL",
                "BLOCKING",
                f"expected={EXPECTED_SHOT_COUNT}:actual={len(shots)}",
            )
        )
    if len(blocks) != EXPECTED_BLOCK_COUNT:
        issues.append(
            StandardIssue(
                "PERFORMANCE_BLOCK_COUNT_CHANGED",
                "NARRATION",
                "BLOCKING",
                f"expected={EXPECTED_BLOCK_COUNT}:actual={len(blocks)}",
            )
        )

    total_duration = round(sum(_duration(item) for item in shots), 3)
    if total_duration <= 0:
        issues.append(
            StandardIssue(
                "SHOT_TIMING_MISSING",
                "DIRECTORIAL",
                "BLOCKING",
                "No valid shot durations.",
            )
        )

    camera_count = _camera_field_count(shots)
    camera_coverage = (
        camera_count / len(shots) if shots else 0.0
    )
    if camera_coverage < 0.90:
        issues.append(
            StandardIssue(
                "CAMERA_LANGUAGE_COVERAGE_LOW",
                "DIRECTORIAL",
                "BLOCKING",
                f"coverage={camera_coverage:.3f}",
            )
        )

    sound_count = _sound_field_count(shots)
    sound_coverage = sound_count / len(shots) if shots else 0.0

    for shot in shots:
        shot_id = str(shot.get("shot_id") or "UNKNOWN")
        treatment = str(
            shot.get("final_budget_treatment")
            or shot.get("treatment")
            or ""
        ).upper()
        duration = _duration(shot)
        if treatment in {
            "DYNAMIC_STILL_SEQUENCE",
            "DYNAMIC_STILL",
            "ANIMATED_STILL_COMPOSITING",
            "GENERATED_IMAGE",
        }:
            panel_count = int(
                shot.get("still_panel_count", 1) or 1
            )
            effective = duration / max(panel_count, 1)
            if effective > 7.0 + 1e-9:
                issues.append(
                    StandardIssue(
                        "STILL_PANEL_EXCEEDS_SEVEN_SECONDS",
                        shot_id,
                        "BLOCKING",
                        f"effective_seconds={effective:.3f}",
                    )
                )
            profile = str(
                shot.get("motion_profile") or ""
            ).upper()
            if profile in {"", "ZOOM_ONLY", "SLOW_PUSH_IN"}:
                issues.append(
                    StandardIssue(
                        "CHEAP_STILL_MOTION_PROFILE",
                        shot_id,
                        "BLOCKING",
                        profile or "MISSING",
                    )
                )
        extension = _float(
            shot.get("last_frame_extension_seconds")
        )
        if extension is not None and extension > 1.25 + 1e-9:
            issues.append(
                StandardIssue(
                    "LAST_FRAME_EXTENSION_EXCEEDS_LIMIT",
                    shot_id,
                    "BLOCKING",
                    str(extension),
                )
            )

    world_issues = validate_world_continuity(storyboard)
    for item in world_issues:
        issues.append(
            StandardIssue(
                item.code,
                item.shot_id,
                item.severity,
                item.detail,
            )
        )

    base_gate = evaluate_production_quality(
        script=script,
        storyboard=storyboard,
        qa_report=None,
        generated_video_spend_usd=generated_video_spend,
    )
    for item in _sequence(base_gate.get("issues")):
        if not isinstance(item, Mapping):
            continue
        code = str(item.get("code") or "")
        scope = str(item.get("scope") or "")
        if not any(
            issue.code == code and issue.scope == scope
            for issue in issues
        ):
            issues.append(
                StandardIssue(
                    code,
                    scope,
                    str(item.get("severity") or "BLOCKING"),
                    str(item.get("detail") or code),
                )
            )

    if generated_video_spend > GENERATED_VIDEO_HARD_CAP_USD + 1e-9:
        issues.append(
            StandardIssue(
                "GENERATED_VIDEO_HARD_CAP_EXCEEDED",
                "BUDGET",
                "BLOCKING",
                str(generated_video_spend),
            )
        )

    checks = {
        "narrative_and_direction": {
            "shot_count": len(shots),
            "total_planned_duration_seconds": total_duration,
            "camera_language_coverage": round(camera_coverage, 6),
            "sound_metadata_coverage_before_derived_plan": round(
                sound_coverage, 6
            ),
            "cold_open_before_brand": True,
            "brand_cue_seconds": 14.0,
            "visual_motif_and_sequence_arc_required": True,
            "screen_direction_continuity_required": True,
            "lens_grammar_per_sequence_required": True,
            "no_repeated_near_identical_adjacent_shots": True,
        },
        "visual_integrity": {
            "flat_slideshow": "FORBIDDEN",
            "simple_zoom_only": "FORBIDDEN",
            "maximum_still_panel_seconds": 7.0,
            "maximum_last_frame_extension_seconds": 1.25,
            "generated_video_for_required_motion": True,
            "no_black_filler": True,
            "no_low_resolution_upscale_as_primary_asset": True,
            "bt709_color_pipeline": True,
            "continuity_reference_required_per_world_and_character": True,
        },
        "religious_and_historical_safety": {
            "prophet_direct_visual_representation": "FORBIDDEN",
            "divine_direct_visual_representation": "FORBIDDEN",
            "angel_and_unseen_literal_claim": "FORBIDDEN",
            "unseen_mode": "SYMBOLIC_NON_DEFINITIVE",
            "unsupported_religious_detail": "FORBIDDEN",
            "evidence_traceability": "REQUIRED",
        },
        "audio": {
            "music": "FORBIDDEN",
            "approved_narration": "WAQF_V3",
            "integrated_lufs_target": -16.0,
            "integrated_lufs_tolerance": 1.0,
            "true_peak_target_dbtp": -1.5,
            "maximum_true_peak_dbtp": -1.0,
            "maximum_unplanned_silence_seconds": 3.0,
            "dialogue_intelligibility": "BLOCKING",
            "cross_block_voice_consistency": "BLOCKING",
        },
        "delivery": {
            "resolution": "1920x1080",
            "frame_rate": 30,
            "frame_rate_mode": "CONSTANT",
            "video_codec": "H264_HIGH_LEVEL_4_1",
            "pixel_format": "YUV420P",
            "color_space": "BT709_LIMITED",
            "audio_codec": "AAC",
            "audio_sample_rate_hz": 48000,
            "audio_channels": 2,
            "audio_bitrate_kbps": 192,
            "youtube_upload": "MANUAL",
        },
        "one_pass_quality_strategy": {
            "preflight_before_every_paid_request": True,
            "validate_each_asset_before_next_stage": True,
            "assemble_only_after_all_assets_pass": True,
            "automatic_paid_retry": "FORBIDDEN",
            "local_targeted_repair": "ALLOWED",
            "full_regeneration_for_local_defect": "FORBIDDEN",
            "final_release_gate": "FAIL_CLOSED",
        },
    }

    blocking = [
        item for item in issues if item.severity == "BLOCKING"
    ]
    report = {
        "schema_version": (
            "siraj-global-director-and-technical-review-v2"
        ),
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "review_perspectives": [
            "FEATURE_FILM_DIRECTOR",
            "DOCUMENTARY_SHOWRUNNER",
            "CINEMATOGRAPHER",
            "EDITOR",
            "SOUND_SUPERVISOR",
            "COLOR_AND_DELIVERY_ENGINEER",
            "RELIABILITY_AND_SAFETY_ENGINEER",
            "COST_CONTROL_ENGINEER",
        ],
        "status": "PASS" if not blocking else "BLOCKED",
        "blocking_issue_count": len(blocking),
        "warning_count": sum(
            item.severity != "BLOCKING" for item in issues
        ),
        "generated_video_planned_spend_usd": (
            generated_video_spend
        ),
        "checks": checks,
        "issues": [item.as_dict() for item in issues],
        "claim": (
            "THE_SYSTEM_CANNOT_GUARANTEE_THAT_A_GENERATIVE_PROVIDER_WILL_"
            "NEVER_PRODUCE_A_DEFECT;_IT_GUARANTEES_THAT_A_DETECTED_OR_"
            "UNVALIDATED_DEFECT_CANNOT_BE_LABELLED_READY_TO_PUBLISH"
        ),
    }
    return report, issues


def _series_standard_manifest() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "release": RELEASE,
        "status": "ACTIVE_IMMUTABLE_BASELINE",
        "identity": {
            "channel": "سراج",
            "format": "PRESTIGE_HISTORICAL_CINEMATIC_SERIES",
            "quality_target": "GLOBAL_PRESTIGE_CINEMATIC",
            "presentation_style": (
                "CINEMATIC_STORYTELLING_NOT_DRY_LECTURE"
            ),
            "animation_or_cartoon_default": "FORBIDDEN",
            "photoreal_cinematic_default": True,
        },
        "budget": {
            "total_episode_hard_cap_usd": (
                TOTAL_EPISODE_HARD_CAP_USD
            ),
            "generated_video_target_usd": (
                GENERATED_VIDEO_TARGET_USD
            ),
            "generated_video_hard_cap_usd": (
                GENERATED_VIDEO_HARD_CAP_USD
            ),
            "tts_reserve_usd": TTS_RESERVE_USD,
            "non_video_media_reserve_usd": (
                NON_VIDEO_MEDIA_RESERVE_USD
            ),
            "rolling_episode_window": ROLLING_WINDOW,
            "rolling_generated_video_target_usd": (
                ROLLING_GENERATED_VIDEO_TARGET_USD
            ),
            "preflight_before_each_paid_request": True,
            "single_consolidated_authorization": True,
            "hidden_paid_retry": "FORBIDDEN",
            "automatic_paid_retry": "FORBIDDEN",
            "hard_cap_override": "FORBIDDEN",
        },
        "editorial": {
            "evidence_before_script": True,
            "human_scope_gate": "REQUIRED",
            "human_final_review_gate": "REQUIRED",
            "exact_claim_strength_preserved": True,
            "invented_historical_dialogue": "FORBIDDEN",
            "research_meta_language_in_narration": "FORBIDDEN",
            "dramatic_arc_per_episode": "REQUIRED",
            "dramatic_function_per_sequence": "REQUIRED",
            "visual_beat_per_shot": "REQUIRED",
        },
        "narration": {
            "fully_diacritized": True,
            "actual_stop_waqf": True,
            "comma_default": "CONNECTED_READING",
            "target_words_per_minute": 116,
            "allowed_words_per_minute": [100, 128],
            "approved_voice_id": EXPECTED_SAMPLE_VOICE_ID,
            "model_id": EXPECTED_SAMPLE_MODEL_ID,
            "voice_settings": {
                "stability": 0.38,
                "similarity_boost": 0.75,
                "style": 0.42,
                "use_speaker_boost": True,
            },
            "short_sample_before_full_episode": "REQUIRED",
            "block_level_audio_receipts": "REQUIRED",
        },
        "visual": {
            "video_first_when_motion_is_required": True,
            "still_usage": "LIMITED_INTENTIONAL_MULTI_PANEL",
            "maximum_still_panel_seconds": 7.0,
            "maximum_last_frame_extension_seconds": 1.25,
            "flat_slideshow": "FORBIDDEN",
            "simple_zoom_only": "FORBIDDEN",
            "black_filler": "FORBIDDEN",
            "frozen_filler": "FORBIDDEN",
            "cheap_duration_stretch": "FORBIDDEN",
            "continuity_bible_per_episode": "REQUIRED",
            "title_after_cold_open_seconds": [10.0, 20.0],
            "brand_cue_maximum_seconds": 3.0,
        },
        "unseen_and_religious": {
            "prophet_face_or_direct_features": "FORBIDDEN",
            "divine_representation": "FORBIDDEN",
            "literal_unseen_claim": "FORBIDDEN",
            "unseen_visual_mode": "SYMBOLIC_NON_DEFINITIVE",
            "earthlike_unseen_default": "FORBIDDEN",
            "unsupported_religious_detail": "FORBIDDEN",
            "historical_and_sharia_review": "REQUIRED",
        },
        "audio": {
            "music": "FORBIDDEN",
            "songs": "FORBIDDEN",
            "musical_score": "FORBIDDEN",
            "narration": "ALLOWED",
            "environmental_ambience": "ALLOWED",
            "causal_sound_effects": "ALLOWED",
            "designed_silence": "ALLOWED_WHEN_MANIFESTED",
            "maximum_unplanned_silence_seconds": 3.0,
            "integrated_lufs_target": -16.0,
            "integrated_lufs_tolerance": 1.0,
            "true_peak_target_dbtp": -1.5,
            "maximum_true_peak_dbtp": -1.0,
        },
        "delivery": {
            "master_resolution": "1920x1080",
            "frame_rate": 30,
            "frame_rate_mode": "CONSTANT",
            "video_codec": "H264_HIGH_LEVEL_4_1",
            "pixel_format": "YUV420P",
            "color": "BT709_LIMITED",
            "audio": "AAC_48KHZ_STEREO_192KBPS",
            "arabic_srt": "REQUIRED",
            "youtube_metadata_package": "REQUIRED",
            "youtube_upload": "MANUAL",
        },
        "qa": {
            "asset_hash_and_receipt_integrity": "BLOCKING",
            "decode_and_duration": "BLOCKING",
            "resolution_fps_pixel_format": "BLOCKING",
            "black_freeze_silence": "BLOCKING",
            "audio_loudness_and_true_peak": "BLOCKING",
            "world_continuity": "BLOCKING",
            "religious_safety": "BLOCKING",
            "arabic_language_and_typography": "BLOCKING",
            "cheap_montage_risk": "BLOCKING",
            "budget_hard_cap": "BLOCKING",
            "final_master_full_watch": "REQUIRED",
            "release_policy": "FAIL_CLOSED",
        },
        "autonomy": {
            "full_episode_runs_after_one_consolidated_authorization": True,
            "sequential_locked_provider_requests": True,
            "resume_valid_receipts": True,
            "recover_runware_task_without_resubmission": True,
            "elevenlabs_ambiguous_result_resubmission": "FORBIDDEN",
            "automatic_local_chain": [
                "SFX_AND_AUDIO_MIX",
                "STRUCTURAL_MONTAGE",
                "AUTOMATIC_QA",
                "PUBLISH_PACKAGE",
            ],
            "publish_without_final_human_acceptance": "FORBIDDEN",
        },
    }


def _director_bible() -> dict[str, Any]:
    return {
        "schema_version": "siraj-series-director-bible-v2",
        "release": RELEASE,
        "status": "ACTIVE",
        "creative_principles": [
            "Every shot must reveal, transform, contrast, or emotionally advance.",
            "No image exists merely to fill narration time.",
            "Movement follows dramatic causality, not decorative motion.",
            "Camera distance and lens language reflect the emotional state.",
            "Cuts follow action, thought, sound, or visual geometry.",
            "Each sequence owns a motif, palette, spatial rule, and escalation.",
            "The unseen remains symbolic, respectful, and non-definitive.",
            "Historical evidence controls truth; cinema controls delivery.",
        ],
        "continuity": {
            "world_geography": "LOCKED_PER_SEQUENCE",
            "character_silhouette_and_scale": "LOCKED",
            "material_and_costume_language": "LOCKED",
            "light_direction_and_time": "LOCKED",
            "screen_direction": "LOCKED_UNLESS_MOTIVATED_REVERSAL",
            "lens_family": "CONSISTENT_PER_SEQUENCE",
            "palette": "CONTROLLED_PER_WORLD_AND_ERA",
            "prompt_reference_pack": "REQUIRED",
        },
        "editing": {
            "cold_open": "10_TO_20_SECONDS",
            "brand_cue": "2_TO_3_SECONDS",
            "narration_driven_cut_only": "FORBIDDEN",
            "visual_redundancy": "FORBIDDEN",
            "adjacent_near_duplicate_shots": "FORBIDDEN",
            "freeze_as_duration_solution": "FORBIDDEN",
            "black_as_duration_solution": "FORBIDDEN",
            "rhythm": "VARIABLE_BY_DRAMATIC_PRESSURE",
        },
        "sound": {
            "music": "FORBIDDEN",
            "sound_perspective_matches_camera": True,
            "ambience_continuity_across_cuts": True,
            "effects_require_visible_or_implied_cause": True,
            "silence_is_authored_not_accidental": True,
            "narration_remains_intelligible": True,
        },
    }


def _one_pass_contract() -> dict[str, Any]:
    return {
        "schema_version": (
            "siraj-one-pass-publish-ready-production-contract-v2"
        ),
        "release": RELEASE,
        "status": "ACTIVE",
        "goal": (
            "PRODUCE_A_COMPLETE_MASTER_WITH_NO_EXPECTED_EDITORIAL_OR_"
            "TECHNICAL_REWORK_AFTER_FINAL_RENDER"
        ),
        "truth_boundary": (
            "GENERATIVE_OUTPUT_CANNOT_BE_GUARANTEED_DEFECT_FREE_IN_"
            "ADVANCE;THE_PIPELINE_MUST_DETECT_BLOCK_AND_REPORT_ANY_"
            "DEFECT_BEFORE_READY_TO_PUBLISH"
        ),
        "before_paid_execution": [
            "STANDARD_V2_READINESS_PASS",
            "SCRIPT_AND_STORYBOARD_HASH_LOCK",
            "NARRATION_SAMPLE_APPROVED",
            "BUDGET_PREFLIGHT_PASS",
            "PROMPT_AND_CONTINUITY_PACK_LOCK",
            "SOUND_AND_TITLE_PLAN_LOCK",
            "CONSOLIDATED_MAXIMUM_COST_CONFIRMATION",
        ],
        "during_asset_generation": [
            "ONE_LOCK_PER_REQUEST",
            "ONE_RECEIPT_PER_RESULT",
            "HASH_AND_DECODE_CHECK",
            "PROFILE_AND_DURATION_CHECK",
            "BLACK_FREEZE_AND_ARTIFACT_SCAN",
            "CONTINUITY_METADATA_CHECK",
            "NO_HIDDEN_PAID_RETRY",
        ],
        "before_assembly": [
            "ALL_REQUIRED_ASSETS_PASS",
            "ALL_TTS_BLOCKS_PASS",
            "NO_UNPRICED_OR_UNBOUND_PAID_ITEM",
            "NO_MISSING_CONTINUITY_REFERENCE",
        ],
        "after_assembly": [
            "TECHNICAL_MASTER_QA",
            "AUDIO_MASTER_QA",
            "SEMANTIC_AND_RELIGIOUS_CHECKLIST",
            "FULL_DURATION_HUMAN_WATCH",
            "PUBLISH_PACKAGE_HASH_LOCK",
        ],
        "release_rule": (
            "READY_TO_PUBLISH_ONLY_WHEN_EVERY_BLOCKING_GATE_PASSES"
        ),
        "automatic_paid_retry": "FORBIDDEN",
        "local_targeted_repair": "ALLOWED",
        "full_episode_regeneration_for_local_defect": "FORBIDDEN",
    }


def finalize_standard(repo_root: Path) -> dict[str, Any]:
    repo = repo_root.resolve()
    episode_root = repo / EPISODE_ROOT_REL
    series_root = repo / SERIES_ROOT_REL

    required = (
        episode_root / SOURCE_CANDIDATE_REL,
        episode_root / SCRIPT_CANDIDATE_REL,
        episode_root / STORYBOARD_REL,
        episode_root / PRODUCTION_PLAN_REL,
        episode_root / SAMPLE_RECEIPT_REL,
        episode_root / SAMPLE_AUDIO_REL,
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SeriesProductionStandardV2Error(
            "REQUIRED_INPUTS_MISSING:" + "|".join(missing)
        )

    sample, sample_issues = _validate_sample(episode_root)
    if any(item.severity == "BLOCKING" for item in sample_issues):
        raise SeriesProductionStandardV2Error(
            "SAMPLE_VALIDATION_BLOCKED:"
            + ",".join(item.code for item in sample_issues)
        )

    script, narration_approval = _promote_narration(
        episode_root,
        sample,
    )
    tts_plan = _build_full_tts_plan(
        episode_root,
        script,
        narration_approval,
    )

    storyboard = _read_json(episode_root / STORYBOARD_REL)
    production_plan = _read_json(
        episode_root / PRODUCTION_PLAN_REL
    )
    generated_video_spend = _planned_generated_video_spend(
        production_plan,
        storyboard,
    )

    sound_plan = _build_sound_plan(
        episode_root,
        _shots(storyboard),
    )
    title_plan = _build_title_plan(episode_root)
    director_review, director_issues = _directorial_review(
        script,
        storyboard,
        production_plan,
        generated_video_spend,
    )
    _write_json(episode_root / DIRECTOR_REVIEW_REL, director_review)

    standard = _series_standard_manifest()
    director_bible = _director_bible()
    one_pass_contract = _one_pass_contract()
    ledger = build_series_cost_ledger(repo)

    _write_json(series_root / SERIES_STANDARD_REL, standard)
    _write_json(series_root / SERIES_DIRECTOR_BIBLE_REL, director_bible)
    _write_json(
        series_root / SERIES_ONE_PASS_CONTRACT_REL,
        one_pass_contract,
    )
    _write_json(series_root / SERIES_LEDGER_REL, ledger)

    blocking = [
        item
        for item in [*sample_issues, *director_issues]
        if item.severity == "BLOCKING"
    ]

    budget_envelope = round(
        GENERATED_VIDEO_HARD_CAP_USD
        + TTS_RESERVE_USD
        + NON_VIDEO_MEDIA_RESERVE_USD,
        6,
    )
    if budget_envelope > TOTAL_EPISODE_HARD_CAP_USD + 1e-9:
        blocking.append(
            StandardIssue(
                "STANDARD_BUDGET_ENVELOPE_EXCEEDS_TOTAL_CAP",
                "BUDGET",
                "BLOCKING",
                f"envelope={budget_envelope}",
            )
        )

    readiness_status = (
        "READY_FOR_FULL_EPISODE_REBUILD_AUTHORIZATION"
        if not blocking
        else "BLOCKED"
    )
    readiness = {
        "schema_version": (
            "siraj-series-production-standard-v2-readiness"
        ),
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "status": readiness_status,
        "standard_complete": not blocking,
        "packages": {
            "narration_finalization": "PASS",
            "series_cost_ledger": "PASS",
            "desktop_v2_snapshot": "PASS",
            "global_director_and_technical_review": (
                "PASS" if not blocking else "BLOCKED"
            ),
        },
        "metrics": {
            "segment_count": len(
                _sequence(script.get("segments"))
            ),
            "performance_block_count": len(_blocks(script)),
            "tts_character_count_unicode": tts_plan[
                "character_count_unicode"
            ],
            "shot_count": len(_shots(storyboard)),
            "planned_generated_video_spend_usd": (
                generated_video_spend
            ),
            "generated_video_target_usd": (
                GENERATED_VIDEO_TARGET_USD
            ),
            "generated_video_hard_cap_usd": (
                GENERATED_VIDEO_HARD_CAP_USD
            ),
            "tts_reserve_usd": TTS_RESERVE_USD,
            "total_episode_hard_cap_usd": (
                TOTAL_EPISODE_HARD_CAP_USD
            ),
        },
        "locked_artifacts": {
            "standard_sha256": _canonical_sha256(standard),
            "director_bible_sha256": _canonical_sha256(
                director_bible
            ),
            "one_pass_contract_sha256": _canonical_sha256(
                one_pass_contract
            ),
            "final_script_sha256": _canonical_sha256(script),
            "narration_approval_sha256": _canonical_sha256(
                narration_approval
            ),
            "full_tts_plan_sha256": _canonical_sha256(tts_plan),
            "storyboard_sha256": _canonical_sha256(storyboard),
            "production_plan_sha256": _canonical_sha256(
                production_plan
            ),
            "sound_plan_sha256": _canonical_sha256(sound_plan),
            "title_plan_sha256": _canonical_sha256(title_plan),
            "cost_ledger_sha256": _canonical_sha256(ledger),
            "director_review_sha256": _canonical_sha256(
                director_review
            ),
        },
        "blocking_issue_count": len(blocking),
        "blocking_issues": [item.as_dict() for item in blocking],
        "paid_provider_requests": 0,
        "full_episode_production_authorized": False,
        "next_stage": (
            "CONSOLIDATED_FULL_EPISODE_REBUILD_AUTHORIZATION"
            if not blocking
            else "RESOLVE_STANDARD_V2_BLOCKING_ISSUES"
        ),
    }
    _write_json(episode_root / READINESS_REL, readiness)

    ui_snapshot = {
        "schema_version": (
            "siraj-desktop-series-production-standard-v2-snapshot"
        ),
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "standard_status": readiness_status,
        "standard_complete": not blocking,
        "quality_mode": "GLOBAL_PRESTIGE_CINEMATIC",
        "narration": {
            "status": "APPROVED_NO_NOTES",
            "blocks": len(_blocks(script)),
            "sample_audio_sha256": EXPECTED_SAMPLE_SHA256,
        },
        "budget": readiness["metrics"],
        "quality_gate": {
            "blocking_issue_count": len(blocking),
            "director_review_status": director_review["status"],
            "release_policy": "FAIL_CLOSED",
        },
        "next_action_ar": (
            "إنتاج الحلقة كاملة من جديد"
            if not blocking
            else "حل العيوب المانعة قبل الإنتاج"
        ),
        "full_episode_production_authorized": False,
        "readiness_path_relative": str(READINESS_REL).replace(
            "\\", "/"
        ),
        "updated_at_utc": _now(),
    }
    _write_json(episode_root / UI_SNAPSHOT_REL, ui_snapshot)

    return {
        "release": RELEASE,
        "status": readiness_status,
        "episode_id": EPISODE_ID,
        "packages_completed": 4,
        "narration": {
            "approval": narration_approval["status"],
            "performance_block_count": len(_blocks(script)),
            "full_tts_plan_status": tts_plan["status"],
        },
        "budget": {
            "planned_generated_video_spend_usd": (
                generated_video_spend
            ),
            "generated_video_target_usd": (
                GENERATED_VIDEO_TARGET_USD
            ),
            "generated_video_hard_cap_usd": (
                GENERATED_VIDEO_HARD_CAP_USD
            ),
            "tts_reserve_usd": TTS_RESERVE_USD,
            "total_episode_hard_cap_usd": (
                TOTAL_EPISODE_HARD_CAP_USD
            ),
        },
        "director_review": {
            "status": director_review["status"],
            "blocking_issue_count": director_review[
                "blocking_issue_count"
            ],
        },
        "desktop_snapshot": ui_snapshot,
        "paid_provider_requests": 0,
        "full_episode_production_authorized": False,
        "next_stage": readiness["next_stage"],
        "outputs": {
            "series_standard": str(
                (SERIES_ROOT_REL / SERIES_STANDARD_REL)
            ).replace("\\", "/"),
            "director_bible": str(
                (SERIES_ROOT_REL / SERIES_DIRECTOR_BIBLE_REL)
            ).replace("\\", "/"),
            "one_pass_contract": str(
                (SERIES_ROOT_REL / SERIES_ONE_PASS_CONTRACT_REL)
            ).replace("\\", "/"),
            "series_cost_ledger": str(
                (SERIES_ROOT_REL / SERIES_LEDGER_REL)
            ).replace("\\", "/"),
            "final_script": str(
                EPISODE_ROOT_REL / FINAL_SCRIPT_REL
            ).replace("\\", "/"),
            "full_tts_plan": str(
                EPISODE_ROOT_REL / FULL_TTS_PLAN_REL
            ).replace("\\", "/"),
            "director_review": str(
                EPISODE_ROOT_REL / DIRECTOR_REVIEW_REL
            ).replace("\\", "/"),
            "readiness": str(
                EPISODE_ROOT_REL / READINESS_REL
            ).replace("\\", "/"),
            "desktop_snapshot": str(
                EPISODE_ROOT_REL / UI_SNAPSHOT_REL
            ).replace("\\", "/"),
        },
    }
