from __future__ import annotations

import pytest

from src.application.local_video_production.voice_cast_v2 import (
    APPROVED_GEMINI_VOICES,
    EDGE_SPEECH_PROVIDER_ID,
    ELEVENLABS_SPEECH_PROVIDER_ID,
    GEMINI_FALLBACK_MODEL,
    GEMINI_PRIMARY_MODEL,
    GEMINI_TTS_PROVIDER_ID,
    GOOGLE_CLOUD_TTS_PROVIDER_ID,
    PRIMARY_VOICE_ID,
    get_approved_cast_entry,
    get_primary_cast_entry,
    get_provider_policy,
    select_male_voice_for_role,
    validate_voice_cast,
    voice_cast_to_dict,
)


def test_gemini_cast_is_valid_and_alnilam_is_primary() -> None:
    validate_voice_cast()
    assert get_primary_cast_entry().voice_id == "Alnilam"
    assert get_primary_cast_entry().provider_id == GEMINI_TTS_PROVIDER_ID
    assert PRIMARY_VOICE_ID == "Alnilam"


def test_only_approved_gemini_voices_are_selectable() -> None:
    manifest = voice_cast_to_dict()
    actual = {entry["voice_id"]: entry["quality_score"] for entry in manifest["entries"] if entry["provider_id"] == GEMINI_TTS_PROVIDER_ID}
    assert actual == APPROVED_GEMINI_VOICES
    with pytest.raises(KeyError, match="VOICE_CAST_ENTRY_NOT_APPROVED"):
        get_approved_cast_entry(GEMINI_TTS_PROVIDER_ID, "UnapprovedVoice")


def test_provider_policy_has_no_google_runtime_path() -> None:
    assert get_provider_policy(GEMINI_TTS_PROVIDER_ID)["primary_model"] == GEMINI_PRIMARY_MODEL
    assert get_provider_policy(GEMINI_TTS_PROVIDER_ID)["fallback_model"] == GEMINI_FALLBACK_MODEL
    assert get_provider_policy(ELEVENLABS_SPEECH_PROVIDER_ID)["activation_status"] == "BLOCKED_BY_SUBSCRIPTION"
    assert get_provider_policy(EDGE_SPEECH_PROVIDER_ID)["role"] == "EMERGENCY_PROVIDER"
    assert get_provider_policy(GOOGLE_CLOUD_TTS_PROVIDER_ID)["activation_status"] == "BLOCKED_BY_BILLING_COUNTRY"
    assert get_provider_policy(GOOGLE_CLOUD_TTS_PROVIDER_ID)["runtime_selectable"] is False


def test_dialogue_selection_is_deterministic_and_distinct() -> None:
    first = select_male_voice_for_role("DIALOGUE")
    second = select_male_voice_for_role("DIALOGUE", exclude_identities={(first.provider_id, first.voice_id)})
    assert first.voice_id == "Alnilam"
    assert second.voice_id == "Charon"
    assert first.voice_id != second.voice_id


def test_manifest_reports_policy_and_dialogue_readiness() -> None:
    result = voice_cast_to_dict()
    assert result["active_provider"] == GEMINI_TTS_PROVIDER_ID
    assert result["primary_voice"] == "Alnilam"
    assert result["dialogue_readiness"] == "READY_WITH_APPROVED_MALE_CAST"
    assert result["female_voice_policy"]["status_without_approved_voice"] == "NEEDS_APPROVED_FEMALE_VOICE"
