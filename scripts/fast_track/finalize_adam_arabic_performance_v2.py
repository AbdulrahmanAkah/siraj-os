from __future__ import annotations

import argparse
import hashlib
import json
import os
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping

from src.application.arabic_performance_script_v2 import validate_performance_script


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def strip_marks(text: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFD", text)
        if unicodedata.category(character) != "Mn"
    )


def blocks(payload: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        raise RuntimeError("SOURCE_SEGMENTS_REQUIRED")
    result: dict[str, Mapping[str, Any]] = {}
    for segment in segments:
        if not isinstance(segment, Mapping):
            raise RuntimeError("SOURCE_SEGMENT_OBJECT_REQUIRED")
        raw_blocks = segment.get("performance_blocks")
        if not isinstance(raw_blocks, list) or not raw_blocks:
            raise RuntimeError("PERFORMANCE_BLOCKS_REQUIRED")
        for block in raw_blocks:
            if not isinstance(block, Mapping):
                raise RuntimeError("PERFORMANCE_BLOCK_OBJECT_REQUIRED")
            block_id = str(block.get("block_id") or "")
            if not block_id:
                raise RuntimeError("PERFORMANCE_BLOCK_ID_REQUIRED")
            result[block_id] = block
    return result


def validate_approved_source(
    current: Mapping[str, Any],
    approved: Mapping[str, Any],
) -> None:
    current_blocks = blocks(current)
    approved_blocks = blocks(approved)
    if set(current_blocks) != set(approved_blocks):
        raise RuntimeError("PERFORMANCE_BLOCK_IDS_CHANGED")

    for block_id, original in current_blocks.items():
        accepted = approved_blocks[block_id]
        canonical = str(original.get("canonical_text_ar") or "")
        accepted_canonical = str(accepted.get("canonical_text_ar") or "")
        if canonical != accepted_canonical:
            raise RuntimeError(f"CANONICAL_TEXT_CHANGED:{block_id}")
        tts_text = str(accepted.get("tts_text_ar") or "").strip()
        if not tts_text:
            raise RuntimeError(f"APPROVED_TTS_TEXT_MISSING:{block_id}")
        if strip_marks(tts_text) != strip_marks(accepted_canonical):
            raise RuntimeError(f"APPROVED_TTS_BASE_TEXT_CHANGED:{block_id}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--approved-source", required=True)
    parser.add_argument("--episode", default="episode-001-adam")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    episode = repo / "projects" / args.episode
    source_path = episode / "script" / "arabic-performance-source-v2.json"
    final_path = episode / "script" / "episode-script-v2.json"
    approval_path = (
        episode / "evidence" / "arabic-performance-human-approval-v2.json"
    )
    report_path = (
        episode / "orchestration" / "arabic-performance-finalization-v2.json"
    )

    current = read_json(source_path)
    approved = read_json(Path(args.approved_source))
    validate_approved_source(current, approved)

    approved_at = datetime.now().astimezone().isoformat()
    approval = {
        "schema_version": "siraj-arabic-performance-human-approval-v2",
        "episode_id": args.episode,
        "status": "HUMAN_APPROVED",
        "decision": "APPROVE_FULL_DIACRITIZATION_AND_PERFORMANCE_PLAN",
        "approved_at_local": approved_at,
        "approval_source": "USER_REVIEWED_IN_CHAT",
        "segment_count": len(approved["segments"]),
        "performance_block_count": len(blocks(approved)),
        "approved_source_sha256": hashlib.sha256(
            Path(args.approved_source).read_bytes()
        ).hexdigest(),
        "tts_execution_authorized": False,
        "paid_execution_authorized": False,
    }

    approved["status"] = (
        "HUMAN_LANGUAGE_AND_PERFORMANCE_APPROVED_READY_FOR_TTS_PREFLIGHT"
    )
    approved["human_approval"] = approval
    instructions = approved.setdefault("instructions", {})
    instructions["do_not_send_to_tts_until_approved"] = False
    instructions["human_language_review_required"] = False
    instructions["human_performance_review_required"] = False
    instructions["tts_execution_requires_separate_preflight"] = True
    write_json(source_path, approved)

    validated = validate_performance_script(approved)
    validated["status"] = (
        "HUMAN_LANGUAGE_AND_PERFORMANCE_APPROVED_READY_FOR_TTS_PREFLIGHT"
    )
    validated["episode_id"] = args.episode
    validated["source_script_path"] = str(
        source_path.relative_to(repo)
    ).replace("\\", "/")
    validated["human_language_review_required"] = False
    validated["human_performance_review_required"] = False
    validated["human_approval"] = approval
    validated["tts_execution_authorized"] = False
    validated["paid_execution_authorized"] = False
    write_json(final_path, validated)
    write_json(approval_path, approval)

    report = {
        "schema_version": "siraj-arabic-performance-finalization-v2",
        "release": "SIRAJ_ADAM_APPROVED_ARABIC_PERFORMANCE_V2",
        "episode_id": args.episode,
        "status": "PASS_READY_FOR_TTS_PREFLIGHT",
        "source_path": str(source_path.relative_to(repo)).replace("\\", "/"),
        "final_script_path": str(final_path.relative_to(repo)).replace("\\", "/"),
        "approval_path": str(approval_path.relative_to(repo)).replace("\\", "/"),
        "metrics": validated["metrics"],
        "human_approval": approval,
        "tts_execution_authorized": False,
        "paid_execution_authorized": False,
        "next_stage": "TTS_PREFLIGHT_AND_SHORT_SAMPLE_GENERATION",
    }
    write_json(report_path, report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
