from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def _configure_utf8_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


_configure_utf8_console()

from src.application.arabic_actual_stop_waqf_v2 import (
    build_cast_candidate,
    build_full_episode_readiness,
    build_second_sample_request,
    process_script,
    write_outputs,
)


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise RuntimeError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", default=".")
    parser.add_argument("--episode", default="episode-001-adam")
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    episode = repo / "projects" / args.episode

    source = read_json(
        episode / "script/arabic-performance-source-v2.json"
    )
    script = read_json(
        episode / "script/episode-script-v2.json"
    )
    storyboard = read_json(
        episode / "cinematic/storyboard-and-media-plan-v2.json"
    )

    source_candidate, source_report = process_script(source)
    script_candidate, report = process_script(script)

    source_text_by_block = {
        block["block_id"]: block["tts_text_ar"]
        for segment in source_candidate["segments"]
        for block in segment["performance_blocks"]
    }
    script_text_by_block = {
        block["block_id"]: block["tts_text_ar"]
        for segment in script_candidate["segments"]
        for block in segment["performance_blocks"]
    }
    if source_text_by_block != script_text_by_block:
        raise RuntimeError("SOURCE_AND_SCRIPT_WAQF_TEXT_DIVERGED")

    cast_plan = build_cast_candidate(
        args.episode,
        script_candidate,
        storyboard,
    )
    sample_request = build_second_sample_request(
        args.episode,
        cast_plan,
    )
    readiness = build_full_episode_readiness(
        args.episode,
        script_candidate,
        cast_plan,
        report,
    )
    outputs = write_outputs(
        repo,
        episode_id=args.episode,
        source_candidate=source_candidate,
        script_candidate=script_candidate,
        report=report,
        cast_plan=cast_plan,
        sample_request=sample_request,
        readiness=readiness,
    )

    print(
        json.dumps(
            {
                "release": "SIRAJ_ARABIC_ACTUAL_STOP_WAQF_V2",
                "status": "PASS_BATCH_REVIEW_READY",
                "episode_id": args.episode,
                "metrics": {
                    "segment_count": report["segment_count"],
                    "performance_block_count": report[
                        "performance_block_count"
                    ],
                    "actual_stop_count": report[
                        "actual_stop_count"
                    ],
                    "changed_stop_count": report[
                        "changed_stop_count"
                    ],
                    "hard_punctuation_stop_count": report[
                        "hard_punctuation_stop_count"
                    ],
                    "strong_clause_comma_stop_count": report[
                        "strong_clause_comma_stop_count"
                    ],
                    "performance_block_end_stop_count": report[
                        "performance_block_end_stop_count"
                    ],
                    "connected_commas_preserved_count": report[
                        "connected_commas_preserved_count"
                    ],
                },
                "sample_before": report["sample_block"][
                    "text_before"
                ],
                "sample_after": report["sample_block"][
                    "text_after"
                ],
                "second_sample": {
                    "status": sample_request["status"],
                    "character_count_unicode": sample_request[
                        "character_count_unicode"
                    ],
                    "suggested_authorization_ceiling_usd": (
                        sample_request[
                            "suggested_authorization_ceiling_usd"
                        ]
                    ),
                    "sample_generation_authorized": False,
                },
                "full_episode_tts_authorized": False,
                "provider_requests": 0,
                "paid_provider_requests": 0,
                "outputs": outputs,
                "next_stage": (
                    "HUMAN_WAQF_DIFF_REVIEW_AND_SECOND_SAMPLE_AUTHORIZATION"
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
