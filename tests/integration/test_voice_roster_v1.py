from __future__ import annotations

import pytest

from src.application.local_video_production.voice_roster_v1 import (
    APPROVED_VOICE_IDS,
    PRIMARY_NARRATOR_VOICE_ID,
    get_primary_voice,
    get_voice_by_id,
    select_voice_for_role,
    validate_voice_roster,
    voice_roster_to_dict,
)


def test_roster_is_valid() -> None:
    validate_voice_roster()


def test_first_voice_is_primary() -> None:
    voice = get_primary_voice()

    assert voice.voice_id == (
        "XdoLPWNt7ytn6BtU4FBf"
    )
    assert voice.is_primary is True
    assert (
        voice.voice_id
        == PRIMARY_NARRATOR_VOICE_ID
    )


def test_roster_preserves_user_order() -> None:
    assert APPROVED_VOICE_IDS == (
        "XdoLPWNt7ytn6BtU4FBf",
        "pCKbQ4EPGE06zpEPGNvS",
        "fkqevZRU7Xj52dY1CTkq",
        "t8atLZaWuCcW6gENDwwa",
    )


def test_default_narrator_uses_primary() -> None:
    selected = select_voice_for_role(
        "NARRATOR"
    )

    assert selected.voice_id == (
        "XdoLPWNt7ytn6BtU4FBf"
    )


def test_secondary_role_uses_approved_voice() -> None:
    selected = select_voice_for_role(
        "QUOTATION",
        preferred_voice_id=(
            "pCKbQ4EPGE06zpEPGNvS"
        ),
    )

    assert selected.voice_id == (
        "pCKbQ4EPGE06zpEPGNvS"
    )


def test_unknown_voice_is_rejected() -> None:
    with pytest.raises(
        KeyError,
        match="VOICE_NOT_APPROVED",
    ):
        get_voice_by_id(
            "unknown-voice"
        )


def test_roster_serialization() -> None:
    result = voice_roster_to_dict()

    assert result["voice_count"] == 4
    assert result["primary_voice_id"] == (
        "XdoLPWNt7ytn6BtU4FBf"
    )