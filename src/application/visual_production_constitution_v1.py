"""Reusable visual-production constitution and storyboard safety checks.

The constitution is intentionally series-level.  Episode-specific planning
belongs in the storyboard artifact; this module only enforces the production
mode's immutable safety and review boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping, Sequence


CONSTITUTION_VERSION = "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V1"
CONSTITUTION_RELATIVE_PATH = Path(
    "projects/_series/siraj-visual-production-constitution-v1.json"
)

_REQUIRED_BOOLEAN_KEYS = (
    "AUDIO_IS_DURATION_AUTHORITY",
    "LITERAL_MAJOR_EVENT_VISUALIZATION_REQUIRED",
    "MUTE_COMPREHENSION_REQUIRED",
    "GRAPHICS_FORBIDDEN",
    "DIAGRAMS_FORBIDDEN",
    "UI_GRAPHICS_FORBIDDEN",
    "ABSTRACT_EXPLAINER_GRAPHICS_FORBIDDEN",
    "LOCAL_GRAPHICS_FORBIDDEN",
    "PLACEHOLDERS_FORBIDDEN",
    "AMBIGUOUS_EVENT_SUBSTITUTION_FORBIDDEN",
    "EXTRA_CHARACTERS_FORBIDDEN",
    "STORYBOARD_HUMAN_APPROVAL_REQUIRED_BEFORE_VISUAL_GENERATION",
    "VISUAL_GENERATION_BLOCKED_UNTIL_APPROVED_STORYBOARD_HASH",
    "AUTOMATIC_PAID_RETRY",
    "AUTOMATIC_PAID_RESUBMISSION",
    "NO_PROVIDER_CALLS_IN_PREPRODUCTION",
    "NO_NETWORK_CALLS_IN_PREPRODUCTION",
)

_REQUIRED_FEMALE_KEYS = (
    "FEMALE_VISIBLE_HAIR",
    "FEMALE_VISIBLE_NECK",
    "FEMALE_VISIBLE_ARMS",
    "FEMALE_VISIBLE_LEGS",
    "FEMALE_VISIBLE_TORSO_SKIN",
    "FEMALE_BODY_CONTOUR_EMPHASIS",
    "TIGHT_CLOTHING",
    "TRANSPARENT_CLOTHING",
    "REVEALING_CLOTHING",
    "NUDE_OR_BODY_SHAPED_SILHOUETTE",
    "VISIBLE_HANDS_PREFERRED",
)


class ConstitutionValidationError(ValueError):
    """Raised when the central constitution is incomplete or weakened."""


@dataclass(frozen=True, slots=True)
class VisualProductionConstitution:
    data: dict[str, Any]
    path: Path
    sha256: str

    @property
    def version(self) -> str:
        return str(self.data["CONSTITUTION_VERSION"])


def _sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def validate_constitution_mapping(data: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if data.get("CONSTITUTION_VERSION") != CONSTITUTION_VERSION:
        errors.append("CONSTITUTION_VERSION_INVALID")
    if data.get("STATUS") != "ACTIVE":
        errors.append("CONSTITUTION_STATUS_NOT_ACTIVE")
    for key in _REQUIRED_BOOLEAN_KEYS:
        if not isinstance(data.get(key), bool):
            errors.append(f"{key}_MUST_BE_BOOLEAN")
    female = data.get("FEMALE_MODESTY_MAXIMUM_STRICT")
    if not isinstance(female, Mapping):
        errors.append("FEMALE_MODESTY_MAXIMUM_STRICT_MISSING")
    else:
        for key in _REQUIRED_FEMALE_KEYS:
            if not isinstance(female.get(key), bool):
                errors.append(f"FEMALE_MODESTY_MAXIMUM_STRICT.{key}_MUST_BE_BOOLEAN")
        if female.get("VISIBLE_HANDS_PREFERRED") is not False:
            errors.append("VISIBLE_HANDS_PREFERRED_MUST_BE_FALSE")
        if female.get("REQUIRED_CLOTHING") in (None, ""):
            errors.append("REQUIRED_CLOTHING_MISSING")
    for key in (
        "GRAPHICS_FORBIDDEN",
        "DIAGRAMS_FORBIDDEN",
        "UI_GRAPHICS_FORBIDDEN",
        "ABSTRACT_EXPLAINER_GRAPHICS_FORBIDDEN",
        "LOCAL_GRAPHICS_FORBIDDEN",
        "PLACEHOLDERS_FORBIDDEN",
        "AMBIGUOUS_EVENT_SUBSTITUTION_FORBIDDEN",
        "EXTRA_CHARACTERS_FORBIDDEN",
        "STORYBOARD_HUMAN_APPROVAL_REQUIRED_BEFORE_VISUAL_GENERATION",
        "VISUAL_GENERATION_BLOCKED_UNTIL_APPROVED_STORYBOARD_HASH",
        "NO_PROVIDER_CALLS_IN_PREPRODUCTION",
        "NO_NETWORK_CALLS_IN_PREPRODUCTION",
    ):
        if data.get(key) is not True:
            errors.append(f"{key}_MUST_BE_TRUE")
    if data.get("AUTOMATIC_PAID_RETRY") is not False:
        errors.append("AUTOMATIC_PAID_RETRY_MUST_BE_FALSE")
    if data.get("AUTOMATIC_PAID_RESUBMISSION") is not False:
        errors.append("AUTOMATIC_PAID_RESUBMISSION_MUST_BE_FALSE")
    return errors


def load_visual_production_constitution(
    repo_root: Path,
    path: Path | None = None,
) -> VisualProductionConstitution:
    repo = Path(repo_root).resolve()
    constitution_path = (path or (repo / CONSTITUTION_RELATIVE_PATH)).resolve()
    raw = constitution_path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    errors = validate_constitution_mapping(data)
    if errors:
        raise ConstitutionValidationError(";".join(errors))
    return VisualProductionConstitution(
        data=dict(data),
        path=constitution_path,
        sha256=_sha256_bytes(raw),
    )


def _female_appendix(constitution: VisualProductionConstitution) -> str:
    female = constitution.data["FEMALE_MODESTY_MAXIMUM_STRICT"]
    return (
        "FEMALE_MODESTY_MAXIMUM_STRICT=TRUE; "
        "FEMALE_VISIBLE_HAIR=FORBIDDEN; FEMALE_VISIBLE_NECK=FORBIDDEN; "
        "FEMALE_VISIBLE_ARMS=FORBIDDEN; FEMALE_VISIBLE_LEGS=FORBIDDEN; "
        "FEMALE_VISIBLE_TORSO_SKIN=FORBIDDEN; "
        "FEMALE_BODY_CONTOUR_EMPHASIS=FORBIDDEN; TIGHT_CLOTHING=FORBIDDEN; "
        "TRANSPARENT_CLOTHING=FORBIDDEN; REVEALING_CLOTHING=FORBIDDEN; "
        "NUDE_OR_BODY_SHAPED_SILHOUETTE=FORBIDDEN; "
        f"VISIBLE_HANDS_PREFERRED={female['VISIBLE_HANDS_PREFERRED']}; "
        f"REQUIRED_CLOTHING={female['REQUIRED_CLOTHING']}."
    )


def constitution_prompt_appendix(
    constitution: VisualProductionConstitution,
    *,
    includes_female: bool,
) -> str:
    lines = [
        f"CONSTITUTION_VERSION={constitution.version}",
        "AUDIO_IS_DURATION_AUTHORITY=TRUE; VISUALS_MAY_NOT_EXTEND_EPISODE=TRUE;",
        "LITERAL_MAJOR_EVENT_VISUALIZATION_REQUIRED=TRUE; MUTE_COMPREHENSION_REQUIRED=TRUE;",
        "GRAPHICS_ALLOWED=FALSE; DIAGRAMS_ALLOWED=FALSE; UI_GRAPHICS_ALLOWED=FALSE;",
        "ABSTRACT_EXPLAINER_GRAPHICS_ALLOWED=FALSE; LOCAL_GRAPHICS_ALLOWED=FALSE;",
        "PLACEHOLDER_VISUALS_ALLOWED=FALSE; AMBIGUOUS_EVENT_SUBSTITUTION=FORBIDDEN;",
        "EXTRA_CHARACTERS=FORBIDDEN; no text, captions, logos, watermark, chart, UI, or explainer panel.",
    ]
    if includes_female:
        lines.append(_female_appendix(constitution))
        lines.append(
            "If compliant female representation is not reliable, use a fully covered rear/distant composition or remove the female figure; do not expose skin or a body-shaped silhouette."
        )
    else:
        lines.append("NO_FEMALE_SUBJECT_IN_FRAME unless the strict female contract is applied.")
    lines.append("STORYBOARD_HUMAN_APPROVAL_REQUIRED_BEFORE_VISUAL_GENERATION=TRUE.")
    return " ".join(lines)


def compile_visual_prompt(
    constitution: VisualProductionConstitution,
    positive_prompt: str,
    negative_prompt: str,
    *,
    includes_female: bool,
) -> dict[str, str]:
    if not positive_prompt.strip():
        raise ValueError("POSITIVE_PROMPT_EMPTY")
    if not negative_prompt.strip():
        raise ValueError("NEGATIVE_PROMPT_EMPTY")
    appendix = constitution_prompt_appendix(
        constitution,
        includes_female=includes_female,
    )
    return {
        "positive_prompt": positive_prompt.strip() + "\n\n" + appendix,
        "negative_prompt": negative_prompt.strip()
        + "\n"
        + "GRAPHICS, diagrams, UI, explainer panels, placeholder frames, readable text, logos, watermark, symbolic substitution for the visible action, extra characters, continuity changes.",
    }


def validate_repair_storyboard(
    storyboard: Mapping[str, Any],
    constitution: VisualProductionConstitution,
) -> dict[str, Any]:
    errors: list[str] = []
    checks: dict[str, bool] = {}
    errors.extend(validate_constitution_mapping(constitution.data))
    checks["constitution_loaded"] = not errors
    if storyboard.get("AUDIO_IS_DURATION_AUTHORITY") is not True:
        errors.append("AUDIO_IS_DURATION_AUTHORITY_FALSE")
    if storyboard.get("VISUAL_GENERATION_ALLOWED") is not False:
        errors.append("VISUAL_GENERATION_MUST_BE_FALSE")
    if storyboard.get("APPROVED_STORYBOARD_SHA256") is not None:
        errors.append("APPROVED_STORYBOARD_SHA256_MUST_BE_NULL")
    if storyboard.get("PLANNED_GRAPHICS_COUNT") != 0:
        errors.append("PLANNED_GRAPHICS_COUNT_MUST_BE_ZERO")
    shots = storyboard.get("timeline_shots")
    if not isinstance(shots, Sequence) or isinstance(shots, (str, bytes)) or not shots:
        errors.append("TIMELINE_SHOTS_MISSING")
        shots = []
    previous_end: float | None = None
    for index, shot in enumerate(shots):
        if not isinstance(shot, Mapping):
            errors.append(f"SHOT_{index}_NOT_OBJECT")
            continue
        for key in (
            "SHOT_ID",
            "START_TIME",
            "END_TIME",
            "DURATION",
            "NARRATION_TEXT",
            "EVENT_ID",
            "EVENT_TYPE",
            "DISPOSITION",
            "VISIBLE_ACTION",
            "MUTE_COMPREHENSION_TARGET",
        ):
            if key not in shot:
                errors.append(f"{shot.get('SHOT_ID', index)}_{key}_MISSING")
        start = shot.get("START_TIME")
        end = shot.get("END_TIME")
        if isinstance(start, (int, float)) and isinstance(end, (int, float)):
            if end <= start or abs((end - start) - float(shot.get("DURATION", -1))) > 0.002:
                errors.append(f"{shot.get('SHOT_ID', index)}_TIME_RANGE_INVALID")
            if previous_end is not None and abs(start - previous_end) > 0.002:
                errors.append(f"{shot.get('SHOT_ID', index)}_TIMELINE_GAP_OR_OVERLAP")
            previous_end = end
        if shot.get("EVENT_TYPE") == "LITERAL_EVENT":
            if not shot.get("VISIBLE_ACTION") or not shot.get("MUTE_COMPREHENSION_TARGET"):
                errors.append(f"{shot.get('SHOT_ID', index)}_LITERAL_CONTRACT_INCOMPLETE")
        if shot.get("SOURCE") == "NEW_GENERATION_REQUIRED":
            compiled = shot.get("COMPILED_PROMPT")
            if not isinstance(compiled, Mapping):
                errors.append(f"{shot.get('SHOT_ID', index)}_COMPILED_PROMPT_MISSING")
            else:
                positive = str(compiled.get("positive_prompt", ""))
                if "GRAPHICS_ALLOWED=FALSE" not in positive:
                    errors.append(f"{shot.get('SHOT_ID', index)}_PROMPT_NOT_COMPILED")
                if shot.get("FEMALE_MODESTY_REQUIREMENTS") not in (None, "", "NOT_APPLICABLE"):
                    if "FEMALE_MODESTY_MAXIMUM_STRICT=TRUE" not in positive:
                        errors.append(f"{shot.get('SHOT_ID', index)}_FEMALE_RULE_NOT_COMPILED")
    checks["timeline_contiguous"] = not any("GAP_OR_OVERLAP" in e for e in errors)
    checks["literal_contracts_complete"] = not any("LITERAL_CONTRACT" in e for e in errors)
    checks["compiled_prompts_safe"] = not any("PROMPT_" in e or "FEMALE_RULE" in e for e in errors)
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checks": checks,
    }

