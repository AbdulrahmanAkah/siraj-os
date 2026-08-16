"""Series-wide visual-context research contract for SIRAJ.

This layer is intentionally provider-agnostic. It does not perform network calls.
It defines what must be researched, how source authority/uncertainty are recorded,
how a visual dossier is validated, and how the system chooses safe body framing.

Constitutional constraints remain superior to every research result.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "siraj-visual-context-research-v1"
DOSSIER_SCHEMA_VERSION = "siraj-visual-context-dossier-v1"
POLICY_VERSION = "siraj-visual-context-research-policy-v1"

SERIES_POLICY_REL = Path(
    "projects/_series/visual-context-research-policy-v1.json"
)
DOSSIER_DIRNAME = "visual-context-dossiers-v1"

REQUIRED_DIMENSIONS = (
    "environment",
    "character_physical_context",
    "wardrobe",
    "society_and_customs",
    "material_culture",
    "architecture_and_settlement",
    "era_and_chronology",
    "geography_and_climate",
    "flora_fauna_and_landscape",
    "motion_and_face_safety",
)

ALLOWED_DIMENSION_STATUS = frozenset(
    {
        "RESOLVED",
        "UNCERTAIN_NEUTRAL_ONLY",
        "NOT_APPLICABLE",
    }
)
ASSERTIVE_CERTAINTY = frozenset(
    {
        "DIRECTLY_SUPPORTED",
        "STRONGLY_SUPPORTED",
    }
)
NONASSERTIVE_CERTAINTY = frozenset(
    {
        "PERMISSIBLE_INFERENCE",
        "UNCERTAIN",
        "DISPUTED",
    }
)

FRAMING_MODES = frozenset(
    {
        "HANDS_ONLY",
        "BODY_DETAIL",
        "TORSO_HEAD_EXCLUDED",
        "FULL_BODY_HEAD_EXCLUDED",
        "REAR_BODY_HEAD_OPTIONAL_MOTION_SAFE",
        "ENVIRONMENT_DOMINANT_BODY_FRAGMENT",
    }
)


class VisualContextResearchError(RuntimeError):
    pass


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_JSON_READ_FAILED:" + str(path)
        ) from exc
    if not isinstance(value, dict):
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_JSON_OBJECT_REQUIRED:" + str(path)
        )
    return value


def load_series_policy(repo_root: Path) -> dict[str, Any]:
    path = Path(repo_root).resolve() / SERIES_POLICY_REL
    if not path.is_file():
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_SERIES_POLICY_MISSING:" + str(path)
        )
    value = _read_json(path)
    if value.get("schema_version") != POLICY_VERSION:
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_SERIES_POLICY_VERSION_MISMATCH"
        )
    if value.get("scope") != "SERIES_WIDE":
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_POLICY_NOT_SERIES_WIDE"
        )
    if value.get("constitution_precedence") is not True:
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_CONSTITUTION_PRECEDENCE_REQUIRED"
        )
    face = value.get("face_policy")
    if not isinstance(face, Mapping):
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_FACE_POLICY_REQUIRED"
        )
    if face.get("visible_face") != "FORBIDDEN_WITHOUT_EXCEPTION":
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_FACE_POLICY_NOT_ABSOLUTE"
        )
    if face.get("head_required") is not False:
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_HEAD_MUST_NOT_BE_REQUIRED"
        )
    return value


def dossier_path(
    repo_root: Path,
    *,
    episode_id: str,
    context_id: str,
) -> Path:
    return (
        Path(repo_root).resolve()
        / "projects"
        / episode_id
        / "research"
        / DOSSIER_DIRNAME
        / f"{context_id}.json"
    )


def build_research_request(
    *,
    episode_id: str,
    context_id: str,
    narration_text: str,
    visual_brief: Mapping[str, Any],
    domain_profile: str = "AUTO",
) -> dict[str, Any]:
    """Build a research plan, not a provider request.

    Missing narration detail expands research scope; it never grants permission
    to invent visual facts.
    """

    brief_text = json.dumps(
        dict(visual_brief),
        ensure_ascii=False,
        sort_keys=True,
    )
    narration = str(narration_text or "").strip()
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_id": str(episode_id),
        "context_id": str(context_id),
        "domain_profile": str(domain_profile or "AUTO"),
        "narration_text": narration,
        "visual_brief_text": brief_text,
        "required_dimensions": list(REQUIRED_DIMENSIONS),
        "missing_fact_policy": (
            "RESEARCH_REQUIRED_BEFORE_ASSERTIVE_VISUALIZATION"
        ),
        "search_strategy": {
            "search_all_configured_source_classes": True,
            "cross_source_reconciliation_required": True,
            "stop_condition": (
                "EACH_DIMENSION_RESOLVED_OR_EXHAUSTED_WITH_NEUTRAL_FALLBACK"
            ),
            "narration_absence_does_not_authorize_invention": True,
        },
        "research_questions": {
            "environment": (
                "What is directly or strongly supported about the physical "
                "environment, scale, water, terrain, atmosphere and spatial "
                "qualities of this event?"
            ),
            "character_physical_context": (
                "What non-facial physical presentation is supportable for the "
                "person or people, including age class, build, posture, hands, "
                "body silhouette and movement?"
            ),
            "wardrobe": (
                "What clothing, covering, materials and modesty constraints are "
                "supportable, and what would be anachronistic?"
            ),
            "society_and_customs": (
                "What social practices, group behavior, gender/public-space "
                "norms, customs or community context are supportable?"
            ),
            "material_culture": (
                "What tools, containers, furniture, textiles, weapons, transport "
                "or ordinary objects are supportable for the context?"
            ),
            "architecture_and_settlement": (
                "What built environment is supportable, and what architecture "
                "would overclaim uncertain history?"
            ),
            "era_and_chronology": (
                "What chronological facts or uncertainty constrain visual design?"
            ),
            "geography_and_climate": (
                "What geography, season, climate, terrain or weather can be "
                "supported without inventing a precise location?"
            ),
            "flora_fauna_and_landscape": (
                "What plant, animal and landscape details are supported, "
                "uncertain, symbolic, or unsafe to literalize?"
            ),
            "motion_and_face_safety": (
                "What framing prevents any visible face now and under plausible "
                "animation, including side-profile, cheek, nose, reflection or "
                "head-turn reveal?"
            ),
        },
    }


def _source_map(dossier: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    sources = dossier.get("sources")
    if not isinstance(sources, Sequence) or isinstance(
        sources, (str, bytes)
    ):
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_SOURCES_REQUIRED"
        )
    for row in sources:
        if not isinstance(row, Mapping):
            raise VisualContextResearchError(
                "VISUAL_CONTEXT_SOURCE_ROW_INVALID"
            )
        source_id = str(row.get("source_id") or "").strip()
        if not source_id or source_id in result:
            raise VisualContextResearchError(
                "VISUAL_CONTEXT_SOURCE_ID_INVALID_OR_DUPLICATE"
            )
        if row.get("verified") is not True:
            raise VisualContextResearchError(
                "VISUAL_CONTEXT_SOURCE_NOT_VERIFIED:" + source_id
            )
        result[source_id] = row
    return result


def validate_visual_context_dossier(
    *,
    dossier: Mapping[str, Any],
    policy: Mapping[str, Any],
    episode_id: str,
    context_id: str,
) -> dict[str, Any]:
    if dossier.get("schema_version") != DOSSIER_SCHEMA_VERSION:
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_DOSSIER_VERSION_MISMATCH"
        )
    if dossier.get("episode_id") != episode_id:
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_DOSSIER_EPISODE_MISMATCH"
        )
    if dossier.get("context_id") != context_id:
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_DOSSIER_CONTEXT_MISMATCH"
        )
    if dossier.get("status") != "COMPLETE":
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_RESEARCH_NOT_COMPLETE"
        )
    if dossier.get("constitution_precedence") is not True:
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_DOSSIER_CONSTITUTION_PRECEDENCE_REQUIRED"
        )
    if dossier.get("unresolved_conflicts") not in ([], ()):
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_UNRESOLVED_SOURCE_CONFLICT"
        )

    sources_by_id = _source_map(dossier)

    policy_classes = policy.get("source_classes")
    if not isinstance(policy_classes, Sequence) or isinstance(
        policy_classes, (str, bytes)
    ):
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_POLICY_SOURCE_CLASSES_INVALID"
        )
    required_source_classes = {
        str(row.get("id"))
        for row in policy_classes
        if isinstance(row, Mapping) and row.get("required_to_check") is True
    }

    exhaustion = dossier.get("research_exhaustion")
    if not isinstance(exhaustion, Mapping):
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_RESEARCH_EXHAUSTION_REQUIRED"
        )
    if exhaustion.get("search_complete") is not True:
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_SOURCE_SWEEP_INCOMPLETE"
        )
    checked = {
        str(x)
        for x in exhaustion.get("source_classes_checked", [])
    }
    unavailable = exhaustion.get("unavailable_source_classes")
    if not isinstance(unavailable, Mapping):
        unavailable = {}
    accounted = checked | {
        str(key)
        for key, reason in unavailable.items()
        if str(reason or "").strip()
    }
    missing_classes = sorted(required_source_classes - accounted)
    if missing_classes:
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_SOURCE_CLASSES_NOT_EXHAUSTED:"
            + ",".join(missing_classes)
        )

    dimensions = dossier.get("dimensions")
    if not isinstance(dimensions, Mapping):
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_DIMENSIONS_REQUIRED"
        )

    missing_dimensions = [
        name for name in REQUIRED_DIMENSIONS if name not in dimensions
    ]
    if missing_dimensions:
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_DIMENSIONS_MISSING:"
            + ",".join(missing_dimensions)
        )

    for dimension_name in REQUIRED_DIMENSIONS:
        row = dimensions[dimension_name]
        if not isinstance(row, Mapping):
            raise VisualContextResearchError(
                "VISUAL_CONTEXT_DIMENSION_INVALID:" + dimension_name
            )
        status = str(row.get("status") or "")
        if status not in ALLOWED_DIMENSION_STATUS:
            raise VisualContextResearchError(
                "VISUAL_CONTEXT_DIMENSION_STATUS_INVALID:"
                + dimension_name
            )
        facts = row.get("facts", [])
        if not isinstance(facts, Sequence) or isinstance(
            facts, (str, bytes)
        ):
            raise VisualContextResearchError(
                "VISUAL_CONTEXT_FACTS_INVALID:" + dimension_name
            )
        for fact in facts:
            if not isinstance(fact, Mapping):
                raise VisualContextResearchError(
                    "VISUAL_CONTEXT_FACT_INVALID:" + dimension_name
                )
            text = str(fact.get("text") or "").strip()
            certainty = str(fact.get("certainty") or "").strip()
            if not text:
                raise VisualContextResearchError(
                    "VISUAL_CONTEXT_FACT_TEXT_REQUIRED:"
                    + dimension_name
                )
            source_ids = [
                str(x)
                for x in fact.get("source_ids", [])
                if str(x).strip()
            ]
            assertive = fact.get("assertive_visualization") is True
            if assertive:
                if certainty not in ASSERTIVE_CERTAINTY:
                    raise VisualContextResearchError(
                        "VISUAL_CONTEXT_ASSERTIVE_FACT_CERTAINTY_TOO_LOW:"
                        + dimension_name
                    )
                if not source_ids:
                    raise VisualContextResearchError(
                        "VISUAL_CONTEXT_ASSERTIVE_FACT_SOURCE_REQUIRED:"
                        + dimension_name
                    )
            for source_id in source_ids:
                if source_id not in sources_by_id:
                    raise VisualContextResearchError(
                        "VISUAL_CONTEXT_FACT_SOURCE_UNKNOWN:"
                        + source_id
                    )

    face = dossier.get("face_and_body_policy")
    if not isinstance(face, Mapping):
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_DOSSIER_FACE_POLICY_REQUIRED"
        )
    if face.get("face_visibility") != "FORBIDDEN_WITHOUT_EXCEPTION":
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_DOSSIER_FACE_POLICY_INVALID"
        )
    if face.get("head_required") is not False:
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_DOSSIER_HEAD_REQUIREMENT_INVALID"
        )
    if face.get("motion_safe_face_exclusion") is not True:
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_MOTION_SAFE_FACE_EXCLUSION_REQUIRED"
        )

    return dict(dossier)


def load_visual_context_dossier(
    repo_root: Path,
    *,
    episode_id: str,
    context_id: str,
) -> dict[str, Any]:
    policy = load_series_policy(repo_root)
    path = dossier_path(
        repo_root,
        episode_id=episode_id,
        context_id=context_id,
    )
    if not path.is_file():
        raise VisualContextResearchError(
            "VISUAL_CONTEXT_RESEARCH_DOSSIER_MISSING:"
            + str(path)
        )
    dossier = _read_json(path)
    return validate_visual_context_dossier(
        dossier=dossier,
        policy=policy,
        episode_id=episode_id,
        context_id=context_id,
    )


def _context_text(
    *,
    dossier: Mapping[str, Any],
    visual_brief: Mapping[str, Any],
) -> str:
    return (
        json.dumps(
            {
                "research_scope": dossier.get("research_scope"),
                "brief": dict(visual_brief),
            },
            ensure_ascii=False,
        )
        .lower()
    )


def select_body_framing(
    *,
    dossier: Mapping[str, Any],
    visual_brief: Mapping[str, Any],
) -> dict[str, Any]:
    """Choose visible anatomy by narrative utility; never require a head."""

    text = _context_text(
        dossier=dossier,
        visual_brief=visual_brief,
    )
    preferred = dossier.get("framing_preferences")
    if not isinstance(preferred, Sequence) or isinstance(
        preferred, (str, bytes)
    ):
        preferred = []

    preferred_modes = [
        str(mode)
        for mode in preferred
        if str(mode) in FRAMING_MODES
    ]

    gesture_terms = (
        "hand",
        "hands",
        "gesture",
        "holding",
        "touch",
        "write",
        "writing",
        "grasp",
        "offer",
        "receive",
    )
    environment_terms = (
        "environment",
        "garden",
        "landscape",
        "city",
        "battlefield",
        "desert",
        "mountain",
        "sea",
        "paradise",
    )
    identity_terms = (
        "canonical",
        "identity",
        "recurring",
        "wardrobe",
        "silhouette",
        "body proportions",
    )

    if preferred_modes:
        mode = preferred_modes[0]
    elif any(term in text for term in gesture_terms):
        mode = "HANDS_ONLY"
    elif any(term in text for term in identity_terms):
        mode = "FULL_BODY_HEAD_EXCLUDED"
    elif any(term in text for term in environment_terms):
        mode = "ENVIRONMENT_DOMINANT_BODY_FRAGMENT"
    else:
        mode = "TORSO_HEAD_EXCLUDED"

    descriptions = {
        "HANDS_ONLY": (
            "Show only the hands/forearms or the minimum body detail needed "
            "for the action; keep the entire head and face outside frame."
        ),
        "BODY_DETAIL": (
            "Use a non-facial body detail selected for narrative meaning; "
            "exclude the entire face and avoid any reflective reveal."
        ),
        "TORSO_HEAD_EXCLUDED": (
            "Frame torso/arms/body while cropping the entire head outside "
            "the image; preserve modesty and identity through clothing/body."
        ),
        "FULL_BODY_HEAD_EXCLUDED": (
            "Show the full or near-full body for recurring-character identity "
            "while excluding the entire head above the safe crop boundary."
        ),
        "REAR_BODY_HEAD_OPTIONAL_MOTION_SAFE": (
            "A rear body view may include the back of the head only when the "
            "composition makes facial reveal impossible under plausible motion; "
            "otherwise exclude the head."
        ),
        "ENVIRONMENT_DOMINANT_BODY_FRAGMENT": (
            "Let researched environment carry the scene; show only the body "
            "portion needed for human presence, preferably below the neck or "
            "another face-safe fragment."
        ),
    }

    return {
        "mode": mode,
        "description": descriptions[mode],
        "face_visibility": "FORBIDDEN_WITHOUT_EXCEPTION",
        "head_required": False,
        "system_selects_visible_body_element": True,
        "motion_safe_face_exclusion": True,
        "forbidden_reveal_vectors": [
            "visible_face",
            "partial_face",
            "side_profile",
            "cheek_contour",
            "nose_silhouette",
            "eye_or_mouth",
            "reflection",
            "transparent_occlusion",
            "plausible_animation_head_turn_reveal",
        ],
    }


def render_visual_context_prompt(
    *,
    dossier: Mapping[str, Any],
    framing: Mapping[str, Any],
) -> str:
    dimensions = dossier["dimensions"]

    supported: list[str] = []
    neutral_only: list[str] = []
    for dimension_name in REQUIRED_DIMENSIONS:
        row = dimensions[dimension_name]
        status = str(row.get("status") or "")
        for fact in row.get("facts", []):
            text = str(fact.get("text") or "").strip()
            certainty = str(fact.get("certainty") or "").strip()
            if not text:
                continue
            if (
                fact.get("assertive_visualization") is True
                and certainty in ASSERTIVE_CERTAINTY
            ):
                supported.append(
                    f"{dimension_name}: {text}"
                )
            elif certainty in NONASSERTIVE_CERTAINTY:
                neutral_only.append(
                    f"{dimension_name}: {text}"
                )

    parts = [
        "Visual-context research contract: use researched evidence rather "
        "than generic cultural, historical, religious, environmental or "
        "cinematic defaults.",
    ]
    if supported:
        parts.append(
            "Supported visual facts: " + " | ".join(supported)
        )
    if neutral_only:
        parts.append(
            "Uncertain/disputed context: do not assert these details literally; "
            "use neutral non-assertive depiction instead: "
            + " | ".join(neutral_only)
        )

    parts.extend(
        [
            "Final body-framing decision: "
            + str(framing.get("mode"))
            + ". "
            + str(framing.get("description")),
            "The system, not a fixed head-shot rule, chooses whether hands, "
            "torso, a body fragment, full body, or a rear body view is most "
            "useful. A head is never required.",
            "Visible human face is forbidden without exception. The still frame "
            "must also be motion-safe: plausible animation must not reveal a "
            "side profile, cheek, nose, eye, mouth, reflection or latent face.",
            "If research does not support a visual detail strongly enough, "
            "omit it or depict it neutrally; narration silence is never "
            "permission to invent.",
            "Constitutional constraints override every research result, "
            "framing choice and aesthetic preference.",
        ]
    )
    return " ".join(" ".join(parts).split())
