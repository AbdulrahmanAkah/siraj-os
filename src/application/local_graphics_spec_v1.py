from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

RELEASE = "LOCAL_PROFESSIONAL_GRAPHICS_ENGINE_V1"
SCHEMA_VERSION = "siraj-local-graphics-spec-v1"

WIDTH = 1920
HEIGHT = 1080
FPS = 30
MIN_DURATION_SECONDS = 4.0
MAX_DURATION_SECONDS = 45.0

GRAPHIC_TYPES = frozenset(
    {
        "ANIMATED_TIMELINE",
        "MAP_ROUTE",
        "RELATION_TREE",
        "SOURCE_CARD",
        "COMPARISON",
        "LOCATION_TIME_CARD",
    }
)
ANIMATION_STYLES = frozenset(
    {
        "CINEMATIC_REVEAL",
        "ROUTE_DRAW",
        "TIMELINE_PROGRESS",
        "NODE_REVEAL",
        "SIDE_BY_SIDE_REVEAL",
        "FOCUS_PULL",
    }
)
BACKGROUND_MODES = frozenset(
    {
        "SOLID",
        "GRADIENT",
        "IMAGE_WITH_OVERLAY",
        "TRANSPARENT",
    }
)


class LocalGraphicsSpecError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LocalGraphicsSpec:
    payload: dict[str, Any]

    @property
    def graphic_id(self) -> str:
        return str(self.payload["graphic_id"])

    @property
    def shot_id(self) -> str:
        return str(self.payload["shot_id"])

    @property
    def graphic_type(self) -> str:
        return str(self.payload["graphic_type"])

    @property
    def duration_seconds(self) -> float:
        return float(self.payload["duration_seconds"])

    @property
    def frame_count(self) -> int:
        return int(round(self.duration_seconds * FPS))


def graphics_spec_json_schema() -> dict[str, Any]:
    source_ref = {
        "type": "string",
        "pattern": "^SRC-[0-9]{3}$",
    }
    item = {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "item_id",
            "label_ar",
            "secondary_ar",
            "value_ar",
            "source_ids",
            "x",
            "y",
            "parent_item_id",
        ],
        "properties": {
            "item_id": {
                "type": "string",
                "pattern": "^GI-[0-9]{2}$",
            },
            "label_ar": {"type": "string"},
            "secondary_ar": {"type": "string"},
            "value_ar": {"type": "string"},
            "source_ids": {
                "type": "array",
                "items": source_ref,
                "maxItems": 8,
            },
            "x": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
            "y": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
            },
            "parent_item_id": {"type": "string"},
        },
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "graphic_id",
            "shot_id",
            "graphic_type",
            "duration_seconds",
            "title_ar",
            "subtitle_ar",
            "items",
            "source_ids",
            "animation_style",
            "background",
            "design",
            "music",
            "sound_policy",
        ],
        "properties": {
            "schema_version": {
                "type": "string",
                "const": SCHEMA_VERSION,
            },
            "graphic_id": {
                "type": "string",
                "pattern": "^GFX-[0-9]{2}$",
            },
            "shot_id": {
                "type": "string",
                "pattern": "^SH-[0-9]{3}$",
            },
            "graphic_type": {
                "type": "string",
                "enum": sorted(GRAPHIC_TYPES),
            },
            "duration_seconds": {
                "type": "number",
                "minimum": MIN_DURATION_SECONDS,
                "maximum": MAX_DURATION_SECONDS,
            },
            "title_ar": {
                "type": "string",
                "minLength": 2,
                "maxLength": 120,
            },
            "subtitle_ar": {
                "type": "string",
                "maxLength": 180,
            },
            "items": {
                "type": "array",
                "items": item,
                "minItems": 1,
                "maxItems": 14,
            },
            "source_ids": {
                "type": "array",
                "items": source_ref,
                "minItems": 1,
                "maxItems": 20,
            },
            "animation_style": {
                "type": "string",
                "enum": sorted(ANIMATION_STYLES),
            },
            "background": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "mode",
                    "image_url",
                    "overlay_opacity",
                ],
                "properties": {
                    "mode": {
                        "type": "string",
                        "enum": sorted(BACKGROUND_MODES),
                    },
                    "image_url": {"type": "string"},
                    "overlay_opacity": {
                        "type": "number",
                        "minimum": 0,
                        "maximum": 1,
                    },
                },
            },
            "design": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "font_family",
                    "accent_hex",
                    "foreground_hex",
                    "background_hex",
                    "safe_margin_px",
                ],
                "properties": {
                    "font_family": {"type": "string"},
                    "accent_hex": {
                        "type": "string",
                        "pattern": "^#[0-9A-Fa-f]{6}$",
                    },
                    "foreground_hex": {
                        "type": "string",
                        "pattern": "^#[0-9A-Fa-f]{6}$",
                    },
                    "background_hex": {
                        "type": "string",
                        "pattern": "^#[0-9A-Fa-f]{6}$",
                    },
                    "safe_margin_px": {
                        "type": "integer",
                        "minimum": 60,
                        "maximum": 180,
                    },
                },
            },
            "music": {
                "type": "string",
                "enum": ["FORBIDDEN"],
            },
            "sound_policy": {
                "type": "string",
                "enum": ["SFX_ONLY_NO_MUSIC"],
            },
        },
    }


def _require(
    condition: bool,
    code: str,
) -> None:
    if not condition:
        raise LocalGraphicsSpecError(code)


def _string(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return value
    return ()


def validate_graphics_spec(
    payload: Mapping[str, Any],
    *,
    known_source_ids: set[str] | None = None,
) -> LocalGraphicsSpec:
    _require(
        payload.get("schema_version") == SCHEMA_VERSION,
        "GRAPHICS_SCHEMA_VERSION_INVALID",
    )
    graphic_id = _string(payload.get("graphic_id"))
    shot_id = _string(payload.get("shot_id"))
    graphic_type = _string(payload.get("graphic_type"))
    _require(
        graphic_id.startswith("GFX-") and len(graphic_id) == 6,
        "GRAPHIC_ID_INVALID",
    )
    _require(
        shot_id.startswith("SH-") and len(shot_id) == 6,
        "GRAPHICS_SHOT_ID_INVALID",
    )
    _require(
        graphic_type in GRAPHIC_TYPES,
        f"GRAPHIC_TYPE_INVALID:{graphic_type}",
    )

    duration = payload.get("duration_seconds")
    _require(
        isinstance(duration, (int, float))
        and MIN_DURATION_SECONDS
        <= float(duration)
        <= MAX_DURATION_SECONDS,
        "GRAPHICS_DURATION_INVALID",
    )
    _require(
        2 <= len(_string(payload.get("title_ar"))) <= 120,
        "GRAPHICS_TITLE_INVALID",
    )
    _require(
        len(_string(payload.get("subtitle_ar"))) <= 180,
        "GRAPHICS_SUBTITLE_TOO_LONG",
    )

    items = _sequence(payload.get("items"))
    _require(1 <= len(items) <= 14, "GRAPHICS_ITEMS_INVALID")
    item_ids: set[str] = set()
    for item in items:
        _require(
            isinstance(item, Mapping),
            "GRAPHICS_ITEM_OBJECT_REQUIRED",
        )
        item_id = _string(item.get("item_id"))
        _require(
            item_id.startswith("GI-") and len(item_id) == 5,
            "GRAPHICS_ITEM_ID_INVALID",
        )
        _require(
            item_id not in item_ids,
            f"GRAPHICS_ITEM_ID_DUPLICATE:{item_id}",
        )
        item_ids.add(item_id)
        _require(
            isinstance(item.get("x"), (int, float))
            and 0 <= float(item["x"]) <= 1,
            f"GRAPHICS_ITEM_X_INVALID:{item_id}",
        )
        _require(
            isinstance(item.get("y"), (int, float))
            and 0 <= float(item["y"]) <= 1,
            f"GRAPHICS_ITEM_Y_INVALID:{item_id}",
        )
        parent = _string(item.get("parent_item_id"))
        if parent:
            _require(
                parent != item_id,
                f"GRAPHICS_SELF_PARENT_FORBIDDEN:{item_id}",
            )

    for item in items:
        parent = _string(item.get("parent_item_id"))
        if parent:
            _require(
                parent in item_ids,
                f"GRAPHICS_PARENT_UNKNOWN:{parent}",
            )

    source_ids = {
        _string(item)
        for item in _sequence(payload.get("source_ids"))
        if _string(item)
    }
    _require(source_ids, "GRAPHICS_SOURCE_IDS_REQUIRED")
    for item in items:
        item_id = _string(item.get("item_id"))
        item_source_ids = {
            _string(value)
            for value in _sequence(item.get("source_ids"))
            if _string(value)
        }
        _require(
            item_source_ids,
            f"GRAPHICS_ITEM_SOURCE_IDS_REQUIRED:{item_id}",
        )
        _require(
            item_source_ids.issubset(source_ids),
            f"GRAPHICS_ITEM_SOURCE_OUTSIDE_SPEC:{item_id}",
        )
    if known_source_ids is not None:
        _require(
            source_ids.issubset(known_source_ids),
            "GRAPHICS_UNKNOWN_SOURCE_REFERENCE",
        )

    animation = _string(payload.get("animation_style"))
    _require(
        animation in ANIMATION_STYLES,
        f"GRAPHICS_ANIMATION_STYLE_INVALID:{animation}",
    )
    background = payload.get("background")
    _require(
        isinstance(background, Mapping),
        "GRAPHICS_BACKGROUND_OBJECT_REQUIRED",
    )
    mode = _string(background.get("mode"))
    _require(
        mode in BACKGROUND_MODES,
        f"GRAPHICS_BACKGROUND_MODE_INVALID:{mode}",
    )
    opacity = background.get("overlay_opacity")
    _require(
        isinstance(opacity, (int, float))
        and 0 <= float(opacity) <= 1,
        "GRAPHICS_BACKGROUND_OVERLAY_INVALID",
    )

    design = payload.get("design")
    _require(
        isinstance(design, Mapping),
        "GRAPHICS_DESIGN_OBJECT_REQUIRED",
    )
    margin = design.get("safe_margin_px")
    _require(
        isinstance(margin, int) and 60 <= margin <= 180,
        "GRAPHICS_SAFE_MARGIN_INVALID",
    )
    _require(
        payload.get("music") == "FORBIDDEN",
        "GRAPHICS_MUSIC_FORBIDDEN",
    )
    _require(
        payload.get("sound_policy") == "SFX_ONLY_NO_MUSIC",
        "GRAPHICS_SOUND_POLICY_INVALID",
    )

    return LocalGraphicsSpec(payload=dict(payload))


def load_graphics_spec(
    path: Path,
    *,
    known_source_ids: set[str] | None = None,
) -> LocalGraphicsSpec:
    try:
        payload = json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalGraphicsSpecError(
            f"GRAPHICS_SPEC_READ_FAILED:{path}:{exc}"
        ) from exc
    if not isinstance(payload, Mapping):
        raise LocalGraphicsSpecError(
            "GRAPHICS_SPEC_OBJECT_REQUIRED"
        )
    return validate_graphics_spec(
        payload,
        known_source_ids=known_source_ids,
    )


def extract_storyboard_graphics_specs(
    storyboard: Mapping[str, Any],
    *,
    known_source_ids: set[str] | None = None,
) -> tuple[LocalGraphicsSpec, ...]:
    shots = storyboard.get("shots")
    _require(
        isinstance(shots, list),
        "STORYBOARD_SHOTS_REQUIRED",
    )
    result: list[LocalGraphicsSpec] = []
    seen_graphic_ids: set[str] = set()
    for shot in shots:
        _require(
            isinstance(shot, Mapping),
            "STORYBOARD_SHOT_OBJECT_REQUIRED",
        )
        treatment = _string(
            shot.get("final_budget_treatment")
        )
        spec_payload = shot.get("graphics_spec")
        if treatment == "GRAPHICS":
            _require(
                isinstance(spec_payload, Mapping),
                "GRAPHICS_SHOT_SPEC_REQUIRED",
            )
            spec = validate_graphics_spec(
                spec_payload,
                known_source_ids=known_source_ids,
            )
            _require(
                spec.shot_id == _string(shot.get("shot_id")),
                "GRAPHICS_SPEC_SHOT_ID_MISMATCH",
            )
            _require(
                spec.graphic_id not in seen_graphic_ids,
                f"GRAPHIC_ID_DUPLICATE:{spec.graphic_id}",
            )
            seen_graphic_ids.add(spec.graphic_id)
            result.append(spec)
        else:
            _require(
                spec_payload is None,
                "NON_GRAPHICS_SHOT_MUST_HAVE_NULL_GRAPHICS_SPEC",
            )
    _require(
        len(result) == 6,
        f"GRAPHICS_SHOT_COUNT_MUST_BE_6:{len(result)}",
    )
    return tuple(result)
