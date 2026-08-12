"""Offline cinematic-director architecture for future SIRAJ episodes.

V2 is a typed creative-quality contract, not a provider, retry mechanism, or
Episode 002 rewrite tool.  Storyboard structure remains deterministic and
outside of this module's ownership.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

from src.application.cinematic_shot_contracts import CREATIVE_FIELDS, STRUCTURAL_FIELDS


SCHEMA_VERSION = "siraj-cinematic-director-v2"
FRESH_EPISODE_MODE = "NATIVE_SIRAJ_CINEMATIC_DIRECTOR_V2"
FRESH_INITIALIZATION = "FRESH_EPISODE"
GENERIC_PHRASES = frozenset({
    "cinematic historical scene", "generic historical scene", "beautiful cinematic scene", "epic cinematic scene",
})
ABSTRACT_TERMS = frozenset({"field", "trace", "boundary", "band", "plane", "haze", "gradient", "seam", "abstract path", "unresolved space"})
MATERIAL_TERMS = frozenset({"stone", "wood", "soil", "dust", "water", "paper", "metal", "weather", "texture", "surface", "earth", "furrow", "ridge"})
SCALE_TOKENS = ("extreme wide", "wide", "full", "medium", "close", "macro", "abstract scaleless")


class CinematicDirectorV2Error(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class SequenceVisualGrammar:
    sequence_id: str
    dramatic_function: str
    visual_thesis: str
    material_world: str
    dominant_spatial_logic: str
    scale_strategy: str
    camera_language: str
    lens_language: str
    composition_language: str
    lighting_language: str
    motion_language: str
    environment_language: str
    symbolic_strategy: str
    continuity_rules: str
    variation_rules: str
    escalation_rules: str
    abstraction_budget: str
    physicality_target: str
    iconic_anchor_requirement: str
    anti_repetition_constraints: str
    source_sensitivity_constraints: str


def fresh_episode_initialization(episode_id: str) -> dict[str, Any]:
    """Return a no-inheritance creative initialization contract."""

    return {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "cinematic_mode": FRESH_EPISODE_MODE,
        "creative_initialization": FRESH_INITIALIZATION,
        "permitted_inheritance": [
            "SIRAJ_BRAND_PRINCIPLES", "CINEMATIC_QUALITY_FRAMEWORK", "SAFETY_CONSTRAINTS",
            "PRODUCTION_ARCHITECTURE", "PROVIDER_KNOWLEDGE", "GENERAL_LESSONS",
        ],
        "forbidden_automatic_inheritance": [
            "EP002_VISUAL_CONCEPTS", "EP002_MOTIFS", "EP002_PALETTES", "EP002_SEQUENCE_GRAMMAR",
            "EP002_PROMPT_LANGUAGE", "EP002_CAMERA_GRAMMAR",
        ],
        "episode_002_visual_grammar_inherited": False,
        "episode_002_motifs_inherited": False,
        "provider_calls_by_default": 0,
    }


def validate_sequence_grammar(value: Mapping[str, Any]) -> SequenceVisualGrammar:
    required = (
        "sequence_id", "dramatic_function", "visual_thesis", "material_world", "dominant_spatial_logic",
        "scale_strategy", "camera_language", "lens_language", "composition_language", "lighting_language",
        "motion_language", "environment_language", "symbolic_strategy", "continuity_rules", "variation_rules",
        "escalation_rules", "abstraction_budget", "physicality_target", "iconic_anchor_requirement",
        "anti_repetition_constraints", "source_sensitivity_constraints",
    )
    missing = [key for key in required if not str(value.get(key) or "").strip()]
    if missing:
        raise CinematicDirectorV2Error("SEQUENCE_VISUAL_GRAMMAR_FIELDS_REQUIRED:" + ",".join(missing))
    return SequenceVisualGrammar(**{key: str(value[key]).strip() for key in required})


def _text(direction: Mapping[str, Any]) -> str:
    return " ".join(str(direction.get(key) or "") for key in CREATIVE_FIELDS).lower()


def _has_any(text: str, terms: Sequence[str] | frozenset[str]) -> bool:
    return any(term in text for term in terms)


def classify_abstraction(direction: Mapping[str, Any]) -> str:
    text = _text(direction)
    abstract = sum(term in text for term in ABSTRACT_TERMS)
    material = sum(term in text for term in MATERIAL_TERMS)
    if abstract and not material:
        return "ABSTRACT_ATMOSPHERIC" if "haze" in text or "gradient" in text else "ABSTRACT_GRAPHIC"
    if material and abstract:
        return "HYBRID"
    if material:
        return "PHYSICAL_SYMBOLIC" if str(direction.get("symbolism") or "").strip() else "PHYSICAL_CONCRETE"
    return "HYBRID"


def quality_vector(direction: Mapping[str, Any]) -> dict[str, str]:
    """A decision aid, deliberately not an arbitrary aggregate score."""

    text = _text(direction)
    required = ("visual_concept", "composition", "environment", "continuity_strategy", "distinctness_strategy")
    vector = {key: "PASS" if str(direction.get(key) or "").strip() else "FAIL" for key in required}
    for key in ("camera_intent", "lighting", "motion"):
        vector[key] = "PASS" if str(direction.get(key) or "").strip() else "WARN"
    vector["material_specificity"] = "PASS" if _has_any(text, MATERIAL_TERMS) else "WARN"
    vector["renderability"] = "FAIL" if _has_any(text, GENERIC_PHRASES) else "PASS"
    # A preservation constraint such as "no prohibited depiction" is evidence
    # of safety, not a depiction.  Flag only affirmative imperatives.
    vector["source_safety"] = (
        "FAIL"
        if any(phrase in text for phrase in ("depict the prophet", "show prophet", "visible prophet"))
        else "PASS"
    )
    vector["abstraction_balance"] = "WARN" if classify_abstraction(direction).startswith("ABSTRACT") else "PASS"
    return vector


def renderability_check(direction: Mapping[str, Any]) -> list[str]:
    text = _text(direction)
    issues: list[str] = []
    if _has_any(text, GENERIC_PHRASES):
        issues.append("GENERIC_PROMPT_REGRESSION")
    if classify_abstraction(direction).startswith("ABSTRACT") and not _has_any(text, MATERIAL_TERMS):
        issues.append("OVERCONCEPTUALIZED_WITHOUT_PHYSICAL_ANCHOR")
    if str(direction.get("motion") or "").strip() and not str(direction.get("camera_intent") or "").strip():
        issues.append("CAMERA_MOVEMENT_WITHOUT_MOTIVATION")
    return issues


def prose_image_gap_check(direction: Mapping[str, Any]) -> str:
    rationale_words = len(str(direction.get("cinematic_treatment") or "").split()) + len(str(direction.get("symbolism") or "").split())
    image_fields = sum(bool(str(direction.get(key) or "").strip()) for key in ("visual_concept", "composition", "environment", "camera_intent", "lighting", "motion"))
    return "WARN_PROSE_IMAGE_GAP" if rationale_words > 45 and image_fields < 4 else "PASS"


def cross_sequence_signatures(groups: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, dict[str, Any]]:
    signatures: dict[str, dict[str, Any]] = {}
    for group_id, directions in groups.items():
        text = " ".join(_text(direction) for direction in directions)
        signatures[group_id] = {
            "abstraction_classes": sorted({classify_abstraction(direction) for direction in directions}),
            "materiality": "PRESENT" if _has_any(text, MATERIAL_TERMS) else "SPARSE",
            "scale_terms": [token for token in SCALE_TOKENS if token in text],
            "camera_terms": sorted({str(d.get("camera_intent") or "")[:80] for d in directions}),
            "lighting_terms": sorted({str(d.get("lighting") or "")[:80] for d in directions}),
            "motif_terms": sorted(term for term in ABSTRACT_TERMS if term in text),
        }
    return signatures


def cross_sequence_distinctness(groups: Mapping[str, Sequence[Mapping[str, Any]]]) -> list[dict[str, str]]:
    signatures = cross_sequence_signatures(groups)
    warnings: list[dict[str, str]] = []
    identifiers = list(signatures)
    for index, left in enumerate(identifiers):
        for right in identifiers[:index]:
            if signatures[left] == signatures[right]:
                warnings.append({"left": left, "right": right, "issue": "IDENTICAL_VISUAL_SIGNATURE"})
    return warnings


def scale_diversity_check(directions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    observed = [
        token
        for direction in directions
        for token in SCALE_TOKENS
        if token in _text(direction)
    ]
    return {
        "observed_scale_terms": observed,
        "status": "WARN" if len(directions) >= 3 and len(set(observed)) <= 1 else "PASS",
        "rule": "Warn on prolonged monotony; do not enforce mechanical alternation.",
    }


def lighting_progression_check(directions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    lighting = [str(direction.get("lighting") or "").strip() for direction in directions]
    return {
        "lighting_states": lighting,
        "status": "WARN" if len(directions) >= 3 and len(set(lighting)) <= 1 else "PASS",
        "rule": "Lighting changes only when dramatic state benefits; decorative variation is not required.",
    }


def motif_lifecycle(directions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = Counter(
        term
        for direction in directions
        for term in ABSTRACT_TERMS
        if term in _text(direction)
    )
    return {
        "motif_counts": dict(sorted(counts.items())),
        "status": "WARN" if any(count >= max(4, len(directions) - 1) for count in counts.values()) else "PASS",
        "rule": "Repeated motifs require deliberate development, not automatic rejection.",
    }


def sequence_quality_review(groups: Mapping[str, Sequence[Mapping[str, Any]]]) -> dict[str, Any]:
    """Compose the V2 decision aids without invoking a model or provider."""

    return {
        "sequence_visual_grammar": "REQUIRED_BEFORE_NEW_EPISODE_PROVIDER_DIRECTION",
        "iconic_visual_anchor_system": "SEQUENCE_AWARE_OPTIONAL_NOT_PER_SHOT_MANDATORY",
        "abstraction_budget": {key: [classify_abstraction(row) for row in value] for key, value in groups.items()},
        "materiality_pass": {key: any(_has_any(_text(row), MATERIAL_TERMS) for row in value) for key, value in groups.items()},
        "scale_diversity": {key: scale_diversity_check(value) for key, value in groups.items()},
        "lighting_progression": {key: lighting_progression_check(value) for key, value in groups.items()},
        "motif_lifecycle": {key: motif_lifecycle(value) for key, value in groups.items()},
        "cross_sequence_distinctness": cross_sequence_distinctness(groups),
        "environmental_storytelling": {key: all(str(row.get("environment") or "").strip() for row in value) for key, value in groups.items()},
        "cinematic_escalation": "EXPLICIT_SEQUENCE_ESCALATION_RULES_REQUIRED",
        "emotional_beat_hierarchy": "EXPLICIT_SEQUENCE_EMOTIONAL_ARC_REQUIRED",
        "provider_calls": 0,
    }


def validate_v2_direction(direction: Mapping[str, Any]) -> dict[str, Any]:
    """Validate a V1-compatible creative direction without taking structure ownership."""

    forbidden = (set(direction) & STRUCTURAL_FIELDS) - {"shot_id"}
    if forbidden:
        raise CinematicDirectorV2Error("STRUCTURAL_FIELD_FORBIDDEN:" + ",".join(sorted(forbidden)))
    if not str(direction.get("shot_id") or "").strip():
        raise CinematicDirectorV2Error("SHOT_ID_REQUIRED")
    return {
        "shot_id": str(direction["shot_id"]),
        "quality_vector": quality_vector(direction),
        "abstraction_class": classify_abstraction(direction),
        "renderability_issues": renderability_check(direction),
        "prose_image_gap": prose_image_gap_check(direction),
        "structural_change": "NONE",
    }


def evaluate_v1_compatibility(directions: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    validations = [validate_v2_direction(direction) for direction in directions]
    return {
        "schema_version": SCHEMA_VERSION,
        "direction_count": len(validations),
        "v1_roundtrip_compatible": True,
        "structural_ownership_preserved": True,
        "provider_calls": 0,
        "validations": validations,
    }
