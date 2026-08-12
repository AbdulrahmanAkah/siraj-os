"""Idempotent consumer patch for the generic FINAL_TTS queue selector."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

IMPORT_LINE = (
    "from src.application.siraj_final_tts_queue_selector_v6_3_2 "
    "import resolve_final_tts_queue_path"
)


class GenericFinalTtsConsumerPatchError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class PatchResult:
    path: Path
    status: str
    selector_call_present: bool
    selector_import_present: bool


def _ensure_import(text: str) -> str:
    if IMPORT_LINE in text:
        return text
    pattern = re.compile(r"^from pathlib import Path\s*$", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        raise GenericFinalTtsConsumerPatchError(
            "PATHLIB_IMPORT_ANCHOR_NOT_FOUND"
        )
    return (
        text[: match.end()]
        + "\n"
        + IMPORT_LINE
        + text[match.end() :]
    )


def _diagnostic_context(text: str) -> str:
    lines = text.splitlines()
    hits = [
        index
        for index, line in enumerate(lines)
        if "final-tts-queue" in line
        or "resolve_final_tts_queue_path" in line
    ]
    if not hits:
        return "NO_FINAL_TTS_QUEUE_TEXT_FOUND"
    index = hits[0]
    start = max(0, index - 4)
    end = min(len(lines), index + 5)
    return "\\n".join(
        f"{line_no + 1}:{lines[line_no]}"
        for line_no in range(start, end)
    )


def patch_audio_timeline(path: Path) -> PatchResult:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    text = _ensure_import(text)

    if "resolve_final_tts_queue_path(repo, episode_id)" not in text:
        pattern = re.compile(
            r'q\s*=\s*_read\(\s*ep\s*/\s*'
            r'["\']orchestration/final-tts-queue-v5-4-3\.json["\']\s*\)',
            re.MULTILINE,
        )
        text, count = pattern.subn(
            "q=_read(resolve_final_tts_queue_path(repo, episode_id))",
            text,
            count=1,
        )
        if count != 1:
            raise GenericFinalTtsConsumerPatchError(
                "AUDIO_TIMELINE_FINAL_TTS_QUEUE_PATCH_ANCHOR_NOT_FOUND:\n"
                + _diagnostic_context(text)
            )
        status = "PATCHED"
    else:
        status = "ALREADY_PATCHED"

    path.write_text(text, encoding="utf-8")
    return PatchResult(
        path=path,
        status=status,
        selector_call_present=(
            "resolve_final_tts_queue_path(repo, episode_id)" in text
        ),
        selector_import_present=(IMPORT_LINE in text),
    )


def patch_montage(path: Path) -> PatchResult:
    path = Path(path)
    text = path.read_text(encoding="utf-8-sig")
    text = _ensure_import(text)

    if "resolve_final_tts_queue_path(repo, episode_id)" not in text:
        pattern = re.compile(
            r'tts\s*=\s*_read\(\s*episode\s*/\s*'
            r'["\']orchestration/final-tts-queue-v5-4-3\.json["\']\s*\)',
            re.MULTILINE,
        )
        replacement = (
            "tts = _read(\n"
            "        resolve_final_tts_queue_path(repo, episode_id)\n"
            "    )"
        )
        text, count = pattern.subn(
            replacement,
            text,
            count=1,
        )
        if count != 1:
            raise GenericFinalTtsConsumerPatchError(
                "MONTAGE_FINAL_TTS_QUEUE_PATCH_ANCHOR_NOT_FOUND:\n"
                + _diagnostic_context(text)
            )
        status = "PATCHED"
    else:
        status = "ALREADY_PATCHED"

    path.write_text(text, encoding="utf-8")
    return PatchResult(
        path=path,
        status=status,
        selector_call_present=(
            "resolve_final_tts_queue_path(repo, episode_id)" in text
        ),
        selector_import_present=(IMPORT_LINE in text),
    )
