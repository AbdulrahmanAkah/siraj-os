"""Series-wide visual production constitution V2.

This module is deliberately episode-agnostic.  It provides the fail-closed
load, source/character gates, prompt compiler, micro-shot validator, and
approval gate used by episode planning.  It does not call a provider and it
does not create or consume a production authorization.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


CONSTITUTION_VERSION = "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2"
CONSTITUTION_RELATIVE_PATH = Path(
    "projects/_series/siraj-visual-production-constitution-v2.json"
)
CONSTITUTION_V2_1_VERSION = "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2_1"
CONSTITUTION_V2_1_RELATIVE_PATH = Path(
    "projects/_series/siraj-visual-production-constitution-v2-1.json"
)
CONSTITUTION_V2_2_VERSION = "SIRAJ_VISUAL_PRODUCTION_CONSTITUTION_V2_2"
CONSTITUTION_V2_2_RELATIVE_PATH = Path(
    "projects/_series/siraj-visual-production-constitution-v2-2.json"
)

_TRUE_KEYS = (
    "CONSTITUTION_LOAD_MANDATORY",
    "FAIL_CLOSED",
    "AUDIO_IS_DURATION_AUTHORITY",
    "FINAL_NARRATION_MASTER_IS_EPISODE_DURATION_AUTHORITY",
    "VISUALS_MAY_NOT_EXTEND_EPISODE",
    "VISUALS_MAY_NOT_CHANGE_AUDIO_DURATION",
    "VISUALS_MUST_FIT_AUDIO_TIMELINE",
    "MANDATORY_STORYBOARD_BEFORE_GENERATION",
    "STORYBOARD_HUMAN_APPROVAL_REQUIRED_BEFORE_VISUAL_GENERATION",
    "VISUAL_GENERATION_BLOCKED_UNTIL_APPROVED_STORYBOARD_HASH",
    "REQUIRE_APPROVED_STORYBOARD_HASH_TO_GENERATE",
    "LITERAL_VISUALIZATION_MUST_NOT_INVENT_UNSPECIFIED_SOURCE_FACTS",
    "LOWER_SOURCE_TIER_MAY_NOT_OVERRIDE_HIGHER_TIER",
    "NO_PROVIDER_CALLS_IN_PREPRODUCTION",
    "NO_NETWORK_CALLS_IN_PREPRODUCTION",
    "NO_AUTHORIZATION_CREATION_OR_CONSUMPTION_IN_PREPRODUCTION",
    "NO_MONTAGE_IN_PREPRODUCTION",
)

_FALSE_KEYS = (
    "FILLER_FOR_DURATION",
    "LOOP_FOR_DURATION",
    "FREEZE_FRAME_FILLER",
    "GRAPHICS_FOR_DURATION",
    "AUDIO_STRETCH_FOR_VISUALS",
    "AUTOMATIC_PAID_RETRY",
    "AUTOMATIC_PAID_RESUBMISSION",
)

_FEMALE_BOOLEAN_KEYS = (
    "FEMALE_VISIBLE_HAIR",
    "FEMALE_VISIBLE_NECK",
    "FEMALE_VISIBLE_ARMS",
    "FEMALE_VISIBLE_LEGS",
    "FEMALE_VISIBLE_TORSO_SKIN",
    "FEMALE_VISIBLE_HANDS",
    "FEMALE_BODY_CONTOUR_EMPHASIS",
    "TIGHT_CLOTHING",
    "TRANSPARENT_CLOTHING",
    "REVEALING_CLOTHING",
    "NUDE_OR_BODY_SHAPED_SILHOUETTE",
)

_REQUIRED_DOSSIER_KEYS = (
    "CHARACTER_ID",
    "SOURCE_BACKED_ATTRIBUTES",
    "UNKNOWN_ATTRIBUTES",
    "DISPUTED_ATTRIBUTES",
    "CONTEXT_DEPENDENT_ATTRIBUTES",
    "SOURCE_REFERENCES",
    "SOURCE_TIERS",
    "PHYSICAL_APPEARANCE_CONTRACT",
    "WARDROBE_CONTRACT",
    "FORBIDDEN_UNSUPPORTED_ASSUMPTIONS",
    "ART_DIRECTION_DECISIONS",
    "HUMAN_REVIEW_REQUIRED_ATTRIBUTES",
)

_ALLOWED_EVENT_TYPES = {
    "LITERAL_EVENT",
    "SOURCE_CONSTRAINED_UNSEEN_EVENT",
    "ESTABLISHING",
    "ATMOSPHERE",
    "TRANSITION",
}

_ALLOWED_SOURCES = {
    "EXISTING",
    "REASSIGNED_EXISTING",
    "NEW_GENERATION_REQUIRED",
}

_CONTRADICTION_PAIRS = (
    ("visible mouth", "all faces forbidden"),
    ("visible hands", "hands forbidden"),
    ("female visible hair", "female visible hair forbidden"),
    ("third adult male", "no third adult male"),
    ("written words", "no written words"),
    ("supernatural beam", "no supernatural beam"),
)


class ConstitutionValidationError(ValueError):
    """Raised when the central constitution is missing or weakened."""


class VisualPlanningValidationError(ValueError):
    """Raised when an episode plan violates the series constitution."""


@dataclass(frozen=True, slots=True)
class VisualProductionConstitution:
    data: dict[str, Any]
    path: Path
    sha256: str

    @property
    def version(self) -> str:
        return str(self.data["CONSTITUTION_VERSION"])


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(Path(path).read_bytes())


def canonical_json_sha256(value: Any) -> str:
    """Hash JSON semantics rather than incidental object insertion order."""

    payload = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256_bytes(payload)


def _require_bool(data: Mapping[str, Any], key: str, errors: list[str]) -> None:
    if not isinstance(data.get(key), bool):
        errors.append(f"{key}_MUST_BE_BOOLEAN")


def validate_constitution_mapping(
    data: Mapping[str, Any],
    *,
    expected_version: str = CONSTITUTION_VERSION,
) -> list[str]:
    errors: list[str] = []
    if data.get("CONSTITUTION_VERSION") != expected_version:
        errors.append("CONSTITUTION_VERSION_INVALID")
    if data.get("STATUS") != "ACTIVE":
        errors.append("CONSTITUTION_STATUS_NOT_ACTIVE")
    if data.get("CONSTITUTION_SCOPE") != "ALL_FUTURE_EPISODES":
        errors.append("CONSTITUTION_SCOPE_MUST_BE_ALL_FUTURE_EPISODES")
    for key in _TRUE_KEYS + _FALSE_KEYS:
        _require_bool(data, key, errors)
    for key in _TRUE_KEYS:
        if data.get(key) is not True:
            errors.append(f"{key}_MUST_BE_TRUE")
    for key in _FALSE_KEYS:
        if data.get(key) is not False:
            errors.append(f"{key}_MUST_BE_FALSE")

    required_stages = data.get("REQUIRED_BEFORE_STAGES")
    if not isinstance(required_stages, list) or not required_stages:
        errors.append("REQUIRED_BEFORE_STAGES_MISSING")
    elif "PROMPT_COMPILATION" not in required_stages:
        errors.append("PROMPT_COMPILATION_STAGE_MISSING")

    literal = data.get("LITERAL_EVENT_POLICY")
    if not isinstance(literal, Mapping):
        errors.append("LITERAL_EVENT_POLICY_MISSING")
    else:
        for key in (
            "LITERAL_MAJOR_EVENT_VISUALIZATION_REQUIRED",
            "MUTE_COMPREHENSION_REQUIRED",
            "SUBJECT_ACTION_OBJECT_RESULT_MUST_BE_VISIBLE_WHERE_APPLICABLE",
            "ATMOSPHERE_MAY_SUPPORT_BUT_NOT_REPLACE_EVENT",
            "AMBIGUOUS_EVENT_SUBSTITUTION_FORBIDDEN",
            "ACTUAL_RENDER_MUTE_COMPREHENSION_REQUIRES_PIXEL_MEDIA_INSPECTION",
        ):
            if literal.get(key) is not True:
                errors.append(f"LITERAL_EVENT_POLICY.{key}_MUST_BE_TRUE")

    unseen = data.get("SOURCE_CONSTRAINED_UNSEEN_EVENT_POLICY")
    if not isinstance(unseen, Mapping):
        errors.append("SOURCE_CONSTRAINED_UNSEEN_EVENT_POLICY_MISSING")
    else:
        for key in (
            "ENABLED",
            "USE_WHEN_EVENT_IS_ESTABLISHED_BUT_MECHANISM_IS_UNSEEN",
            "SHOW_OBSERVABLE_CONSEQUENCE_OR_REACTION",
            "INVENTED_UNSEEN_BODY_FORBIDDEN",
            "INVENTED_UNSEEN_OBJECT_FORBIDDEN",
            "INVENTED_UNSEEN_GEOGRAPHY_FORBIDDEN",
            "INVENTED_SUPERNATURAL_MECHANISM_FORBIDDEN",
        ):
            if unseen.get(key) is not True:
                errors.append(f"SOURCE_CONSTRAINED_UNSEEN_EVENT_POLICY.{key}_MUST_BE_TRUE")

    female = data.get("FEMALE_MODESTY_MAXIMUM_STRICT")
    if not isinstance(female, Mapping):
        errors.append("FEMALE_MODESTY_MAXIMUM_STRICT_MISSING")
    else:
        for key in _FEMALE_BOOLEAN_KEYS:
            if female.get(key) is not False:
                errors.append(f"FEMALE_MODESTY_MAXIMUM_STRICT.{key}_MUST_BE_FALSE")
        if not str(female.get("REQUIRED_CLOTHING", "")).strip():
            errors.append("FEMALE_MODESTY_MAXIMUM_STRICT.REQUIRED_CLOTHING_MISSING")
        if female.get("REQUIRED_FEMALE_CHARACTER_MAY_NOT_BE_SILENTLY_OMITTED") is not True:
            errors.append("REQUIRED_FEMALE_CHARACTER_OMISSION_MUST_BE_FORBIDDEN")

    graphics = data.get("GRAPHICS_POLICY")
    if not isinstance(graphics, Mapping):
        errors.append("GRAPHICS_POLICY_MISSING")
    else:
        for key in (
            "GRAPHICS_ALLOWED",
            "DIAGRAMS_ALLOWED",
            "UI_GRAPHICS_ALLOWED",
            "ABSTRACT_EXPLAINER_GRAPHICS_ALLOWED",
            "LOCAL_GRAPHICS_ALLOWED",
            "PLACEHOLDER_VISUALS_ALLOWED",
            "PLANNED_GRAPHICS_COUNT_MUST_BE_ZERO",
            "ACTUAL_RENDER_GRAPHICS_COUNT_MUST_BE_ZERO",
        ):
            if graphics.get(key) is not False and key.endswith("_ALLOWED"):
                errors.append(f"GRAPHICS_POLICY.{key}_MUST_BE_FALSE")
            if graphics.get(key) is not True and key.endswith("_MUST_BE_ZERO"):
                errors.append(f"GRAPHICS_POLICY.{key}_MUST_BE_TRUE")

    hierarchy = data.get("SOURCE_HIERARCHY")
    expected_hierarchy = [
        "TIER_1_QURAN",
        "TIER_2_SAHIH_SUNNAH",
        "TIER_3_RELIABLE_ATHAR_EARLY_REPORTS",
        "TIER_4_RELIABLE_HISTORICAL_REPORTS",
        "TIER_5_PERMISSIBLE_ISRAILIYYAT",
        "TIER_6_ART_DIRECTION",
    ]
    if hierarchy != expected_hierarchy:
        errors.append("SOURCE_HIERARCHY_INVALID")

    israiliyyat = data.get("ISRAILIYYAT_POLICY")
    if not isinstance(israiliyyat, Mapping):
        errors.append("ISRAILIYYAT_POLICY_MISSING")
    else:
        if israiliyyat.get("ISRAILIYYAT_ALLOWED") is not True:
            errors.append("ISRAILIYYAT_MUST_BE_SUPPORTED")
        for key in (
            "ISRAILIYYAT_MAY_OVERRIDE_QURAN",
            "ISRAILIYYAT_MAY_OVERRIDE_SAHIH_SUNNAH",
            "ISRAILIYYAT_MAY_CONTRADICT_ISLAMIC_AQIDAH",
            "ISRAILIYYAT_PRESENTED_AS_ISLAMIC_CERTAINTY",
        ):
            if israiliyyat.get(key) is not False:
                errors.append(f"{key}_MUST_BE_FALSE")
        for key in (
            "ISRAILIYYAT_SOURCE_LABEL_REQUIRED",
            "ISRAILIYYAT_CERTAINTY_REQUIRED",
            "MATERIAL_ISRAILIYYAT_VISUAL_DETAIL_REQUIRES_HUMAN_REVIEW",
        ):
            if israiliyyat.get(key) is not True:
                errors.append(f"{key}_MUST_BE_TRUE")

    micro = data.get("MICRO_SHOT_ARCHITECTURE")
    if not isinstance(micro, Mapping):
        errors.append("MICRO_SHOT_ARCHITECTURE_MISSING")
    else:
        for key in ("NO_LOOP", "NO_HIDDEN_STRETCH", "NO_DUPLICATED_STILL_AS_EXCESSIVE_FILL"):
            if micro.get(key) is not True:
                errors.append(f"MICRO_SHOT_ARCHITECTURE.{key}_MUST_BE_TRUE")

    temporal = data.get("TEMPORAL_REUSE_AUDIT")
    if not isinstance(temporal, Mapping):
        errors.append("TEMPORAL_REUSE_AUDIT_MISSING")
    else:
        if temporal.get("REQUIRED_BEFORE_KEEP_OR_REASSIGN") is not True:
            errors.append("TEMPORAL_REUSE_AUDIT_REQUIRED")
        if temporal.get("MIDPOINT_ONLY_ACCEPTANCE_FORBIDDEN") is not True:
            errors.append("MIDPOINT_ONLY_ACCEPTANCE_MUST_BE_FORBIDDEN")

    prompt = data.get("PROMPT_COMPILATION")
    if not isinstance(prompt, Mapping):
        errors.append("PROMPT_COMPILATION_MISSING")
    else:
        for key in (
            "FINAL_COMPILED_PROVIDER_PROMPT_REQUIRED_FOR_NEW_MICRO_SHOT",
            "CONSTITUTION_RULES_MUST_BE_EXPLICIT",
            "CHARACTER_DOSSIER_RULES_MUST_BE_EXPLICIT",
            "SOURCE_FACTS_AND_ART_DIRECTION_MUST_BE_EXPLICITLY_SEPARATED",
            "PROMPT_CONTRADICTIONS_MUST_EQUAL_ZERO",
            "PROMPT_MATERIAL_CHANGE_INVALIDATES_APPROVAL",
        ):
            if prompt.get(key) is not True:
                errors.append(f"PROMPT_COMPILATION.{key}_MUST_BE_TRUE")

    legacy_female = data.get("LEGACY_FEMALE_REUSE_POLICY")
    if legacy_female is not None:
        if not isinstance(legacy_female, Mapping):
            errors.append("LEGACY_FEMALE_REUSE_POLICY_MUST_BE_OBJECT")
        else:
            for key in (
                "ZERO_LEGACY_FEMALE_REUSE_REQUIRED",
                "UNCERTAIN_FEMALE_PRESENCE_REJECT",
                "FORENSIC_ASSET_PRESERVED",
                "PRODUCTION_REUSE_ALLOWED_FOR_FEMALE_ASSET",
                "FINAL_MONTAGE_ALLOWED_FOR_FEMALE_ASSET",
            ):
                if not isinstance(legacy_female.get(key), bool):
                    errors.append(f"LEGACY_FEMALE_REUSE_POLICY.{key}_MUST_BE_BOOLEAN")
            for key in (
                "ZERO_LEGACY_FEMALE_REUSE_REQUIRED",
                "UNCERTAIN_FEMALE_PRESENCE_REJECT",
                "FORENSIC_ASSET_PRESERVED",
            ):
                if legacy_female.get(key) is not True:
                    errors.append(f"LEGACY_FEMALE_REUSE_POLICY.{key}_MUST_BE_TRUE")
            for key in (
                "PRODUCTION_REUSE_ALLOWED_FOR_FEMALE_ASSET",
                "FINAL_MONTAGE_ALLOWED_FOR_FEMALE_ASSET",
            ):
                if legacy_female.get(key) is not False:
                    errors.append(f"LEGACY_FEMALE_REUSE_POLICY.{key}_MUST_BE_FALSE")
            if legacy_female.get("SAFETY_EXCLUDED_DISPOSITION") != "SAFETY_EXCLUDED":
                errors.append("LEGACY_FEMALE_REUSE_POLICY.SAFETY_EXCLUDED_DISPOSITION_INVALID")
    return errors


def load_visual_production_constitution_v2(
    repo_root: Path,
    path: Path | None = None,
    *,
    expected_version: str = CONSTITUTION_VERSION,
) -> VisualProductionConstitution:
    repo = Path(repo_root).resolve()
    constitution_path = (path or (repo / CONSTITUTION_RELATIVE_PATH)).resolve()
    if not constitution_path.is_file():
        raise ConstitutionValidationError("CONSTITUTION_FILE_MISSING")
    raw = constitution_path.read_bytes()
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConstitutionValidationError("CONSTITUTION_JSON_INVALID") from exc
    errors = validate_constitution_mapping(data, expected_version=expected_version)
    if errors:
        raise ConstitutionValidationError(";".join(errors))
    return VisualProductionConstitution(
        data=dict(data),
        path=constitution_path,
        sha256=sha256_bytes(raw),
    )


def load_visual_production_constitution_v2_1(
    repo_root: Path,
    path: Path | None = None,
) -> VisualProductionConstitution:
    return load_visual_production_constitution_v2(
        repo_root,
        path or (Path(repo_root) / CONSTITUTION_V2_1_RELATIVE_PATH),
        expected_version=CONSTITUTION_V2_1_VERSION,
    )


_V22_REQUIRED_KEYS = (
    "AUDIO_BEAT_MAPPING_REQUIRED",
    "SUB_FRAME_MICRO_SHOTS_MUST_EQUAL_ZERO",
    "MICRO_CRUMB_SHOTS_MUST_EQUAL_ZERO",
    "PROVIDER_EDITORIAL_DURATION_SEPARATION_REQUIRED",
    "GENERATION_CONSOLIDATION_REQUIRED",
    "EXECUTION_ENVELOPE_SEPARATE_FROM_VISUAL_PROVIDER_PROMPT",
    "MUSA_SOURCE_BACKED_TRAITS_REQUIRED_WHEN_USED",
    "LEGACY_FEMALE_REUSE_COUNT_MUST_EQUAL_ZERO",
)


def validate_constitution_v2_2_mapping(data: Mapping[str, Any]) -> list[str]:
    """Validate the V2.2 additions without weakening the V2/V2.1 contract."""

    errors = validate_constitution_mapping(
        data,
        expected_version=CONSTITUTION_V2_2_VERSION,
    )
    for key in _V22_REQUIRED_KEYS:
        if data.get(key) is not True:
            errors.append(f"{key}_MUST_BE_TRUE")
    if data.get("PREPRODUCTION_VISUAL_GENERATION_ALLOWED") is not False:
        errors.append("PREPRODUCTION_VISUAL_GENERATION_ALLOWED_MUST_BE_FALSE")
    audio = data.get("AUDIO_BEAT_MAPPING_POLICY")
    if not isinstance(audio, Mapping):
        errors.append("AUDIO_BEAT_MAPPING_POLICY_MISSING")
    else:
        for key in (
            "AUDIO_BEAT_ID_REQUIRED",
            "AUDIO_BEAT_START_REQUIRED",
            "AUDIO_BEAT_END_REQUIRED",
            "AUDIO_TRANSCRIPT_FRAGMENT_REQUIRED",
            "AUDIO_SOURCE_TIMING_REFERENCE_REQUIRED",
            "NO_STALE_PARENT_NARRATION_INHERITANCE",
            "FULL_TIMELINE_CONTIGUOUS_AND_GAP_FREE",
        ):
            if audio.get(key) is not True:
                errors.append(f"AUDIO_BEAT_MAPPING_POLICY.{key}_MUST_BE_TRUE")
    frames = data.get("FRAME_QUANTIZATION_POLICY")
    if not isinstance(frames, Mapping):
        errors.append("FRAME_QUANTIZATION_POLICY_MISSING")
    else:
        if frames.get("PRODUCTION_FPS") not in (24, 25, 30, 50, 60):
            errors.append("FRAME_QUANTIZATION_POLICY.PRODUCTION_FPS_INVALID")
        if frames.get("MINIMUM_VISUAL_SHOT_FRAMES", 0) < 1:
            errors.append("FRAME_QUANTIZATION_POLICY.MINIMUM_VISUAL_SHOT_FRAMES_INVALID")
    prompt = data.get("PROMPT_COMPILATION")
    if isinstance(prompt, Mapping):
        for key in (
            "EXECUTION_ENVELOPE_OUTSIDE_PROVIDER_PROMPT",
            "NO_EXECUTION_STATE_IN_PROVIDER_PROMPT",
            "DUPLICATED_NEGATIVE_LINES_FORBIDDEN",
        ):
            if prompt.get(key) is not True:
                errors.append(f"PROMPT_COMPILATION.{key}_MUST_BE_TRUE")
    return errors


def load_visual_production_constitution_v2_2(
    repo_root: Path,
    path: Path | None = None,
) -> VisualProductionConstitution:
    constitution = load_visual_production_constitution_v2(
        repo_root,
        path or (Path(repo_root) / CONSTITUTION_V2_2_RELATIVE_PATH),
        expected_version=CONSTITUTION_V2_2_VERSION,
    )
    errors = validate_constitution_v2_2_mapping(constitution.data)
    if errors:
        raise ConstitutionValidationError(";".join(errors))
    return constitution


def validate_character_evidence_dossier(dossier: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in _REQUIRED_DOSSIER_KEYS:
        if key not in dossier:
            errors.append(f"DOSSIER_{key}_MISSING")
    if not str(dossier.get("CHARACTER_ID", "")).strip():
        errors.append("DOSSIER_CHARACTER_ID_EMPTY")
    for key in (
        "SOURCE_BACKED_ATTRIBUTES",
        "UNKNOWN_ATTRIBUTES",
        "DISPUTED_ATTRIBUTES",
        "CONTEXT_DEPENDENT_ATTRIBUTES",
        "SOURCE_REFERENCES",
        "SOURCE_TIERS",
        "FORBIDDEN_UNSUPPORTED_ASSUMPTIONS",
        "ART_DIRECTION_DECISIONS",
        "HUMAN_REVIEW_REQUIRED_ATTRIBUTES",
    ):
        if not isinstance(dossier.get(key), list):
            errors.append(f"DOSSIER_{key}_MUST_BE_LIST")
    if dossier.get("SOURCE_FACTS_AND_ART_DIRECTION_SEPARATED") is not True:
        errors.append("DOSSIER_SOURCE_FACTS_AND_ART_DIRECTION_MUST_BE_SEPARATED")
    if not isinstance(dossier.get("PHYSICAL_APPEARANCE_CONTRACT"), Mapping):
        errors.append("DOSSIER_PHYSICAL_APPEARANCE_CONTRACT_MISSING")
    if not isinstance(dossier.get("WARDROBE_CONTRACT"), Mapping):
        errors.append("DOSSIER_WARDROBE_CONTRACT_MISSING")
    return errors


def validate_character_dossiers(dossiers: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    errors: list[str] = []
    seen: set[str] = set()
    for dossier in dossiers:
        errors.extend(validate_character_evidence_dossier(dossier))
        identifier = str(dossier.get("CHARACTER_ID", ""))
        if identifier in seen:
            errors.append(f"DOSSIER_DUPLICATE:{identifier}")
        seen.add(identifier)
        facts = {str(item) for item in dossier.get("SOURCE_BACKED_ATTRIBUTES", [])}
        art = {str(item) for item in dossier.get("ART_DIRECTION_DECISIONS", [])}
        if facts & art:
            errors.append(f"DOSSIER_FACT_ART_DIRECTION_OVERLAP:{identifier}")
        if "TIER_6_ART_DIRECTION" in dossier.get("SOURCE_TIERS", []) and not art:
            errors.append(f"DOSSIER_ART_DIRECTION_TIER_WITHOUT_DECISIONS:{identifier}")
    return {"status": "PASS" if not errors else "FAIL", "errors": errors}


# Short public alias for callers that validate one dossier at a time.
validate_character_dossier = validate_character_evidence_dossier


def validate_source_hierarchy_records(records: Sequence[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    order = {
        "TIER_1_QURAN": 1,
        "TIER_2_SAHIH_SUNNAH": 2,
        "TIER_3_RELIABLE_ATHAR_EARLY_REPORTS": 3,
        "TIER_4_RELIABLE_HISTORICAL_REPORTS": 4,
        "TIER_5_PERMISSIBLE_ISRAILIYYAT": 5,
        "TIER_6_ART_DIRECTION": 6,
    }
    for index, record in enumerate(records):
        tier = str(record.get("SOURCE_TIER", ""))
        if tier not in order:
            errors.append(f"SOURCE_RECORD_{index}_TIER_INVALID")
        if tier == "TIER_5_PERMISSIBLE_ISRAILIYYAT":
            if not record.get("SOURCE_LABEL") or not record.get("CERTAINTY"):
                errors.append(f"SOURCE_RECORD_{index}_ISRAILIYYAT_LABEL_OR_CERTAINTY_MISSING")
            if record.get("ISRAILIYYAT_STATUS") in ("CONFLICTING_FORBIDDEN", "UNRESOLVED"):
                errors.append(f"SOURCE_RECORD_{index}_ISRAILIYYAT_NOT_RENDERABLE")
        if record.get("ASSERTION_MODE") == "STATE_AS_FACT" and tier in (
            "TIER_5_PERMISSIBLE_ISRAILIYYAT",
            "TIER_6_ART_DIRECTION",
        ):
            errors.append(f"SOURCE_RECORD_{index}_LOWER_TIER_PRESENTED_AS_FACT")
    return errors


def _female_prompt_appendix(constitution: VisualProductionConstitution) -> str:
    female = constitution.data["FEMALE_MODESTY_MAXIMUM_STRICT"]
    return (
        "FEMALE_MODESTY_MAXIMUM_STRICT=TRUE; "
        "FEMALE_VISIBLE_HAIR=FORBIDDEN; FEMALE_VISIBLE_NECK=FORBIDDEN; "
        "FEMALE_VISIBLE_ARMS=FORBIDDEN; FEMALE_VISIBLE_LEGS=FORBIDDEN; "
        "FEMALE_VISIBLE_TORSO_SKIN=FORBIDDEN; FEMALE_VISIBLE_HANDS=FORBIDDEN; "
        "FEMALE_BODY_CONTOUR_EMPHASIS=FORBIDDEN; TIGHT_CLOTHING=FORBIDDEN; "
        "TRANSPARENT_CLOTHING=FORBIDDEN; REVEALING_CLOTHING=FORBIDDEN; "
        "NUDE_OR_BODY_SHAPED_SILHOUETTE=FORBIDDEN; "
        f"REQUIRED_CLOTHING={female['REQUIRED_CLOTHING']}."
    )


def _constitution_prompt_appendix(
    constitution: VisualProductionConstitution,
    *,
    includes_female: bool,
    event_type: str,
    source_tier: str,
    source_certainty: str,
    source_facts: Sequence[str],
    art_direction: Sequence[str],
    dossier_refs: Sequence[str],
) -> str:
    lines = [
        f"CONSTITUTION_VERSION={constitution.version}",
        "AUDIO_IS_DURATION_AUTHORITY=TRUE; VISUALS_MAY_NOT_EXTEND_EPISODE=TRUE; VISUALS_MAY_NOT_CHANGE_AUDIO_DURATION=TRUE.",
        "LITERAL_MAJOR_EVENT_VISUALIZATION_REQUIRED=TRUE; MUTE_COMPREHENSION_REQUIRED=TRUE; actual action must be visible.",
        "GRAPHICS_ALLOWED=FALSE; DIAGRAMS_ALLOWED=FALSE; UI_GRAPHICS_ALLOWED=FALSE; ABSTRACT_EXPLAINER_GRAPHICS_ALLOWED=FALSE; LOCAL_GRAPHICS_ALLOWED=FALSE; PLACEHOLDER_VISUALS_ALLOWED=FALSE.",
        "No text, captions, logos, watermark, chart, diagram, interface, explainer panel, filler, loop, freeze-frame filler, or ambiguous substitution.",
        f"EVENT_TYPE={event_type}; SOURCE_TIER={source_tier}; SOURCE_CERTAINTY={source_certainty}.",
        "SOURCE_FACTS=" + (" | ".join(source_facts) if source_facts else "NONE") + ".",
        "ART_DIRECTION=" + (" | ".join(art_direction) if art_direction else "NONE") + ".",
        "CHARACTER_DOSSIERS=" + (" | ".join(dossier_refs) if dossier_refs else "NONE") + ".",
        "SOURCE_FACT_AND_ART_DIRECTION_MUST_NOT_BE_MIXED; unknown attributes remain unknown.",
        "STORYBOARD_HUMAN_APPROVAL_REQUIRED_BEFORE_VISUAL_GENERATION=TRUE; VISUAL_GENERATION_ALLOWED=FALSE until an immutable approved storyboard hash exists.",
    ]
    if event_type == "SOURCE_CONSTRAINED_UNSEEN_EVENT":
        lines.append(
            "SOURCE_CONSTRAINED_UNSEEN_EVENT=TRUE; show only observable human consequence or reaction; do not invent an unseen body, object, geography, beam, portal, voice mechanism, or supernatural form."
        )
    legacy_female = constitution.data.get("LEGACY_FEMALE_REUSE_POLICY")
    if isinstance(legacy_female, Mapping) and legacy_female.get(
        "ZERO_LEGACY_FEMALE_REUSE_REQUIRED"
    ) is True:
        lines.append(
            "ZERO_LEGACY_FEMALE_REUSE_REQUIRED=TRUE; any legacy asset with confirmed or uncertain female presence is forensic-only, SAFETY_EXCLUDED, and must never be reused or montage eligible; no blur, crop, mask, occlusion, reframing, or defect-hiding salvage."
        )
    if includes_female:
        lines.append(_female_prompt_appendix(constitution))
    return " ".join(lines)


def validate_prompt_contradictions(positive: str, negative: str) -> list[str]:
    positive_lower = positive.lower()
    negative_lower = negative.lower()
    errors: list[str] = []
    for positive_phrase, negative_phrase in _CONTRADICTION_PAIRS:
        if positive_phrase in positive_lower and negative_phrase in negative_lower:
            errors.append(f"PROMPT_CONTRADICTION:{positive_phrase}:{negative_phrase}")
    return errors


def compile_visual_prompt_v2(
    constitution: VisualProductionConstitution,
    image_prompt: str,
    video_prompt: str,
    negative_prompt: str,
    *,
    includes_female: bool,
    event_type: str,
    source_tier: str,
    source_certainty: str,
    source_facts: Sequence[str],
    art_direction: Sequence[str],
    dossier_refs: Sequence[str],
) -> dict[str, Any]:
    if not image_prompt.strip() or not video_prompt.strip() or not negative_prompt.strip():
        raise VisualPlanningValidationError("PROMPT_COMPONENT_EMPTY")
    if event_type not in _ALLOWED_EVENT_TYPES:
        raise VisualPlanningValidationError("PROMPT_EVENT_TYPE_INVALID")
    appendix = _constitution_prompt_appendix(
        constitution,
        includes_female=includes_female,
        event_type=event_type,
        source_tier=source_tier,
        source_certainty=source_certainty,
        source_facts=source_facts,
        art_direction=art_direction,
        dossier_refs=dossier_refs,
    )
    compiled_image = image_prompt.strip() + "\n\n" + appendix
    compiled_video = video_prompt.strip() + "\n\n" + appendix
    compiled_negative = (
        negative_prompt.strip()
        + "\nGRAPHICS, diagrams, UI, explainer panels, placeholder frames, readable text, logos, watermark, loops, freeze-frame filler, unsupported source details, extra characters, continuity changes."
    )
    contradictions = validate_prompt_contradictions(
        compiled_video,
        compiled_negative,
    )
    if contradictions:
        raise VisualPlanningValidationError(";".join(contradictions))
    return {
        "IMAGE_PROMPT": image_prompt.strip(),
        "VIDEO_PROMPT": video_prompt.strip(),
        "NEGATIVE_PROMPT": compiled_negative,
        "COMPILED_PROVIDER_PROMPT": {
            "positive_image": compiled_image,
            "positive_video": compiled_video,
            "negative": compiled_negative,
            "constitution_version": constitution.version,
            "constitution_sha256": constitution.sha256,
            "character_dossier_references": list(dossier_refs),
            "source_facts": list(source_facts),
            "art_direction": list(art_direction),
            "prompt_contradictions": [],
        },
    }


def validate_temporal_reuse_audit(audit: Mapping[str, Any]) -> list[str]:
    errors: list[str] = []
    if audit.get("FULL_TEMPORAL_REUSE_AUDIT") is not True:
        errors.append("FULL_TEMPORAL_REUSE_AUDIT_NOT_PROVEN")
    if audit.get("MIDPOINT_ONLY_ACCEPTANCE") is not False:
        errors.append("MIDPOINT_ONLY_ACCEPTANCE_FORBIDDEN")
    sample_types = set(audit.get("SAMPLE_TYPES", audit.get("TEMPORAL_SAMPLE_TYPES", [])))
    if "FULL_IMAGE" in sample_types:
        return errors
    required = {
        "FIRST_FRAME_OR_START_WINDOW",
        "MIDDLE_FRAME_OR_MIDDLE_WINDOW",
        "LAST_FRAME_OR_END_WINDOW",
    }
    if not required.issubset(sample_types):
        errors.append("TEMPORAL_SAMPLE_SET_INCOMPLETE")
    if audit.get("POLICY_STATUS") not in ("PASS", "PASS_WITH_EXPLICIT_EXCLUSIONS"):
        errors.append("TEMPORAL_POLICY_STATUS_NOT_PASS")
    return errors


def validate_legacy_female_asset_record(record: Mapping[str, Any]) -> list[str]:
    """Validate the tri-state legacy-female audit contract.

    A legacy asset with confirmed or uncertain female presence is forensic-only:
    it may never be reused or become montage eligible.  The record is kept in
    the audit packet so the historical asset remains traceable.
    """

    errors: list[str] = []
    if record.get("NO_SALVAGE_TRANSFORM_USED") is not True:
        errors.append("NO_SALVAGE_TRANSFORM_USED_MUST_BE_TRUE")
    presence = record.get("FEMALE_PRESENT")
    if presence not in {"TRUE", "FALSE", "UNCERTAIN"}:
        errors.append("FEMALE_PRESENT_MUST_BE_TRUE_FALSE_OR_UNCERTAIN")
        return errors
    if record.get("FORENSIC_ASSET_PRESERVED") is not True:
        errors.append("FORENSIC_ASSET_PRESERVED_MUST_BE_TRUE")
    if presence in {"TRUE", "UNCERTAIN"}:
        if record.get("REUSE_ALLOWED") is not False:
            errors.append("LEGACY_FEMALE_REUSE_ALLOWED_MUST_BE_FALSE")
        if record.get("MONTAGE_ELIGIBLE") is not False:
            errors.append("LEGACY_FEMALE_MONTAGE_ELIGIBLE_MUST_BE_FALSE")
        if record.get("DISPOSITION") != "SAFETY_EXCLUDED":
            errors.append("LEGACY_FEMALE_DISPOSITION_MUST_BE_SAFETY_EXCLUDED")
        if presence == "UNCERTAIN" and record.get("UNCERTAIN_FEMALE_PRESENCE") is not True:
            errors.append("UNCERTAIN_FEMALE_PRESENCE_MUST_BE_TRUE")
    else:
        if record.get("UNCERTAIN_FEMALE_PRESENCE") is not False:
            errors.append("FALSE_FEMALE_PRESENCE_MUST_NOT_BE_UNCERTAIN")
        if record.get("REUSE_ALLOWED") is True and record.get("MONTAGE_ELIGIBLE") is not True:
            errors.append("SAFE_REUSE_MUST_BE_MONTAGE_ELIGIBLE")
    return errors


def validate_legacy_female_reuse_plan(
    records: Sequence[Mapping[str, Any]],
) -> list[str]:
    """Fail closed unless every planned legacy reuse record is female-free."""

    errors: list[str] = []
    for index, record in enumerate(records):
        prefix = f"LEGACY_REUSE_{index}"
        errors.extend(
            f"{prefix}_{item}"
            for item in validate_legacy_female_asset_record(record)
        )
        if record.get("FEMALE_PRESENT") != "FALSE":
            errors.append(f"{prefix}_FEMALE_PRESENT_MUST_BE_FALSE")
        if record.get("UNCERTAIN_FEMALE_PRESENCE") is not False:
            errors.append(f"{prefix}_UNCERTAIN_FEMALE_PRESENCE_MUST_BE_FALSE")
        if record.get("REUSE_ALLOWED") is not True:
            errors.append(f"{prefix}_REUSE_ALLOWED_MUST_BE_TRUE_FOR_PLAN_RECORD")
        if record.get("MONTAGE_ELIGIBLE") is not True:
            errors.append(f"{prefix}_MONTAGE_ELIGIBLE_MUST_BE_TRUE_FOR_PLAN_RECORD")
    return errors


def _validate_planned_mute(shot: Mapping[str, Any], errors: list[str]) -> None:
    planned = shot.get("PLANNED_MUTE_COMPREHENSION")
    if not isinstance(planned, Mapping):
        errors.append(f"{shot.get('MICRO_SHOT_ID', 'UNKNOWN')}_PLANNED_MUTE_MISSING")
        return
    if shot.get("EVENT_ROLE") == "LITERAL_EVENT":
        for key in (
            "PLANNED_EVENT_VISIBLE",
            "PLANNED_SUBJECT_VISIBLE",
            "PLANNED_ACTION_VISIBLE",
            "PLANNED_OBJECT_VISIBLE",
            "PLANNED_RESULT_VISIBLE",
            "PLANNED_MUTE_COMPREHENSION",
        ):
            if planned.get(key) is not True:
                errors.append(f"{shot.get('MICRO_SHOT_ID', 'UNKNOWN')}_{key}_MUST_BE_TRUE")


def validate_micro_shot_storyboard(
    storyboard: Mapping[str, Any],
    constitution: VisualProductionConstitution,
    *,
    dossiers: Sequence[Mapping[str, Any]] = (),
    temporal_audits: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    errors: list[str] = []
    constitution_errors = validate_constitution_mapping(
        constitution.data,
        expected_version=constitution.version,
    )
    errors.extend(constitution_errors)
    if storyboard.get("VISUAL_CONSTITUTION_LOADED") is not True:
        errors.append("VISUAL_CONSTITUTION_LOADED_MUST_BE_TRUE")
    if storyboard.get("VISUAL_CONSTITUTION_VERSION") != constitution.version:
        errors.append("VISUAL_CONSTITUTION_VERSION_MISMATCH")
    if storyboard.get("VISUAL_CONSTITUTION_SHA256") != constitution.sha256:
        errors.append("VISUAL_CONSTITUTION_SHA256_MISMATCH")
    if storyboard.get("CONSTITUTION_SCOPE") != "ALL_FUTURE_EPISODES":
        errors.append("STORYBOARD_CONSTITUTION_SCOPE_INVALID")
    if storyboard.get("AUDIO_IS_DURATION_AUTHORITY") is not True:
        errors.append("AUDIO_IS_DURATION_AUTHORITY_FALSE")
    if storyboard.get("CURRENT_NARRATION_FROZEN") is not True:
        errors.append("CURRENT_NARRATION_NOT_FROZEN")
    if storyboard.get("VISUAL_GENERATION_ALLOWED") is not False:
        errors.append("VISUAL_GENERATION_MUST_BE_FALSE")
    if storyboard.get("STORYBOARD_STATUS") != "AWAITING_HUMAN_APPROVAL":
        errors.append("STORYBOARD_STATUS_MUST_AWAIT_HUMAN_APPROVAL")
    if storyboard.get("APPROVED_STORYBOARD_SHA256") is not None:
        errors.append("APPROVED_STORYBOARD_SHA256_MUST_BE_NULL")
    if storyboard.get("PLANNED_GRAPHICS_COUNT") != 0:
        errors.append("PLANNED_GRAPHICS_COUNT_MUST_BE_ZERO")
    if storyboard.get("NETWORK_CALLS") != 0 or storyboard.get("PROVIDER_CALLS") != 0:
        errors.append("PREPRODUCTION_EXTERNAL_CALLS_MUST_BE_ZERO")
    if storyboard.get("PAID_CALLS") != 0:
        errors.append("PREPRODUCTION_PAID_CALLS_MUST_BE_ZERO")

    dossier_result = validate_character_dossiers(dossiers)
    errors.extend(dossier_result["errors"])
    event_types = set()
    micro_shots = storyboard.get("MICRO_SHOTS")
    if not isinstance(micro_shots, Sequence) or isinstance(micro_shots, (str, bytes)) or not micro_shots:
        errors.append("MICRO_SHOTS_MISSING")
        micro_shots = []
    previous_end: float | None = None
    duration = float(storyboard.get("AUDIO_DURATION_SECONDS", -1))
    used_assets: list[str] = []
    for index, shot in enumerate(micro_shots):
        if not isinstance(shot, Mapping):
            errors.append(f"MICRO_SHOT_{index}_NOT_OBJECT")
            continue
        shot_id = str(shot.get("MICRO_SHOT_ID", index))
        for key in (
            "MICRO_SHOT_ID",
            "PARENT_AUDIO_SEGMENT_ID",
            "TIMELINE_IN",
            "TIMELINE_OUT",
            "DURATION",
            "NARRATION_TEXT",
            "EVENT_ID",
            "EVENT_TYPE",
            "SOURCE_TIER",
            "SOURCE_CERTAINTY",
            "SOURCE_FACTS_USED",
            "ART_DIRECTION_USED",
            "CHARACTERS",
            "VISIBLE_ACTION",
            "VISUAL_INFORMATION",
            "EVENT_ROLE",
            "SOURCE",
            "PLANNED_MUTE_COMPREHENSION",
            "ACTUAL_RENDER_MUTE_COMPREHENSION",
        ):
            if key not in shot:
                errors.append(f"{shot_id}_{key}_MISSING")
        start = shot.get("TIMELINE_IN")
        end = shot.get("TIMELINE_OUT")
        shot_duration = shot.get("DURATION")
        if not all(isinstance(v, (int, float)) for v in (start, end, shot_duration)):
            errors.append(f"{shot_id}_TIME_FIELDS_INVALID")
        else:
            if float(end) <= float(start) or abs((float(end) - float(start)) - float(shot_duration)) > 0.002:
                errors.append(f"{shot_id}_TIME_RANGE_INVALID")
            if previous_end is not None and abs(float(start) - previous_end) > 0.002:
                errors.append(f"{shot_id}_TIMELINE_GAP_OR_OVERLAP")
            previous_end = float(end)
        event_type = str(shot.get("EVENT_TYPE", ""))
        event_types.add(event_type)
        if event_type not in _ALLOWED_EVENT_TYPES:
            errors.append(f"{shot_id}_EVENT_TYPE_INVALID")
        if event_type == "SOURCE_CONSTRAINED_UNSEEN_EVENT":
            if shot.get("UNSEEN_ENTITY_VISIBLE") is not False:
                errors.append(f"{shot_id}_UNSEEN_ENTITY_MUST_NOT_BE_VISIBLE")
            if shot.get("UNSEEN_MECHANISM_VISIBLE") is not False:
                errors.append(f"{shot_id}_UNSEEN_MECHANISM_MUST_NOT_BE_VISIBLE")
            characters_upper = {str(item).upper() for item in shot.get("CHARACTERS", [])}
            if characters_upper & {"SATAN", "IBLIS", "DEMON", "HOODED_TEMPTER", "SMOKE_BEING"}:
                errors.append(f"{shot_id}_UNSEEN_AGENT_INVENTED_AS_CHARACTER")
        if shot.get("INCLUDES_FEMALE") is True and "HAWWA_SPOUSE" not in {
            str(item) for item in shot.get("CHARACTERS", [])
        }:
            errors.append(f"{shot_id}_REQUIRED_FEMALE_CHARACTER_OMITTED")
        if shot.get("EVENT_ROLE") == "LITERAL_EVENT":
            if not shot.get("VISIBLE_ACTION") or not shot.get("MUTE_COMPREHENSION_TARGET"):
                errors.append(f"{shot_id}_LITERAL_CONTRACT_INCOMPLETE")
        _validate_planned_mute(shot, errors)
        if shot.get("ACTUAL_RENDER_MUTE_COMPREHENSION") != "NOT_RUN":
            errors.append(f"{shot_id}_ACTUAL_RENDER_MUTE_MUST_BE_NOT_RUN")
        source = shot.get("SOURCE")
        if source not in _ALLOWED_SOURCES:
            errors.append(f"{shot_id}_SOURCE_INVALID")
        if source in {"EXISTING", "REASSIGNED_EXISTING"}:
            for key in ("ASSET_ID", "ASSET_PATH", "ASSET_SHA256", "SOURCE_IN", "SOURCE_OUT", "PLAYBACK_RATE"):
                if key not in shot:
                    errors.append(f"{shot_id}_{key}_MISSING")
            if isinstance(shot.get("PLAYBACK_RATE"), (int, float)) and float(shot["PLAYBACK_RATE"]) != 1.0:
                errors.append(f"{shot_id}_HIDDEN_STRETCH_OR_RATE_CHANGE")
            legacy_policy = constitution.data.get("LEGACY_FEMALE_REUSE_POLICY")
            if isinstance(legacy_policy, Mapping) and legacy_policy.get(
                "ZERO_LEGACY_FEMALE_REUSE_REQUIRED"
            ) is True:
                if shot.get("FEMALE_PRESENT") != "FALSE":
                    errors.append(f"{shot_id}_FEMALE_PRESENT_MUST_BE_FALSE")
                if shot.get("UNCERTAIN_FEMALE_PRESENCE") is not False:
                    errors.append(f"{shot_id}_UNCERTAIN_FEMALE_PRESENCE_MUST_BE_FALSE")
                if shot.get("REUSE_ALLOWED") is not True:
                    errors.append(f"{shot_id}_REUSE_ALLOWED_MUST_BE_TRUE")
                if shot.get("MONTAGE_ELIGIBLE") is not True:
                    errors.append(f"{shot_id}_MONTAGE_ELIGIBLE_MUST_BE_TRUE")
                legacy_record = {
                    "FEMALE_PRESENT": shot.get("FEMALE_PRESENT"),
                    "UNCERTAIN_FEMALE_PRESENCE": shot.get("UNCERTAIN_FEMALE_PRESENCE"),
                    "REUSE_ALLOWED": shot.get("REUSE_ALLOWED"),
                    "MONTAGE_ELIGIBLE": shot.get("MONTAGE_ELIGIBLE"),
                    "FORENSIC_ASSET_PRESERVED": shot.get("FORENSIC_ASSET_PRESERVED"),
                    "DISPOSITION": shot.get("DISPOSITION"),
                    "NO_SALVAGE_TRANSFORM_USED": shot.get("NO_SALVAGE_TRANSFORM_USED"),
                }
                errors.extend(
                    f"{shot_id}_{item}"
                    for item in validate_legacy_female_asset_record(legacy_record)
                )
            asset_id = str(shot.get("ASSET_ID", ""))
            if asset_id:
                used_assets.append(asset_id)
            if temporal_audits is not None:
                audit = temporal_audits.get(asset_id)
                if not isinstance(audit, Mapping):
                    errors.append(f"{shot_id}_TEMPORAL_AUDIT_MISSING")
                else:
                    errors.extend(f"{shot_id}_{item}" for item in validate_temporal_reuse_audit(audit))
        if source == "NEW_GENERATION_REQUIRED":
            for key in ("IMAGE_PROMPT", "VIDEO_PROMPT", "NEGATIVE_PROMPT", "COMPILED_PROVIDER_PROMPT", "TARGET_DURATION", "PROVIDER_CAPABILITY_REQUIREMENTS"):
                if key not in shot:
                    errors.append(f"{shot_id}_{key}_MISSING")
            compiled = shot.get("COMPILED_PROVIDER_PROMPT")
            if not isinstance(compiled, Mapping):
                errors.append(f"{shot_id}_COMPILED_PROVIDER_PROMPT_INVALID")
            else:
                positive = str(compiled.get("positive_video", ""))
                negative = str(compiled.get("negative", ""))
                errors.extend(f"{shot_id}_{item}" for item in validate_prompt_contradictions(positive, negative))
                if "GRAPHICS_ALLOWED=FALSE" not in positive:
                    errors.append(f"{shot_id}_PROMPT_GRAPHICS_RULE_MISSING")
                if shot.get("INCLUDES_FEMALE") is True and "FEMALE_MODESTY_MAXIMUM_STRICT=TRUE" not in positive:
                    errors.append(f"{shot_id}_FEMALE_RULE_NOT_COMPILED")
                dossier_refs = shot.get("CHARACTER_DOSSIER_REFERENCES", [])
                known = {str(d.get("CHARACTER_ID")) for d in dossiers}
                for ref in dossier_refs:
                    if str(ref) not in known:
                        errors.append(f"{shot_id}_DOSSIER_REFERENCE_UNKNOWN:{ref}")
    if previous_end is not None and duration > 0 and abs(previous_end - duration) > 0.002:
        errors.append("MICRO_SHOT_TIMELINE_DOES_NOT_END_AT_AUDIO_DURATION")
    if not any(item.get("EVENT_ROLE") == "LITERAL_EVENT" for item in micro_shots if isinstance(item, Mapping)):
        errors.append("NO_LITERAL_EVENT_MICRO_SHOTS")
    checks = {
        "constitution_loaded": not constitution_errors,
        "timeline_contiguous": not any("GAP_OR_OVERLAP" in e for e in errors),
        "audio_authority": storyboard.get("AUDIO_IS_DURATION_AUTHORITY") is True,
        "dossiers_valid": not dossier_result["errors"],
        "compiled_prompts_safe": not any("PROMPT_" in e or "FEMALE_RULE" in e for e in errors),
        "temporal_reuse_audits_present": not any("TEMPORAL" in e for e in errors),
        "graphics_forbidden_and_zero": storyboard.get("PLANNED_GRAPHICS_COUNT") == 0,
        "visual_generation_blocked": storyboard.get("VISUAL_GENERATION_ALLOWED") is False,
    }
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checks": checks,
        "event_types_seen": sorted(event_types),
        "unique_assets_used": sorted(set(used_assets)),
    }


def assert_visual_generation_gate(
    *,
    storyboard_status: str,
    approved_storyboard_sha256: str | None,
    current_storyboard_sha256: str,
) -> None:
    if storyboard_status != "APPROVED":
        raise VisualPlanningValidationError("STORYBOARD_APPROVAL_REQUIRED")
    if not approved_storyboard_sha256:
        raise VisualPlanningValidationError("APPROVED_STORYBOARD_SHA256_REQUIRED")
    if approved_storyboard_sha256 != current_storyboard_sha256:
        raise VisualPlanningValidationError("APPROVED_STORYBOARD_HASH_MISMATCH")


# ---------------------------------------------------------------------------
# V2.2 prompt and release-gate helpers
# ---------------------------------------------------------------------------

_V22_EXECUTION_STATE_TERMS = (
    "AWAITING_HUMAN_APPROVAL",
    "VISUAL_GENERATION_ALLOWED",
    "APPROVED_STORYBOARD_SHA256",
    "PAID_CALLS",
    "NETWORK_CALLS",
    "PROVIDER_CALLS",
    "RUNWARE_CALLS",
    "IMAGE_GENERATION_CALLS",
    "VIDEO_GENERATION_CALLS",
    "AUTHORIZATION",
    "RETRY",
    "RESUBMISSION",
)


def _dedupe_prompt_lines(value: str) -> tuple[str, int]:
    """Deduplicate complete prompt lines while preserving human readability."""

    lines = [line.strip() for line in value.replace("\r", "").split("\n")]
    kept: list[str] = []
    seen: set[str] = set()
    duplicates = 0
    for line in lines:
        if not line:
            continue
        key = re.sub(r"\s+", " ", line).casefold()
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        kept.append(line)
    return "\n".join(kept), duplicates


def compile_visual_prompt_v2_2(
    constitution: VisualProductionConstitution,
    image_prompt: str,
    video_prompt: str,
    negative_prompt: str,
    *,
    includes_female: bool,
    event_type: str,
    source_tier: str,
    source_certainty: str,
    source_facts: Sequence[str],
    art_direction: Sequence[str],
    dossier_refs: Sequence[str],
    execution_envelope: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Compile visual-only provider text and keep execution state beside it.

    V2.1 put approval and call-state strings into the provider prompt.  V2.2
    makes the separation explicit: the provider sees visual instructions only;
    the executor retains the immutable envelope used for local gating.
    """

    if not image_prompt.strip() or not video_prompt.strip() or not negative_prompt.strip():
        raise VisualPlanningValidationError("PROMPT_COMPONENT_EMPTY")
    if event_type not in _ALLOWED_EVENT_TYPES:
        raise VisualPlanningValidationError("PROMPT_EVENT_TYPE_INVALID")
    visual_rules = [
        "Literal visible action is primary; the narrated event must be understandable with audio muted.",
        "No graphics, diagrams, UI, explainer panels, captions, readable text, logos, watermarks, or placeholders.",
        "No loops, freeze-frame filler, visual filler, unsupported source facts, or invented exact geography.",
        f"EVENT_TYPE={event_type}; SOURCE_TIER={source_tier}; SOURCE_CERTAINTY={source_certainty}.",
        "SOURCE_FACTS=" + (" | ".join(str(item) for item in source_facts) if source_facts else "NONE") + ".",
        "ART_DIRECTION=" + (" | ".join(str(item) for item in art_direction) if art_direction else "NONE") + ".",
        "CHARACTER_DOSSIERS=" + (" | ".join(str(item) for item in dossier_refs) if dossier_refs else "NONE") + ".",
        "Source facts and art direction remain separate; unknown attributes stay unknown.",
    ]
    if event_type == "SOURCE_CONSTRAINED_UNSEEN_EVENT":
        visual_rules.append(
            "Show only observable human consequence or reaction; keep the unseen agent, mechanism, object, beam, portal, and supernatural form offscreen."
        )
    legacy_female = constitution.data.get("LEGACY_FEMALE_REUSE_POLICY")
    if isinstance(legacy_female, Mapping) and legacy_female.get(
        "ZERO_LEGACY_FEMALE_REUSE_REQUIRED"
    ) is True:
        visual_rules.append(
            "Legacy female-containing or uncertain assets are forensic-only and cannot be reused; no blur, crop, mask, occlusion, reframing, or defect-hiding salvage."
        )
    if includes_female:
        visual_rules.append(_female_prompt_appendix(constitution))

    compiled_image, image_duplicates = _dedupe_prompt_lines(
        image_prompt.strip() + "\n" + "\n".join(visual_rules)
    )
    compiled_video, video_duplicates = _dedupe_prompt_lines(
        video_prompt.strip() + "\n" + "\n".join(visual_rules)
    )
    negative_lines = [
        negative_prompt.strip(),
        "graphics, diagrams, UI, explainer panels, placeholder frames",
        "readable text, captions, logos, watermark",
        "loops, freeze-frame filler, unsupported source details, extra characters, continuity changes",
    ]
    compiled_negative, negative_duplicates = _dedupe_prompt_lines("\n".join(negative_lines))
    contradictions = validate_prompt_contradictions(compiled_video, compiled_negative)
    all_provider_text = "\n".join((compiled_image, compiled_video, compiled_negative))
    state_terms = [term for term in _V22_EXECUTION_STATE_TERMS if term.casefold() in all_provider_text.casefold()]
    if state_terms:
        raise VisualPlanningValidationError(
            "EXECUTION_STATE_IN_PROVIDER_PROMPT:" + ",".join(state_terms)
        )
    if contradictions:
        raise VisualPlanningValidationError(";".join(contradictions))
    return {
        "IMAGE_PROMPT": image_prompt.strip(),
        "VIDEO_PROMPT": video_prompt.strip(),
        "NEGATIVE_PROMPT": negative_prompt.strip(),
        "VISUAL_PROVIDER_PROMPT": {
            "positive_image": compiled_image,
            "positive_video": compiled_video,
            "negative": compiled_negative,
        },
        "EXECUTION_ENVELOPE": dict(execution_envelope or {}),
        "PROMPT_CONTRADICTIONS": contradictions,
        "DUPLICATED_NEGATIVE_PROMPT_LINES": negative_duplicates,
        "DUPLICATED_POSITIVE_PROMPT_LINES": image_duplicates + video_duplicates,
        "EXECUTION_STATE_TEXT_IN_PROVIDER_PROMPT": state_terms,
        "SOURCE_FACTS": list(source_facts),
        "ART_DIRECTION": list(art_direction),
        "CHARACTER_DOSSIER_REFERENCES": list(dossier_refs),
    }


def validate_v2_2_prompt_bundle(
    prompt_bundle: Mapping[str, Any],
    *,
    includes_female: bool,
) -> list[str]:
    errors: list[str] = []
    provider = prompt_bundle.get("VISUAL_PROVIDER_PROMPT")
    if not isinstance(provider, Mapping):
        return ["V22_VISUAL_PROVIDER_PROMPT_MISSING"]
    for key in ("positive_image", "positive_video", "negative"):
        if not str(provider.get(key, "")).strip():
            errors.append(f"V22_PROVIDER_PROMPT_{key.upper()}_MISSING")
    text = "\n".join(str(provider.get(key, "")) for key in ("positive_image", "positive_video", "negative"))
    for term in _V22_EXECUTION_STATE_TERMS:
        if term.casefold() in text.casefold():
            errors.append(f"V22_EXECUTION_STATE_IN_PROVIDER_PROMPT:{term}")
    errors.extend(f"V22_{item}" for item in validate_prompt_contradictions(
        str(provider.get("positive_video", "")), str(provider.get("negative", ""))
    ))
    if includes_female and "FEMALE_MODESTY_MAXIMUM_STRICT=TRUE" not in str(provider.get("positive_video", "")):
        errors.append("V22_FEMALE_MODESTY_CONTRACT_NOT_COMPILED")
    if prompt_bundle.get("PROMPT_CONTRADICTIONS") != []:
        errors.append("V22_PROMPT_CONTRADICTIONS_MUST_BE_ZERO")
    if prompt_bundle.get("DUPLICATED_NEGATIVE_PROMPT_LINES") != 0:
        errors.append("V22_DUPLICATED_NEGATIVE_LINES_MUST_BE_ZERO")
    if not isinstance(prompt_bundle.get("EXECUTION_ENVELOPE"), Mapping):
        errors.append("V22_EXECUTION_ENVELOPE_MISSING")
    return errors


def validate_v2_2_storyboard(
    storyboard: Mapping[str, Any],
    constitution: VisualProductionConstitution,
    *,
    dossiers: Sequence[Mapping[str, Any]],
    temporal_audits: Mapping[str, Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Fail-closed validation for the complete V2.2 preproduction packet."""

    errors: list[str] = []
    errors.extend(validate_constitution_v2_2_mapping(constitution.data))
    if storyboard.get("VISUAL_CONSTITUTION_LOADED") is not True:
        errors.append("VISUAL_CONSTITUTION_LOADED_MUST_BE_TRUE")
    if storyboard.get("VISUAL_CONSTITUTION_VERSION") != constitution.version:
        errors.append("VISUAL_CONSTITUTION_VERSION_MISMATCH")
    if storyboard.get("VISUAL_CONSTITUTION_SHA256") != constitution.sha256:
        errors.append("VISUAL_CONSTITUTION_SHA256_MISMATCH")
    required_false = (
        "VISUAL_GENERATION_ALLOWED",
        "APPROVED_STORYBOARD_SHA256",
        "PLANNED_GRAPHICS_COUNT",
        "NETWORK_CALLS",
        "PROVIDER_CALLS",
        "PAID_CALLS",
        "SUB_FRAME_MICRO_SHOTS",
        "MICRO_CRUMB_SHOTS",
    )
    if storyboard.get("VISUAL_GENERATION_ALLOWED") is not False:
        errors.append("VISUAL_GENERATION_MUST_BE_FALSE")
    if storyboard.get("APPROVED_STORYBOARD_SHA256") is not None:
        errors.append("APPROVED_STORYBOARD_SHA256_MUST_BE_NULL")
    for key in ("PLANNED_GRAPHICS_COUNT", "NETWORK_CALLS", "PROVIDER_CALLS", "PAID_CALLS", "SUB_FRAME_MICRO_SHOTS", "MICRO_CRUMB_SHOTS"):
        if storyboard.get(key) != 0:
            errors.append(f"{key}_MUST_EQUAL_ZERO")
    if storyboard.get("STORYBOARD_STATUS") != "AWAITING_HUMAN_APPROVAL":
        errors.append("STORYBOARD_STATUS_MUST_AWAIT_HUMAN_APPROVAL")
    if storyboard.get("CURRENT_NARRATION_FROZEN") is not True or storyboard.get("AUDIO_IS_DURATION_AUTHORITY") is not True:
        errors.append("AUDIO_AUTHORITY_OR_NARRATION_FREEZE_INVALID")
    dossier_result = validate_character_dossiers(dossiers)
    errors.extend(dossier_result["errors"])
    if {str(item.get("CHARACTER_ID")) for item in dossiers} != {"ADAM", "HAWWA_SPOUSE", "MUSA"}:
        errors.append("V22_REQUIRED_CHARACTER_DOSSIERS_INCOMPLETE")

    shots = storyboard.get("MICRO_SHOTS")
    if not isinstance(shots, Sequence) or isinstance(shots, (str, bytes)) or not shots:
        errors.append("MICRO_SHOTS_MISSING")
        shots = []
    audio_duration = float(storyboard.get("AUDIO_DURATION_SECONDS", -1.0))
    fps = float(storyboard.get("PRODUCTION_FPS", 0))
    minimum_frames = int(storyboard.get("MINIMUM_VISUAL_SHOT_FRAMES", 0))
    previous_end: float | None = None
    beat_ids: set[str] = set()
    reused_rows = 0
    new_rows = 0
    for index, shot in enumerate(shots):
        if not isinstance(shot, Mapping):
            errors.append(f"MICRO_SHOT_{index}_NOT_OBJECT")
            continue
        shot_id = str(shot.get("MICRO_SHOT_ID", index))
        for key in (
            "MICRO_SHOT_ID", "TIMELINE_IN", "TIMELINE_OUT", "DURATION", "NARRATION_TEXT",
            "AUDIO_BEAT_ID", "AUDIO_BEAT_START", "AUDIO_BEAT_END", "AUDIO_TRANSCRIPT_FRAGMENT",
            "AUDIO_SOURCE_TIMING_REFERENCE", "EVENT_ID", "EVENT_TYPE", "EVENT_ROLE",
            "CHARACTERS", "VISIBLE_ACTION", "MUTE_COMPREHENSION_TARGET", "SOURCE",
            "PLANNED_MUTE_COMPREHENSION", "ACTUAL_RENDER_MUTE_COMPREHENSION",
        ):
            if key not in shot:
                errors.append(f"{shot_id}_{key}_MISSING")
        start, end, duration = shot.get("TIMELINE_IN"), shot.get("TIMELINE_OUT"), shot.get("DURATION")
        if not all(isinstance(item, (int, float)) for item in (start, end, duration)):
            errors.append(f"{shot_id}_TIME_FIELDS_INVALID")
            continue
        start_f, end_f, duration_f = float(start), float(end), float(duration)
        if end_f <= start_f or abs((end_f - start_f) - duration_f) > 1e-6:
            errors.append(f"{shot_id}_TIME_RANGE_INVALID")
        if previous_end is not None and abs(start_f - previous_end) > 1e-6:
            errors.append(f"{shot_id}_TIMELINE_GAP_OR_OVERLAP")
        previous_end = end_f
        final_audio_tail = (
            index == len(shots) - 1
            and storyboard.get("FINAL_AUDIO_TAIL_NON_FRAME_ALIGNED") is True
        )
        if fps <= 0 or abs(start_f * fps - round(start_f * fps)) > 1e-6 or (
            not final_audio_tail and abs(end_f * fps - round(end_f * fps)) > 1e-6
        ):
            errors.append(f"{shot_id}_FRAME_BOUNDARY_NOT_QUANTIZED")
        if duration_f * fps < minimum_frames - 1e-6:
            errors.append(f"{shot_id}_BELOW_MINIMUM_VISUAL_SHOT_FRAMES")
        if shot.get("AUDIO_BEAT_END") < shot.get("AUDIO_BEAT_START"):
            errors.append(f"{shot_id}_AUDIO_BEAT_RANGE_INVALID")
        if not str(shot.get("AUDIO_TRANSCRIPT_FRAGMENT", "")).strip():
            errors.append(f"{shot_id}_AUDIO_TRANSCRIPT_FRAGMENT_EMPTY")
        beat_ids.add(str(shot.get("AUDIO_BEAT_ID")))
        if shot.get("NARRATION_TEXT") != shot.get("AUDIO_TRANSCRIPT_FRAGMENT"):
            errors.append(f"{shot_id}_STALE_OR_NONCANONICAL_NARRATION_TEXT")
        if shot.get("ACTUAL_RENDER_MUTE_COMPREHENSION") != "NOT_RUN":
            errors.append(f"{shot_id}_ACTUAL_RENDER_MUTE_MUST_BE_NOT_RUN")
        planned = shot.get("PLANNED_MUTE_COMPREHENSION")
        if not isinstance(planned, Mapping) or planned.get("PLANNED_MUTE_COMPREHENSION") is not True:
            errors.append(f"{shot_id}_PLANNED_MUTE_COMPREHENSION_MUST_PASS")
        if shot.get("EVENT_ROLE") == "LITERAL_EVENT":
            for key in ("PLANNED_EVENT_VISIBLE", "PLANNED_SUBJECT_VISIBLE", "PLANNED_ACTION_VISIBLE", "PLANNED_OBJECT_VISIBLE", "PLANNED_RESULT_VISIBLE"):
                if not isinstance(planned, Mapping) or planned.get(key) is not True:
                    errors.append(f"{shot_id}_{key}_MUST_BE_TRUE")
        if shot.get("EVENT_TYPE") == "SOURCE_CONSTRAINED_UNSEEN_EVENT":
            if shot.get("UNSEEN_ENTITY_VISIBLE") is not False or shot.get("UNSEEN_MECHANISM_VISIBLE") is not False:
                errors.append(f"{shot_id}_UNSEEN_EVENT_VISIBILITY_INVALID")
        if shot.get("SOURCE") in {"EXISTING", "REASSIGNED_EXISTING"}:
            reused_rows += 1
            for key in ("ASSET_ID", "ASSET_PATH", "ASSET_SHA256", "SOURCE_IN", "SOURCE_OUT", "ACTUAL_VISIBLE_CONTENT", "EXACT_AUDIO_RELEVANCE", "NEW_VISUAL_INFORMATION", "SEMANTIC_CATEGORY"):
                if key not in shot:
                    errors.append(f"{shot_id}_{key}_MISSING")
            if shot.get("FEMALE_PRESENT") != "FALSE" or shot.get("UNCERTAIN_FEMALE_PRESENCE") is not False:
                errors.append(f"{shot_id}_LEGACY_FEMALE_REUSE_NOT_PROVEN_FALSE")
            if shot.get("REUSE_ALLOWED") is not True or shot.get("MONTAGE_ELIGIBLE") is not True:
                errors.append(f"{shot_id}_LEGACY_REUSE_NOT_ALLOWED_FOR_SAFE_ASSET")
            if temporal_audits is not None and not isinstance(temporal_audits.get(str(shot.get("ASSET_ID"))), Mapping):
                errors.append(f"{shot_id}_TEMPORAL_AUDIT_MISSING")
        elif shot.get("SOURCE") == "NEW_GENERATION_REQUIRED":
            new_rows += 1
            for key in ("IMAGE_PROMPT", "VIDEO_PROMPT", "NEGATIVE_PROMPT", "VISUAL_PROVIDER_PROMPT", "EXECUTION_ENVELOPE", "PROVIDER_REQUEST_DURATION_SECONDS", "GENERATION_UNIT_ID"):
                if key not in shot:
                    errors.append(f"{shot_id}_{key}_MISSING")
            prompt_errors = validate_v2_2_prompt_bundle(
                {
                    "VISUAL_PROVIDER_PROMPT": shot.get("VISUAL_PROVIDER_PROMPT"),
                    "EXECUTION_ENVELOPE": shot.get("EXECUTION_ENVELOPE"),
                    "PROMPT_CONTRADICTIONS": shot.get("PROMPT_CONTRADICTIONS", []),
                    "DUPLICATED_NEGATIVE_PROMPT_LINES": shot.get("DUPLICATED_NEGATIVE_PROMPT_LINES", 0),
                },
                includes_female=bool(shot.get("INCLUDES_FEMALE")),
            )
            errors.extend(f"{shot_id}_{item}" for item in prompt_errors)
            if shot.get("PROVIDER_REQUEST_DURATION_SECONDS") not in (4, 6, 8):
                errors.append(f"{shot_id}_PROVIDER_DURATION_UNSUPPORTED")
        else:
            errors.append(f"{shot_id}_SOURCE_INVALID")
    if previous_end is None or abs(previous_end - audio_duration) > 1e-6:
        errors.append("MICRO_SHOT_TIMELINE_DOES_NOT_END_AT_AUDIO_DURATION")
    if storyboard.get("STALE_PARENT_NARRATION_INHERITANCE") != 0:
        errors.append("STALE_PARENT_NARRATION_INHERITANCE_MUST_EQUAL_ZERO")
    if storyboard.get("AUDIO_TIMELINE_GAPS") != 0 or storyboard.get("AUDIO_TIMELINE_OVERLAPS") != 0:
        errors.append("AUDIO_TIMELINE_MUST_BE_GAP_FREE_AND_NONOVERLAPPING")
    if storyboard.get("UNJUSTIFIED_EXACT_RANGE_REUSE") != 0 or storyboard.get("UNJUSTIFIED_SEMANTIC_REPETITION") != 0:
        errors.append("REUSE_GUARDS_MUST_BE_ZERO")
    if storyboard.get("LEGACY_FEMALE_REUSE_COUNT") != 0:
        errors.append("LEGACY_FEMALE_REUSE_COUNT_MUST_EQUAL_ZERO")
    checks = {
        "constitution": not any(item.endswith("MUST_BE_TRUE") or item.endswith("INVALID") for item in errors if item.startswith(("CONSTITUTION", "AUDIO_BEAT_MAPPING_POLICY", "FRAME_QUANTIZATION_POLICY", "PROMPT_COMPILATION"))),
        "audio_mapping": not any("AUDIO_" in item or "NARRATION" in item or "TIMELINE" in item for item in errors),
        "frame_quantization": not any("FRAME_" in item or "MINIMUM_VISUAL_SHOT_FRAMES" in item for item in errors),
        "prompt_separation": not any("PROMPT" in item or "EXECUTION_STATE" in item for item in errors),
        "zero_legacy_female_reuse": storyboard.get("LEGACY_FEMALE_REUSE_COUNT") == 0 and reused_rows >= 0,
        "mute_comprehension_precheck": storyboard.get("MUTE_COMPREHENSION_PRECHECK") == "PASS",
        "visual_generation_blocked": storyboard.get("VISUAL_GENERATION_ALLOWED") is False,
    }
    return {
        "status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "checks": checks,
        "micro_shot_count": len(shots),
        "reused_micro_shot_count": reused_rows,
        "new_generation_micro_shot_count": new_rows,
        "audio_beat_ids_seen": sorted(beat_ids),
    }


def source_fact_art_direction_overlap(
    source_facts: Sequence[str],
    art_direction: Sequence[str],
) -> set[str]:
    return {str(item) for item in source_facts} & {str(item) for item in art_direction}


__all__ = [
    "CONSTITUTION_RELATIVE_PATH",
    "CONSTITUTION_VERSION",
    "CONSTITUTION_V2_1_RELATIVE_PATH",
    "CONSTITUTION_V2_1_VERSION",
    "ConstitutionValidationError",
    "VisualPlanningValidationError",
    "VisualProductionConstitution",
    "assert_visual_generation_gate",
    "canonical_json_sha256",
    "compile_visual_prompt_v2",
    "load_visual_production_constitution_v2",
    "load_visual_production_constitution_v2_1",
    "sha256_file",
    "source_fact_art_direction_overlap",
    "validate_legacy_female_asset_record",
    "validate_legacy_female_reuse_plan",
    "validate_character_dossier",
    "validate_character_dossiers",
    "validate_constitution_mapping",
    "validate_micro_shot_storyboard",
    "validate_prompt_contradictions",
    "validate_source_hierarchy_records",
    "validate_temporal_reuse_audit",
]
