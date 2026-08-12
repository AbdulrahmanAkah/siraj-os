"""Immutable storyboard structure plus rich cinematic creative overlay.

Luna remains the semantic/directorial intelligence.  It may create and improve
the overlay, but structural timing and bindings are joined back from the
accepted storyboard by deterministic local code.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence

from src.application.artifact_provenance_v1 import canonical_sha256


STRUCTURAL_SCHEMA_VERSION = "siraj-immutable-storyboard-structure-v1"
CREATIVE_SCHEMA_VERSION = "siraj-creative-shot-direction-v1"
PROVIDER_PLAN_SCHEMA_VERSION = "siraj-provider-ready-shot-plan-v1"

STRUCTURAL_FIELDS = frozenset(
    {
        "shot_id",
        "queue_index",
        "beat_id",
        "segment_id",
        "segment_ids",
        "start_seconds",
        "end_seconds",
        "start_ms",
        "end_ms",
        "duration_seconds",
        "duration_ms",
        "shot_order",
    }
)

CREATIVE_FIELDS = (
    "narrative_function",
    "visual_concept",
    "cinematic_treatment",
    "composition",
    "camera_intent",
    "lens_scale_intent",
    "subject_staging",
    "foreground",
    "midground",
    "background",
    "lighting",
    "color_mood",
    "atmosphere",
    "environment",
    "motion",
    "symbolism",
    "continuity_strategy",
    "distinctness_strategy",
    "transition_intent",
    "historical_material_details",
    "internal_constraints",
    "provider_notes",
    "provider_ready_prompt",
    "final_budget_treatment",
    "contains_people",
    "reuse_justification",
    "scene_continuity_id",
    "visual_progression_id",
    "graphics_spec",
    "video_subshots",
)


class CinematicShotContractError(RuntimeError):
    pass


def _milliseconds(value: Any) -> int:
    try:
        return int(round(float(value) * 1000.0))
    except (TypeError, ValueError) as exc:
        raise CinematicShotContractError("TIMING_NUMBER_REQUIRED") from exc


@dataclass(frozen=True, slots=True)
class StructuralShot:
    shot_id: str
    queue_index: int
    beat_id: str
    segment_ids: tuple[str, ...]
    start_ms: int
    end_ms: int

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms

    def as_dict(self) -> dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "queue_index": self.queue_index,
            "beat_id": self.beat_id,
            "segment_ids": list(self.segment_ids),
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True, slots=True)
class CreativeShotDirection:
    shot_id: str
    narrative_function: Any = ""
    visual_concept: Any = ""
    cinematic_treatment: Any = ""
    composition: Any = ""
    camera_intent: Any = ""
    lens_scale_intent: Any = ""
    subject_staging: Any = ""
    foreground: Any = ""
    midground: Any = ""
    background: Any = ""
    lighting: Any = ""
    color_mood: Any = ""
    atmosphere: Any = ""
    environment: Any = ""
    motion: Any = ""
    symbolism: Any = ""
    continuity_strategy: Any = ""
    distinctness_strategy: Any = ""
    transition_intent: Any = ""
    historical_material_details: Any = ""
    internal_constraints: Any = ""
    provider_notes: Any = ""
    provider_ready_prompt: Any = ""
    final_budget_treatment: Any = ""
    contains_people: Any = False
    reuse_justification: Any = ""
    scene_continuity_id: Any = ""
    visual_progression_id: Any = ""
    graphics_spec: Any = None
    video_subshots: Any = None
    extensions: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["extensions"] = dict(self.extensions)
        return value


def structural_shots_from_storyboard(
    storyboard: Mapping[str, Any],
) -> tuple[StructuralShot, ...]:
    rows = storyboard.get("shots")
    if not isinstance(rows, list) or not rows:
        raise CinematicShotContractError("STORYBOARD_SHOTS_REQUIRED")
    result: list[StructuralShot] = []
    previous_end = 0
    seen: set[str] = set()
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, Mapping):
            raise CinematicShotContractError("STORYBOARD_SHOT_OBJECT_REQUIRED")
        audio = row.get("audio_ref") if isinstance(row.get("audio_ref"), Mapping) else {}
        timing = audio.get("range_seconds")
        if not isinstance(timing, Sequence) or len(timing) != 2:
            timing = (row.get("start_seconds"), row.get("end_seconds"))
        start_ms = _milliseconds(timing[0])
        end_ms = _milliseconds(timing[1])
        shot_id = str(row.get("shot_id") or "").strip()
        if not shot_id or shot_id in seen:
            raise CinematicShotContractError("SHOT_ID_REQUIRED_AND_UNIQUE")
        if end_ms <= start_ms:
            raise CinematicShotContractError("SHOT_DURATION_MUST_BE_POSITIVE:" + shot_id)
        if index > 1 and start_ms != previous_end:
            raise CinematicShotContractError("STORYBOARD_TIMELINE_DISCONTINUITY:" + shot_id)
        segment_values = row.get("segment_ids")
        if not isinstance(segment_values, list):
            segment = audio.get("segment_id") or row.get("segment_id")
            segment_values = [segment] if segment else []
        beat_id = str(audio.get("beat_id") or row.get("beat_id") or "").strip()
        result.append(
            StructuralShot(
                shot_id=shot_id,
                queue_index=int(row.get("queue_index") or index),
                beat_id=beat_id,
                segment_ids=tuple(str(item) for item in segment_values if str(item)),
                start_ms=start_ms,
                end_ms=end_ms,
            )
        )
        seen.add(shot_id)
        previous_end = end_ms
    return tuple(result)


LEGACY_CREATIVE_MAP: Mapping[str, tuple[str, ...]] = {
    "narrative_function": ("narrative_function", "semantic_beat"),
    "visual_concept": ("visual_concept", "semantic_beat", "subject"),
    "cinematic_treatment": ("cinematic_treatment", "visual_treatment"),
    "composition": ("composition",),
    "camera_intent": ("camera_intent", "camera", "camera_angle", "camera_movement"),
    "lens_scale_intent": ("lens_scale_intent", "lens", "scale"),
    "subject_staging": ("subject_staging", "subject"),
    "foreground": ("foreground",),
    "midground": ("midground",),
    "background": ("background",),
    "lighting": ("lighting", "lighting_direction"),
    "color_mood": ("color_mood", "mood"),
    "atmosphere": ("atmosphere",),
    "environment": ("environment",),
    "motion": ("motion", "motion_direction", "camera_movement"),
    "symbolism": ("symbolism", "visual_metaphor", "symbolic_imagery"),
    "continuity_strategy": ("continuity_strategy", "scene_continuity_id"),
    "distinctness_strategy": ("distinctness_strategy", "visual_progression_id"),
    "transition_intent": ("transition_intent", "transition"),
    "historical_material_details": ("historical_material_details", "historical_details"),
    "internal_constraints": ("internal_constraints", "runware_negative_prompt_en"),
    "provider_notes": ("provider_notes",),
    "provider_ready_prompt": ("provider_ready_prompt", "runware_positive_prompt_en"),
    "final_budget_treatment": ("final_budget_treatment",),
    "contains_people": ("contains_people",),
    "reuse_justification": ("reuse_justification",),
    "scene_continuity_id": ("scene_continuity_id",),
    "visual_progression_id": ("visual_progression_id",),
    "graphics_spec": ("graphics_spec",),
    "video_subshots": ("video_subshots",),
}


def _first_present(row: Mapping[str, Any], names: Sequence[str]) -> Any:
    for name in names:
        if name in row and row[name] not in (None, ""):
            return row[name]
    return ""


def migrate_legacy_creative_overlay(
    storyboard: Mapping[str, Any],
    legacy_prompt_plan: Mapping[str, Any],
) -> dict[str, Any]:
    structures = structural_shots_from_storyboard(storyboard)
    rows = legacy_prompt_plan.get("items")
    if not isinstance(rows, list):
        rows = legacy_prompt_plan.get("shots")
    if not isinstance(rows, list):
        raise CinematicShotContractError("LEGACY_PROMPT_ITEMS_REQUIRED")
    by_id = {
        str(row.get("shot_id")): row
        for row in rows
        if isinstance(row, Mapping) and row.get("shot_id")
    }
    storyboard_by_id = {
        str(row.get("shot_id")): row
        for row in storyboard.get("shots", [])
        if isinstance(row, Mapping) and row.get("shot_id")
    }
    directions: list[dict[str, Any]] = []
    for structure in structures:
        if structure.shot_id not in by_id:
            raise CinematicShotContractError(
                "CREATIVE_DIRECTION_MISSING_SHOT:" + structure.shot_id
            )
        legacy = dict(by_id[structure.shot_id])
        creative_values = {
            field_name: _first_present(legacy, legacy_names)
            for field_name, legacy_names in LEGACY_CREATIVE_MAP.items()
        }
        used_legacy = {
            name for names in LEGACY_CREATIVE_MAP.values() for name in names
        }
        extensions = {
            key: value
            for key, value in legacy.items()
            if key not in STRUCTURAL_FIELDS and key not in used_legacy
        }
        extensions["legacy_fields_exact"] = {
            key: value for key, value in legacy.items() if key not in STRUCTURAL_FIELDS
        }
        storyboard_row = storyboard_by_id.get(structure.shot_id, {})
        extensions["legacy_storyboard_creative_context"] = {
            key: value
            for key, value in storyboard_row.items()
            if key not in STRUCTURAL_FIELDS and key != "audio_ref"
        }
        direction = CreativeShotDirection(
            shot_id=structure.shot_id,
            **creative_values,
            extensions=extensions,
        )
        directions.append(direction.as_dict())
    return {
        "schema_version": CREATIVE_SCHEMA_VERSION,
        "status": "PASS",
        "storyboard_structural_fingerprint": structural_fingerprint(structures),
        "directions": directions,
        "legacy_source_sha256": canonical_sha256(legacy_prompt_plan),
        "creative_information_preserved": True,
    }


def validate_creative_overlay(
    overlay: Mapping[str, Any],
    structures: Sequence[StructuralShot],
) -> tuple[CreativeShotDirection, ...]:
    if overlay.get("schema_version") != CREATIVE_SCHEMA_VERSION:
        raise CinematicShotContractError("CREATIVE_OVERLAY_SCHEMA_INVALID")
    rows = overlay.get("directions")
    if not isinstance(rows, list):
        raise CinematicShotContractError("CREATIVE_DIRECTIONS_REQUIRED")
    expected_ids = [shot.shot_id for shot in structures]
    actual_ids = [str(row.get("shot_id")) for row in rows if isinstance(row, Mapping)]
    if actual_ids != expected_ids:
        raise CinematicShotContractError("CREATIVE_SHOT_ID_ORDER_MISMATCH")
    directions: list[CreativeShotDirection] = []
    for row in rows:
        if not isinstance(row, Mapping):
            raise CinematicShotContractError("CREATIVE_DIRECTION_OBJECT_REQUIRED")
        forbidden = STRUCTURAL_FIELDS.intersection(row.keys()) - {"shot_id"}
        if forbidden:
            raise CinematicShotContractError(
                "CREATIVE_OVERLAY_STRUCTURAL_FIELDS_FORBIDDEN:"
                + ",".join(sorted(forbidden))
            )
        values = {name: row.get(name, "") for name in CREATIVE_FIELDS}
        extensions = row.get("extensions")
        if not isinstance(extensions, Mapping):
            extensions = {}
        directions.append(
            CreativeShotDirection(
                shot_id=str(row.get("shot_id")),
                **values,
                extensions=dict(extensions),
            )
        )
    if overlay.get("storyboard_structural_fingerprint") != structural_fingerprint(structures):
        raise CinematicShotContractError("CREATIVE_OVERLAY_STORYBOARD_HASH_MISMATCH")
    return tuple(directions)


def structural_fingerprint(structures: Sequence[StructuralShot]) -> str:
    return canonical_sha256([shot.as_dict() for shot in structures])


def join_provider_ready_plan(
    structures: Sequence[StructuralShot],
    overlay: Mapping[str, Any],
) -> dict[str, Any]:
    directions = validate_creative_overlay(overlay, structures)
    items: list[dict[str, Any]] = []
    for structure, direction in zip(structures, directions):
        creative = direction.as_dict()
        extensions = dict(creative.pop("extensions", {}))
        item = {
            **structure.as_dict(),
            **creative,
            "start_seconds": structure.start_ms / 1000.0,
            "end_seconds": structure.end_ms / 1000.0,
            "duration_seconds": structure.duration_ms / 1000.0,
            "runware_positive_prompt_en": creative.get("provider_ready_prompt", ""),
            "runware_negative_prompt_en": creative.get("internal_constraints", ""),
            "semantic_beat": creative.get("narrative_function", ""),
            "camera_movement": creative.get("motion", ""),
            "camera_angle": creative.get("camera_intent", ""),
            "extensions": extensions,
        }
        items.append(item)
    return {
        "schema_version": PROVIDER_PLAN_SCHEMA_VERSION,
        "status": "PASS",
        "structural_schema_version": STRUCTURAL_SCHEMA_VERSION,
        "creative_schema_version": CREATIVE_SCHEMA_VERSION,
        "storyboard_structural_fingerprint": structural_fingerprint(structures),
        "creative_overlay_sha256": canonical_sha256(overlay),
        "items": items,
    }


def legacy_creative_information(
    legacy_prompt_plan: Mapping[str, Any],
) -> dict[str, dict[str, Any]]:
    rows = legacy_prompt_plan.get("items") or legacy_prompt_plan.get("shots") or []
    return {
        str(row.get("shot_id")): {
            key: value
            for key, value in row.items()
            if key not in STRUCTURAL_FIELDS
        }
        for row in rows
        if isinstance(row, Mapping) and row.get("shot_id")
    }


def roundtrip_preserves_legacy_creative_data(
    storyboard: Mapping[str, Any],
    legacy_prompt_plan: Mapping[str, Any],
) -> bool:
    overlay = migrate_legacy_creative_overlay(storyboard, legacy_prompt_plan)
    structures = structural_shots_from_storyboard(storyboard)
    joined = join_provider_ready_plan(structures, overlay)
    original = legacy_creative_information(legacy_prompt_plan)
    reconstructed = legacy_creative_information(joined)
    for shot_id, fields in original.items():
        joined_fields = reconstructed.get(shot_id, {})
        extensions = joined_fields.get("extensions") or {}
        exact_legacy = extensions.get("legacy_fields_exact") or {}
        direction = next(
            row for row in overlay["directions"] if row["shot_id"] == shot_id
        )
        for key, value in fields.items():
            if key in exact_legacy and exact_legacy[key] == value:
                continue
            mapped_values = [
                direction.get(field_name)
                for field_name, legacy_names in LEGACY_CREATIVE_MAP.items()
                if key in legacy_names and isinstance(direction.get(field_name), (str, int, float, bool, type(None)))
            ]
            if key in extensions and extensions[key] == value:
                continue
            if value in mapped_values:
                continue
            if key == "runware_positive_prompt_en" and joined_fields.get(key) == value:
                continue
            if key == "runware_negative_prompt_en" and joined_fields.get(key) == value:
                continue
            return False
    return True


def creative_quality_problems(overlay: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = overlay.get("directions")
    if not isinstance(rows, list):
        return [{"type": "CREATIVE_DIRECTIONS_REQUIRED"}]
    problems: list[dict[str, Any]] = []
    prior_camera = None
    prior_composition = None
    for row in rows:
        if not isinstance(row, Mapping):
            problems.append({"type": "CREATIVE_DIRECTION_OBJECT_REQUIRED"})
            continue
        shot_id = str(row.get("shot_id") or "")
        required = (
            "visual_concept",
            "composition",
            "camera_intent",
            "environment",
            "motion",
            "provider_ready_prompt",
        )
        missing = [field for field in required if not str(row.get(field) or "").strip()]
        if missing:
            problems.append({"type": "CREATIVE_FIELDS_MISSING", "shot_id": shot_id, "fields": missing})
        camera = str(row.get("camera_intent") or "").strip().casefold()
        composition = str(row.get("composition") or "").strip().casefold()
        continuity = str(row.get("continuity_strategy") or "").strip()
        if camera and composition and camera == prior_camera and composition == prior_composition and not continuity:
            problems.append({"type": "ADJACENT_GENERIC_CAMERA_COMPOSITION", "shot_id": shot_id})
        prior_camera = camera
        prior_composition = composition
    return problems
