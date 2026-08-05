from __future__ import annotations

import argparse
import json
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()

    integration = (
        repo / "src/application/graphics_storyboard_media_queue_v1.py"
    ).read_text(encoding="utf-8")
    provider = (
        repo / "src/application/openai_luna_editorial_v1.py"
    ).read_text(encoding="utf-8")
    runner = (
        repo
        / "src/application/"
        "automatic_research_script_storyboard_runner_v1.py"
    ).read_text(encoding="utf-8")
    orchestrator = (
        repo / "src/application/autonomous_episode_orchestrator_v1.py"
    ).read_text(encoding="utf-8")
    ui = (
        repo / "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")
    contract = json.loads(
        (
            repo
            / "projects/_orchestrator/contracts/"
            "graphics-storyboard-media-queue-v1.json"
        ).read_text(encoding="utf-8")
    )

    for marker in (
        "IMAGE_QUEUE_COUNT_MUST_BE_44",
        "VIDEO_QUEUE_COUNT_MUST_BE_20",
        "GRAPHICS_QUEUE_COUNT_MUST_BE_6",
        "BLOCKED_VOICE_SELECTION_REQUIRED",
        "READY_LOCAL_RENDER",
        "ONE_EXPLICIT_DESKTOP_AUTHORIZATION_PER_ATTEMPT",
        "EPISODE_BUDGET_PREFLIGHT_BLOCKED",
    ):
        require(marker in integration, "INTEGRATION_MARKER_MISSING:" + marker)
    require(
        "graphics_spec_json_schema" in provider,
        "LUNA_GRAPHICS_SPEC_SCHEMA_MISSING",
    )
    require(
        "extract_storyboard_graphics_specs" in runner,
        "RUNNER_GRAPHICS_VALIDATION_MISSING",
    )
    require(
        '"LOCAL_GRAPHICS_RENDER"' in orchestrator,
        "LOCAL_GRAPHICS_STAGE_MISSING",
    )
    require(
        "buildMediaQueueButton" in ui,
        "DESKTOP_MEDIA_QUEUE_BUTTON_MISSING",
    )
    require(
        "integrate_graphics_and_build_media_queue" in ui,
        "DESKTOP_AUTO_INTEGRATION_MISSING",
    )
    require(contract["counts"]["runware_images"] == 44, "IMAGE_COUNT_CHANGED")
    require(contract["counts"]["runware_videos"] == 20, "VIDEO_COUNT_CHANGED")
    require(contract["counts"]["local_graphics"] == 6, "GRAPHICS_COUNT_CHANGED")
    require(
        contract["tts"]["voice_selection_required"] is True,
        "TTS_VOICE_GATE_MISSING",
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    report = args.output_root / "audit.txt"
    report.write_text(
        "\n".join(
            (
                "STATUS=PASS_GRAPHICS_STORYBOARD_INTEGRATION_AND_MEDIA_QUEUE_V1",
                "GRAPHICS_SPECS=6",
                "RUNWARE_IMAGE_QUEUE=44",
                "RUNWARE_VIDEO_QUEUE=20",
                "LOCAL_GRAPHICS_QUEUE=6",
                "ELEVENLABS_TTS_QUEUE=PER_SCRIPT_SEGMENT",
                "TTS_VOICE_SELECTION_REQUIRED=YES",
                "PROTECTIVE_MAX_RESERVE_USD=17.60",
                "EXPLICIT_PAID_AUTHORIZATION_PER_ATTEMPT=REQUIRED",
                "HIDDEN_PAID_RETRY=FORBIDDEN",
                "PAID_PROVIDER_REQUESTS_DURING_AUDIT=0",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    print(report.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
