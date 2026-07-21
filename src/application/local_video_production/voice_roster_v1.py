"""Legacy ElevenLabs roster retained for a future paid-provider activation.

The current production selection is ``voice_cast_v2``: Gemini TTS is
active, this roster is retained only as the approved paid-performer catalog.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


VOICE_ROSTER_SCHEMA_V1 = (
    "siraj-production-voice-roster-v1"
)

VOICE_ROSTER_PROVIDER_ID = "elevenlabs-speech-v1"
VOICE_ROSTER_ACTIVATION_STATUS = "BLOCKED_BY_SUBSCRIPTION"

PRIMARY_NARRATOR_VOICE_ID = (
    "XdoLPWNt7ytn6BtU4FBf"
)

APPROVED_VOICE_IDS = (
    "XdoLPWNt7ytn6BtU4FBf",
    "pCKbQ4EPGE06zpEPGNvS",
    "fkqevZRU7Xj52dY1CTkq",
    "t8atLZaWuCcW6gENDwwa",
)


@dataclass(frozen=True)
class ProductionVoice:
    voice_id: str
    roster_order: int
    is_primary: bool
    allowed_roles: tuple[str, ...]


PRODUCTION_VOICE_ROSTER = (
    ProductionVoice(
        voice_id="XdoLPWNt7ytn6BtU4FBf",
        roster_order=1,
        is_primary=True,
        allowed_roles=(
            "PRIMARY_NARRATOR",
            "NARRATOR",
            "HOST",
        ),
    ),
    ProductionVoice(
        voice_id="pCKbQ4EPGE06zpEPGNvS",
        roster_order=2,
        is_primary=False,
        allowed_roles=(
            "SECONDARY_NARRATOR",
            "QUOTATION",
            "HISTORICAL_CHARACTER",
        ),
    ),
    ProductionVoice(
        voice_id="fkqevZRU7Xj52dY1CTkq",
        roster_order=3,
        is_primary=False,
        allowed_roles=(
            "SECONDARY_NARRATOR",
            "QUOTATION",
            "HISTORICAL_CHARACTER",
        ),
    ),
    ProductionVoice(
        voice_id="t8atLZaWuCcW6gENDwwa",
        roster_order=4,
        is_primary=False,
        allowed_roles=(
            "SECONDARY_NARRATOR",
            "QUOTATION",
            "HISTORICAL_CHARACTER",
        ),
    ),
)


def validate_voice_roster() -> None:
    voice_ids = [
        voice.voice_id
        for voice in PRODUCTION_VOICE_ROSTER
    ]

    if len(voice_ids) != len(
        set(voice_ids)
    ):
        raise ValueError(
            "VOICE_ROSTER_DUPLICATE_ID"
        )

    primary = [
        voice
        for voice in PRODUCTION_VOICE_ROSTER
        if voice.is_primary
    ]

    if len(primary) != 1:
        raise ValueError(
            "VOICE_ROSTER_REQUIRES_ONE_PRIMARY"
        )

    if (
        primary[0].voice_id
        != PRIMARY_NARRATOR_VOICE_ID
    ):
        raise ValueError(
            "VOICE_ROSTER_PRIMARY_ID_MISMATCH"
        )

    if tuple(voice_ids) != (
        APPROVED_VOICE_IDS
    ):
        raise ValueError(
            "VOICE_ROSTER_ORDER_MISMATCH"
        )


def get_primary_voice() -> ProductionVoice:
    validate_voice_roster()

    return next(
        voice
        for voice in PRODUCTION_VOICE_ROSTER
        if voice.is_primary
    )


def get_voice_by_id(
    voice_id: str,
) -> ProductionVoice:
    validate_voice_roster()

    for voice in PRODUCTION_VOICE_ROSTER:
        if voice.voice_id == voice_id:
            return voice

    raise KeyError(
        f"VOICE_NOT_APPROVED:{voice_id}"
    )


def select_voice_for_role(
    role: str,
    *,
    preferred_voice_id: str | None = None,
) -> ProductionVoice:
    validate_voice_roster()

    normalized_role = str(
        role
    ).strip().upper()

    if not normalized_role:
        raise ValueError(
            "VOICE_ROLE_REQUIRED"
        )

    if preferred_voice_id:
        preferred = get_voice_by_id(
            preferred_voice_id
        )

        if normalized_role not in (
            preferred.allowed_roles
        ):
            raise ValueError(
                "VOICE_NOT_ALLOWED_FOR_ROLE:"
                f"{preferred.voice_id}:"
                f"{normalized_role}"
            )

        return preferred

    if normalized_role in {
        "PRIMARY_NARRATOR",
        "NARRATOR",
        "HOST",
    }:
        return get_primary_voice()

    for voice in PRODUCTION_VOICE_ROSTER:
        if normalized_role in (
            voice.allowed_roles
        ):
            return voice

    raise KeyError(
        f"NO_APPROVED_VOICE_FOR_ROLE:{normalized_role}"
    )


def voice_roster_to_dict() -> dict[str, Any]:
    validate_voice_roster()

    return {
        "schema_version": (
            VOICE_ROSTER_SCHEMA_V1
        ),
        "primary_voice_id": (
            PRIMARY_NARRATOR_VOICE_ID
        ),
        "provider_id": VOICE_ROSTER_PROVIDER_ID,
        "activation_status": VOICE_ROSTER_ACTIVATION_STATUS,
        "voice_count": len(
            PRODUCTION_VOICE_ROSTER
        ),
        "voices": [
            {
                "voice_id": voice.voice_id,
                "roster_order": (
                    voice.roster_order
                ),
                "is_primary": (
                    voice.is_primary
                ),
                "allowed_roles": list(
                    voice.allowed_roles
                ),
            }
            for voice in PRODUCTION_VOICE_ROSTER
        ],
    }
