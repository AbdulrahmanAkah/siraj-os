from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Mapping

from src.application.adam_world_motion_repair_v2 import (
    build_narration_export,
    narration_export_text,
    repair_visual_plan,
)


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(value, encoding="utf-8", newline="\n")
    os.replace(temporary, path)


def locate_script(episode: Path) -> Path:
    candidates = [
        episode / "script" / "episode-script-v1.json",
        episode / "editorial" / "prestige-cinematic-script-v2-1.json",
    ]
    definition_path = episode / "contracts" / "episode-definition-v1.json"
    if definition_path.is_file():
        definition = read_json(definition_path)
        cinematic = definition.get("cinematic_script")
        if isinstance(cinematic, Mapping):
            relative = str(cinematic.get("path") or "").strip()
            if relative:
                candidates.insert(0, episode / relative)
    for path in candidates:
        if path.is_file():
            return path
    raise RuntimeError(
        "SCRIPT_SOURCE_NOT_FOUND:" + "|".join(str(path) for path in candidates)
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--episode", default="episode-001-adam")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    episode = repo / "projects" / args.episode
    storyboard_path = (
        episode / "cinematic" / "storyboard-and-media-plan-v2.json"
    )
    plan_path = (
        episode / "cinematic" / "episode-production-plan-v2.json"
    )
    result = repair_visual_plan(
        read_json(storyboard_path),
        read_json(plan_path),
    )
    write_json(storyboard_path, result.storyboard)
    write_json(plan_path, result.production_plan)

    summary_path = (
        episode / "orchestration" / "adam-world-motion-repair-v2-summary.json"
    )
    write_json(summary_path, result.visual_summary)

    source_script_path = locate_script(episode)
    source_script = read_json(source_script_path)
    narration = build_narration_export(
        source_script,
        str(source_script_path.relative_to(repo)).replace("\\", "/"),
    )
    narration_json_path = (
        episode / "script" / "arabic-performance-source-v2.json"
    )
    narration_text_path = (
        episode / "script" / "arabic-performance-source-v2.txt"
    )
    write_json(narration_json_path, narration)
    write_text(narration_text_path, narration_export_text(narration))

    compact = {
        "release": "SIRAJ_ADAM_WORLD_MOTION_REPAIR_AND_NARRATION_EXPORT_V2",
        "status": "PASS",
        "visual": result.visual_summary,
        "narration_export": {
            "json_path": str(narration_json_path.relative_to(repo)).replace("\\", "/"),
            "text_path": str(narration_text_path.relative_to(repo)).replace("\\", "/"),
            "segment_count": narration["metrics"]["segment_count"],
            "performance_block_count": narration["metrics"][
                "performance_block_count"
            ],
            "word_count": narration["metrics"]["word_count"],
            "status": narration["status"],
        },
        "paid_execution_authorized": False,
        "next_stage": "UPLOAD_ARABIC_PERFORMANCE_SOURCE_FOR_FULL_DIACRITIZATION",
    }
    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
