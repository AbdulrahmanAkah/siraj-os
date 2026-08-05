from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.application.artifact_dependency_graph_v1 import canonical_sha256
from src.application.episode_cost_ledger_v1 import scan_episode_costs
from src.application.local_graphics_spec_v1 import (
    LocalGraphicsSpec,
    LocalGraphicsSpecError,
    extract_storyboard_graphics_specs,
    validate_graphics_spec,
)
from src.application.runware_image_model_routing_v1 import (
    build_runware_image_task,
    route_image_shot,
)

RELEASE = "GRAPHICS_STORYBOARD_INTEGRATION_AND_MEDIA_QUEUE_V1"

ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
EVIDENCE_REL = Path("research/evidence-package-v1.json")
SCRIPT_REL = Path("script/episode-script-v1.json")
STORYBOARD_REL = Path("cinematic/storyboard-and-media-plan-v1.json")
STORYBOARD_BACKUP_REL = Path(
    "cinematic/storyboard-and-media-plan-v1.pre-graphics-integration.json"
)
GRAPHICS_SPEC_DIR_REL = Path("cinematic/graphics/specs")
GRAPHICS_OUTPUT_DIR_REL = Path("cinematic/graphics/outputs")
MEDIA_QUEUE_REL = Path("orchestration/media-production-queue-v1.json")
BUDGET_PREFLIGHT_REL = Path("orchestration/budget-preflight-v1.json")
INTEGRATION_STATE_REL = Path(
    "orchestration/graphics-storyboard-media-queue-state-v1.json"
)
STAGE_LEDGER_REL = Path("orchestration/stage-ledger-v1.json")
DEPENDENCY_GRAPH_REL = Path(
    "orchestration/artifact-dependency-graph-v1.json"
)
EDITORIAL_RUNNER_STATE_REL = Path(
    "orchestration/editorial-runner-state-v1.json"
)

EPISODE_HARD_CAP_USD = 40.0
IMAGE_MAX_AUTHORIZED_USD = 0.15
VIDEO_MAX_AUTHORIZED_USD = 0.40
TTS_TOTAL_MAX_AUTHORIZED_USD = 3.00
LOCAL_GRAPHICS_API_COST_USD = 0.0

VIDEO_MODEL = "google:veo@3.1-lite"
VIDEO_WIDTH = 1280
VIDEO_HEIGHT = 720
VIDEO_DURATION_SECONDS = 8

TYPE_TERMS = {
    "MAP_ROUTE": (
        "map", "route", "journey", "migration", "location",
        "خريطة", "مسار", "رحلة", "هجرة", "موقع", "انتقل",
    ),
    "RELATION_TREE": (
        "genealogy", "lineage", "family", "father", "son", "tribe",
        "نسب", "سلالة", "عائلة", "والد", "ابن", "قبيلة", "علاقة",
    ),
    "COMPARISON": (
        "compare", "comparison", "difference", "views",
        "مقارنة", "الفرق", "روايتان", "قولان", "رأيان", "اختلاف",
    ),
    "SOURCE_CARD": (
        "source", "book", "reference", "hadith", "verse",
        "مصدر", "كتاب", "مرجع", "حديث", "آية", "إسناد",
    ),
    "ANIMATED_TIMELINE": (
        "timeline", "chronology", "sequence", "stages", "year",
        "زمني", "تسلسل", "مراحل", "سنة", "فترة", "ترتيب",
    ),
}
DEFAULT_TYPES = (
    "ANIMATED_TIMELINE",
    "SOURCE_CARD",
    "LOCATION_TIME_CARD",
    "COMPARISON",
    "ANIMATED_TIMELINE",
    "SOURCE_CARD",
)
ANIMATION_BY_TYPE = {
    "ANIMATED_TIMELINE": "TIMELINE_PROGRESS",
    "MAP_ROUTE": "ROUTE_DRAW",
    "RELATION_TREE": "NODE_REVEAL",
    "SOURCE_CARD": "FOCUS_PULL",
    "COMPARISON": "SIDE_BY_SIDE_REVEAL",
    "LOCATION_TIME_CARD": "CINEMATIC_REVEAL",
}
HUMAN_TERMS = (
    "person", "people", "human", "man", "woman", "child", "crowd",
    "traveler", "soldier", "merchant", "شخص", "أشخاص", "إنسان",
    "رجل", "امرأة", "طفل", "حشد", "مسافر", "جندي", "تاجر",
)


class GraphicsMediaQueueError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GraphicsMediaQueueResult:
    episode_id: str
    storyboard_path: Path
    media_queue_path: Path
    budget_preflight_path: Path
    graphics_spec_paths: tuple[Path, ...]
    image_count: int
    video_count: int
    graphics_count: int
    tts_segment_count: int
    seedream_count: int
    nano_banana_count: int
    reserved_max_usd: float
    recorded_total_usd: float
    projected_total_usd: float
    tts_voice_selection_required: bool
    status: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GraphicsMediaQueueError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise GraphicsMediaQueueError(f"JSON_OBJECT_REQUIRED:{path}")
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


def _hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _rel(repo: Path, path: Path) -> str:
    return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")


def _seq(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value, (str, bytes, bytearray)
    ):
        return value
    return ()


def _clip(value: Any, maximum: int) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text if len(text) <= maximum else text[: maximum - 1].rstrip() + "…"


def _current(repo: Path) -> tuple[str, dict[str, Any], Path]:
    state_path = repo.resolve() / ORCHESTRATOR_STATE_REL
    state = _read(state_path)
    episode_id = state.get("current_episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        raise GraphicsMediaQueueError("CURRENT_EPISODE_REQUIRED_FOR_MEDIA_QUEUE")
    allowed = {
        "EDITORIAL_PIPELINE_COMPLETE_BUDGET_PREFLIGHT_QUEUED",
        "GRAPHICS_MEDIA_QUEUE_FAILED",
        "MEDIA_QUEUE_READY",
        "RUNWARE_IMAGE_GENERATION_QUEUED",
    }
    status = str(state.get("status", ""))
    if status not in allowed:
        raise GraphicsMediaQueueError(
            f"GRAPHICS_MEDIA_QUEUE_NOT_ALLOWED:{status}"
        )
    root = repo.resolve() / "projects" / episode_id
    if not root.is_dir():
        raise GraphicsMediaQueueError(
            f"CURRENT_EPISODE_DIRECTORY_MISSING:{episode_id}"
        )
    return episode_id, state, root


def _sources(evidence: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for source in _seq(evidence.get("source_register")):
        if isinstance(source, Mapping):
            source_id = str(source.get("source_id", "")).strip()
            if source_id:
                result[source_id] = dict(source)
    if not result:
        raise GraphicsMediaQueueError("EVIDENCE_SOURCE_REGISTER_REQUIRED")
    return result


def _segments(script: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    result = {}
    for segment in _seq(script.get("segments")):
        if isinstance(segment, Mapping):
            segment_id = str(segment.get("segment_id", "")).strip()
            if segment_id:
                result[segment_id] = dict(segment)
    if not result:
        raise GraphicsMediaQueueError("SCRIPT_SEGMENTS_REQUIRED")
    return result


def _event_sources(evidence: Mapping[str, Any]) -> dict[str, set[str]]:
    result: dict[str, set[str]] = {}
    for event in _seq(evidence.get("events")):
        if not isinstance(event, Mapping):
            continue
        event_id = str(event.get("event_id", "")).strip()
        if not event_id:
            continue
        bucket = result.setdefault(event_id, set())
        for claim in _seq(event.get("claims")):
            if not isinstance(claim, Mapping):
                continue
            if claim.get("use_policy") == "EXCLUDED":
                continue
            bucket.update(
                str(value)
                for value in _seq(claim.get("source_ids"))
                if str(value).strip()
            )
    return result


def _shot_segments(
    shot: Mapping[str, Any],
    segments: Mapping[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    return [
        segments[str(segment_id)]
        for segment_id in _seq(shot.get("segment_ids"))
        if str(segment_id) in segments
    ]


def _shot_sources(
    shot: Mapping[str, Any],
    segments: Sequence[Mapping[str, Any]],
    event_sources: Mapping[str, set[str]],
    known: set[str],
) -> list[str]:
    refs: set[str] = set()
    for segment in segments:
        refs.update(
            str(value)
            for value in _seq(segment.get("source_ids"))
            if str(value).strip()
        )
    if not refs:
        refs.update(event_sources.get(str(shot.get("event_id", "")), set()))
    refs &= known
    if not refs:
        raise GraphicsMediaQueueError(
            "GRAPHICS_SHOT_HAS_NO_TRACEABLE_SOURCE:"
            + str(shot.get("shot_id", ""))
        )
    return sorted(refs)


def _graphic_type(
    shot: Mapping[str, Any],
    segments: Sequence[Mapping[str, Any]],
    ordinal: int,
) -> str:
    explicit = str(
        shot.get("graphic_type") or shot.get("local_graphic_type") or ""
    ).strip().upper()
    if explicit:
        return explicit
    text = " ".join(
        [
            str(shot.get("label_ar", "")),
            str(shot.get("dramatic_function_ar", "")),
            str(shot.get("visual_brief_ar", "")),
            *[
                str(segment.get("title_ar", ""))
                + " "
                + str(segment.get("narration_ar", ""))
                for segment in segments
            ],
        ]
    ).lower()
    for graphic_type in (
        "MAP_ROUTE",
        "RELATION_TREE",
        "COMPARISON",
        "SOURCE_CARD",
        "ANIMATED_TIMELINE",
    ):
        if any(term in text for term in TYPE_TERMS[graphic_type]):
            return graphic_type
    return DEFAULT_TYPES[(ordinal - 1) % len(DEFAULT_TYPES)]


def _item(
    number: int,
    label: str,
    secondary: str,
    value: str,
    source_ids: Sequence[str],
    x: float,
    y: float,
    parent: str = "",
) -> dict[str, Any]:
    refs = [str(value) for value in source_ids if str(value).strip()]
    if not refs:
        raise GraphicsMediaQueueError(
            f"GRAPHICS_ITEM_SOURCE_REQUIRED:GI-{number:02d}"
        )
    return {
        "item_id": f"GI-{number:02d}",
        "label_ar": _clip(label, 68),
        "secondary_ar": _clip(secondary, 120),
        "value_ar": _clip(value, 190),
        "source_ids": refs[:8],
        "x": round(x, 4),
        "y": round(y, 4),
        "parent_item_id": parent,
    }


def _timeline_items(
    segments: Sequence[Mapping[str, Any]],
    source_ids: Sequence[str],
) -> list[dict[str, Any]]:
    values = list(segments[:6]) or [
        {"title_ar": "المرحلة", "source_ids": source_ids}
    ]
    result = []
    count = len(values)
    for index, segment in enumerate(values, start=1):
        refs = [
            str(value)
            for value in _seq(segment.get("source_ids"))
            if str(value) in source_ids
        ] or list(source_ids[:1])
        x = 0.5 if count == 1 else 0.08 + (index - 1) * 0.84 / (count - 1)
        result.append(
            _item(
                index,
                str(segment.get("title_ar", f"المرحلة {index}")),
                str(segment.get("event_id", "")),
                f"المرحلة {index} من {count}",
                refs,
                x,
                0.5,
                f"GI-{index - 1:02d}" if index > 1 else "",
            )
        )
    return result


def _map_items(
    segments: Sequence[Mapping[str, Any]],
    source_ids: Sequence[str],
) -> list[dict[str, Any]]:
    values = list(segments[:5]) or [
        {"title_ar": "المحطة", "source_ids": source_ids}
    ]
    result = []
    count = len(values)
    y_positions = (0.30, 0.58, 0.38, 0.68, 0.46)
    for index, segment in enumerate(values, start=1):
        refs = [
            str(value)
            for value in _seq(segment.get("source_ids"))
            if str(value) in source_ids
        ] or list(source_ids[:1])
        x = 0.5 if count == 1 else 0.08 + (index - 1) * 0.84 / (count - 1)
        result.append(
            _item(
                index,
                str(segment.get("title_ar", f"المحطة {index}")),
                "موضع توضيحي غير مقياس جغرافي",
                str(segment.get("event_id", "")),
                refs,
                x,
                y_positions[(index - 1) % 5],
                f"GI-{index - 1:02d}" if index > 1 else "",
            )
        )
    return result


def _source_item(
    source_ids: Sequence[str],
    sources: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    source = sources[source_ids[0]]
    author = str(source.get("publisher_or_author", "")).strip()
    edition = str(source.get("date_or_edition", "")).strip()
    secondary = " — ".join(value for value in (author, edition) if value)
    value = str(source.get("reliability_ar", "")).strip() or (
        "مصدر معتمد في حزمة أدلة الحلقة."
    )
    if str(source.get("url", "")).startswith("shamela://local/"):
        value += " المرجع محفوظ محليًا في مكتبة الشاملة."
    return [
        _item(
            1,
            str(source.get("title", "المصدر المعتمد")),
            secondary,
            value,
            [source_ids[0]],
            0.5,
            0.5,
        )
    ]


def _comparison_items(
    segments: Sequence[Mapping[str, Any]],
    source_ids: Sequence[str],
) -> list[dict[str, Any]]:
    values = list(segments[:2])
    if len(values) >= 2:
        result = []
        for index, segment in enumerate(values, start=1):
            refs = [
                str(value)
                for value in _seq(segment.get("source_ids"))
                if str(value) in source_ids
            ] or list(source_ids[:1])
            result.append(
                _item(
                    index,
                    str(segment.get("title_ar", f"الجانب {index}")),
                    str(segment.get("uncertainty_language_ar", "")),
                    str(segment.get("narration_ar", "")),
                    refs,
                    0.25 if index == 1 else 0.75,
                    0.5,
                )
            )
        return result
    segment = values[0] if values else {}
    refs = [
        str(value)
        for value in _seq(segment.get("source_ids"))
        if str(value) in source_ids
    ] or list(source_ids[:1])
    return [
        _item(
            1,
            "المعلومة المثبتة",
            str(segment.get("title_ar", "")),
            str(segment.get("narration_ar", "")),
            refs,
            0.25,
            0.5,
        ),
        _item(
            2,
            "حدود الجزم",
            "صياغة تحفظية",
            str(segment.get("uncertainty_language_ar", ""))
            or "لا يزاد على القدر الذي تثبته المصادر.",
            refs,
            0.75,
            0.5,
        ),
    ]


def _generic_items(
    graphic_type: str,
    shot: Mapping[str, Any],
    segments: Sequence[Mapping[str, Any]],
    source_ids: Sequence[str],
    sources: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    if graphic_type == "SOURCE_CARD":
        return _source_item(source_ids, sources)
    if graphic_type == "ANIMATED_TIMELINE":
        return _timeline_items(segments, source_ids)
    if graphic_type == "MAP_ROUTE":
        return _map_items(segments, source_ids)
    if graphic_type == "COMPARISON":
        return _comparison_items(segments, source_ids)
    if graphic_type == "RELATION_TREE":
        values = list(segments[:5]) or [
            {"title_ar": "العلاقة", "source_ids": source_ids}
        ]
        positions = (
            (0.5, 0.12),
            (0.22, 0.48),
            (0.50, 0.48),
            (0.78, 0.48),
            (0.5, 0.82),
        )
        result = []
        for index, segment in enumerate(values, start=1):
            refs = [
                str(value)
                for value in _seq(segment.get("source_ids"))
                if str(value) in source_ids
            ] or list(source_ids[:1])
            x, y = positions[(index - 1) % len(positions)]
            result.append(
                _item(
                    index,
                    str(segment.get("title_ar", f"العنصر {index}")),
                    str(segment.get("event_id", "")),
                    "علاقة موضحة وفق ترتيب النص المعتمد",
                    refs,
                    x,
                    y,
                    "GI-01" if index > 1 else "",
                )
            )
        return result
    segment = segments[0] if segments else {}
    refs = [
        str(value)
        for value in _seq(segment.get("source_ids"))
        if str(value) in source_ids
    ] or list(source_ids[:1])
    return [
        _item(
            1,
            str(shot.get("label_ar", "المكان والزمان")),
            str(shot.get("visual_brief_ar", "")),
            str(segment.get("title_ar") or shot.get("event_id", "")),
            refs,
            0.5,
            0.5,
        )
    ]


def _make_spec(
    shot: Mapping[str, Any],
    ordinal: int,
    segments: Mapping[str, dict[str, Any]],
    event_sources: Mapping[str, set[str]],
    sources: Mapping[str, Mapping[str, Any]],
) -> LocalGraphicsSpec:
    shot_segments = _shot_segments(shot, segments)
    source_ids = _shot_sources(
        shot, shot_segments, event_sources, set(sources)
    )
    graphic_type = _graphic_type(shot, shot_segments, ordinal)
    payload = {
        "schema_version": "siraj-local-graphics-spec-v1",
        "graphic_id": f"GFX-{ordinal:02d}",
        "shot_id": str(shot.get("shot_id", "")),
        "graphic_type": graphic_type,
        "duration_seconds": float(
            shot.get("editorial_duration_seconds", 10)
        ),
        "title_ar": _clip(
            shot.get("label_ar")
            or (
                shot_segments[0].get("title_ar")
                if shot_segments
                else "جرافيك توضيحي"
            ),
            80,
        ),
        "subtitle_ar": _clip(
            "مسار توضيحي غير مقياس جغرافي"
            if graphic_type == "MAP_ROUTE"
            else shot.get("dramatic_function_ar", ""),
            140,
        ),
        "items": _generic_items(
            graphic_type,
            shot,
            shot_segments,
            source_ids,
            sources,
        ),
        "source_ids": source_ids,
        "animation_style": ANIMATION_BY_TYPE[graphic_type],
        "background": {
            "mode": "GRADIENT",
            "image_url": "",
            "overlay_opacity": 0.08,
        },
        "design": {
            "font_family": "Segoe UI",
            "accent_hex": "#C99A45",
            "foreground_hex": "#F3EBDD",
            "background_hex": "#17130F",
            "safe_margin_px": 120,
        },
        "music": "FORBIDDEN",
        "sound_policy": "SFX_ONLY_NO_MUSIC",
    }
    try:
        return validate_graphics_spec(payload, known_source_ids=set(sources))
    except LocalGraphicsSpecError as exc:
        raise GraphicsMediaQueueError(
            f"GRAPHICS_SPEC_VALIDATION_FAILED:{shot.get('shot_id')}:{exc}"
        ) from exc


def _integrate(
    evidence: Mapping[str, Any],
    script: Mapping[str, Any],
    storyboard: dict[str, Any],
) -> tuple[dict[str, Any], tuple[LocalGraphicsSpec, ...]]:
    sources = _sources(evidence)
    segments = _segments(script)
    event_sources = _event_sources(evidence)
    shots = storyboard.get("shots")
    if not isinstance(shots, list) or len(shots) != 70:
        raise GraphicsMediaQueueError("STORYBOARD_70_SHOTS_REQUIRED")
    fields = [
        "graphics_spec" in shot
        for shot in shots
        if isinstance(shot, Mapping)
    ]
    if fields and all(fields):
        try:
            specs = extract_storyboard_graphics_specs(
                storyboard, known_source_ids=set(sources)
            )
        except LocalGraphicsSpecError as exc:
            raise GraphicsMediaQueueError(str(exc)) from exc
        return storyboard, specs

    integrated = []
    ordinal = 0
    for raw in shots:
        if not isinstance(raw, Mapping):
            raise GraphicsMediaQueueError("STORYBOARD_SHOT_OBJECT_REQUIRED")
        shot = dict(raw)
        if shot.get("final_budget_treatment") == "GRAPHICS":
            ordinal += 1
            shot["graphics_spec"] = _make_spec(
                shot, ordinal, segments, event_sources, sources
            ).payload
        else:
            shot["graphics_spec"] = None
        integrated.append(shot)
    if ordinal != 6:
        raise GraphicsMediaQueueError(
            f"GRAPHICS_SHOT_COUNT_MUST_BE_6:{ordinal}"
        )
    result = dict(storyboard)
    result["shots"] = integrated
    try:
        specs = extract_storyboard_graphics_specs(
            result, known_source_ids=set(sources)
        )
    except LocalGraphicsSpecError as exc:
        raise GraphicsMediaQueueError(str(exc)) from exc
    return result, specs


def _uuid(episode_id: str, category: str, identity: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"siraj:{episode_id}:{category}:{identity}:attempt-1",
        )
    )


def _has_humans(shot: Mapping[str, Any]) -> bool:
    text = " ".join(
        str(shot.get(field, ""))
        for field in (
            "label_ar",
            "visual_brief_ar",
            "dramatic_function_ar",
            "runware_positive_prompt_en",
        )
    ).lower()
    return any(term in text for term in HUMAN_TERMS)


def _video_task(
    episode_id: str,
    shot: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    shot_id = str(shot.get("shot_id", ""))
    person_required = _has_humans(shot)
    google: dict[str, Any] = {"generateAudio": False}
    if not person_required:
        google["personGeneration"] = "dont_allow"
    return (
        {
            "taskType": "videoInference",
            "taskUUID": _uuid(episode_id, "video", shot_id),
            "model": VIDEO_MODEL,
            "positivePrompt": str(
                shot.get("runware_positive_prompt_en", "")
            ).strip(),
            "width": VIDEO_WIDTH,
            "height": VIDEO_HEIGHT,
            "duration": VIDEO_DURATION_SECONDS,
            "numberResults": 1,
            "deliveryMethod": "async",
            "includeCost": True,
            "providerSettings": {"google": google},
        },
        person_required,
    )


def _queue(
    repo: Path,
    episode_id: str,
    script: Mapping[str, Any],
    storyboard: Mapping[str, Any],
    specs: Sequence[LocalGraphicsSpec],
    recorded_override: float | None,
) -> dict[str, Any]:
    images, videos, graphics = [], [], []
    seedream = nano = 0
    specs_by_shot = {spec.shot_id: spec for spec in specs}

    for shot in _seq(storyboard.get("shots")):
        if not isinstance(shot, Mapping):
            raise GraphicsMediaQueueError("STORYBOARD_SHOT_OBJECT_REQUIRED")
        treatment = str(shot.get("final_budget_treatment", ""))
        shot_id = str(shot.get("shot_id", ""))
        index = int(shot.get("queue_index", 0))

        if treatment == "ANIMATED_STILL_COMPOSITING":
            task_uuid = _uuid(episode_id, "image", shot_id)
            route = route_image_shot(shot)
            task = build_runware_image_task(shot, task_uuid)
            if route.model == "bytedance:seedream@5.0-pro":
                seedream += 1
            elif route.model == "google:4@3":
                nano += 1
            images.append(
                {
                    "queue_id": f"IMG-{shot_id}",
                    "queue_index": index,
                    "shot_id": shot_id,
                    "event_id": shot.get("event_id"),
                    "segment_ids": list(_seq(shot.get("segment_ids"))),
                    "status": (
                        "READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED"
                    ),
                    "selected_model": route.model,
                    "selected_role": route.role,
                    "routing_reason": route.reason,
                    "task_uuid": task_uuid,
                    "task_draft": task,
                    "maximum_authorized_usd": IMAGE_MAX_AUTHORIZED_USD,
                    "output_path_relative": (
                        f"projects/{episode_id}/cinematic/"
                        f"runware-images/{shot_id}/attempt-01.jpg"
                    ),
                    "hidden_paid_retry": "FORBIDDEN",
                }
            )
        elif treatment == "GENERATED_VIDEO":
            task, person_required = _video_task(episode_id, shot)
            videos.append(
                {
                    "queue_id": f"VID-{shot_id}",
                    "queue_index": index,
                    "shot_id": shot_id,
                    "event_id": shot.get("event_id"),
                    "segment_ids": list(_seq(shot.get("segment_ids"))),
                    "status": (
                        "SAFETY_PREFLIGHT_REQUIRED"
                        if person_required
                        else "READY_EXPLICIT_PAID_AUTHORIZATION_REQUIRED"
                    ),
                    "selected_model": VIDEO_MODEL,
                    "task_uuid": task["taskUUID"],
                    "task_draft": task,
                    "person_generation_resolution_required": person_required,
                    "maximum_authorized_usd": VIDEO_MAX_AUTHORIZED_USD,
                    "output_path_relative": (
                        f"projects/{episode_id}/cinematic/"
                        f"runware-videos/{shot_id}/attempt-01.mp4"
                    ),
                    "hidden_paid_retry": "FORBIDDEN",
                }
            )
        elif treatment == "GRAPHICS":
            spec = specs_by_shot.get(shot_id)
            if spec is None:
                raise GraphicsMediaQueueError(
                    f"GRAPHICS_SPEC_MISSING_FOR_QUEUE:{shot_id}"
                )
            graphics.append(
                {
                    "queue_id": f"LOCAL-{shot_id}",
                    "queue_index": index,
                    "shot_id": shot_id,
                    "event_id": shot.get("event_id"),
                    "segment_ids": list(_seq(shot.get("segment_ids"))),
                    "status": "READY_LOCAL_RENDER",
                    "graphic_id": spec.graphic_id,
                    "graphic_type": spec.graphic_type,
                    "spec_path_relative": (
                        f"projects/{episode_id}/"
                        f"{GRAPHICS_SPEC_DIR_REL.as_posix()}/"
                        f"{spec.graphic_id}.json"
                    ),
                    "output_path_relative": (
                        f"projects/{episode_id}/"
                        f"{GRAPHICS_OUTPUT_DIR_REL.as_posix()}/"
                        f"{spec.graphic_id}.mp4"
                    ),
                    "api_cost_usd": 0.0,
                    "renderer": "PYSIDE6_QT_QUICK_QML_FFMPEG",
                }
            )

    tts = []
    for index, segment in enumerate(_seq(script.get("segments")), start=1):
        if not isinstance(segment, Mapping):
            raise GraphicsMediaQueueError("SCRIPT_SEGMENT_OBJECT_REQUIRED")
        segment_id = str(segment.get("segment_id", ""))
        narration = str(segment.get("narration_ar", "")).strip()
        if not narration:
            raise GraphicsMediaQueueError(
                f"TTS_NARRATION_REQUIRED:{segment_id}"
            )
        tts.append(
            {
                "queue_id": f"TTS-{segment_id}",
                "queue_index": index,
                "segment_id": segment_id,
                "event_id": segment.get("event_id"),
                "source_ids": list(_seq(segment.get("source_ids"))),
                "status": "BLOCKED_VOICE_SELECTION_REQUIRED",
                "provider": "ELEVENLABS",
                "voice_id": None,
                "model_id": None,
                "text_ar": narration,
                "output_path_relative": (
                    f"projects/{episode_id}/audio/tts/{segment_id}.mp3"
                ),
                "hidden_paid_retry": "FORBIDDEN",
            }
        )

    if len(images) != 44:
        raise GraphicsMediaQueueError(
            f"IMAGE_QUEUE_COUNT_MUST_BE_44:{len(images)}"
        )
    if len(videos) != 20:
        raise GraphicsMediaQueueError(
            f"VIDEO_QUEUE_COUNT_MUST_BE_20:{len(videos)}"
        )
    if len(graphics) != 6:
        raise GraphicsMediaQueueError(
            f"GRAPHICS_QUEUE_COUNT_MUST_BE_6:{len(graphics)}"
        )

    recorded = (
        float(recorded_override)
        if recorded_override is not None
        else scan_episode_costs(repo, episode_id).recorded_total_usd
    )
    image_reserve = round(len(images) * IMAGE_MAX_AUTHORIZED_USD, 2)
    video_reserve = round(len(videos) * VIDEO_MAX_AUTHORIZED_USD, 2)
    reserve = round(
        image_reserve + video_reserve + TTS_TOTAL_MAX_AUTHORIZED_USD,
        2,
    )
    projected = round(recorded + reserve, 4)
    if projected > EPISODE_HARD_CAP_USD + 1e-9:
        raise GraphicsMediaQueueError(
            "EPISODE_BUDGET_PREFLIGHT_BLOCKED:"
            f"recorded={recorded:.4f}:reserve={reserve:.2f}:"
            f"projected={projected:.4f}:cap={EPISODE_HARD_CAP_USD:.2f}"
        )

    return {
        "schema_version": "siraj-media-production-queue-v1",
        "release": RELEASE,
        "episode_id": episode_id,
        "status": "READY_AWAITING_EXPLICIT_PAID_EXECUTION",
        "counts": {
            "runware_images": len(images),
            "runware_videos": len(videos),
            "local_graphics": len(graphics),
            "elevenlabs_tts_segments": len(tts),
            "seedream_images": seedream,
            "nano_banana_images": nano,
        },
        "budget_preflight": {
            "episode_hard_cap_usd": EPISODE_HARD_CAP_USD,
            "recorded_total_usd": round(recorded, 8),
            "image_max_reserve_usd": image_reserve,
            "video_max_reserve_usd": video_reserve,
            "tts_max_reserve_usd": TTS_TOTAL_MAX_AUTHORIZED_USD,
            "local_graphics_api_cost_usd": 0.0,
            "reserved_max_usd": reserve,
            "projected_max_total_usd": projected,
            "remaining_unreserved_headroom_usd": round(
                EPISODE_HARD_CAP_USD - projected, 4
            ),
            "reserve_basis": (
                "PROTECTIVE_MAXIMUM_NOT_EXPECTED_PROVIDER_CHARGE"
            ),
            "provider_billing_is_source_of_truth": True,
        },
        "execution_policy": {
            "paid_submission_trigger": (
                "ONE_EXPLICIT_DESKTOP_AUTHORIZATION_PER_ATTEMPT"
            ),
            "hidden_paid_retry": "FORBIDDEN",
            "recover_existing_task_uuid_without_resubmission": True,
            "local_graphics_may_render_without_paid_authorization": True,
            "music": "FORBIDDEN",
        },
        "queues": {
            "runware_images": images,
            "runware_videos": videos,
            "local_graphics": graphics,
            "elevenlabs_tts": tts,
        },
        "created_at_utc": _now(),
    }


def _write_specs(
    root: Path,
    specs: Sequence[LocalGraphicsSpec],
) -> tuple[Path, ...]:
    result = []
    for spec in specs:
        path = root / GRAPHICS_SPEC_DIR_REL / f"{spec.graphic_id}.json"
        _write(path, spec.payload)
        result.append(path)
    return tuple(result)


def _edge(edges: list[dict[str, str]], parent: str, child: str) -> None:
    value = {"from": parent, "to": child}
    if value not in edges:
        edges.append(value)


def _graph(
    repo: Path,
    episode_id: str,
    root: Path,
    storyboard: Mapping[str, Any],
    queue_path: Path,
    spec_paths: Mapping[str, Path],
    storyboard_path: Path,
) -> None:
    path = root / DEPENDENCY_GRAPH_REL
    graph = _read(path)
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not isinstance(edges, list):
        raise GraphicsMediaQueueError("DEPENDENCY_GRAPH_STRUCTURE_INVALID")
    index = {
        str(node.get("node_id")): node
        for node in nodes
        if isinstance(node, dict)
    }

    def add(
        node_id: str,
        kind: str,
        source_id: str,
        status: str,
        artifact_path: str | None = None,
        artifact_hash: str | None = None,
    ) -> None:
        if node_id in index:
            node = index[node_id]
            node.update(
                {
                    "kind": kind,
                    "source_id": source_id,
                    "status": status,
                    "artifact_path_relative": artifact_path,
                    "artifact_sha256": artifact_hash,
                    "invalidated_at_utc": None,
                    "invalidation_reason": None,
                }
            )
            return
        node = {
            "node_id": node_id,
            "kind": kind,
            "source_id": source_id,
            "status": status,
            "version": 1,
            "artifact_path_relative": artifact_path,
            "artifact_sha256": artifact_hash,
            "invalidated_at_utc": None,
            "invalidation_reason": None,
        }
        nodes.append(node)
        index[node_id] = node

    storyboard_rel = _rel(repo, storyboard_path)
    storyboard_hash = _hash(storyboard_path)
    for node in nodes:
        if isinstance(node, dict) and node.get("kind") == "SHOT_PLAN":
            node["status"] = "COMPLETE"
            node["artifact_path_relative"] = storyboard_rel
            node["artifact_sha256"] = storyboard_hash

    queue_node = f"{episode_id}:MEDIA_QUEUE"
    add(
        queue_node,
        "MEDIA_QUEUE",
        episode_id,
        "COMPLETE",
        _rel(repo, queue_path),
        _hash(queue_path),
    )

    kind_by_treatment = {
        "GENERATED_VIDEO": "RUNWARE_VIDEO_ASSET",
        "ANIMATED_STILL_COMPOSITING": "RUNWARE_IMAGE_ASSET",
        "GRAPHICS": "LOCAL_GRAPHICS_ASSET",
    }
    for shot in _seq(storyboard.get("shots")):
        if not isinstance(shot, Mapping):
            continue
        shot_id = str(shot.get("shot_id", ""))
        event_id = str(shot.get("event_id", ""))
        treatment = str(shot.get("final_budget_treatment", ""))
        asset = f"{episode_id}:ASSET:{shot_id}"
        add(asset, kind_by_treatment[treatment], shot_id, "PLANNED")
        plan = f"{episode_id}:SHOT_PLAN:{event_id}"
        timeline = f"{episode_id}:TIMELINE:{event_id}"
        if plan in index:
            _edge(edges, plan, queue_node)
            _edge(edges, plan, asset)
        _edge(edges, queue_node, asset)
        if timeline in index:
            _edge(edges, asset, timeline)
        if treatment == "GRAPHICS":
            spec_path = spec_paths[shot_id]
            spec_node = f"{episode_id}:GRAPHICS_SPEC:{shot_id}"
            add(
                spec_node,
                "LOCAL_GRAPHICS_SPEC",
                shot_id,
                "COMPLETE",
                _rel(repo, spec_path),
                _hash(spec_path),
            )
            if plan in index:
                _edge(edges, plan, spec_node)
            _edge(edges, spec_node, asset)

    graph["status"] = "MEDIA_QUEUE_READY"
    graph["updated_at_utc"] = _now()
    graph.pop("graph_sha256", None)
    graph["graph_sha256"] = canonical_sha256(graph)
    _write(path, graph)


def _ledger(
    repo: Path,
    root: Path,
    budget_path: Path,
    queue_path: Path,
) -> None:
    path = root / STAGE_LEDGER_REL
    ledger = _read(path)
    stages = ledger.get("stages")
    if not isinstance(stages, list):
        raise GraphicsMediaQueueError("STAGE_LEDGER_STAGES_REQUIRED")
    if not any(
        isinstance(item, Mapping)
        and item.get("stage") == "LOCAL_GRAPHICS_RENDER"
        for item in stages
    ):
        position = len(stages)
        for index, item in enumerate(stages):
            if (
                isinstance(item, Mapping)
                and item.get("stage") == "RUNWARE_VIDEO_GENERATION"
            ):
                position = index + 1
                break
        stages.insert(
            position,
            {"stage": "LOCAL_GRAPHICS_RENDER", "status": "QUEUED"},
        )
    for order, item in enumerate(stages, start=1):
        if not isinstance(item, dict):
            continue
        item["order"] = order
        if item.get("stage") == "BUDGET_PREFLIGHT":
            item["status"] = "COMPLETE"
            item["artifact_path_relative"] = _rel(repo, budget_path)
            item["updated_at_utc"] = _now()
    ledger["status"] = "MEDIA_QUEUE_READY"
    ledger["resume_from"] = "RUNWARE_IMAGE_GENERATION"
    ledger["media_queue_path_relative"] = _rel(repo, queue_path)
    ledger["updated_at_utc"] = _now()
    _write(path, ledger)


def _runner_state(repo: Path, root: Path, storyboard_path: Path) -> None:
    path = root / EDITORIAL_RUNNER_STATE_REL
    if not path.is_file():
        return
    state = _read(path)
    state.setdefault("artifacts", {})[
        "STORYBOARD_AND_MEDIA_PLANNING"
    ] = {
        "path_relative": _rel(repo, storyboard_path),
        "sha256": _hash(storyboard_path),
        "postprocessed_by": RELEASE,
    }
    state["status"] = "EDITORIAL_PIPELINE_COMPLETE"
    state["current_stage"] = "BUDGET_PREFLIGHT"
    state["updated_at_utc"] = _now()
    _write(path, state)


def _result(
    episode_id: str,
    storyboard_path: Path,
    queue_path: Path,
    budget_path: Path,
    spec_paths: Sequence[Path],
    queue: Mapping[str, Any],
) -> GraphicsMediaQueueResult:
    counts = queue["counts"]
    budget = queue["budget_preflight"]
    return GraphicsMediaQueueResult(
        episode_id=episode_id,
        storyboard_path=storyboard_path,
        media_queue_path=queue_path,
        budget_preflight_path=budget_path,
        graphics_spec_paths=tuple(spec_paths),
        image_count=int(counts["runware_images"]),
        video_count=int(counts["runware_videos"]),
        graphics_count=int(counts["local_graphics"]),
        tts_segment_count=int(counts["elevenlabs_tts_segments"]),
        seedream_count=int(counts["seedream_images"]),
        nano_banana_count=int(counts["nano_banana_images"]),
        reserved_max_usd=float(budget["reserved_max_usd"]),
        recorded_total_usd=float(budget["recorded_total_usd"]),
        projected_total_usd=float(budget["projected_max_total_usd"]),
        tts_voice_selection_required=True,
        status=str(queue["status"]),
    )


def load_media_queue_summary(
    repo_root: Path,
) -> GraphicsMediaQueueResult | None:
    state_path = repo_root.resolve() / ORCHESTRATOR_STATE_REL
    if not state_path.is_file():
        return None
    state = _read(state_path)
    episode_id = state.get("current_episode_id")
    if not isinstance(episode_id, str) or not episode_id:
        return None
    root = repo_root.resolve() / "projects" / episode_id
    queue_path = root / MEDIA_QUEUE_REL
    if not queue_path.is_file():
        return None
    queue = _read(queue_path)
    specs = tuple(sorted((root / GRAPHICS_SPEC_DIR_REL).glob("GFX-*.json")))
    return _result(
        episode_id,
        root / STORYBOARD_REL,
        queue_path,
        root / BUDGET_PREFLIGHT_REL,
        specs,
        queue,
    )


def integrate_graphics_and_build_media_queue(
    repo_root: Path,
    *,
    recorded_total_usd_override: float | None = None,
) -> GraphicsMediaQueueResult:
    repo = repo_root.resolve()
    episode_id, orchestrator, root = _current(repo)
    storyboard_path = root / STORYBOARD_REL
    queue_path = root / MEDIA_QUEUE_REL
    budget_path = root / BUDGET_PREFLIGHT_REL
    integration_state_path = root / INTEGRATION_STATE_REL

    try:
        evidence = _read(root / EVIDENCE_REL)
        script = _read(root / SCRIPT_REL)
        original = _read(storyboard_path)
        integrated, specs = _integrate(evidence, script, original)

        backup = root / STORYBOARD_BACKUP_REL
        if not backup.is_file():
            _write(backup, original)
        _write(storyboard_path, integrated)
        spec_paths = _write_specs(root, specs)

        queue = _queue(
            repo,
            episode_id,
            script,
            integrated,
            specs,
            recorded_total_usd_override,
        )
        _write(queue_path, queue)
        _write(
            budget_path,
            {
                "schema_version": "siraj-budget-preflight-v1",
                "release": RELEASE,
                "episode_id": episode_id,
                "status": "PASS",
                **queue["budget_preflight"],
                "created_at_utc": _now(),
            },
        )

        paths_by_shot = {
            spec.shot_id: path
            for spec, path in zip(specs, spec_paths)
        }
        _graph(
            repo,
            episode_id,
            root,
            integrated,
            queue_path,
            paths_by_shot,
            storyboard_path,
        )
        _ledger(repo, root, budget_path, queue_path)
        _runner_state(repo, root, storyboard_path)

        orchestrator.update(
            {
                "status": "MEDIA_QUEUE_READY",
                "stage": "RUNWARE_IMAGE_GENERATION",
                "next_stage": (
                    "DESKTOP_MEDIA_EXECUTION_AND_"
                    "ELEVENLABS_VOICE_SELECTION_V1"
                ),
                "media_queue_path_relative": _rel(repo, queue_path),
                "budget_preflight_path_relative": _rel(repo, budget_path),
                "last_error": None,
                "updated_at_utc": _now(),
            }
        )
        _write(repo / ORCHESTRATOR_STATE_REL, orchestrator)
        _write(
            integration_state_path,
            {
                "schema_version": (
                    "siraj-graphics-storyboard-media-queue-state-v1"
                ),
                "release": RELEASE,
                "episode_id": episode_id,
                "status": "COMPLETE",
                "storyboard_path_relative": _rel(repo, storyboard_path),
                "storyboard_sha256": _hash(storyboard_path),
                "graphics_spec_paths_relative": [
                    _rel(repo, path) for path in spec_paths
                ],
                "media_queue_path_relative": _rel(repo, queue_path),
                "media_queue_sha256": _hash(queue_path),
                "budget_preflight_path_relative": _rel(repo, budget_path),
                "paid_provider_requests": 0,
                "created_at_utc": _now(),
            },
        )
        return _result(
            episode_id,
            storyboard_path,
            queue_path,
            budget_path,
            spec_paths,
            queue,
        )
    except Exception as exc:
        error = str(exc)
        orchestrator.update(
            {
                "status": "GRAPHICS_MEDIA_QUEUE_FAILED",
                "stage": "BUDGET_PREFLIGHT",
                "next_stage": (
                    "RESUME_GRAPHICS_STORYBOARD_"
                    "INTEGRATION_AND_MEDIA_QUEUE"
                ),
                "last_error": error,
                "updated_at_utc": _now(),
            }
        )
        _write(repo / ORCHESTRATOR_STATE_REL, orchestrator)
        _write(
            integration_state_path,
            {
                "schema_version": (
                    "siraj-graphics-storyboard-media-queue-state-v1"
                ),
                "release": RELEASE,
                "episode_id": episode_id,
                "status": "FAILED",
                "last_error": error,
                "paid_provider_requests": 0,
                "updated_at_utc": _now(),
            },
        )
        if isinstance(exc, GraphicsMediaQueueError):
            raise
        raise GraphicsMediaQueueError(error) from exc
