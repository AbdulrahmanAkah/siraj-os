from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import unicodedata
import wave
from copy import deepcopy
from pathlib import Path
from typing import Any

from src.application.episode_canonical_state_v1 import (
    CanonicalStateError,
    EpisodeStage,
    bind_artifact,
    load_state,
    transition,
)

SCHEMA_VERSION = "siraj-audio-timing-map-v1"
AUTHORITY_VERSION = "SIRAJ_AUDIO_TIMING_AUTHORITY_V1"

FINAL_SOURCE_MODES = {
    "TTS_NATIVE_WORD_BOUNDARY",
    "FORCED_ALIGNMENT_LOCAL",
    "MANUAL_VERIFIED",
}
FORBIDDEN_SOURCE_MODES = {
    "PROPORTIONAL_ESTIMATE",
    "PROPORTIONAL_TIMING",
    "HEURISTIC_PROPORTIONAL",
}

DURATION_TOLERANCE_SECONDS = 0.030
TIMING_EPSILON_SECONDS = 0.005

FFPROBE_FALLBACK = Path(
    r"C:\Users\abdul\AppData\Local\Microsoft\WinGet\Packages"
    r"\Gyan.FFmpeg.Shared_Microsoft.Winget.Source_8wekyb3d8bbwe"
    r"\ffmpeg-8.1.2-full_build-shared\bin\ffprobe.EXE"
)


class AudioTimingAuthorityError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.replace("\ufeff", "")
    return re.sub(r"\s+", " ", text).strip()


def _probe_wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wf:
        rate = wf.getframerate()
        frames = wf.getnframes()
        if rate <= 0:
            raise AudioTimingAuthorityError("WAV_INVALID_SAMPLE_RATE")
        return frames / float(rate)


def _resolve_ffprobe() -> str:
    found = shutil.which("ffprobe")
    if found:
        return found
    if FFPROBE_FALLBACK.is_file():
        return str(FFPROBE_FALLBACK)
    raise AudioTimingAuthorityError("FFPROBE_NOT_FOUND_FOR_NON_WAV_AUDIO")


def probe_audio_duration(path: Path) -> float:
    if not path.is_file():
        raise AudioTimingAuthorityError("AUDIO_FILE_MISSING:" + str(path))
    if path.suffix.lower() == ".wav":
        try:
            return _probe_wav_duration(path)
        except (wave.Error, EOFError):
            pass

    ffprobe = _resolve_ffprobe()
    cp = subprocess.run(
        [
            ffprobe,
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=nw=1:nk=1",
            str(path),
        ],
        text=True,
        capture_output=True,
    )
    if cp.returncode != 0:
        raise AudioTimingAuthorityError(
            "AUDIO_DURATION_PROBE_FAILED:" + cp.stderr[-2000:]
        )
    try:
        return float(cp.stdout.strip())
    except ValueError as exc:
        raise AudioTimingAuthorityError("AUDIO_DURATION_PARSE_FAILED") from exc


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AudioTimingAuthorityError(f"{label}_MUST_BE_NUMBER")
    value = float(value)
    if value < 0:
        raise AudioTimingAuthorityError(f"{label}_NEGATIVE")
    return value


def _validate_interval(start: float, end: float, label: str) -> None:
    if end <= start:
        raise AudioTimingAuthorityError(f"{label}_INVALID_INTERVAL:{start}->{end}")


def _validate_word_timing(
    sentence: dict[str, Any],
    sentence_start: float,
    sentence_end: float,
    seen_word_ids: set[str],
) -> None:
    words = sentence.get("words")
    if not isinstance(words, list) or not words:
        raise AudioTimingAuthorityError(
            f"SENTENCE_WORD_TIMING_REQUIRED:{sentence.get('sentence_id')}"
        )

    previous_end: float | None = None
    for index, word in enumerate(words, start=1):
        if not isinstance(word, dict):
            raise AudioTimingAuthorityError("WORD_ENTRY_NOT_OBJECT")
        word_id = str(word.get("word_id") or "").strip()
        if not word_id:
            raise AudioTimingAuthorityError("WORD_ID_MISSING")
        if word_id in seen_word_ids:
            raise AudioTimingAuthorityError("DUPLICATE_WORD_ID:" + word_id)
        seen_word_ids.add(word_id)

        text = str(word.get("text") or "").strip()
        if not text:
            raise AudioTimingAuthorityError("WORD_TEXT_MISSING:" + word_id)

        start = _number(word.get("start"), f"{word_id}_START")
        end = _number(word.get("end"), f"{word_id}_END")
        _validate_interval(start, end, word_id)

        if start < sentence_start - TIMING_EPSILON_SECONDS:
            raise AudioTimingAuthorityError(
                f"WORD_BEFORE_SENTENCE:{word_id}:{start}<{sentence_start}"
            )
        if end > sentence_end + TIMING_EPSILON_SECONDS:
            raise AudioTimingAuthorityError(
                f"WORD_AFTER_SENTENCE:{word_id}:{end}>{sentence_end}"
            )
        if previous_end is not None and start < previous_end - TIMING_EPSILON_SECONDS:
            raise AudioTimingAuthorityError(
                f"WORD_OVERLAP:{word_id}:{start}<{previous_end}"
            )
        previous_end = end


def validate_timing_map(
    *,
    episode_id: str,
    narration_path: Path,
    audio_path: Path,
    timing_path: Path,
) -> dict[str, Any]:
    for path, label in (
        (narration_path, "NARRATION"),
        (audio_path, "AUDIO"),
        (timing_path, "TIMING"),
    ):
        if not path.is_file():
            raise AudioTimingAuthorityError(f"{label}_FILE_MISSING:{path}")

    narration_bytes_sha = sha256_file(narration_path)
    audio_bytes_sha = sha256_file(audio_path)
    actual_audio_duration = probe_audio_duration(audio_path)

    try:
        timing = json.loads(timing_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise AudioTimingAuthorityError("TIMING_JSON_INVALID") from exc

    if not isinstance(timing, dict):
        raise AudioTimingAuthorityError("TIMING_ROOT_NOT_OBJECT")
    if timing.get("schema_version") != SCHEMA_VERSION:
        raise AudioTimingAuthorityError("TIMING_SCHEMA_VERSION_MISMATCH")
    if timing.get("episode_id") != episode_id:
        raise AudioTimingAuthorityError(
            f"TIMING_EPISODE_ID_MISMATCH:{timing.get('episode_id')}:{episode_id}"
        )

    source_mode = str(timing.get("source_mode") or "").strip()
    if source_mode in FORBIDDEN_SOURCE_MODES:
        raise AudioTimingAuthorityError(
            "PROPORTIONAL_TIMING_FORBIDDEN_AS_FINAL_AUTHORITY:" + source_mode
        )
    if source_mode not in FINAL_SOURCE_MODES:
        raise AudioTimingAuthorityError("UNSUPPORTED_TIMING_SOURCE_MODE:" + source_mode)

    if timing.get("narration_sha256") != narration_bytes_sha:
        raise AudioTimingAuthorityError(
            "NARRATION_SHA_MISMATCH:"
            + str(timing.get("narration_sha256"))
            + ":expected="
            + narration_bytes_sha
        )
    if timing.get("audio_sha256") != audio_bytes_sha:
        raise AudioTimingAuthorityError(
            "AUDIO_SHA_MISMATCH:"
            + str(timing.get("audio_sha256"))
            + ":expected="
            + audio_bytes_sha
        )

    declared_duration = _number(
        timing.get("audio_duration_seconds"), "AUDIO_DURATION_SECONDS"
    )
    if abs(declared_duration - actual_audio_duration) > DURATION_TOLERANCE_SECONDS:
        raise AudioTimingAuthorityError(
            "AUDIO_DURATION_MISMATCH:"
            f"declared={declared_duration:.6f}:actual={actual_audio_duration:.6f}"
        )

    sentences = timing.get("sentences")
    if not isinstance(sentences, list) or not sentences:
        raise AudioTimingAuthorityError("SENTENCES_REQUIRED")

    narration_text = normalize_text(
        narration_path.read_text(encoding="utf-8-sig")
    )
    sentence_texts: list[str] = []
    seen_sentence_ids: set[str] = set()
    seen_word_ids: set[str] = set()
    previous_sentence_end: float | None = None

    for sentence in sentences:
        if not isinstance(sentence, dict):
            raise AudioTimingAuthorityError("SENTENCE_ENTRY_NOT_OBJECT")
        sentence_id = str(sentence.get("sentence_id") or "").strip()
        if not sentence_id:
            raise AudioTimingAuthorityError("SENTENCE_ID_MISSING")
        if sentence_id in seen_sentence_ids:
            raise AudioTimingAuthorityError("DUPLICATE_SENTENCE_ID:" + sentence_id)
        seen_sentence_ids.add(sentence_id)

        text = normalize_text(str(sentence.get("text") or ""))
        if not text:
            raise AudioTimingAuthorityError("SENTENCE_TEXT_MISSING:" + sentence_id)
        sentence_texts.append(text)

        start = _number(sentence.get("start"), f"{sentence_id}_START")
        end = _number(sentence.get("end"), f"{sentence_id}_END")
        _validate_interval(start, end, sentence_id)

        if end > actual_audio_duration + DURATION_TOLERANCE_SECONDS:
            raise AudioTimingAuthorityError(
                f"SENTENCE_EXCEEDS_AUDIO:{sentence_id}:{end}>{actual_audio_duration}"
            )
        if (
            previous_sentence_end is not None
            and start < previous_sentence_end - TIMING_EPSILON_SECONDS
        ):
            raise AudioTimingAuthorityError(
                f"SENTENCE_OVERLAP:{sentence_id}:{start}<{previous_sentence_end}"
            )
        previous_sentence_end = end

        _validate_word_timing(
            sentence,
            sentence_start=start,
            sentence_end=end,
            seen_word_ids=seen_word_ids,
        )

    reconstructed = normalize_text(" ".join(sentence_texts))
    if reconstructed != narration_text:
        raise AudioTimingAuthorityError(
            "TIMING_SENTENCE_TEXT_DOES_NOT_MATCH_FROZEN_NARRATION"
        )

    first_start = _number(sentences[0]["start"], "FIRST_SENTENCE_START")
    last_end = _number(sentences[-1]["end"], "LAST_SENTENCE_END")

    coverage = {
        "leading_silence_seconds": round(first_start, 6),
        "trailing_silence_seconds": round(
            max(0.0, actual_audio_duration - last_end), 6
        ),
        "first_speech_seconds": round(first_start, 6),
        "last_speech_seconds": round(last_end, 6),
        "audio_duration_seconds": round(actual_audio_duration, 6),
        "sentence_count": len(sentences),
        "word_count": sum(len(s["words"]) for s in sentences),
        "allows_natural_inter_sentence_silence": True,
        "proportional_estimate_used": False,
    }

    return {
        "episode_id": episode_id,
        "schema_version": SCHEMA_VERSION,
        "source_mode": source_mode,
        "narration_path": str(narration_path.resolve()),
        "narration_sha256": narration_bytes_sha,
        "audio_path": str(audio_path.resolve()),
        "audio_sha256": audio_bytes_sha,
        "timing_path": str(timing_path.resolve()),
        "timing_sha256": sha256_file(timing_path),
        "audio_duration_seconds": round(actual_audio_duration, 6),
        "coverage": coverage,
    }


def _atomic_restore(path: Path, original_bytes: bytes) -> None:
    temp = path.with_suffix(path.suffix + ".restore.tmp")
    temp.write_bytes(original_bytes)
    os.replace(temp, path)


def freeze_and_lock_audio_authority(
    *,
    state_path: Path,
    narration_path: Path,
    audio_path: Path,
    timing_path: Path,
    receipt_path: Path | None = None,
) -> dict[str, Any]:
    state = load_state(state_path)
    if state["stage"] != EpisodeStage.SCRIPT_LOCKED.value:
        raise AudioTimingAuthorityError(
            "AUDIO_FREEZE_REQUIRES_SCRIPT_LOCKED:"
            + str(state["stage"])
        )

    validation = validate_timing_map(
        episode_id=state["episode_id"],
        narration_path=narration_path,
        audio_path=audio_path,
        timing_path=timing_path,
    )

    original_state_bytes = state_path.read_bytes()
    receipt_created = False
    try:
        bind_artifact(
            state_path,
            "narration",
            narration_path,
            metadata={
                "authority_version": AUTHORITY_VERSION,
                "timing_source_mode": validation["source_mode"],
            },
        )
        bind_artifact(
            state_path,
            "audio",
            audio_path,
            metadata={
                "authority_version": AUTHORITY_VERSION,
                "duration_seconds": validation["audio_duration_seconds"],
                "is_duration_authority": True,
            },
        )
        bind_artifact(
            state_path,
            "timing",
            timing_path,
            metadata={
                "authority_version": AUTHORITY_VERSION,
                "source_mode": validation["source_mode"],
                "narration_sha256": validation["narration_sha256"],
                "audio_sha256": validation["audio_sha256"],
                "audio_duration_seconds": validation["audio_duration_seconds"],
                "proportional_estimate_used": False,
            },
        )
        locked = transition(state_path, EpisodeStage.AUDIO_LOCKED.value)

        receipt = {
            "schema_version": "siraj-audio-timing-authority-receipt-v1",
            "authority_version": AUTHORITY_VERSION,
            "status": "PASS_AUDIO_TIMING_AUTHORITY_LOCKED",
            "episode_id": locked["episode_id"],
            "stage": locked["stage"],
            "canonical_state_revision": locked["revision"],
            **validation,
            "rule": (
                "AUDIO_BYTES_ARE_DURATION_AUTHORITY; "
                "SENTENCE_AND_WORD_TIMES_ARE_TIMING_AUTHORITY; "
                "PROPORTIONAL_FINAL_TIMING_FORBIDDEN"
            ),
            "network_calls": 0,
            "provider_calls": 0,
            "paid_calls": 0,
        }
        if receipt_path is not None:
            receipt_path.parent.mkdir(parents=True, exist_ok=True)
            if receipt_path.exists():
                existing = json.loads(receipt_path.read_text(encoding="utf-8-sig"))
                if existing != receipt:
                    raise AudioTimingAuthorityError(
                        "RECEIPT_ALREADY_EXISTS_WITH_DIFFERENT_CONTENT"
                    )
            else:
                temp = receipt_path.with_suffix(receipt_path.suffix + ".tmp")
                temp.write_text(
                    json.dumps(receipt, ensure_ascii=False, indent=2, sort_keys=True)
                    + "\n",
                    encoding="utf-8",
                    newline="\n",
                )
                os.replace(temp, receipt_path)
                receipt_created = True
        return receipt

    except Exception:
        _atomic_restore(state_path, original_state_bytes)
        if receipt_created and receipt_path is not None and receipt_path.is_file():
            receipt_path.unlink()
        raise


def build_template(episode_id: str) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "source_mode": "TTS_NATIVE_WORD_BOUNDARY",
        "narration_sha256": "<SHA256_OF_EXACT_NARRATION_FILE>",
        "audio_sha256": "<SHA256_OF_EXACT_AUDIO_FILE>",
        "audio_duration_seconds": 0.0,
        "sentences": [
            {
                "sentence_id": "S001",
                "text": "<EXACT_SENTENCE_TEXT>",
                "start": 0.0,
                "end": 0.0,
                "words": [
                    {
                        "word_id": "S001-W001",
                        "text": "<WORD>",
                        "start": 0.0,
                        "end": 0.0,
                    }
                ],
            }
        ],
    }


def cli() -> int:
    p = argparse.ArgumentParser(description="SIRAJ audio timing authority v1")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_template = sub.add_parser("template")
    p_template.add_argument("--episode-id", required=True)
    p_template.add_argument("--output", required=True)

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("--episode-id", required=True)
    p_validate.add_argument("--narration", required=True)
    p_validate.add_argument("--audio", required=True)
    p_validate.add_argument("--timing", required=True)

    p_freeze = sub.add_parser("freeze")
    p_freeze.add_argument("--state", required=True)
    p_freeze.add_argument("--narration", required=True)
    p_freeze.add_argument("--audio", required=True)
    p_freeze.add_argument("--timing", required=True)
    p_freeze.add_argument("--receipt")

    args = p.parse_args()

    if args.cmd == "template":
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = build_template(args.episode_id)
        output.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        print("STATUS=PASS_TIMING_TEMPLATE_CREATED")
        print("OUTPUT=" + str(output))
        return 0

    if args.cmd == "validate":
        result = validate_timing_map(
            episode_id=args.episode_id,
            narration_path=Path(args.narration),
            audio_path=Path(args.audio),
            timing_path=Path(args.timing),
        )
        print("STATUS=PASS_AUDIO_TIMING_VALIDATION")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.cmd == "freeze":
        result = freeze_and_lock_audio_authority(
            state_path=Path(args.state),
            narration_path=Path(args.narration),
            audio_path=Path(args.audio),
            timing_path=Path(args.timing),
            receipt_path=Path(args.receipt) if args.receipt else None,
        )
        print("STATUS=PASS_AUDIO_TIMING_AUTHORITY_LOCKED")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    raise AssertionError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(cli())
