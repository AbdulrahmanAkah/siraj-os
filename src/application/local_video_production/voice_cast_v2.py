"""Approved Gemini production voice cast and provider policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VOICE_CAST_SCHEMA_V2 = "siraj-production-voice-cast-v2"
GEMINI_TTS_PROVIDER_ID = "gemini-tts-v1"
ELEVENLABS_SPEECH_PROVIDER_ID = "elevenlabs-speech-v1"
EDGE_SPEECH_PROVIDER_ID = "edge-speech-v1"
GOOGLE_CLOUD_TTS_PROVIDER_ID = "google-cloud-tts-v1"
GEMINI_PRIMARY_MODEL = "gemini-3.1-flash-tts-preview"
GEMINI_FALLBACK_MODEL = "gemini-2.5-flash-preview-tts"
PRIMARY_PROVIDER_ID = GEMINI_TTS_PROVIDER_ID
PRIMARY_VOICE_ID = "Alnilam"
MINIMUM_APPROVED_SCORE = 7

APPROVED_GEMINI_VOICES = {
    "Alnilam": 8,
    "Charon": 8,
    "Rasalgethi": 8,
    "Iapetus": 8,
    "Schedar": 7,
    "Enceladus": 7,
}

PROVIDER_POLICY = {
    GEMINI_TTS_PROVIDER_ID: {
        "role": "ACTIVE_PRIMARY_PROVIDER",
        "activation_status": "ACTIVE",
        "primary_model": GEMINI_PRIMARY_MODEL,
        "fallback_model": GEMINI_FALLBACK_MODEL,
        "automatic_fallback_eligible": True,
    },
    ELEVENLABS_SPEECH_PROVIDER_ID: {
        "role": "PREFERRED_PAID_PROVIDER",
        "activation_status": "BLOCKED_BY_SUBSCRIPTION",
        "primary_voice": "XdoLPWNt7ytn6BtU4FBf",
        "automatic_fallback_eligible": False,
    },
    EDGE_SPEECH_PROVIDER_ID: {
        "role": "EMERGENCY_PROVIDER",
        "activation_status": "EMERGENCY_READY",
        "voice_id": "ar-KW-FahedNeural",
        "automatic_fallback_eligible": True,
    },
    GOOGLE_CLOUD_TTS_PROVIDER_ID: {
        "role": "CAPABILITY_RECORDED_ONLY",
        "activation_status": "BLOCKED_BY_BILLING_COUNTRY",
        "runtime_selectable": False,
        "automatic_fallback_eligible": False,
    },
}


@dataclass(frozen=True)
class VoiceCastEntry:
    provider_id: str
    voice_id: str
    provider_rank: int
    voice_rank: int
    gender: str
    quality_score: int | None
    tier: str
    allowed_roles: tuple[str, ...]
    model_reference: str | None = None
    is_primary: bool = False


def _gemini(voice_id: str, rank: int, roles: tuple[str, ...], *, primary: bool = False) -> VoiceCastEntry:
    return VoiceCastEntry(
        provider_id=GEMINI_TTS_PROVIDER_ID,
        voice_id=voice_id,
        provider_rank=1,
        voice_rank=rank,
        gender="male",
        quality_score=APPROVED_GEMINI_VOICES[voice_id],
        tier="PRIMARY" if primary else "SUPPORTING",
        allowed_roles=roles,
        model_reference=GEMINI_PRIMARY_MODEL,
        is_primary=primary,
    )


VOICE_CAST = (
    _gemini("Alnilam", 1, ("PRIMARY_NARRATOR", "NARRATOR", "HOST", "SECONDARY_NARRATOR", "QUOTATION", "DIALOGUE"), primary=True),
    _gemini("Charon", 2, ("SECONDARY_NARRATOR", "HISTORICAL_CHARACTER", "QUOTATION", "DIALOGUE")),
    _gemini("Rasalgethi", 3, ("SECONDARY_NARRATOR", "HISTORICAL_CHARACTER", "QUOTATION", "DIALOGUE")),
    _gemini("Iapetus", 4, ("SECONDARY_NARRATOR", "HISTORICAL_CHARACTER", "QUOTATION", "DIALOGUE")),
    _gemini("Schedar", 5, ("HISTORICAL_CHARACTER", "QUOTATION", "DIALOGUE")),
    _gemini("Enceladus", 6, ("HISTORICAL_CHARACTER", "QUOTATION", "DIALOGUE")),
    VoiceCastEntry(ELEVENLABS_SPEECH_PROVIDER_ID, "XdoLPWNt7ytn6BtU4FBf", 2, 1, "male", None, "PREFERRED_PAID", ("PRIMARY_NARRATOR", "NARRATOR", "HOST")),
    VoiceCastEntry(ELEVENLABS_SPEECH_PROVIDER_ID, "pCKbQ4EPGE06zpEPGNvS", 2, 2, "male", None, "PREFERRED_PAID", ("SECONDARY_NARRATOR", "HISTORICAL_CHARACTER", "QUOTATION", "DIALOGUE")),
    VoiceCastEntry(ELEVENLABS_SPEECH_PROVIDER_ID, "fkqevZRU7Xj52dY1CTkq", 2, 3, "male", None, "PREFERRED_PAID", ("SECONDARY_NARRATOR", "HISTORICAL_CHARACTER", "QUOTATION", "DIALOGUE")),
    VoiceCastEntry(ELEVENLABS_SPEECH_PROVIDER_ID, "t8atLZaWuCcW6gENDwwa", 2, 4, "male", None, "PREFERRED_PAID", ("SECONDARY_NARRATOR", "HISTORICAL_CHARACTER", "QUOTATION", "DIALOGUE")),
    VoiceCastEntry(EDGE_SPEECH_PROVIDER_ID, "ar-KW-FahedNeural", 99, 1, "male", None, "EMERGENCY", ("EMERGENCY_NARRATOR",)),
)


def validate_voice_cast() -> None:
    identities = [(entry.provider_id, entry.voice_id) for entry in VOICE_CAST]
    if len(identities) != len(set(identities)):
        raise ValueError("VOICE_CAST_DUPLICATE_IDENTITY")
    primary = [entry for entry in VOICE_CAST if entry.is_primary]
    if len(primary) != 1 or (primary[0].provider_id, primary[0].voice_id) != (PRIMARY_PROVIDER_ID, PRIMARY_VOICE_ID):
        raise ValueError("VOICE_CAST_PRIMARY_MISMATCH")
    actual = {entry.voice_id: entry.quality_score for entry in VOICE_CAST if entry.provider_id == GEMINI_TTS_PROVIDER_ID}
    if actual != APPROVED_GEMINI_VOICES or any(score is None or score < MINIMUM_APPROVED_SCORE for score in actual.values()):
        raise ValueError("GEMINI_VOICE_APPROVAL_SET_MISMATCH")


def get_provider_policy(provider_id: str) -> dict[str, Any]:
    try:
        return dict(PROVIDER_POLICY[provider_id])
    except KeyError as error:
        raise KeyError(f"VOICE_PROVIDER_NOT_APPROVED:{provider_id}") from error


def get_primary_cast_entry() -> VoiceCastEntry:
    validate_voice_cast()
    return next(entry for entry in VOICE_CAST if entry.is_primary)


def get_approved_cast_entry(provider_id: str, voice_id: str) -> VoiceCastEntry:
    validate_voice_cast()
    for entry in VOICE_CAST:
        if (entry.provider_id, entry.voice_id) == (provider_id, voice_id):
            return entry
    raise KeyError(f"VOICE_CAST_ENTRY_NOT_APPROVED:{provider_id}:{voice_id}")


def select_male_voice_for_role(role: str, *, exclude_identities: set[tuple[str, str]] | None = None, include_preferred_paid: bool = False) -> VoiceCastEntry:
    validate_voice_cast()
    normalized_role = str(role).strip().upper()
    excluded = exclude_identities or set()
    candidates = [entry for entry in VOICE_CAST if entry.gender == "male" and entry.tier != "EMERGENCY" and (include_preferred_paid or entry.provider_id == GEMINI_TTS_PROVIDER_ID) and normalized_role in entry.allowed_roles and (entry.provider_id, entry.voice_id) not in excluded]
    if not candidates:
        raise KeyError(f"NO_APPROVED_MALE_VOICE_FOR_ROLE:{normalized_role}")
    return sorted(candidates, key=lambda entry: (entry.provider_rank, entry.voice_rank))[0]


def female_voice_policy() -> dict[str, Any]:
    return {
        "provider_id": GEMINI_TTS_PROVIDER_ID,
        "selection_mode": "APPROVED_EVENT_MATCHED_ONLY",
        "fixed_voice_configured": False,
        "status_without_approved_voice": "NEEDS_APPROVED_FEMALE_VOICE",
        "narrator_fallback_allowed": True,
    }


def voice_cast_to_dict() -> dict[str, Any]:
    validate_voice_cast()
    return {
        "schema_version": VOICE_CAST_SCHEMA_V2,
        "status": "VALID",
        "active_provider": GEMINI_TTS_PROVIDER_ID,
        "active_model": GEMINI_PRIMARY_MODEL,
        "fallback_model": GEMINI_FALLBACK_MODEL,
        "primary_voice": PRIMARY_VOICE_ID,
        "supporting_voices": [voice for voice in APPROVED_GEMINI_VOICES if voice != PRIMARY_VOICE_ID],
        "provider_policy": {key: dict(value) for key, value in PROVIDER_POLICY.items()},
        "minimum_approved_score": MINIMUM_APPROVED_SCORE,
        "entry_count": len(VOICE_CAST),
        "female_voice_policy": female_voice_policy(),
        "dialogue_readiness": "READY_WITH_APPROVED_MALE_CAST",
        "entries": [{"provider_id": entry.provider_id, "voice_id": entry.voice_id, "provider_rank": entry.provider_rank, "voice_rank": entry.voice_rank, "gender": entry.gender, "quality_score": entry.quality_score, "tier": entry.tier, "model_reference": entry.model_reference, "provider_activation_status": PROVIDER_POLICY[entry.provider_id]["activation_status"], "allowed_roles": list(entry.allowed_roles), "is_primary": entry.is_primary} for entry in VOICE_CAST],
    }
