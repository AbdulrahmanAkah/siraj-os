"""Discover Arabic voices exposed by edge-tts."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import edge_tts


EDGE_VOICE_CATALOG_SCHEMA_V1 = (
    "siraj-edge-voice-catalog-v1"
)


@dataclass(frozen=True)
class EdgeVoiceCandidate:
    short_name: str
    locale: str
    gender: str
    friendly_name: str


async def fetch_edge_voices_async() -> list[dict[str, Any]]:
    return await edge_tts.list_voices()


def fetch_arabic_edge_voices() -> list[
    EdgeVoiceCandidate
]:
    voices = asyncio.run(
        fetch_edge_voices_async()
    )

    candidates = []

    for voice in voices:
        locale = str(
            voice.get(
                "Locale",
                "",
            )
        )

        short_name = str(
            voice.get(
                "ShortName",
                "",
            )
        )

        if not locale.lower().startswith(
            "ar-"
        ):
            continue

        if not short_name:
            continue

        candidates.append(
            EdgeVoiceCandidate(
                short_name=short_name,
                locale=locale,
                gender=str(
                    voice.get(
                        "Gender",
                        "",
                    )
                ),
                friendly_name=str(
                    voice.get(
                        "FriendlyName",
                        "",
                    )
                ),
            )
        )

    return sorted(
        candidates,
        key=lambda item: (
            item.locale,
            item.gender,
            item.short_name,
        ),
    )


def edge_voice_to_dict(
    voice: EdgeVoiceCandidate,
) -> dict[str, str]:
    return {
        "short_name": voice.short_name,
        "locale": voice.locale,
        "gender": voice.gender,
        "friendly_name": (
            voice.friendly_name
        ),
    }