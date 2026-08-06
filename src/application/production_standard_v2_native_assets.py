"""Production Standard V2 native asset planner and queue builder.

The planner consumes the 70 Luna-certified shot masters and expands them into
provider-level assets without asking a provider to repeat or invent art
direction:

- 137 generated-video clips for 50 video shots.
- 61 still panels for 14 dynamic-still shots.
- 6 locally authored graphics.
- 43 ElevenLabs performance blocks.

Every image/video asset receives a deterministic certification derived from the
Luna master cinematic blueprint. Provider execution remains impossible without
that certification. This module performs no provider network requests.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
from typing import Any, Mapping, Sequence


RELEASE = "SIRAJ_PRODUCTION_STANDARD_V2_NATIVE_ASSET_PIPELINE"
SCHEMA_VERSION = "siraj-production-standard-v2-native-asset-plan-v1"
EPISODE_ID = "episode-001-adam"
GENERATION_ID = "PSV2-ADAM-R1"

EPISODE_ROOT_REL = Path("projects") / EPISODE_ID
CANONICAL_STORYBOARD_REL = (
    EPISODE_ROOT_REL
    / "cinematic/storyboard-and-media-plan-production-standard-v2.json"
)
CERTIFIED_STORYBOARD_REL = (
    EPISODE_ROOT_REL
    / "cinematic/storyboard-and-media-plan-luna-certified-v2.json"
)
TTS_PLAN_REL = (
    EPISODE_ROOT_REL
    / "orchestration/full-episode-tts-execution-plan-production-standard-v2.json"
)
ASSET_PLAN_REL = (
    EPISODE_ROOT_REL
    / "orchestration/production-standard-v2-native-asset-plan-v1.json"
)
MEDIA_QUEUE_REL = (
    EPISODE_ROOT_REL
    / "orchestration/media-production-queue-v1.json"
)
QUEUE_PREVIEW_REL = (
    EPISODE_ROOT_REL
    / "orchestration/media-production-queue-v2-preview.json"
)
LEGACY_QUEUE_ARCHIVE_DIR_REL = (
    EPISODE_ROOT_REL / "orchestration/legacy-v1"
)
GRAPHICS_SPEC_DIR_REL = (
    EPISODE_ROOT_REL
    / "cinematic/production-standard-v2/graphics/specs"
)
ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
SAMPLE_AUDIO_REL = (
    EPISODE_ROOT_REL
    / "audio/tts/samples/VB-001-01-primary-narrator-waqf-v3-sample.mp3"
)
SAMPLE_AUDIO_SHA256 = (
    "e6a3e74cc6c3c1bd5588a10a9c77c7029a3abcf580d4cc48d8dca42adab35e07"
)
SAMPLE_BLOCK_ID = "VB-001-01"

EXPECTED_SHOT_COUNT = 70
EXPECTED_TREATMENTS = {
    "GENERATED_VIDEO": 50,
    "DYNAMIC_STILL_SEQUENCE": 14,
    "AUTHORED_GRAPHICS": 6,
}
EXPECTED_VIDEO_CLIPS = 137
EXPECTED_STILL_PANELS = 61
EXPECTED_GRAPHICS = 6
EXPECTED_TTS_BLOCKS = 43
VIDEO_CLIP_PROVIDER_SECONDS = 8
VIDEO_CLIP_MAXIMUM_USD = 0.24
IMAGE_PANEL_MAXIMUM_USD = 0.04815
SAFE_TECHNICAL_REPAIR_RESERVE_USD = 0.15
EPISODE_HARD_CAP_USD = 40.0

VIDEO_MODEL = "google:veo@3.1-lite"
IMAGE_MODEL = "bytedance:seedream@5.0-pro"

GRAPHIC_TYPES = (
    "ANIMATED_TIMELINE",
    "SOURCE_CARD",
    "RELATION_TREE",
    "COMPARISON",
    "LOCATION_TIME_CARD",
    "ANIMATED_TIMELINE",
)
GRAPHIC_ANIMATIONS = (
    "TIMELINE_PROGRESS",
    "FOCUS_PULL",
    "NODE_REVEAL",
    "SIDE_BY_SIDE_REVEAL",
    "CINEMATIC_REVEAL",
    "TIMELINE_PROGRESS",
)


class ProductionStandardV2AssetError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ProductionStandardV2AssetError(
            f"CANNOT_READ_JSON:{path}:{exc}"
        ) from exc
    if not isinstance(value, dict):
        raise ProductionStandardV2AssetError(
            f"JSON_OBJECT_REQUIRED:{path}"
        )
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
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
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _canonical_sha256(value: Any) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return value
    return ()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _shots(payload: Mapping[str, Any], path: Path) -> list[dict[str, Any]]:
    values = payload.get("shots")
    if not isinstance(values, list) or not all(
        isinstance(item, dict) for item in values
    ):
        raise ProductionStandardV2AssetError(
            f"STORYBOARD_SHOTS_REQUIRED:{path}"
        )
    return values


def _validate_master_certification(
    shot_id: str,
    certification: Any,
    expected_kind: str,
) -> dict[str, Any]:
    if not isinstance(certification, Mapping):
        raise ProductionStandardV2AssetError(
            f"LUNA_MASTER_CERTIFICATION_REQUIRED:{shot_id}"
        )
    value = dict(certification)
    if str(value.get("status") or "") != "PASS":
        raise ProductionStandardV2AssetError(
            f"LUNA_MASTER_CERTIFICATION_NOT_PASS:{shot_id}"
        )
    if int(value.get("final_score", 0) or 0) < 94:
        raise ProductionStandardV2AssetError(
            f"LUNA_MASTER_CERTIFICATION_SCORE_LOW:{shot_id}"
        )
    if list(_sequence(value.get("blocking_flags"))):
        raise ProductionStandardV2AssetError(
            f"LUNA_MASTER_CERTIFICATION_BLOCKED:{shot_id}"
        )
    if str(value.get("prompt_kind") or "") != expected_kind:
        raise ProductionStandardV2AssetError(
            f"LUNA_MASTER_KIND_MISMATCH:{shot_id}:"
            f"{value.get('prompt_kind')}:{expected_kind}"
        )
    positive = _clean(value.get("certified_positive_prompt_en"))
    negative = _clean(value.get("certified_negative_prompt_en"))
    if not positive:
        raise ProductionStandardV2AssetError(
            f"LUNA_MASTER_POSITIVE_PROMPT_REQUIRED:{shot_id}"
        )
    if _text_sha256(positive) != str(
        value.get("positive_prompt_sha256") or ""
    ):
        raise ProductionStandardV2AssetError(
            f"LUNA_MASTER_POSITIVE_HASH_MISMATCH:{shot_id}"
        )
    if _text_sha256(negative) != str(
        value.get("negative_prompt_sha256") or ""
    ):
        raise ProductionStandardV2AssetError(
            f"LUNA_MASTER_NEGATIVE_HASH_MISMATCH:{shot_id}"
        )
    return value


def _chronological_note(
    blueprint: Mapping[str, Any],
    *,
    asset_label: str,
    index: int,
    count: int,
    duration_seconds: float,
) -> str:
    temporal = _clean(blueprint.get("temporal_motion"))
    action = _clean(blueprint.get("action"))
    continuity = _clean(blueprint.get("continuity"))
    start = (index - 1) / count
    end = index / count
    return (
        f" Asset execution segment: {asset_label} {index} of {count}. "
        f"Render only the chronological interval from {start:.3f} to "
        f"{end:.3f} of the approved master action, for "
        f"{duration_seconds:.3f} seconds of final timeline use. "
        "Begin from the exact visual continuity state left by the preceding "
        "asset and end on a usable continuity state for the next asset. "
        "Do not restart, summarize, repeat, or jump ahead. "
        f"Approved temporal motion: {temporal or action}. "
        f"Continuity lock: {continuity}. "
        "All camera, lens, lighting, materials, palette, screen direction, "
        "historical safety, religious safety, and world-continuity decisions "
        "remain exactly as authored in the Luna master."
    )


def _derived_certification(
    master: Mapping[str, Any],
    *,
    shot_id: str,
    asset_id: str,
    kind: str,
    positive_prompt: str,
    index: int,
    count: int,
) -> dict[str, Any]:
    result = deepcopy(dict(master))
    master_positive = _clean(
        master.get("certified_positive_prompt_en")
    )
    master_negative = _clean(
        master.get("certified_negative_prompt_en")
    )
    result.update(
        {
            "schema_version": (
                "siraj-luna-supervised-asset-certification-v1"
            ),
            "status": "PASS",
            "prompt_kind": kind,
            "shot_id": shot_id,
            "asset_id": asset_id,
            "prompt_id": (
                str(master.get("prompt_id") or shot_id)
                + "-"
                + asset_id
            ),
            "authorship": (
                "LUNA_MASTER_DETERMINISTIC_ASSET_DERIVATION"
            ),
            "certified_positive_prompt_en": positive_prompt,
            "certified_negative_prompt_en": master_negative,
            "positive_prompt_sha256": _text_sha256(
                positive_prompt
            ),
            "negative_prompt_sha256": _text_sha256(
                master_negative
            ),
            "source_prompt_sha256": _text_sha256(
                master_positive
            ),
            "asset_derivation": {
                "release": RELEASE,
                "policy": (
                    "DETERMINISTIC_FROM_LUNA_CINEMATIC_BLUEPRINT"
                ),
                "master_prompt_id": str(
                    master.get("prompt_id") or ""
                ),
                "master_luna_response_id": str(
                    master.get("luna_response_id") or ""
                ),
                "master_positive_prompt_sha256": _text_sha256(
                    master_positive
                ),
                "asset_index": index,
                "asset_count": count,
                "no_new_creative_decision": True,
                "provider_execution_without_master": "FORBIDDEN",
            },
            "certified_at_utc": _now(),
        }
    )
    result["asset_derivation"]["derivation_sha256"] = (
        _canonical_sha256(
            {
                "asset_id": asset_id,
                "positive_prompt": positive_prompt,
                "master_prompt_sha256": _text_sha256(
                    master_positive
                ),
                "index": index,
                "count": count,
            }
        )
    )
    return result


def _video_prompt(
    master: Mapping[str, Any],
    *,
    index: int,
    count: int,
    duration_seconds: float,
) -> str:
    positive = _clean(
        master.get("certified_positive_prompt_en")
    )
    blueprint = master.get("cinematic_blueprint")
    blueprint = (
        blueprint if isinstance(blueprint, Mapping) else {}
    )
    return positive + _chronological_note(
        blueprint,
        asset_label="provider video clip",
        index=index,
        count=count,
        duration_seconds=duration_seconds,
    )


def _still_prompt(
    master: Mapping[str, Any],
    *,
    index: int,
    count: int,
    duration_seconds: float,
) -> str:
    positive = _clean(
        master.get("certified_positive_prompt_en")
    )
    positive = re.sub(
        r"\b(?:video|film clip)\s*,?\s*\d+(?:\.\d+)?\s*seconds?\b",
        "single photoreal prestige cinematic still frame",
        positive,
        flags=re.IGNORECASE,
    )
    blueprint = master.get("cinematic_blueprint")
    blueprint = (
        blueprint if isinstance(blueprint, Mapping) else {}
    )
    return (
        positive
        + _chronological_note(
            blueprint,
            asset_label="still-sequence panel",
            index=index,
            count=count,
            duration_seconds=duration_seconds,
        )
        + " Output one still image only, with layered foreground, midground, "
        "and background depth suitable for local multi-axis parallax. "
        "No text, no frame border, no diptych, no contact sheet, and no "
        "multiple moments in one image."
    )


def _source_id_from_shot(shot: Mapping[str, Any]) -> str:
    segments = [
        str(item)
        for item in _sequence(shot.get("segment_ids"))
        if str(item).startswith("SEG-")
    ]
    if segments:
        match = re.search(r"(\d+)$", segments[0])
        if match:
            return f"SRC-{int(match.group(1)):03d}"
    return "SRC-001"


def _graphic_spec(
    shot: Mapping[str, Any],
    *,
    ordinal: int,
) -> dict[str, Any]:
    shot_id = str(shot["shot_id"])
    source_id = _source_id_from_shot(shot)
    certification = shot["luna_prompt_certification_v2"]
    art_ar = _clean(certification.get("art_direction_ar"))
    label = _clean(shot.get("label_ar")) or "لوحة سراج"
    subtitle = art_ar[:176]
    return {
        "schema_version": "siraj-local-graphics-spec-v1",
        "graphic_id": f"GFX-{ordinal:02d}",
        "shot_id": shot_id,
        "graphic_type": GRAPHIC_TYPES[ordinal - 1],
        "duration_seconds": float(
            shot.get("editorial_duration_seconds", 8.0)
        ),
        "title_ar": label[:120],
        "subtitle_ar": subtitle,
        "items": [
            {
                "item_id": "GI-01",
                "label_ar": label[:80],
                "secondary_ar": "",
                "value_ar": "",
                "source_ids": [source_id],
                "x": 0.5,
                "y": 0.5,
                "parent_item_id": "",
            }
        ],
        "source_ids": [source_id],
        "animation_style": GRAPHIC_ANIMATIONS[ordinal - 1],
        "background": {
            "mode": "GRADIENT",
            "image_url": "",
            "overlay_opacity": 0.82,
        },
        "design": {
            "font_family": "Noto Naskh Arabic",
            "accent_hex": "#C6A15B",
            "foreground_hex": "#F1E7D0",
            "background_hex": "#151414",
            "safe_margin_px": 108,
        },
        "music": "FORBIDDEN",
        "sound_policy": "SFX_ONLY_NO_MUSIC",
        "luna_art_direction": {
            "status": "PASS",
            "prompt_id": str(
                certification.get("prompt_id") or ""
            ),
            "luna_response_id": str(
                certification.get("luna_response_id") or ""
            ),
            "art_direction_ar": art_ar,
            "cinematic_blueprint": deepcopy(
                certification.get("cinematic_blueprint") or {}
            ),
        },
    }


def _archive_legacy_queue(repo: Path, queue_path: Path) -> str | None:
    if not queue_path.is_file():
        return None
    current = _read(queue_path)
    if str(current.get("production_generation_id") or "") == (
        GENERATION_ID
    ):
        return None
    target_dir = repo / LEGACY_QUEUE_ARCHIVE_DIR_REL
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / (
        "media-production-queue-before-"
        + GENERATION_ID.lower()
        + ".json"
    )
    if not target.is_file():
        shutil.copy2(queue_path, target)
    return str(target.relative_to(repo)).replace("\\", "/")


def _reuse_approved_sample(
    repo: Path,
    item: dict[str, Any],
) -> None:
    if str(item.get("block_id") or "") != SAMPLE_BLOCK_ID:
        return
    source = repo / SAMPLE_AUDIO_REL
    if not source.is_file() or _sha256(source) != SAMPLE_AUDIO_SHA256:
        return
    output = repo / str(item["output_path_relative"])
    output.parent.mkdir(parents=True, exist_ok=True)
    if not output.is_file() or _sha256(output) != SAMPLE_AUDIO_SHA256:
        shutil.copy2(source, output)
    receipt = (
        repo
        / EPISODE_ROOT_REL
        / "orchestration/media-execution/receipts/"
        / f"{item['queue_id']}-attempt-01-receipt.json"
    )
    _write(
        receipt,
        {
            "schema_version": (
                "siraj-approved-tts-sample-reuse-receipt-v1"
            ),
            "release": RELEASE,
            "production_generation_id": GENERATION_ID,
            "queue_id": item["queue_id"],
            "block_id": SAMPLE_BLOCK_ID,
            "status": "COMPLETE",
            "provider": "ELEVENLABS",
            "reuse_source": str(SAMPLE_AUDIO_REL).replace(
                "\\", "/"
            ),
            "actual_cost_usd": 0.0,
            "estimated_cost_usd": 0.0,
            "historical_paid_sample": True,
            "output_path_relative": item[
                "output_path_relative"
            ],
            "output_sha256": SAMPLE_AUDIO_SHA256,
            "human_review": "APPROVED_NO_NOTES",
            "completed_at_utc": _now(),
        },
    )
    item.update(
        {
            "status": "COMPLETE",
            "actual_cost_usd": 0.0,
            "estimated_cost_usd": 0.0,
            "output_sha256": SAMPLE_AUDIO_SHA256,
            "receipt_path_relative": str(
                receipt.relative_to(repo)
            ).replace("\\", "/"),
            "approved_sample_reused": True,
            "completed_at_utc": _now(),
        }
    )


def build_native_asset_plan(
    repo_root: Path,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    canonical_path = repo / CANONICAL_STORYBOARD_REL
    certified_path = repo / CERTIFIED_STORYBOARD_REL
    tts_path = repo / TTS_PLAN_REL
    canonical = _read(canonical_path)
    certified = _read(certified_path)
    tts_plan = _read(tts_path)
    source_shots = _shots(canonical, canonical_path)
    target_shots = _shots(certified, certified_path)
    if len(source_shots) != EXPECTED_SHOT_COUNT:
        raise ProductionStandardV2AssetError(
            f"CANONICAL_SHOT_COUNT_INVALID:{len(source_shots)}"
        )
    if len(target_shots) != EXPECTED_SHOT_COUNT:
        raise ProductionStandardV2AssetError(
            f"CERTIFIED_SHOT_COUNT_INVALID:{len(target_shots)}"
        )
    source_by_id = {
        str(item.get("shot_id") or ""): item
        for item in source_shots
    }
    if {
        str(item.get("shot_id") or "")
        for item in target_shots
    } != set(source_by_id):
        raise ProductionStandardV2AssetError(
            "CERTIFIED_STORYBOARD_SHOT_ID_DRIFT"
        )

    treatment_counts = {
        key: 0 for key in EXPECTED_TREATMENTS
    }
    image_items: list[dict[str, Any]] = []
    video_items: list[dict[str, Any]] = []
    graphics_items: list[dict[str, Any]] = []
    assemblies: list[dict[str, Any]] = []
    graphics_specs: list[dict[str, Any]] = []

    asset_order = 0
    graphic_ordinal = 0
    total_video_timeline_seconds = 0.0
    total_episode_seconds = 0.0

    for target in sorted(
        target_shots,
        key=lambda item: int(item.get("queue_index", 0)),
    ):
        shot_id = str(target.get("shot_id") or "")
        canonical_shot = source_by_id[shot_id]
        treatment = str(
            canonical_shot.get("final_budget_treatment") or ""
        )
        if treatment not in treatment_counts:
            raise ProductionStandardV2AssetError(
                f"SHOT_TREATMENT_INVALID:{shot_id}:{treatment}"
            )
        if str(target.get("final_budget_treatment") or "") != (
            treatment
        ):
            raise ProductionStandardV2AssetError(
                f"CERTIFIED_TREATMENT_DRIFT:{shot_id}"
            )
        treatment_counts[treatment] += 1
        duration = float(
            canonical_shot.get(
                "editorial_duration_seconds",
                canonical_shot.get("planned_seconds", 0),
            )
            or 0
        )
        if duration <= 0:
            raise ProductionStandardV2AssetError(
                f"SHOT_DURATION_INVALID:{shot_id}"
            )
        total_episode_seconds += duration
        sequence_id = str(
            canonical_shot.get("sequence_id") or ""
        )
        queue_index = int(
            canonical_shot.get("queue_index", 0) or 0
        )
        assembly_assets: list[dict[str, Any]] = []

        if treatment == "GENERATED_VIDEO":
            master = _validate_master_certification(
                shot_id,
                target.get("luna_prompt_certification_v2"),
                "VIDEO_GENERATION",
            )
            clip_count = int(
                canonical_shot.get("provider_clip_count", 0)
                or 0
            )
            provider_seconds = int(
                canonical_shot.get(
                    "provider_clip_seconds",
                    VIDEO_CLIP_PROVIDER_SECONDS,
                )
                or VIDEO_CLIP_PROVIDER_SECONDS
            )
            planned = float(
                canonical_shot.get(
                    "planned_generated_video_seconds",
                    duration,
                )
                or duration
            )
            if (
                clip_count <= 0
                or provider_seconds != VIDEO_CLIP_PROVIDER_SECONDS
                or math.ceil(planned / provider_seconds)
                != clip_count
            ):
                raise ProductionStandardV2AssetError(
                    f"VIDEO_CLIP_PLAN_INVALID:{shot_id}"
                )
            remaining = planned
            for index in range(1, clip_count + 1):
                asset_order += 1
                timeline_seconds = min(
                    float(provider_seconds),
                    remaining,
                )
                remaining = round(
                    remaining - timeline_seconds,
                    6,
                )
                asset_id = f"{shot_id}-C{index:02d}"
                prompt = _video_prompt(
                    master,
                    index=index,
                    count=clip_count,
                    duration_seconds=timeline_seconds,
                )
                certification = _derived_certification(
                    master,
                    shot_id=shot_id,
                    asset_id=asset_id,
                    kind="VIDEO_GENERATION",
                    positive_prompt=prompt,
                    index=index,
                    count=clip_count,
                )
                output = (
                    EPISODE_ROOT_REL
                    / "cinematic/production-standard-v2/video"
                    / shot_id
                    / f"clip-{index:02d}.mp4"
                )
                item = {
                    "queue_id": f"VID-{shot_id}-C{index:02d}",
                    "queue_index": asset_order,
                    "shot_queue_index": queue_index,
                    "shot_id": shot_id,
                    "asset_id": asset_id,
                    "asset_index": index,
                    "asset_count": clip_count,
                    "treatment": treatment,
                    "sequence_id": sequence_id,
                    "timeline_duration_seconds": timeline_seconds,
                    "provider_duration_seconds": provider_seconds,
                    "selected_model": VIDEO_MODEL,
                    "provider": "RUNWARE",
                    "status": (
                        "READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED"
                    ),
                    "maximum_authorized_usd": (
                        VIDEO_CLIP_MAXIMUM_USD
                    ),
                    "output_path_relative": str(output).replace(
                        "\\", "/"
                    ),
                    "hidden_paid_retry": "FORBIDDEN",
                    "automatic_resubmission": "FORBIDDEN",
                    "production_generation_id": GENERATION_ID,
                    "luna_prompt_certification_v2": certification,
                    "task_draft": {
                        "taskType": "videoInference",
                        "model": VIDEO_MODEL,
                        "duration": provider_seconds,
                        "width": 1280,
                        "height": 720,
                        "numberResults": 1,
                        "deliveryMethod": "async",
                        "includeCost": True,
                        "positivePrompt": prompt,
                        "negativePrompt": certification[
                            "certified_negative_prompt_en"
                        ],
                        "providerSettings": {
                            "google": {
                                "generateAudio": False,
                                "personGeneration": "dont_allow",
                            }
                        },
                    },
                }
                video_items.append(item)
                assembly_assets.append(
                    {
                        "queue_id": item["queue_id"],
                        "asset_id": asset_id,
                        "asset_index": index,
                        "timeline_duration_seconds": (
                            timeline_seconds
                        ),
                        "output_path_relative": item[
                            "output_path_relative"
                        ],
                    }
                )
            if abs(remaining) > 1e-6:
                raise ProductionStandardV2AssetError(
                    f"VIDEO_TIMELINE_REMAINDER:{shot_id}:{remaining}"
                )
            total_video_timeline_seconds += planned

        elif treatment == "DYNAMIC_STILL_SEQUENCE":
            master = _validate_master_certification(
                shot_id,
                target.get("luna_prompt_certification_v2"),
                "IMAGE_GENERATION",
            )
            panel_count = int(
                canonical_shot.get("still_panel_count", 0)
                or 0
            )
            maximum_panel = float(
                canonical_shot.get(
                    "maximum_still_panel_seconds",
                    7.0,
                )
                or 7.0
            )
            if panel_count <= 0:
                raise ProductionStandardV2AssetError(
                    f"STILL_PANEL_COUNT_INVALID:{shot_id}"
                )
            base_duration = duration / panel_count
            if base_duration > maximum_panel + 1e-6:
                raise ProductionStandardV2AssetError(
                    f"STILL_PANEL_DURATION_EXCEEDS_MAX:{shot_id}"
                )
            allocated = 0.0
            for index in range(1, panel_count + 1):
                asset_order += 1
                panel_duration = (
                    duration - allocated
                    if index == panel_count
                    else round(base_duration, 6)
                )
                allocated = round(
                    allocated + panel_duration,
                    6,
                )
                asset_id = f"{shot_id}-P{index:02d}"
                prompt = _still_prompt(
                    master,
                    index=index,
                    count=panel_count,
                    duration_seconds=panel_duration,
                )
                certification = _derived_certification(
                    master,
                    shot_id=shot_id,
                    asset_id=asset_id,
                    kind="IMAGE_GENERATION",
                    positive_prompt=prompt,
                    index=index,
                    count=panel_count,
                )
                output = (
                    EPISODE_ROOT_REL
                    / "cinematic/production-standard-v2/stills"
                    / shot_id
                    / f"panel-{index:02d}.jpg"
                )
                item = {
                    "queue_id": f"IMG-{shot_id}-P{index:02d}",
                    "queue_index": asset_order,
                    "shot_queue_index": queue_index,
                    "shot_id": shot_id,
                    "asset_id": asset_id,
                    "asset_index": index,
                    "asset_count": panel_count,
                    "treatment": treatment,
                    "sequence_id": sequence_id,
                    "timeline_duration_seconds": panel_duration,
                    "selected_model": IMAGE_MODEL,
                    "provider": "RUNWARE",
                    "status": (
                        "READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED"
                    ),
                    "maximum_authorized_usd": (
                        IMAGE_PANEL_MAXIMUM_USD
                    ),
                    "output_path_relative": str(output).replace(
                        "\\", "/"
                    ),
                    "hidden_paid_retry": "FORBIDDEN",
                    "automatic_resubmission": "FORBIDDEN",
                    "production_generation_id": GENERATION_ID,
                    "luna_prompt_certification_v2": certification,
                    "task_draft": {
                        "taskType": "imageInference",
                        "model": IMAGE_MODEL,
                        "width": 1424,
                        "height": 800,
                        "numberResults": 1,
                        "outputType": "URL",
                        "outputFormat": "JPG",
                        "includeCost": True,
                        "positivePrompt": prompt,
                        "negativePrompt": certification[
                            "certified_negative_prompt_en"
                        ],
                        "sirajRouting": {
                            "release": RELEASE,
                            "role": "DYNAMIC_STILL_PANEL",
                            "panel_index": index,
                            "panel_count": panel_count,
                        },
                    },
                }
                image_items.append(item)
                assembly_assets.append(
                    {
                        "queue_id": item["queue_id"],
                        "asset_id": asset_id,
                        "asset_index": index,
                        "timeline_duration_seconds": (
                            panel_duration
                        ),
                        "output_path_relative": item[
                            "output_path_relative"
                        ],
                    }
                )
            if abs(allocated - duration) > 1e-4:
                raise ProductionStandardV2AssetError(
                    f"STILL_TIMELINE_ALLOCATION_INVALID:{shot_id}"
                )

        else:
            graphic_ordinal += 1
            master = _validate_master_certification(
                shot_id,
                target.get("luna_prompt_certification_v2"),
                "LOCAL_GRAPHICS_ART_DIRECTION",
            )
            asset_order += 1
            spec = _graphic_spec(
                target,
                ordinal=graphic_ordinal,
            )
            graphics_specs.append(spec)
            spec_path = (
                GRAPHICS_SPEC_DIR_REL
                / f"{spec['graphic_id']}.json"
            )
            output = (
                EPISODE_ROOT_REL
                / "cinematic/production-standard-v2/graphics"
                / f"{spec['graphic_id']}.mp4"
            )
            item = {
                "queue_id": f"LOCAL-{shot_id}",
                "queue_index": asset_order,
                "shot_queue_index": queue_index,
                "shot_id": shot_id,
                "asset_id": f"{shot_id}-G01",
                "asset_index": 1,
                "asset_count": 1,
                "treatment": treatment,
                "sequence_id": sequence_id,
                "timeline_duration_seconds": duration,
                "graphic_id": spec["graphic_id"],
                "graphic_type": spec["graphic_type"],
                "spec_path_relative": str(spec_path).replace(
                    "\\", "/"
                ),
                "output_path_relative": str(output).replace(
                    "\\", "/"
                ),
                "status": "READY_LOCAL_RENDER",
                "maximum_authorized_usd": 0.0,
                "actual_cost_usd": 0.0,
                "provider": "LOCAL",
                "renderer": "PYSIDE6_QT_QUICK_QML_FFMPEG",
                "production_generation_id": GENERATION_ID,
                "luna_prompt_certification_v2": deepcopy(
                    master
                ),
            }
            graphics_items.append(item)
            assembly_assets.append(
                {
                    "queue_id": item["queue_id"],
                    "asset_id": item["asset_id"],
                    "asset_index": 1,
                    "timeline_duration_seconds": duration,
                    "output_path_relative": item[
                        "output_path_relative"
                    ],
                }
            )

        assemblies.append(
            {
                "shot_id": shot_id,
                "queue_index": queue_index,
                "sequence_id": sequence_id,
                "treatment": treatment,
                "duration_seconds": duration,
                "motion_profile": str(
                    canonical_shot.get("motion_profile") or ""
                ),
                "assets": assembly_assets,
                "output_path_relative": str(
                    EPISODE_ROOT_REL
                    / "cinematic/production-standard-v2/shot-clips"
                    / f"{shot_id}.mp4"
                ).replace("\\", "/"),
            }
        )

    if treatment_counts != EXPECTED_TREATMENTS:
        raise ProductionStandardV2AssetError(
            "TREATMENT_COUNTS_INVALID:"
            + json.dumps(treatment_counts, sort_keys=True)
        )
    if len(video_items) != EXPECTED_VIDEO_CLIPS:
        raise ProductionStandardV2AssetError(
            f"VIDEO_CLIP_COUNT_INVALID:{len(video_items)}"
        )
    if len(image_items) != EXPECTED_STILL_PANELS:
        raise ProductionStandardV2AssetError(
            f"STILL_PANEL_COUNT_INVALID:{len(image_items)}"
        )
    if len(graphics_items) != EXPECTED_GRAPHICS:
        raise ProductionStandardV2AssetError(
            f"GRAPHICS_COUNT_INVALID:{len(graphics_items)}"
        )
    if len(assemblies) != EXPECTED_SHOT_COUNT:
        raise ProductionStandardV2AssetError(
            f"ASSEMBLY_COUNT_INVALID:{len(assemblies)}"
        )
    if abs(total_episode_seconds - 1320.0) > 1e-6:
        raise ProductionStandardV2AssetError(
            f"EPISODE_DURATION_INVALID:{total_episode_seconds}"
        )
    if abs(total_video_timeline_seconds - 891.0) > 1e-6:
        raise ProductionStandardV2AssetError(
            f"VIDEO_TIMELINE_SECONDS_INVALID:{total_video_timeline_seconds}"
        )

    tts_values = [
        dict(item)
        for item in _sequence(tts_plan.get("queue"))
        if isinstance(item, Mapping)
    ]
    if len(tts_values) != EXPECTED_TTS_BLOCKS:
        raise ProductionStandardV2AssetError(
            f"TTS_BLOCK_COUNT_INVALID:{len(tts_values)}"
        )
    tts_items: list[dict[str, Any]] = []
    for offset, source in enumerate(tts_values, start=1):
        item = {
            "queue_id": str(source.get("queue_id") or ""),
            "queue_index": asset_order + offset,
            "block_id": str(source.get("block_id") or ""),
            "segment_id": str(source.get("segment_id") or ""),
            "voice_slot": str(
                source.get("speaker_key") or "NARRATOR"
            ),
            "voice_id": str(source.get("voice_id") or ""),
            "model_id": str(source.get("model_id") or ""),
            "voice_settings": dict(
                source.get("voice_settings") or {}
            ),
            "text_ar": str(source.get("text_ar") or ""),
            "pause_before_ms": int(
                source.get("pause_before_ms", 0) or 0
            ),
            "pause_after_ms": int(
                source.get("pause_after_ms", 0) or 0
            ),
            "status": (
                "READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED"
            ),
            "maximum_authorized_usd": float(
                source.get("internal_reserve_share_usd", 0)
                or 0
            ),
            "output_path_relative": str(
                source.get("output_path_relative") or ""
            ),
            "hidden_paid_retry": "FORBIDDEN",
            "automatic_resubmission": "FORBIDDEN",
            "production_generation_id": GENERATION_ID,
        }
        if not item["queue_id"] or not item["block_id"]:
            raise ProductionStandardV2AssetError(
                "TTS_QUEUE_ID_AND_BLOCK_ID_REQUIRED"
            )
        tts_items.append(item)

    video_maximum = round(
        sum(
            float(item["maximum_authorized_usd"])
            for item in video_items
        ),
        6,
    )
    image_maximum = round(
        sum(
            float(item["maximum_authorized_usd"])
            for item in image_items
        ),
        6,
    )
    tts_maximum = round(
        sum(
            float(item["maximum_authorized_usd"])
            for item in tts_items
        ),
        6,
    )
    paid_maximum = round(
        video_maximum + image_maximum + tts_maximum,
        6,
    )
    consolidated_maximum = round(
        paid_maximum + SAFE_TECHNICAL_REPAIR_RESERVE_USD,
        6,
    )
    if consolidated_maximum > EPISODE_HARD_CAP_USD:
        raise ProductionStandardV2AssetError(
            "NATIVE_V2_PLAN_EXCEEDS_EPISODE_HARD_CAP:"
            f"{consolidated_maximum:.6f}"
        )

    plan: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "release": RELEASE,
        "status": "READY_EXPLICIT_CONSOLIDATED_AUTHORIZATION",
        "episode_id": EPISODE_ID,
        "production_generation_id": GENERATION_ID,
        "shot_count": EXPECTED_SHOT_COUNT,
        "treatment_counts": treatment_counts,
        "asset_counts": {
            "runware_images": len(image_items),
            "runware_videos": len(video_items),
            "local_graphics": len(graphics_items),
            "elevenlabs_tts": len(tts_items),
            "provider_visual_assets": (
                len(image_items) + len(video_items)
            ),
            "total_queue_items": (
                len(image_items)
                + len(video_items)
                + len(graphics_items)
                + len(tts_items)
            ),
        },
        "timeline": {
            "episode_seconds": round(
                total_episode_seconds, 6
            ),
            "generated_video_seconds": round(
                total_video_timeline_seconds, 6
            ),
            "dynamic_still_seconds": round(
                sum(
                    float(item["duration_seconds"])
                    for item in assemblies
                    if item["treatment"]
                    == "DYNAMIC_STILL_SEQUENCE"
                ),
                6,
            ),
        },
        "budget": {
            "runware_video_maximum_usd": video_maximum,
            "runware_image_maximum_usd": image_maximum,
            "tts_maximum_usd": tts_maximum,
            "safe_technical_repair_reserve_usd": (
                SAFE_TECHNICAL_REPAIR_RESERVE_USD
            ),
            "pending_media_maximum_usd": paid_maximum,
            "consolidated_maximum_authorized_usd": (
                consolidated_maximum
            ),
            "episode_hard_cap_usd": EPISODE_HARD_CAP_USD,
            "historical_legacy_spend": (
                "REPORTED_SEPARATELY_NOT_CHARGED_TO_GENERATION_CAP"
            ),
        },
        "prompt_direction": {
            "master_luna_certifications": EXPECTED_SHOT_COUNT,
            "derived_video_certifications": len(video_items),
            "derived_image_certifications": len(image_items),
            "derivation_policy": (
                "DETERMINISTIC_FROM_LUNA_CINEMATIC_BLUEPRINT"
            ),
            "additional_luna_requests_required": 0,
            "provider_execution_without_certification": "FORBIDDEN",
        },
        "shot_assemblies": assemblies,
        "queues": {
            "runware_images": image_items,
            "runware_videos": video_items,
            "local_graphics": graphics_items,
            "elevenlabs_tts": tts_items,
        },
        "graphics_specs": graphics_specs,
        "automatic_paid_retry": "FORBIDDEN",
        "hidden_paid_retry": "FORBIDDEN",
        "created_at_utc": _now(),
    }
    plan["plan_sha256"] = _canonical_sha256(plan)
    return plan


def materialize_native_media_queue(
    repo_root: Path,
    *,
    live: bool = True,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    plan = build_native_asset_plan(repo)
    for spec in plan["graphics_specs"]:
        path = (
            repo
            / GRAPHICS_SPEC_DIR_REL
            / f"{spec['graphic_id']}.json"
        )
        _write(path, spec)

    queues = deepcopy(plan["queues"])
    legacy_archive = None
    queue_path = repo / MEDIA_QUEUE_REL
    if live:
        legacy_archive = _archive_legacy_queue(
            repo,
            queue_path,
        )
        for item in queues["elevenlabs_tts"]:
            _reuse_approved_sample(repo, item)

    pending_maximum = round(
        sum(
            float(item.get("maximum_authorized_usd", 0))
            for collection in (
                "runware_images",
                "runware_videos",
                "elevenlabs_tts",
            )
            for item in queues[collection]
            if str(item.get("status") or "") != "COMPLETE"
        ),
        6,
    )
    queue = {
        "schema_version": (
            "siraj-media-production-queue-production-standard-v2-native"
        ),
        "release": RELEASE,
        "status": "MEDIA_QUEUE_READY",
        "episode_id": EPISODE_ID,
        "production_generation_id": GENERATION_ID,
        "source_plan_relative": str(ASSET_PLAN_REL).replace(
            "\\", "/"
        ),
        "source_plan_sha256": plan["plan_sha256"],
        "queues": queues,
        "counts": {
            "runware_images": len(queues["runware_images"]),
            "runware_videos": len(queues["runware_videos"]),
            "local_graphics": len(queues["local_graphics"]),
            "elevenlabs_tts_segments": len(
                queues["elevenlabs_tts"]
            ),
            "elevenlabs_voice_performers_used": 1,
            "elevenlabs_multi_performer_required": False,
        },
        "budget_preflight": {
            **plan["budget"],
            "pending_media_maximum_usd": pending_maximum,
            "consolidated_maximum_authorized_usd": round(
                pending_maximum
                + SAFE_TECHNICAL_REPAIR_RESERVE_USD,
                6,
            ),
        },
        "execution_policy": {
            "one_lock_and_receipt_per_asset": True,
            "sequential_execution": True,
            "hidden_paid_retry": "FORBIDDEN",
            "automatic_paid_retry": "FORBIDDEN",
            "explicit_consolidated_authorization_required": True,
        },
        "shot_assemblies": deepcopy(
            plan["shot_assemblies"]
        ),
        "legacy_queue_archive_relative": legacy_archive,
        "created_at_utc": _now(),
    }
    queue["queue_sha256"] = _canonical_sha256(queue)

    _write(repo / ASSET_PLAN_REL, plan)
    _write(repo / QUEUE_PREVIEW_REL, queue)
    if live:
        _write(queue_path, queue)
        state_path = repo / ORCHESTRATOR_STATE_REL
        state = _read(state_path)
        state.update(
            {
                "current_episode_id": EPISODE_ID,
                "status": "MEDIA_QUEUE_READY",
                "stage": "BUDGET_PREFLIGHT",
                "next_stage": (
                    "CONSOLIDATED_PRODUCTION_STANDARD_V2_EXECUTION"
                ),
                "production_generation_id": GENERATION_ID,
                "media_queue_path_relative": str(
                    MEDIA_QUEUE_REL
                ).replace("\\", "/"),
                "full_episode_production_authorized": False,
                "last_error": None,
                "updated_at_utc": _now(),
            }
        )
        _write(state_path, state)
    return queue


def inspect_native_execution_plan(
    repo_root: Path,
) -> dict[str, Any]:
    repo = repo_root.resolve()
    queue_path = repo / MEDIA_QUEUE_REL
    if (
        not queue_path.is_file()
        or str(
            _read(queue_path).get(
                "production_generation_id"
            )
            or ""
        )
        != GENERATION_ID
    ):
        queue = materialize_native_media_queue(
            repo,
            live=False,
        )
    else:
        queue = _read(queue_path)

    queues = queue.get("queues")
    if not isinstance(queues, Mapping):
        raise ProductionStandardV2AssetError(
            "MEDIA_QUEUE_COLLECTIONS_REQUIRED"
        )
    pending_maximum = round(
        sum(
            float(item.get("maximum_authorized_usd", 0))
            for key in (
                "runware_images",
                "runware_videos",
                "elevenlabs_tts",
            )
            for item in _sequence(queues.get(key))
            if isinstance(item, Mapping)
            and str(item.get("status") or "") != "COMPLETE"
        ),
        6,
    )
    return {
        "status": (
            "READY_FOR_CONSOLIDATED_V2_EXECUTION_AUTHORIZATION"
        ),
        "episode_id": EPISODE_ID,
        "production_generation_id": GENERATION_ID,
        "generated_video_maximum_usd": round(
            sum(
                float(item.get("maximum_authorized_usd", 0))
                for item in _sequence(
                    queues.get("runware_videos")
                )
                if isinstance(item, Mapping)
                and str(item.get("status") or "")
                != "COMPLETE"
            ),
            6,
        ),
        "image_maximum_usd": round(
            sum(
                float(item.get("maximum_authorized_usd", 0))
                for item in _sequence(
                    queues.get("runware_images")
                )
                if isinstance(item, Mapping)
                and str(item.get("status") or "")
                != "COMPLETE"
            ),
            6,
        ),
        "tts_maximum_usd": round(
            sum(
                float(item.get("maximum_authorized_usd", 0))
                for item in _sequence(
                    queues.get("elevenlabs_tts")
                )
                if isinstance(item, Mapping)
                and str(item.get("status") or "")
                != "COMPLETE"
            ),
            6,
        ),
        "safe_repair_reserve_usd": (
            SAFE_TECHNICAL_REPAIR_RESERVE_USD
        ),
        "pending_media_maximum_usd": pending_maximum,
        "consolidated_maximum_usd": round(
            pending_maximum
            + SAFE_TECHNICAL_REPAIR_RESERVE_USD,
            6,
        ),
        "episode_hard_cap_usd": EPISODE_HARD_CAP_USD,
        "counts": dict(queue.get("counts") or {}),
        "queue_sha256": str(
            queue.get("queue_sha256") or ""
        ),
    }
