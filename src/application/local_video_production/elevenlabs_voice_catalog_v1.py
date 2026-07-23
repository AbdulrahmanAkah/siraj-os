"""Retrieve and rank ElevenLabs voices for SIRAJ narration."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


ELEVENLABS_VOICE_CATALOG_SCHEMA_V1 = (
    "siraj-elevenlabs-voice-catalog-v1"
)

DEFAULT_ELEVENLABS_VOICES_ENDPOINT = (
    "https://api.elevenlabs.io/v2/voices"
)


class ElevenLabsVoiceCatalogError(
    RuntimeError
):
    pass


class ElevenLabsVoiceCatalogAuthenticationError(
    ElevenLabsVoiceCatalogError
):
    pass


class ElevenLabsVoiceCatalogTemporaryError(
    ElevenLabsVoiceCatalogError
):
    pass


@dataclass(frozen=True)
class ElevenLabsVoiceCandidate:
    voice_id: str
    name: str
    category: str
    description: str
    gender: str
    age: str
    accent: str
    use_case: str
    preview_url: str | None
    available_for_free: bool
    narration_score: int

def _text(
    value: Any,
) -> str:
    if value is None:
        return ""

    return str(value).strip()


def _labels(
    voice: dict[str, Any],
) -> dict[str, str]:
    value = voice.get(
        "labels",
        {},
    )

    if not isinstance(value, dict):
        return {}

    return {
        str(key): _text(item)
        for key, item in value.items()
    }


def calculate_narration_score(
    voice: dict[str, Any],
) -> int:
    labels = _labels(
        voice
    )

    searchable = " ".join(
        [
            _text(
                voice.get("name")
            ),
            _text(
                voice.get("description")
            ),
            *labels.values(),
        ]
    ).lower()

    score = 0

    positive_terms = {
        "narration": 12,
        "narrator": 12,
        "documentary": 12,
        "storytelling": 10,
        "audiobook": 10,
        "educational": 8,
        "professional": 7,
        "calm": 6,
        "deep": 5,
        "clear": 5,
        "authoritative": 5,
        "middle-aged": 3,
        "mature": 3,
    }

    negative_terms = {
        "social media": -3,
        "characters": -4,
        "whisper": -4,
        "child": -5,
        "cartoon": -6,
        "comedic": -4,
    }

    for term, weight in (
        positive_terms.items()
    ):
        if term in searchable:
            score += weight

    for term, weight in (
        negative_terms.items()
    ):
        if term in searchable:
            score += weight

    if voice.get(
        "is_bookmarked"
    ):
        score += 2

    if _text(
        voice.get("category")
    ).lower() == "professional":
        score += 4

    return score


def parse_voice_candidate(
    voice: dict[str, Any],
) -> ElevenLabsVoiceCandidate:
    labels = _labels(
        voice
    )

    available_tiers = voice.get(
        "available_for_tiers",
        [],
    )

    if not isinstance(
        available_tiers,
        list,
    ):
        available_tiers = []

    available_for_free = (
        not available_tiers
        or "free" in {
            _text(item).lower()
            for item in available_tiers
        }
    )

    return ElevenLabsVoiceCandidate(
        voice_id=_text(
            voice.get("voice_id")
        ),
        name=_text(
            voice.get("name")
        ),
        category=_text(
            voice.get("category")
        ),
        description=_text(
            voice.get("description")
        ),
        gender=_text(
            labels.get("gender")
        ),
        age=_text(
            labels.get("age")
        ),
        accent=_text(
            labels.get("accent")
        ),
        use_case=_text(
            labels.get("use_case")
        ),
        preview_url=(
            _text(
                voice.get("preview_url")
            )
            or None
        ),
        available_for_free=(
            available_for_free
        ),
        narration_score=(
            calculate_narration_score(
                voice
            )
        ),
    )

def resolve_api_key() -> str:
    value = os.environ.get(
        "ELEVENLABS_API_KEY",
        "",
    ).strip()

    if not value:
        raise ElevenLabsVoiceCatalogAuthenticationError(
            "ELEVENLABS_API_KEY_MISSING"
        )

    return value


def fetch_voice_catalog(
    *,
    endpoint: str = (
        DEFAULT_ELEVENLABS_VOICES_ENDPOINT
    ),
    page_size: int = 100,
    timeout_seconds: float = 30.0,
    opener: Callable[..., Any] = urlopen,
) -> list[ElevenLabsVoiceCandidate]:
    if page_size < 1 or page_size > 100:
        raise ValueError(
            "ELEVENLABS_VOICE_PAGE_SIZE_INVALID"
        )

    api_key = resolve_api_key()

    query = urlencode(
        {
            "page_size": page_size,
        }
    )

    request = Request(
        url=f"{endpoint}?{query}",
        headers={
            "xi-api-key": api_key,
            "Accept": "application/json",
            "User-Agent": (
                "siraj-os/production-tts-v1"
            ),
        },
        method="GET",
    )

    try:
        response = opener(
            request,
            timeout=timeout_seconds,
        )

        with response:
            content = response.read()

    except HTTPError as error:
        try:
            detail = error.read().decode(
                "utf-8",
                errors="replace",
            )
        except Exception:
            detail = str(
                error.reason
            )

        if error.code in {
            401,
            403,
        }:
            raise (
                ElevenLabsVoiceCatalogAuthenticationError(
                    "ELEVENLABS_VOICE_CATALOG_AUTH_FAILED:"
                    + detail[-1000:]
                )
            ) from error

        if error.code in {
            408,
            429,
            500,
            502,
            503,
            504,
        }:
            raise (
                ElevenLabsVoiceCatalogTemporaryError(
                    "ELEVENLABS_VOICE_CATALOG_TEMPORARY:"
                    + detail[-1000:]
                )
            ) from error

        raise ElevenLabsVoiceCatalogError(
            "ELEVENLABS_VOICE_CATALOG_REQUEST_FAILED:"
            + detail[-1000:]
        ) from error

    except URLError as error:
        raise ElevenLabsVoiceCatalogTemporaryError(
            "ELEVENLABS_VOICE_CATALOG_NETWORK_ERROR:"
            f"{error.reason}"
        ) from error

    try:
        payload = json.loads(
            content.decode("utf-8")
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
    ) as error:
        raise ElevenLabsVoiceCatalogError(
            "ELEVENLABS_VOICE_CATALOG_JSON_INVALID"
        ) from error

    raw_voices = payload.get(
        "voices",
        [],
    )

    if not isinstance(
        raw_voices,
        list,
    ):
        raise ElevenLabsVoiceCatalogError(
            "ELEVENLABS_VOICE_LIST_INVALID"
        )

    candidates = [
        parse_voice_candidate(
            voice
        )
        for voice in raw_voices
        if isinstance(voice, dict)
        and _text(
            voice.get("voice_id")
        )
    ]

    return sorted(
        candidates,
        key=lambda item: (
            not item.available_for_free,
            -item.narration_score,
            item.name.lower(),
        ),
    )


def voice_candidate_to_dict(
    candidate: ElevenLabsVoiceCandidate,
) -> dict[str, Any]:
    return {
        "voice_id": candidate.voice_id,
        "name": candidate.name,
        "category": candidate.category,
        "description": (
            candidate.description
        ),
        "gender": candidate.gender,
        "age": candidate.age,
        "accent": candidate.accent,
        "use_case": candidate.use_case,
        "preview_url": (
            candidate.preview_url
        ),
        "available_for_free": (
            candidate.available_for_free
        ),
        "narration_score": (
            candidate.narration_score
        ),
    }