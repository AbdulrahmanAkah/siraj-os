from __future__ import annotations

from src.application.desktop_canonical_reference_generation_v1 import (
    ENVIRONMENT_PROMPT_CONTRACT_VERSION,
    SUPPLEMENTAL_REFERENCE_QUALITY_CHECKS,
    compose_reference_prompt,
)


GLOBAL = {
    "visual_style": (
        "cinematic, grounded, dignified, naturalistic, restrained; "
        "avoid fantasy spectacle and modern visual cues"
    ),
    "historical_uncertainty_policy": (
        "use neutral non-assertive visual design; "
        "do not invent precise historical facts"
    ),
}


def _brief(character: str, state: str) -> dict:
    return {
        "brief": {
            "character": character,
            "narrative_state": state,
            "purpose": "canonical identity for the approved narrative state",
            "composition": [
                "full body",
                "rear view or fully occluded face",
            ],
            "identity_lock": ["stable body identity"],
            "wardrobe": ["simple time-neutral draped garment"],
            "hard_forbidden": [
                "visible face",
                "modern clothing",
            ],
        }
    }


def test_adam_garden_environment_is_inferred_as_paradisal_not_generic():
    prompt = compose_reference_prompt(
        global_style_and_policy=GLOBAL,
        brief=_brief("ADAM", "GARDEN"),
        has_reference_input=False,
    )
    assert ENVIRONMENT_PROMPT_CONTRACT_VERSION in prompt
    assert "extraordinary paradisal garden" in prompt
    assert "ordinary earthly park, forest, farm, orchard" in prompt
    assert "scale, abundance, harmony, serenity, depth, water, vegetation and light" in prompt
    assert "no fantasy architecture" in prompt
    assert "Do not claim a precise physical topology or architecture of Paradise" in prompt
    assert "No visible human face under any circumstance." in prompt
    assert "no generic filler" in prompt


def test_hawwa_garden_uses_same_context_driven_paradise_logic_without_reference_id():
    prompt = compose_reference_prompt(
        global_style_and_policy=GLOBAL,
        brief=_brief("HAWWA", "GARDEN"),
        has_reference_input=False,
    )
    assert "extraordinary paradisal garden" in prompt
    assert "Environmental richness must never weaken face concealment, modesty" in prompt


def test_earth_environment_is_grounded_without_inventing_location():
    prompt = compose_reference_prompt(
        global_style_and_policy=GLOBAL,
        brief=_brief("ADAM", "EARTH"),
        has_reference_input=True,
    )
    assert "unmistakably terrestrial" in prompt
    assert "without inventing a precise historical location" in prompt
    assert "Preserve the same body identity" in prompt


def test_debate_environment_remains_neutral_and_nonassertive():
    prompt = compose_reference_prompt(
        global_style_and_policy=GLOBAL,
        brief=_brief("MUSA", "DEBATE"),
        has_reference_input=False,
    )
    assert "calm, dignified, visually uncluttered" in prompt
    assert "Do not invent a specific historical venue" in prompt
    assert "neutral, non-assertive environmental context" in prompt


def test_unknown_state_falls_back_to_supported_context_instead_of_invented_lore():
    prompt = compose_reference_prompt(
        global_style_and_policy=GLOBAL,
        brief=_brief("GENERIC", "UNSPECIFIED"),
        has_reference_input=False,
    )
    assert "Infer the strongest supported setting" in prompt
    assert "neutral non-assertive environment" in prompt
    assert "Do not invent unsupported doctrinal" in prompt


def test_environment_human_quality_check_is_runtime_supplement():
    assert SUPPLEMENTAL_REFERENCE_QUALITY_CHECKS == (
        "ENVIRONMENT_SUPPORTS_NARRATIVE_STATE",
        "VISUAL_CONTEXT_DOSSIER_MATCH",
        "MOTION_SAFE_FACE_EXCLUSION",
    )
