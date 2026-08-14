"""Presentation-only UX contracts for Shorts narration captions.

This module intentionally contains no Qt widgets, rendering, filesystem
mutation, provider transport, or production execution.  It gives the existing
Shorts surface a small, testable view-model contract while keeping caption
technical details separate from the user-facing toggle.  Longform receives an
explicit no-control model so a Shorts exception cannot leak into that surface.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
import re
from types import MappingProxyType
from typing import Any, Mapping, Sequence


SCHEMA_VERSION = "siraj-shorts-caption-ux-v1"
VISUAL_FIXTURE_SCHEMA_VERSION = "siraj-shorts-caption-visual-fixtures-v1"

SURFACE_SHORTS_PRODUCTION = "SHORTS_PRODUCTION"
SURFACE_SHORTS_REVIEW = "SHORTS_REVIEW"
SURFACE_LONGFORM = "LONGFORM"
SHORTS_SURFACES = frozenset({SURFACE_SHORTS_PRODUCTION, SURFACE_SHORTS_REVIEW})

CAPTIONS_DEFAULT_ENABLED = True
CAPTION_FRAME_WIDTH = 1080
CAPTION_FRAME_HEIGHT = 1920
CAPTION_ASPECT_RATIO = "9:16"
CAPTION_MAX_LINES = 2

CAPTION_LABELS_AR = MappingProxyType(
    {
        "toggle": "التسميات التوضيحية",
        "enabled": "مفعلة",
        "disabled": "متوقفة",
        "technical_details": "التفاصيل التقنية",
        "timing_source": "مصدر التوقيت",
        "cue_count": "عدد المقاطع النصية",
        "status": "حالة التسميات",
    }
)

REQUIRED_VISUAL_SCENARIOS = (
    "arabic",
    "long_sentence",
    "arabic_english",
    "arabic_numbers",
    "two_lines",
    "subject_near_bottom",
    "subject_center",
    "subject_right",
    "subject_left",
    "bright_background",
    "dark_background",
    "fallback_placement",
    "impossible_placement",
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_ALLOWED_CONTENT_PROFILES = frozenset(
    {"ARABIC", "LONG_SENTENCE", "ARABIC_ENGLISH", "ARABIC_NUMBERS", "TWO_LINES"}
)
_ALLOWED_SUBJECT_POSITIONS = frozenset(
    {"NONE", "CENTER", "NEAR_BOTTOM", "RIGHT", "LEFT"}
)
_ALLOWED_BACKGROUNDS = frozenset({"NEUTRAL", "BRIGHT", "DARK"})
_ALLOWED_PLACEMENTS = frozenset({"PRIMARY_SAFE", "FALLBACK_SAFE", "NONE"})


class CaptionUxContractError(ValueError):
    """Raised when presentation data cannot be represented safely."""


class CaptionVisualFixtureError(CaptionUxContractError):
    """Raised when the local visual-fixture manifest is incomplete or unsafe."""


def _required_string(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CaptionUxContractError(f"{field_name}:NON_EMPTY_STRING_REQUIRED")
    return value.strip()


def _nonnegative_int(value: Any, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CaptionUxContractError(f"{field_name}:NON_NEGATIVE_INTEGER_REQUIRED")
    return value


def _optional_sha256(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise CaptionUxContractError(f"{field_name}:SHA256_REQUIRED")
    return value


@dataclass(frozen=True, slots=True)
class CaptionTechnicalDetails:
    """Small technical summary safe to show in an expandable details area."""

    timing_source: str
    cue_count: int
    status: str
    source_sha256: str | None = None
    transcript_sha256: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "timing_source", _required_string(self.timing_source, "timing_source"))
        object.__setattr__(self, "cue_count", _nonnegative_int(self.cue_count, "cue_count"))
        object.__setattr__(self, "status", _required_string(self.status, "status"))
        object.__setattr__(self, "source_sha256", _optional_sha256(self.source_sha256, "source_sha256"))
        object.__setattr__(self, "transcript_sha256", _optional_sha256(self.transcript_sha256, "transcript_sha256"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CaptionTechnicalDetails":
        """Build details from an adapter payload without accepting cue arrays."""

        if not isinstance(value, Mapping):
            raise CaptionUxContractError("technical_details:OBJECT_REQUIRED")
        timing_source = value.get("timing_source", value.get("timing_source_type"))
        status = value.get("status", value.get("caption_status"))
        return cls(
            timing_source=timing_source,
            cue_count=value.get("cue_count"),
            status=status,
            source_sha256=value.get("source_sha256", value.get("timing_source_sha256")),
            transcript_sha256=value.get("transcript_sha256"),
        )

    def to_dict(self) -> dict[str, Any]:
        """Return technical metadata only; raw cue JSON is never part of it."""

        payload: dict[str, Any] = {
            "timing_source": self.timing_source,
            "cue_count": self.cue_count,
            "status": self.status,
        }
        if self.source_sha256 is not None:
            payload["source_sha256"] = self.source_sha256
        if self.transcript_sha256 is not None:
            payload["transcript_sha256"] = self.transcript_sha256
        return payload


@dataclass(frozen=True, slots=True)
class ShortsCaptionUxViewModel:
    """User-facing Shorts production/review state."""

    surface: str
    captions_enabled: bool
    technical_details: CaptionTechnicalDetails
    schema_version: str = SCHEMA_VERSION
    toggle_visible: bool = True
    technical_details_visible: bool = True
    raw_cue_json_visible: bool = False

    def __post_init__(self) -> None:
        if self.surface not in SHORTS_SURFACES:
            raise CaptionUxContractError("surface:SHORTS_SURFACE_REQUIRED")
        if not isinstance(self.captions_enabled, bool):
            raise CaptionUxContractError("captions_enabled:BOOLEAN_REQUIRED")
        if not isinstance(self.technical_details, CaptionTechnicalDetails):
            raise CaptionUxContractError("technical_details:CAPTION_DETAILS_REQUIRED")
        if self.raw_cue_json_visible:
            raise CaptionUxContractError("raw_cue_json:FORBIDDEN_IN_MAIN_UI")

    @property
    def toggle_label(self) -> str:
        return str(CAPTION_LABELS_AR["toggle"])

    @property
    def state_label(self) -> str:
        key = "enabled" if self.captions_enabled else "disabled"
        return str(CAPTION_LABELS_AR[key])

    def with_captions_enabled(self, enabled: bool) -> "ShortsCaptionUxViewModel":
        """Apply the explicit human toggle without changing technical evidence."""

        if not isinstance(enabled, bool):
            raise CaptionUxContractError("captions_enabled:BOOLEAN_REQUIRED")
        return ShortsCaptionUxViewModel(
            surface=self.surface,
            captions_enabled=enabled,
            technical_details=self.technical_details,
            schema_version=self.schema_version,
            toggle_visible=self.toggle_visible,
            technical_details_visible=self.technical_details_visible,
            raw_cue_json_visible=False,
        )

    def to_public_dict(self) -> dict[str, Any]:
        """Serialize the main UI contract without raw cues or cue JSON."""

        return {
            "schema_version": self.schema_version,
            "surface": self.surface,
            "captions_enabled": self.captions_enabled,
            "toggle_visible": self.toggle_visible,
            "toggle_label": self.toggle_label,
            "state_label": self.state_label,
            "technical_details_visible": self.technical_details_visible,
            "technical_details": self.technical_details.to_dict(),
            "raw_cue_json_visible": False,
        }


@dataclass(frozen=True, slots=True)
class LongformCaptionUxViewModel:
    """Explicit longform no-caption-control contract."""

    surface: str = SURFACE_LONGFORM
    schema_version: str = SCHEMA_VERSION
    caption_control_visible: bool = False
    raw_cue_json_visible: bool = False

    def __post_init__(self) -> None:
        if self.surface != SURFACE_LONGFORM:
            raise CaptionUxContractError("surface:LONGFORM_REQUIRED")
        if self.caption_control_visible:
            raise CaptionUxContractError("longform_caption_control:FORBIDDEN")
        if self.raw_cue_json_visible:
            raise CaptionUxContractError("raw_cue_json:FORBIDDEN_IN_MAIN_UI")

    def to_public_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "surface": self.surface,
            "caption_control_visible": False,
            "raw_cue_json_visible": False,
        }


def build_shorts_caption_ux_view_model(
    surface: str,
    technical_details: CaptionTechnicalDetails | Mapping[str, Any],
    *,
    captions_enabled: bool = CAPTIONS_DEFAULT_ENABLED,
) -> ShortsCaptionUxViewModel:
    """Create the small Shorts-only model used by production and review views."""

    details = technical_details if isinstance(technical_details, CaptionTechnicalDetails) else CaptionTechnicalDetails.from_mapping(technical_details)
    return ShortsCaptionUxViewModel(
        surface=surface,
        captions_enabled=captions_enabled,
        technical_details=details,
    )


def build_longform_caption_ux_view_model() -> LongformCaptionUxViewModel:
    """Return a model that deliberately exposes no longform caption control."""

    return LongformCaptionUxViewModel()


def build_caption_ux_view_model(
    surface: str,
    technical_details: CaptionTechnicalDetails | Mapping[str, Any] | None = None,
    *,
    captions_enabled: bool = CAPTIONS_DEFAULT_ENABLED,
) -> ShortsCaptionUxViewModel | LongformCaptionUxViewModel:
    """Dispatch the presentation contract without a Shorts policy bypass."""

    if surface == SURFACE_LONGFORM:
        if technical_details is not None:
            raise CaptionUxContractError("longform_technical_details:NOT_A_MAIN_UI_CONTROL")
        return build_longform_caption_ux_view_model()
    if surface in SHORTS_SURFACES:
        if technical_details is None:
            raise CaptionUxContractError("shorts_technical_details:REQUIRED")
        return build_shorts_caption_ux_view_model(
            surface,
            technical_details,
            captions_enabled=captions_enabled,
        )
    raise CaptionUxContractError("surface:UNKNOWN")


@dataclass(frozen=True, slots=True)
class CaptionVisualFixture:
    """A descriptor for one local, non-production visual QA scenario."""

    scenario_id: str
    content_profile: str
    subject_position: str
    background: str
    expected_placement: str
    expected_result: str
    expected_max_lines: int = CAPTION_MAX_LINES

    def __post_init__(self) -> None:
        object.__setattr__(self, "scenario_id", _required_string(self.scenario_id, "scenario_id"))
        if self.content_profile not in _ALLOWED_CONTENT_PROFILES:
            raise CaptionVisualFixtureError("content_profile:UNSUPPORTED")
        if self.subject_position not in _ALLOWED_SUBJECT_POSITIONS:
            raise CaptionVisualFixtureError("subject_position:UNSUPPORTED")
        if self.background not in _ALLOWED_BACKGROUNDS:
            raise CaptionVisualFixtureError("background:UNSUPPORTED")
        if self.expected_placement not in _ALLOWED_PLACEMENTS:
            raise CaptionVisualFixtureError("expected_placement:UNSUPPORTED")
        object.__setattr__(self, "expected_result", _required_string(self.expected_result, "expected_result"))
        if (
            isinstance(self.expected_max_lines, bool)
            or not isinstance(self.expected_max_lines, int)
            or self.expected_max_lines != CAPTION_MAX_LINES
        ):
            raise CaptionVisualFixtureError("expected_max_lines:CAPTION_MAX_LINES_REQUIRED")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "CaptionVisualFixture":
        if not isinstance(value, Mapping):
            raise CaptionVisualFixtureError("scenario:OBJECT_REQUIRED")
        return cls(
            scenario_id=value.get("id"),
            content_profile=value.get("content_profile"),
            subject_position=value.get("subject_position"),
            background=value.get("background"),
            expected_placement=value.get("expected_placement"),
            expected_result=value.get("expected_result"),
            expected_max_lines=value.get("expected_max_lines", CAPTION_MAX_LINES),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.scenario_id,
            "content_profile": self.content_profile,
            "subject_position": self.subject_position,
            "background": self.background,
            "expected_placement": self.expected_placement,
            "expected_result": self.expected_result,
            "expected_max_lines": self.expected_max_lines,
        }


@dataclass(frozen=True, slots=True)
class CaptionVisualFixtureManifest:
    """Validated local visual QA manifest; it never represents a production render."""

    schema_version: str
    width: int
    height: int
    aspect_ratio: str
    scenarios: tuple[CaptionVisualFixture, ...]
    max_lines: int = CAPTION_MAX_LINES

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "width": self.width,
            "height": self.height,
            "aspect_ratio": self.aspect_ratio,
            "max_lines": self.max_lines,
            "scenarios": [scenario.to_dict() for scenario in self.scenarios],
        }


_REQUIRED_SCENARIO_CONTRACT: Mapping[str, Mapping[str, str]] = MappingProxyType(
    {
        "arabic": {"content_profile": "ARABIC"},
        "long_sentence": {"content_profile": "LONG_SENTENCE"},
        "arabic_english": {"content_profile": "ARABIC_ENGLISH"},
        "arabic_numbers": {"content_profile": "ARABIC_NUMBERS"},
        "two_lines": {"content_profile": "TWO_LINES"},
        "subject_near_bottom": {"subject_position": "NEAR_BOTTOM"},
        "subject_center": {"subject_position": "CENTER"},
        "subject_right": {"subject_position": "RIGHT"},
        "subject_left": {"subject_position": "LEFT"},
        "bright_background": {"background": "BRIGHT"},
        "dark_background": {"background": "DARK"},
        "fallback_placement": {
            "expected_placement": "FALLBACK_SAFE",
            "expected_result": "FALLBACK_PLACEMENT",
        },
        "impossible_placement": {
            "expected_placement": "NONE",
            "expected_result": "CAPTION_PLACEMENT_BLOCKED",
        },
    }
)


def parse_visual_fixture_manifest(value: Mapping[str, Any]) -> CaptionVisualFixtureManifest:
    """Parse and fail closed on dimensions or missing visual-QA scenarios."""

    if not isinstance(value, Mapping):
        raise CaptionVisualFixtureError("manifest:OBJECT_REQUIRED")
    if value.get("schema_version") != VISUAL_FIXTURE_SCHEMA_VERSION:
        raise CaptionVisualFixtureError("schema_version:UNSUPPORTED")
    width = value.get("width")
    height = value.get("height")
    if (
        isinstance(width, bool)
        or isinstance(height, bool)
        or not isinstance(width, int)
        or not isinstance(height, int)
        or width != CAPTION_FRAME_WIDTH
        or height != CAPTION_FRAME_HEIGHT
    ):
        raise CaptionVisualFixtureError("frame:1080X1920_REQUIRED")
    if value.get("aspect_ratio") != CAPTION_ASPECT_RATIO:
        raise CaptionVisualFixtureError("aspect_ratio:9_16_REQUIRED")
    max_lines = value.get("max_lines", CAPTION_MAX_LINES)
    if isinstance(max_lines, bool) or not isinstance(max_lines, int) or max_lines != CAPTION_MAX_LINES:
        raise CaptionVisualFixtureError("max_lines:2_REQUIRED")
    raw_scenarios = value.get("scenarios")
    if not isinstance(raw_scenarios, Sequence) or isinstance(raw_scenarios, (str, bytes, bytearray)):
        raise CaptionVisualFixtureError("scenarios:ARRAY_REQUIRED")
    scenarios = tuple(CaptionVisualFixture.from_mapping(item) for item in raw_scenarios)
    ids = [scenario.scenario_id for scenario in scenarios]
    if len(ids) != len(set(ids)):
        raise CaptionVisualFixtureError("scenarios:DUPLICATE_ID")
    by_id = {scenario.scenario_id: scenario for scenario in scenarios}
    missing = [scenario_id for scenario_id in REQUIRED_VISUAL_SCENARIOS if scenario_id not in by_id]
    if missing:
        raise CaptionVisualFixtureError(f"scenarios:MISSING:{','.join(missing)}")
    for scenario_id, expected in _REQUIRED_SCENARIO_CONTRACT.items():
        scenario = by_id[scenario_id]
        for field_name, expected_value in expected.items():
            if getattr(scenario, field_name) != expected_value:
                raise CaptionVisualFixtureError(f"scenario:{scenario_id}:{field_name}:CONTRACT_MISMATCH")
    return CaptionVisualFixtureManifest(
        schema_version=VISUAL_FIXTURE_SCHEMA_VERSION,
        width=width,
        height=height,
        aspect_ratio=CAPTION_ASPECT_RATIO,
        max_lines=max_lines,
        scenarios=scenarios,
    )


def load_visual_fixture_manifest(path: Path) -> CaptionVisualFixtureManifest:
    """Load only a local JSON descriptor; no image or video is opened."""

    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CaptionVisualFixtureError("manifest:READ_FAILED") from exc
    return parse_visual_fixture_manifest(value)


def validate_visual_fixture_manifest(value: Mapping[str, Any]) -> CaptionVisualFixtureManifest:
    """Named validation entry point for tests and the later desktop integrator."""

    return parse_visual_fixture_manifest(value)


__all__ = [
    "CAPTION_ASPECT_RATIO",
    "CAPTION_FRAME_HEIGHT",
    "CAPTION_FRAME_WIDTH",
    "CAPTION_LABELS_AR",
    "CAPTION_MAX_LINES",
    "CAPTIONS_DEFAULT_ENABLED",
    "CaptionTechnicalDetails",
    "CaptionUxContractError",
    "CaptionVisualFixture",
    "CaptionVisualFixtureError",
    "CaptionVisualFixtureManifest",
    "LongformCaptionUxViewModel",
    "REQUIRED_VISUAL_SCENARIOS",
    "SCHEMA_VERSION",
    "SHORTS_SURFACES",
    "SURFACE_LONGFORM",
    "SURFACE_SHORTS_PRODUCTION",
    "SURFACE_SHORTS_REVIEW",
    "VISUAL_FIXTURE_SCHEMA_VERSION",
    "ShortsCaptionUxViewModel",
    "build_caption_ux_view_model",
    "build_longform_caption_ux_view_model",
    "build_shorts_caption_ux_view_model",
    "load_visual_fixture_manifest",
    "parse_visual_fixture_manifest",
    "validate_visual_fixture_manifest",
]
