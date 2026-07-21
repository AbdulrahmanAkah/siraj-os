"""Provider-independent production voice contracts."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
import tempfile
from typing import Any


VOICE_REQUEST_SCHEMA_V1 = (
    "siraj-production-voice-request-v1"
)

VOICE_REPORT_SCHEMA_V1 = (
    "siraj-production-voice-report-v1"
)


@dataclass(frozen=True)
class VoiceSegment:
    segment_id: str
    text: str
    normalized_text: str
    order: int
    estimated_duration_ms: int


@dataclass(frozen=True)
class VoiceSynthesisResult:
    status: str
    provider: str
    output_path: str
    report_path: str
    segment_count: int
    output_sha256: str


class VoiceProvider(ABC):
    """Replaceable text-to-speech provider contract."""

    provider_id: str

    @abstractmethod
    def synthesize(
        self,
        request: dict[str, Any],
        project_root: Path,
    ) -> VoiceSynthesisResult:
        """Synthesize reviewed narration into an audio artifact."""


def atomic_write_json(
    path: Path,
    value: dict[str, Any],
) -> None:
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    content = (
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n"
    )

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        newline="\n",
        dir=path.parent,
        suffix=".tmp",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(content)

    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def file_sha256(path: Path) -> str:
    return sha256(
        path.read_bytes()
    ).hexdigest()

DEFAULT_ARABIC_PRONUNCIATION_MAP = {
    "ﷺ": "صلى الله عليه وسلم",
    "ﷻ": "جل جلاله",
    "عليه السلام": "عليه السلام",
    "عليها السلام": "عليها السلام",
    "رضي الله عنه": "رضي الله عنه",
    "رضي الله عنها": "رضي الله عنها",
}


def normalize_arabic_text(
    text: str,
    pronunciation_map: dict[str, str] | None = None,
) -> str:
    if not isinstance(text, str):
        raise TypeError(
            "VOICE_TEXT_MUST_BE_STRING"
        )

    value = text.strip()

    if not value:
        raise ValueError(
            "VOICE_TEXT_REQUIRED"
        )

    replacements = dict(
        DEFAULT_ARABIC_PRONUNCIATION_MAP
    )

    if pronunciation_map:
        replacements.update(
            pronunciation_map
        )

    for source, target in replacements.items():
        value = value.replace(
            source,
            target,
        )

    value = re.sub(
        r"[\u064B-\u065F\u0670]",
        "",
        value,
    )

    value = value.replace(
        "ـ",
        "",
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def validate_pronunciation_map(
    value: Any,
) -> dict[str, str]:
    if value is None:
        return {}

    if not isinstance(value, dict):
        raise ValueError(
            "PRONUNCIATION_MAP_INVALID"
        )

    result: dict[str, str] = {}

    for source, target in value.items():
        if (
            not isinstance(source, str)
            or not source.strip()
            or not isinstance(target, str)
            or not target.strip()
        ):
            raise ValueError(
                "PRONUNCIATION_ENTRY_INVALID"
            )

        result[source.strip()] = (
            target.strip()
        )

    return result

def estimate_arabic_duration_ms(
    text: str,
    words_per_minute: int = 135,
) -> int:
    if words_per_minute < 60:
        raise ValueError(
            "WORDS_PER_MINUTE_TOO_LOW"
        )

    words = [
        word
        for word in text.split()
        if word.strip()
    ]

    if not words:
        return 0

    duration = (
        len(words)
        / words_per_minute
        * 60_000
    )

    punctuation_pause = (
        text.count("،") * 180
        + text.count(".") * 320
        + text.count("؟") * 380
        + text.count("!") * 320
        + text.count(":") * 180
    )

    return max(
        500,
        int(duration + punctuation_pause),
    )


def split_arabic_narration(
    text: str,
    pronunciation_map: dict[str, str] | None = None,
    max_words: int = 28,
) -> list[VoiceSegment]:
    if max_words < 5:
        raise ValueError(
            "MAX_SEGMENT_WORDS_TOO_LOW"
        )

    normalized = normalize_arabic_text(
        text,
        pronunciation_map,
    )

    raw_sentences = re.split(
        r"(?<=[.!؟!])\s+",
        normalized,
    )

    segments: list[str] = []

    for sentence in raw_sentences:
        sentence = sentence.strip()

        if not sentence:
            continue

        words = sentence.split()

        if len(words) <= max_words:
            segments.append(sentence)
            continue

        cursor = 0

        while cursor < len(words):
            chunk = words[
                cursor:cursor + max_words
            ]

            segments.append(
                " ".join(chunk)
            )

            cursor += max_words

    result: list[VoiceSegment] = []

    for index, segment_text in enumerate(
        segments,
        start=1,
    ):
        result.append(
            VoiceSegment(
                segment_id=(
                    f"voice-segment-{index:03d}"
                ),
                text=segment_text,
                normalized_text=segment_text,
                order=index,
                estimated_duration_ms=(
                    estimate_arabic_duration_ms(
                        segment_text
                    )
                ),
            )
        )

    if not result:
        raise ValueError(
            "VOICE_SEGMENTS_EMPTY"
        )

    return result

def validate_voice_request(
    request: dict[str, Any],
) -> None:
    if not isinstance(request, dict):
        raise ValueError(
            "VOICE_REQUEST_NOT_OBJECT"
        )

    if (
        request.get("schema_version")
        != VOICE_REQUEST_SCHEMA_V1
    ):
        raise ValueError(
            "VOICE_REQUEST_SCHEMA_INVALID"
        )

    if not str(
        request.get("request_id", "")
    ).strip():
        raise ValueError(
            "VOICE_REQUEST_ID_REQUIRED"
        )

    if not str(
        request.get("episode_id", "")
    ).strip():
        raise ValueError(
            "VOICE_EPISODE_ID_REQUIRED"
        )

    if not str(
        request.get("language", "")
    ).strip():
        raise ValueError(
            "VOICE_LANGUAGE_REQUIRED"
        )

    if request.get("language") != "ar":
        raise ValueError(
            "VOICE_LANGUAGE_UNSUPPORTED"
        )

    if not str(
        request.get("text", "")
    ).strip():
        raise ValueError(
            "VOICE_TEXT_REQUIRED"
        )

    voice = request.get("voice")

    if not isinstance(voice, dict):
        raise ValueError(
            "VOICE_CONFIGURATION_REQUIRED"
        )

    if not str(
        voice.get("voice_id", "")
    ).strip():
        raise ValueError(
            "VOICE_ID_REQUIRED"
        )

    speed = voice.get(
        "speed",
        1.0,
    )

    if (
        not isinstance(speed, (int, float))
        or speed < 0.7
        or speed > 1.3
    ):
        raise ValueError(
            "VOICE_SPEED_INVALID"
        )

    output = request.get("output")

    if not isinstance(output, dict):
        raise ValueError(
            "VOICE_OUTPUT_REQUIRED"
        )

    if not str(
        output.get("audio", "")
    ).strip():
        raise ValueError(
            "VOICE_AUDIO_OUTPUT_REQUIRED"
        )

    if not str(
        output.get("report", "")
    ).strip():
        raise ValueError(
            "VOICE_REPORT_OUTPUT_REQUIRED"
        )

    validate_pronunciation_map(
        request.get(
            "pronunciation_map"
        )
    )


def build_voice_segments(
    request: dict[str, Any],
) -> list[VoiceSegment]:
    validate_voice_request(
        request
    )

    pronunciation_map = (
        validate_pronunciation_map(
            request.get(
                "pronunciation_map"
            )
        )
    )

    segmentation = request.get(
        "segmentation",
        {},
    )

    max_words = int(
        segmentation.get(
            "max_words",
            28,
        )
    )

    return split_arabic_narration(
        text=str(request["text"]),
        pronunciation_map=(
            pronunciation_map
        ),
        max_words=max_words,
    )