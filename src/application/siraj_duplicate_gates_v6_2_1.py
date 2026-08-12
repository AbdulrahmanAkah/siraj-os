"""Pre-spend and post-generation duplicate gates for SIRAJ V6.2.1."""

from __future__ import annotations

from collections import Counter
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Mapping, Sequence

from src.application.siraj_cinematic_media_mix_policy_v2 import (
    PROMPT_NEAR_DUPLICATE_THRESHOLD,
    SEMANTIC_NEAR_DUPLICATE_THRESHOLD,
    PERCEPTUAL_HASH_MAX_AVG_HAMMING,
    PERCEPTUAL_HASH_MAX_SAMPLE_HAMMING,
)

TOKEN_RE = re.compile(r"[\w\u0600-\u06ff]+", re.UNICODE)


class DuplicateGateV621Error(RuntimeError):
    pass


def _tokens(value: Any) -> list[str]:
    return [x.lower() for x in TOKEN_RE.findall(str(value or ""))]


def _cosine(a: Any, b: Any) -> float:
    ca = Counter(_tokens(a))
    cb = Counter(_tokens(b))
    if not ca or not cb:
        return 0.0
    dot = sum(v * cb.get(k, 0) for k, v in ca.items())
    na = math.sqrt(sum(v * v for v in ca.values()))
    nb = math.sqrt(sum(v * v for v in cb.values()))
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def _prompt(item: Mapping[str, Any]) -> str:
    return str(
        item.get("runware_positive_prompt_en")
        or item.get("prompt_en")
        or item.get("prompt")
        or ""
    ).strip()


def _semantic_signature(item: Mapping[str, Any]) -> str:
    fields = (
        "semantic_beat",
        "narration_semantic_beat",
        "dramatic_function",
        "dramatic_function_ar",
        "subject",
        "environment",
        "composition",
        "camera",
        "camera_angle",
        "camera_movement",
        "visual_progression",
    )
    return " | ".join(
        str(item.get(field) or "").strip()
        for field in fields
        if str(item.get(field) or "").strip()
    )


def validate_pre_spend_duplicates(
    items: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    problems: list[dict[str, Any]] = []
    seen_progression: set[tuple[str, str]] = set()

    for index, item in enumerate(items):
        shot_id = str(item.get("shot_id") or f"index-{index}")
        prompt = _prompt(item)
        if not prompt:
            problems.append(
                {
                    "type": "EMPTY_PROMPT",
                    "shot_id": shot_id,
                }
            )
            continue

        continuity = str(item.get("scene_continuity_id") or "").strip()
        progression = str(item.get("visual_progression_id") or "").strip()
        if continuity and progression:
            key = (continuity, progression)
            if key in seen_progression:
                problems.append(
                    {
                        "type": "DUPLICATE_VISUAL_PROGRESSION_ID",
                        "shot_id": shot_id,
                        "scene_continuity_id": continuity,
                        "visual_progression_id": progression,
                    }
                )
            seen_progression.add(key)

        for previous_index in range(index):
            previous = items[previous_index]
            previous_id = str(
                previous.get("shot_id") or f"index-{previous_index}"
            )
            prompt_score = _cosine(prompt, _prompt(previous))
            if prompt_score >= PROMPT_NEAR_DUPLICATE_THRESHOLD:
                problems.append(
                    {
                        "type": "PROMPT_NEAR_DUPLICATE",
                        "a": previous_id,
                        "b": shot_id,
                        "score": round(prompt_score, 5),
                    }
                )

            semantic_a = _semantic_signature(item)
            semantic_b = _semantic_signature(previous)
            semantic_score = _cosine(semantic_a, semantic_b)
            if (
                semantic_a
                and semantic_b
                and semantic_score >= SEMANTIC_NEAR_DUPLICATE_THRESHOLD
            ):
                problems.append(
                    {
                        "type": "SEMANTIC_NEAR_DUPLICATE",
                        "a": previous_id,
                        "b": shot_id,
                        "score": round(semantic_score, 5),
                    }
                )

            # Adjacent shots receive a stricter structural guard even if
            # wording differs.
            if previous_index == index - 1:
                camera_a = " ".join(
                    str(item.get(k) or "")
                    for k in (
                        "composition",
                        "camera",
                        "camera_angle",
                        "camera_movement",
                    )
                )
                camera_b = " ".join(
                    str(previous.get(k) or "")
                    for k in (
                        "composition",
                        "camera",
                        "camera_angle",
                        "camera_movement",
                    )
                )
                adjacent_score = _cosine(camera_a, camera_b)
                if camera_a and camera_b and adjacent_score >= 0.96:
                    problems.append(
                        {
                            "type": "ADJACENT_SHOT_VISUAL_STRUCTURE_DUPLICATE",
                            "a": previous_id,
                            "b": shot_id,
                            "score": round(adjacent_score, 5),
                        }
                    )

    return problems


def _ffprobe() -> Path:
    configured = os.environ.get("SIRAJ_FFPROBE_EXE", "").strip()
    if configured and Path(configured).is_file():
        return Path(configured)
    found = shutil.which("ffprobe")
    if not found:
        raise DuplicateGateV621Error("FFPROBE_NOT_AVAILABLE")
    return Path(found)


def _ffmpeg() -> Path:
    configured = os.environ.get("SIRAJ_FFMPEG_EXE", "").strip()
    if configured and Path(configured).is_file():
        return Path(configured)
    found = shutil.which("ffmpeg")
    if not found:
        raise DuplicateGateV621Error("FFMPEG_NOT_AVAILABLE")
    return Path(found)


def _duration(path: Path) -> float:
    proc = subprocess.run(
        [
            str(_ffprobe()),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if proc.returncode:
        return 0.0
    try:
        return max(0.0, float(proc.stdout.strip()))
    except ValueError:
        return 0.0


def _frame_hash(path: Path, at_seconds: float) -> int:
    args = [
        str(_ffmpeg()),
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    if at_seconds > 0:
        args.extend(["-ss", f"{at_seconds:.6f}"])
    args.extend(
        [
            "-i",
            str(path),
            "-frames:v",
            "1",
            "-vf",
            "scale=8:8,format=gray",
            "-f",
            "rawvideo",
            "-pix_fmt",
            "gray",
            "pipe:1",
        ]
    )
    proc = subprocess.run(
        args,
        capture_output=True,
        check=False,
    )
    if proc.returncode or len(proc.stdout) < 64:
        raise DuplicateGateV621Error(
            "PERCEPTUAL_FRAME_EXTRACTION_FAILED:" + str(path)
        )
    pixels = proc.stdout[:64]
    mean = sum(pixels) / 64.0
    result = 0
    for index, value in enumerate(pixels):
        if value >= mean:
            result |= 1 << index
    return result


def perceptual_fingerprint(path: Path) -> tuple[int, ...]:
    path = Path(path)
    if not path.is_file():
        raise DuplicateGateV621Error(
            "ASSET_NOT_FOUND:" + str(path)
        )
    suffix = path.suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return (_frame_hash(path, 0.0),)

    duration = _duration(path)
    if duration <= 0:
        return (_frame_hash(path, 0.0),)

    moments = (
        max(0.0, duration * 0.10),
        max(0.0, duration * 0.50),
        max(0.0, duration * 0.90),
    )
    return tuple(_frame_hash(path, moment) for moment in moments)


def _hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def perceptually_near_duplicate(
    a: tuple[int, ...],
    b: tuple[int, ...],
) -> tuple[bool, float, int]:
    # Compare each sample against its best match in the other asset. This
    # catches repeated clips even if trims are shifted slightly.
    distances: list[int] = []
    for left in a:
        distances.append(min(_hamming(left, right) for right in b))
    for right in b:
        distances.append(min(_hamming(right, left) for left in a))

    avg = sum(distances) / len(distances)
    max_distance = max(distances)
    duplicate = (
        avg <= PERCEPTUAL_HASH_MAX_AVG_HAMMING
        and max_distance <= PERCEPTUAL_HASH_MAX_SAMPLE_HAMMING
    )
    return duplicate, avg, max_distance


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_completed_assets(
    repo_root: Path,
    queue_items: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    repo = Path(repo_root).resolve()
    completed = [
        item
        for item in queue_items
        if item.get("status") == "COMPLETE"
        and str(item.get("output_path_relative") or "")
    ]
    problems: list[dict[str, Any]] = []

    fingerprints: dict[str, tuple[int, ...]] = {}
    hashes: dict[str, str] = {}

    for item in completed:
        queue_id = str(item.get("queue_id") or "")
        path = repo / str(item.get("output_path_relative"))
        hashes[queue_id] = sha256_file(path)
        fingerprints[queue_id] = perceptual_fingerprint(path)

    for index, item in enumerate(completed):
        queue_id = str(item.get("queue_id") or "")
        for previous in completed[:index]:
            previous_id = str(previous.get("queue_id") or "")

            reuse_justification = str(
                item.get("reuse_justification")
                or previous.get("reuse_justification")
                or ""
            ).strip()

            if hashes[queue_id] == hashes[previous_id]:
                if not reuse_justification:
                    problems.append(
                        {
                            "type": "EXACT_ASSET_REUSE_FORBIDDEN",
                            "a": previous_id,
                            "b": queue_id,
                        }
                    )
                continue

            duplicate, avg, max_distance = perceptually_near_duplicate(
                fingerprints[queue_id],
                fingerprints[previous_id],
            )
            if duplicate and not reuse_justification:
                problems.append(
                    {
                        "type": "PERCEPTUAL_NEAR_DUPLICATE",
                        "a": previous_id,
                        "b": queue_id,
                        "average_hamming": round(avg, 3),
                        "maximum_hamming": max_distance,
                    }
                )

    return problems
