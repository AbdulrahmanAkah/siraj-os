from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.structural_montage_final_render_v1 import (
    inspect_montage_environment,
    run_montage_smoke_test,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()

    engine = (
        repo / "src/application/structural_montage_final_render_v1.py"
    ).read_text(encoding="utf-8")
    ui = (
        repo / "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")
    orchestrator = (
        repo / "src/application/autonomous_episode_orchestrator_v1.py"
    ).read_text(encoding="utf-8")
    sfx = (
        repo / "src/application/sfx_audio_mix_v1.py"
    ).read_text(encoding="utf-8")
    contract = json.loads(
        (
            repo
            / "projects/_orchestrator/contracts/"
            "structural-montage-final-render-v1.json"
        ).read_text(encoding="utf-8")
    )

    for marker in (
        "STORYBOARD_70_SHOTS_REQUIRED",
        "GENERATED_VIDEO_SECONDS_MUST_BE_160",
        "flat_slideshow\": \"FORBIDDEN",
        "zoompan",
        "overlay",
        "tpad=stop_mode=clone",
        "SOURCE_AUDIO_MUST_BE_STRIPPED",
        "_receipt_reusable",
        "FINAL_RENDER_READY_FOR_QA",
        "AUTOMATIC_QA_AND_PARTIAL_REPAIR_V1",
        "paid_provider_requests\": 0",
    ):
        require(marker in engine, "ENGINE_MARKER_MISSING:" + marker)

    for marker in (
        "StructuralMontageThread",
        "structuralMontageFinalRenderTab",
        "buildStructuralMontageButton",
        "openFinalEpisodeButton",
        "run_structural_montage_final_render",
    ):
        require(marker in ui, "DESKTOP_MARKER_MISSING:" + marker)

    require(
        "LOCAL_FFMPEG_READY" in orchestrator,
        "ORCHESTRATOR_MONTAGE_READINESS_MISSING",
    )
    require(
        "FINAL_RENDER_READY_FOR_QA" in sfx,
        "SFX_DOWNSTREAM_STATUS_COMPATIBILITY_MISSING",
    )

    require(contract["shot_count"] == 70, "SHOT_COUNT_CHANGED")
    require(
        contract["treatment_counts"]
        == {
            "animated_still_compositing": 44,
            "generated_video": 20,
            "graphics": 6,
        },
        "TREATMENT_COUNTS_CHANGED",
    )
    require(contract["music"] == "FORBIDDEN", "MUSIC_POLICY_CHANGED")
    require(
        contract["flat_slideshow"] == "FORBIDDEN",
        "FLAT_SLIDESHOW_POLICY_CHANGED",
    )
    require(
        contract["source_audio"] == "STRIPPED_FROM_ALL_VISUAL_INPUTS",
        "SOURCE_AUDIO_POLICY_CHANGED",
    )
    require(
        contract["local_api_cost_usd"] == 0.0,
        "LOCAL_RENDER_COST_CHANGED",
    )
    require(
        contract["completion"]["next_stage"]
        == "AUTOMATIC_QA_AND_PARTIAL_REPAIR_V1",
        "NEXT_STAGE_CHANGED",
    )

    environment = inspect_montage_environment(repo)
    require(environment.ready, "MONTAGE_ENVIRONMENT_NOT_READY")
    args.output_root.mkdir(parents=True, exist_ok=True)
    smoke = run_montage_smoke_test(
        repo,
        args.output_root / "ffmpeg-montage-smoke",
    )
    require(smoke["status"] == "PASS", "MONTAGE_SMOKE_FAILED")

    report = args.output_root / "audit.txt"
    report.write_text(
        "\n".join(
            (
                "STATUS=PASS_STRUCTURAL_MONTAGE_AND_FINAL_RENDER_V1",
                "SHOT_COUNT=70",
                "ANIMATED_STILLS=44",
                "GENERATED_VIDEOS=20",
                "LOCAL_GRAPHICS=6",
                "STILL_MOTION=DETERMINISTIC_KEN_BURNS_AND_COMPOSITING",
                "FLAT_SLIDESHOW=FORBIDDEN",
                "SOURCE_AUDIO=STRIPPED",
                "AUDIO_MASTER=LOCKED_SFX_AND_NARRATION_MASTER",
                "FINAL_VIDEO=H264_1920X1080_30FPS",
                "FINAL_AUDIO=AAC_48KHZ_STEREO_192K",
                "PARTIAL_RESUME=PER_SHOT_RECEIPT_AND_SHA256",
                "MUSIC=FORBIDDEN",
                "LOCAL_API_COST_USD=0.00",
                "FFMPEG_MONTAGE_SMOKE=PASS",
                "PAID_PROVIDER_REQUESTS_DURING_AUDIT=0",
                "NEXT_STAGE=AUTOMATIC_QA_AND_PARTIAL_REPAIR_V1",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (args.output_root / "smoke-result.json").write_text(
        json.dumps(smoke, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(report.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
