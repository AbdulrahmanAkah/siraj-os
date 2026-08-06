"""World, location, and unseen-realm continuity validation for Siraj."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from src.application.series_production_quality_v2 import (
    RepresentationMode,
    SceneDomain,
    SeriesProductionQualityError,
)

SCHEMA_VERSION = "siraj-world-continuity-policy-v1"

_EARTHLIKE_TERMS = (
    "blue sky",
    "sunlit valley",
    "ordinary mountain",
    "earth landscape",
    "سماء زرقاء",
    "وادٍ أرضي",
    "وادي أرضي",
    "شمس مألوفة",
    "جبال أرضية",
)


class WorldContinuityError(SeriesProductionQualityError):
    pass


@dataclass(frozen=True, slots=True)
class WorldContinuityIssue:
    code: str
    shot_id: str
    detail: str
    severity: str = "BLOCKING"

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "shot_id": self.shot_id,
            "detail": self.detail,
            "severity": self.severity,
        }


def _shots(storyboard: Mapping[str, Any]) -> Sequence[Any]:
    value = storyboard.get("shots")
    return value if isinstance(value, list) else ()


def validate_world_continuity(
    storyboard: Mapping[str, Any],
) -> tuple[WorldContinuityIssue, ...]:
    issues: list[WorldContinuityIssue] = []
    prior_domain: str | None = None
    prior_location: str | None = None
    for index, raw in enumerate(_shots(storyboard), start=1):
        if not isinstance(raw, Mapping):
            issues.append(
                WorldContinuityIssue(
                    "SHOT_OBJECT_REQUIRED",
                    f"INDEX-{index}",
                    "Storyboard shot must be an object.",
                )
            )
            continue
        shot_id = str(raw.get("shot_id") or f"INDEX-{index}")
        domain = str(raw.get("scene_domain") or "")
        location = str(raw.get("character_location") or "")
        transition = str(raw.get("location_transition") or "")
        representation = str(raw.get("representation_mode") or "")
        visual = " ".join(
            str(raw.get(key) or "")
            for key in (
                "label_ar",
                "visual_brief_ar",
                "positive_prompt",
                "negative_prompt",
            )
        ).lower()

        if domain not in {item.value for item in SceneDomain}:
            issues.append(
                WorldContinuityIssue(
                    "SCENE_DOMAIN_REQUIRED",
                    shot_id,
                    "Every shot requires an explicit valid scene_domain.",
                )
            )
        if not location:
            issues.append(
                WorldContinuityIssue(
                    "CHARACTER_LOCATION_REQUIRED",
                    shot_id,
                    "Every shot requires character_location, including NONE.",
                )
            )
        if (
            prior_domain is not None
            and domain
            and domain != prior_domain
            and not transition
        ):
            issues.append(
                WorldContinuityIssue(
                    "UNPLANNED_LOCATION_TRANSITION",
                    shot_id,
                    f"Domain changed from {prior_domain} to {domain} without transition.",
                )
            )
        if (
            prior_location not in (None, "", "NONE")
            and location not in ("", "NONE", prior_location)
            and not transition
        ):
            issues.append(
                WorldContinuityIssue(
                    "CHARACTER_LOCATION_CONTINUITY_VIOLATION",
                    shot_id,
                    f"Character moved from {prior_location} to {location} without transition.",
                )
            )
        if domain == SceneDomain.HEAVENLY_UNSEEN_SYMBOLIC.value:
            if representation != RepresentationMode.SYMBOLIC_UNSEEN.value:
                issues.append(
                    WorldContinuityIssue(
                        "UNSEEN_REPRESENTATION_MODE_INVALID",
                        shot_id,
                        "Heavenly/unseen scenes must use SYMBOLIC_UNSEEN.",
                    )
                )
            if raw.get("earthly_visual_default") is True or any(
                term in visual for term in _EARTHLIKE_TERMS
            ):
                issues.append(
                    WorldContinuityIssue(
                        "UNSEEN_REALM_TOO_EARTHLIKE",
                        shot_id,
                        "Unseen scene defaults to familiar earthly geography.",
                    )
                )
            if str(raw.get("representation_claim") or "") != (
                "SYMBOLIC_NON_DEFINITIVE"
            ):
                issues.append(
                    WorldContinuityIssue(
                        "RELIGIOUS_REPRESENTATION_RISK",
                        shot_id,
                        "Unseen imagery must be explicitly symbolic and non-definitive.",
                    )
                )
        if domain:
            prior_domain = domain
        if location:
            prior_location = location
    return tuple(issues)


def assert_world_continuity(storyboard: Mapping[str, Any]) -> None:
    issues = validate_world_continuity(storyboard)
    blocking = [item for item in issues if item.severity == "BLOCKING"]
    if blocking:
        codes = ",".join(item.code for item in blocking)
        raise WorldContinuityError(f"WORLD_CONTINUITY_BLOCKED:{codes}")
