from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import pytest

from src.application.unified_constitution_enforcement_v1 import (
    RuleRegistry,
    ValidatorRegistry,
    analyze_sensitive_semantics,
    build_rule_test_artifact,
    load_unified_constitution,
)


REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def registry() -> RuleRegistry:
    return RuleRegistry.build(load_unified_constitution(REPO))


SEMANTIC_ATTACKS = (
    ("female_hair", "woman with visible hair", ("MODESTY",), "FAIL_FEMALE_MODESTY"),
    ("female_hand", "female hand visible", ("MODESTY",), "FAIL_FEMALE_MODESTY"),
    ("female_arm", "woman with exposed arm", ("MODESTY",), "FAIL_FEMALE_MODESTY"),
    ("body_contour", "visible body contours", ("MODESTY",), "FAIL_WARDROBE_POLICY"),
    ("transparent_cloth", "transparent clothing", ("MODESTY",), "FAIL_WARDROBE_POLICY"),
    ("missing_required_woman", "omit the required woman", ("MODESTY",), "FAIL_CHARACTER_REQUIRED_BUT_OMITTED"),
    ("male_bare_torso", "Adam has a gratuitous bare torso", ("MODESTY",), "FAIL_WARDROBE_POLICY"),
    ("divine_depiction", "depict the divine self", ("UNSEEN",), "FAIL_SACRED_DEPICTION"),
    ("invented_angel_body", "invented angel body", ("UNSEEN",), "FAIL_UNSEEN_INVENTION"),
    ("magical_portal", "magical portal as factual unseen mechanism", ("UNSEEN",), "FAIL_UNSEEN_INVENTION"),
    ("magic_beam", "magic beam shortcut", ("UNSEEN",), "FAIL_UNSEEN_INVENTION"),
    ("modern_object", "modern object in the ancient settlement", ("PERIOD",), "FAIL_PERIOD_ANACHRONISM"),
    ("smartphone", "a smartphone appears", ("PERIOD",), "FAIL_PERIOD_ANACHRONISM"),
    ("hollywood_detail", "unsupported Hollywood detail", ("PERIOD",), "FAIL_UNSUPPORTED_MATERIAL_CULTURE"),
    ("invented_adam_costume", "invented Adam archaeological costume", ("PERIOD",), "FAIL_UNSUPPORTED_MATERIAL_CULTURE"),
    ("unsourced_claim", "unsourced factual claim", ("SOURCE",), "FAIL_UNSUPPORTED_CLAIM"),
    ("lower_source_override", "lower source overrides Quran", ("SOURCE",), "FAIL_SOURCE_HIERARCHY"),
    ("certainty_upgrade", "upgrade the certainty downstream", ("SOURCE",), "FAIL_CERTAINTY_MISMATCH"),
    ("israiliyyat_jazm", "Israiliyyat stated certainly", ("SOURCE",), "FAIL_CERTAINTY_MISMATCH"),
    ("israiliyyat_aqidah", "Israiliyyat conflicts with aqidah", ("SOURCE",), "FAIL_ISRAILIYYAT_CONDITIONS"),
    ("weak_hadith_aqidah", "weak hadith used for aqidah", ("SOURCE",), "FAIL_WEAK_HADITH_CONDITIONS"),
    ("hidden_weak_grade", "weak hadith with grade hidden", ("SOURCE",), "FAIL_WEAK_HADITH_CONDITIONS"),
    ("hidden_disagreement", "hide material disagreement", ("SOURCE",), "FAIL_MATERIAL_DISAGREEMENT_DISCLOSURE"),
    ("source_card", "source card", ("MONTAGE",), "FAIL_FORBIDDEN_GRAPHICS"),
    ("title_card", "title card", ("MONTAGE",), "FAIL_FORBIDDEN_GRAPHICS"),
    ("lower_third", "lower third", ("MONTAGE",), "FAIL_FORBIDDEN_GRAPHICS"),
    ("infographic", "infographic", ("MONTAGE",), "FAIL_FORBIDDEN_GRAPHICS"),
    ("burned_subtitle", "burned-in subtitle", ("MONTAGE",), "FAIL_FORBIDDEN_GRAPHICS"),
    ("arbitrary_graphic", "arbitrary new graphic", ("MONTAGE",), "FAIL_FORBIDDEN_GRAPHICS"),
    ("background_music", "background music", ("AUDIO",), "FAIL_MUSIC_DETECTED"),
    ("intro_music", "intro music", ("AUDIO",), "FAIL_MUSIC_DETECTED"),
    ("outro_music", "outro music", ("AUDIO",), "FAIL_MUSIC_DETECTED"),
    ("musical_sting", "musical sting", ("AUDIO",), "FAIL_MUSIC_DETECTED"),
    ("musical_transition", "musical transition", ("AUDIO",), "FAIL_MUSIC_DETECTED"),
    ("embedded_music", "asset with embedded music", ("AUDIO",), "FAIL_MUSIC_DETECTED"),
)


@pytest.mark.parametrize(
    ("case_id", "text", "domains", "expected"),
    SEMANTIC_ATTACKS,
    ids=[case[0] for case in SEMANTIC_ATTACKS],
)
def test_adversarial_sensitive_semantic_matrix(
    case_id: str,
    text: str,
    domains: tuple[str, ...],
    expected: str,
) -> None:
    del case_id
    assert expected in analyze_sensitive_semantics(text, domains)


SAFE_SEMANTICS = (
    ("modesty", "opaque loose period-appropriate garments with full required coverage", ("MODESTY",)),
    ("unseen", "show only an observable consequence while the unseen mechanism remains unknown", ("UNSEEN",)),
    ("period", "neutral art direction for an unsupported historical detail", ("PERIOD",)),
    ("source", "Israiliyyat is disclosed without certainty and does not conflict with aqidah", ("SOURCE",)),
    ("audio", "non-musical footsteps synchronized to the visible action", ("AUDIO",)),
    ("graphics", "external closed captions are delivered as a separate file", ("MONTAGE",)),
)


@pytest.mark.parametrize(("case_id", "text", "domains"), SAFE_SEMANTICS, ids=[case[0] for case in SAFE_SEMANTICS])
def test_safe_sensitive_semantic_matrix(case_id: str, text: str, domains: tuple[str, ...]) -> None:
    del case_id
    assert analyze_sensitive_semantics(text, domains) == ()


STRUCTURED_ATTACKS = (
    ("female_required_missing", "SIRAJ.S01.MODESTY", "wardrobe_contract_validator", ("wardrobe_contract", "required_characters_present"), False),
    ("period_evidence_missing", "SIRAJ.S01.PERIOD_AUTHENTICITY", "period_evidence_validator", ("period_contract", "evidence_approved"), False),
    ("identity_drift", "SIRAJ.S01.RECURRING_CHARACTER_CANONICAL_STILL", "continuity_validator", ("character_contract", "identity_drift"), True),
    ("wrong_character_count", "SIRAJ.S01.RECURRING_CHARACTER_CANONICAL_STILL", "continuity_validator", ("character_contract", "extra_characters"), 1),
    ("certainty_upgrade", "SIRAJ.S02.SOURCE_HIERARCHY", "source_hierarchy_validator", ("claims", 0, "certainty_out"), "CERTAIN"),
    ("source_override", "SIRAJ.S02.SOURCE_HIERARCHY", "source_hierarchy_validator", ("claims", 0, "lower_source_overrides_higher"), True),
    ("israiliyyat_jazm", "SIRAJ.S02.ISRAILIYYAT", "narrator_certainty_validator", ("claims", 0, "classification"), "ISRAILIYYAT"),
    ("weak_hadith_hidden_grade", "SIRAJ.S02.WEAK_HADITH", "hadith_grade_validator", ("claims", 0, "classification"), "WEAK_HADITH"),
    ("material_disagreement_hidden", "SIRAJ.S02.MATERIAL_DISAGREEMENT", "script_disclosure_validator", ("claims", 0, "material_disagreement"), True),
    ("false_hook", "SIRAJ.S03.NARRATIVE_TRUTH_AND_ENGAGEMENT", "script_structure_validator", ("narrative_contract", "false_hook"), True),
    ("filler", "SIRAJ.S03.NARRATIVE_TRUTH_AND_ENGAGEMENT", "filler_validator", ("narrative_contract", "filler"), True),
    ("duration_below_floor", "SIRAJ.S03.EPISODE_DURATION", "duration_policy_validator", ("episode_duration_contract", "minutes"), 5.0),
    ("stale_approval", "SIRAJ.S03.HUMAN_PRESPEND_REVIEWS", "approval_receipt_validator", ("approval_contract", "stale"), True),
    ("approval_hash_mismatch", "SIRAJ.S03.HUMAN_PRESPEND_REVIEWS", "approval_input_hash_validator", ("approval_contract", "artifact_hash_match"), False),
    ("tts_semantic_drift", "SIRAJ.S03.TTS_PERFORMANCE_SCRIPT", "script_semantic_equivalence_validator", ("tts_contract", "semantic_equivalence"), False),
    ("wrong_action", "SIRAJ.S04.VISUAL_SEMANTIC_ALIGNMENT", "render_semantic_validator", ("visual_contract", "action_inverted"), True),
    ("generic_filler", "SIRAJ.S04.VISUAL_SEMANTIC_ALIGNMENT", "storyboard_semantic_validator", ("visual_contract", "generic_filler"), True),
    ("video_share_low", "SIRAJ.S04.VIDEO_SHARE", "timeline_media_share_validator", ("media_share_contract", "video_seconds"), 100),
    ("video_share_high", "SIRAJ.S04.VIDEO_SHARE", "timeline_media_share_validator", ("media_share_contract", "video_seconds"), 500),
    ("reuse_padding", "SIRAJ.S04.REUSE_POLICY", "reuse_semantic_validator", ("reuse_contract", "repetitive_padding"), True),
    ("pilot_missing", "SIRAJ.S04.HARD_SHOT_PILOT", "pilot_coverage_validator", ("pilot_contract", "approved"), False),
    ("freeform_prompt", "SIRAJ.S05.STRUCTURED_PROMPT_COMPILATION", "structured_contract_validator", ("prompt_contract", "structured"), False),
    ("missing_reference", "SIRAJ.S05.STRUCTURED_PROMPT_COMPILATION", "contract_completeness_validator", ("prompt_contract", "canonical_reference_approved"), False),
    ("prompt_hash_mismatch", "SIRAJ.S05.STRUCTURED_PROMPT_COMPILATION", "payload_hash_validator", ("prompt_contract", "payload_hash_match"), False),
    ("executor_prefix_injection", "SIRAJ.S05.STRUCTURED_PROMPT_COMPILATION", "payload_hash_validator", ("prompt_contract", "executor_mutated_payload"), True),
    ("silent_provider_switch", "SIRAJ.S05.PRIMARY_VISUAL_PROVIDER", "provider_profile_validator", ("provider_profile", "automatic_switching"), True),
    ("silent_model_fallback", "SIRAJ.S05.PRIMARY_VISUAL_PROVIDER", "model_profile_validator", ("provider_profile", "silent_fallback"), True),
    ("unapproved_alternate", "SIRAJ.S05.PRIMARY_VISUAL_PROVIDER", "provider_approval_validator", ("provider_profile", "approved"), False),
    ("unbounded_batch", "SIRAJ.S05.PROGRESSIVE_BATCHING", "batch_scope_validator", ("batch_contract", "bounded_request_count"), False),
    ("new_unpiloted_risk", "SIRAJ.S05.PROGRESSIVE_BATCHING", "batch_risk_validator", ("batch_contract", "new_risk_class_piloted"), False),
    ("automatic_retry", "SIRAJ.S05.PAID_RETRY_POLICY", "retry_root_cause_validator", ("retry_contract", "automatic"), True),
    ("identical_quality_retry", "SIRAJ.S05.PAID_RETRY_POLICY", "material_delta_validator", ("retry_contract",), {"requested": True, "automatic": False, "root_cause": True, "material_delta": False, "new_preflight": True, "new_human_authorization": True, "identical_quality_retry": True}),
    ("narrator_replacement", "SIRAJ.S06.NARRATOR_IDENTITY", "voice_identity_validator", ("narrator_contract", "replacement"), True),
    ("quran_llm_reconstruction", "SIRAJ.S06.QURAN_AUDIO_INTEGRITY", "quran_text_integrity_validator", ("quran_contract", "llm_reconstruction"), True),
    ("music_track", "SIRAJ.S06.MUSIC_PROHIBITION", "music_content_validator", ("audio_tracks", 0, "contains_music"), True),
    ("unsupported_factual_sfx", "SIRAJ.S06.SFX_POLICY", "sfx_semantic_validator", ("sfx_contract", "false_factual_presentation"), True),
    ("wrong_period_ambience", "SIRAJ.S06.SFX_POLICY", "period_audio_validator", ("sfx_contract", "period_appropriate"), False),
    ("burned_caption", "SIRAJ.S06.EXTERNAL_CLOSED_CAPTIONS", "caption_separation_validator", ("burned_captions",), True),
    ("manual_duration_override", "SIRAJ.S06.NARRATION_TIMELINE_AUTHORITY", "duration_authority_validator", ("timeline", "duration_ticks"), 999),
    ("montage_unpromoted_asset", "SIRAJ.S07.MONTAGE_ADMISSION", "asset_promotion_receipt_validator", ("approval_contract", "required_receipts_present"), False),
    ("brand_cardinality", "SIRAJ.S07.BRAND_ASSET_DISCOVERY", "brand_asset_cardinality_validator", ("brand_contract", "intro_count"), 2),
    ("brand_face_bypass", "SIRAJ.S07.BRAND_GRAPHICS_EXCEPTION", "graphics_whitelist_validator", ("graphics_contract", "face_policy_pass"), False),
    ("brand_music_bypass", "SIRAJ.S07.BRAND_GRAPHICS_EXCEPTION", "music_policy_validator", ("audio_tracks", 0, "contains_music"), True),
    ("outro_wrong_position", "SIRAJ.S07.INTRO_OUTRO_PLACEMENT", "outro_position_validator", ("placement_contract", "outro_after_core_end"), False),
    ("final_candidate_hash", "SIRAJ.S08.FINAL_HUMAN_CERTIFICATION", "candidate_hash_validator", ("approval_contract", "artifact_hash_match"), False),
    ("auto_thumbnail", "SIRAJ.S08.MANUAL_PUBLIC_TITLE_AND_THUMBNAIL", "publication_metadata_boundary_validator", ("publication_contract", "siraj_generates_thumbnail"), True),
    ("working_title_leak", "SIRAJ.S08.MANUAL_PUBLIC_TITLE_AND_THUMBNAIL", "working_title_leak_validator", ("publication_contract", "working_title_auto_publish"), True),
    ("terminal_paid", "SIRAJ.S09.PAID_EXECUTION_BOUNDARY", "execution_origin_validator", ("paid_contract", "origin"), "TERMINAL"),
    ("missing_click", "SIRAJ.S09.PAID_EXECUTION_BOUNDARY", "human_click_nonce_validator", ("paid_contract", "desktop_click_nonce"), ""),
    ("cost_above_ceiling", "SIRAJ.S09.COST_AUTHORIZATION", "cost_ceiling_validator", ("cost_authorization", "estimated_cost"), 3.0),
    ("stale_rate", "SIRAJ.S09.COST_AUTHORIZATION", "rate_profile_freshness_validator", ("cost_authorization", "stale"), True),
    ("unknown_resubmit", "SIRAJ.S09.UNKNOWN_NO_RESUBMIT", "attempt_state_validator", ("submission_state",), "SUBMISSION_UNKNOWN"),
    ("reconciliation_authorizes", "SIRAJ.S09.UNKNOWN_NO_RESUBMIT", "reconciliation_receipt_validator", ("reconciliation_contract", "authorizes_execution"), True),
    ("historical_unknown_mutated", "SIRAJ.S09.HISTORICAL_UNKNOWN_ATTEMPT", "historical_attempt_ledger_validator", ("historical_unknown_contract", "status"), "FAILED"),
    ("duplicate_transaction", "SIRAJ.S09.IDEMPOTENT_TRANSACTION", "idempotency_validator", ("transaction_contract", "duplicate"), True),
    ("recovery_paid_capability", "SIRAJ.S09.RECOVERY_PRESPEND_ONLY", "recovery_capability_validator", ("recovery_contract", "paid_capability"), True),
    ("duplicate_authority", "SIRAJ.S10.SINGLE_CANONICAL_AUTHORITY", "duplicate_policy_authority_validator", ("governance_contract", "machine_rule_source_count"), 2),
    ("coverage_gap", "SIRAJ.S10.ENFORCEMENT_CHAIN", "enforcement_coverage_validator", ("coverage_contract", "covered_rules"), 50),
    ("test_network_capability", "SIRAJ.S10.SEPARATION_OF_CAPABILITIES", "network_fixture_validator", ("capability_contract", "tests_production_network"), True),
    ("historical_evidence_mutation", "SIRAJ.S10.APPEND_ONLY_EVIDENCE", "evidence_mutation_validator", ("ledger_contract", "historical_mutation"), True),
)


def _set_path(value: dict, path: tuple[object, ...], replacement: object) -> None:
    cursor: object = value
    for part in path[:-1]:
        cursor = cursor[part]  # type: ignore[index]
    cursor[path[-1]] = replacement  # type: ignore[index]


@pytest.mark.parametrize(
    ("case_id", "rule_id", "validator_name", "path", "replacement"),
    STRUCTURED_ATTACKS,
    ids=[case[0] for case in STRUCTURED_ATTACKS],
)
def test_adversarial_structured_contract_matrix(
    registry: RuleRegistry,
    case_id: str,
    rule_id: str,
    validator_name: str,
    path: tuple[object, ...],
    replacement: object,
) -> None:
    artifact = build_rule_test_artifact(registry.require(rule_id), registry.constitution)
    _set_path(artifact, path, replacement)
    if case_id == "unknown_resubmit":
        artifact["resubmit"] = True
    assert ValidatorRegistry(registry).validate(validator_name, artifact).status == "BLOCKED"


def test_public_metadata_absence_does_not_block_episode_production(registry: RuleRegistry) -> None:
    rule = registry.require("SIRAJ.S08.MANUAL_PUBLIC_TITLE_AND_THUMBNAIL")
    artifact = build_rule_test_artifact(rule, registry.constitution)
    artifact["publication_contract"]["public_title"] = None
    artifact["publication_contract"]["thumbnail"] = None
    findings = ValidatorRegistry(registry).validate_rule(rule["id"], artifact)
    assert findings and all(finding.status == "PASS" for finding in findings)


def test_unknown_is_preserved_but_never_resubmitted(registry: RuleRegistry) -> None:
    rule = registry.require("SIRAJ.S09.UNKNOWN_NO_RESUBMIT")
    artifact = build_rule_test_artifact(rule, registry.constitution)
    artifact["submission_state"] = "SUBMISSION_UNKNOWN"
    artifact["resubmit"] = False
    findings = ValidatorRegistry(registry).validate_rule(rule["id"], artifact)
    assert findings and all(finding.status == "PASS" for finding in findings)
