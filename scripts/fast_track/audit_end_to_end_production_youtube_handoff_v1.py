from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.end_to_end_production_v1 import (
    run_end_to_end_planner_smoke_test,
)
from src.application.youtube_publish_handoff_v1 import (
    run_youtube_handoff_smoke_test,
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
    output = args.output_root.resolve()
    output.mkdir(parents=True, exist_ok=True)

    engine = (repo / "src/application/end_to_end_production_v1.py").read_text(encoding="utf-8")
    handoff = (repo / "src/application/youtube_publish_handoff_v1.py").read_text(encoding="utf-8")
    console = (repo / "src/presentation/desktop/production_console.py").read_text(encoding="utf-8")
    review = (repo / "src/application/final_review_publish_package_v1.py").read_text(encoding="utf-8")
    dialog = (repo / "src/presentation/desktop/final_review_publish_dialog_v1.py").read_text(encoding="utf-8")
    contract = json.loads(
        (repo / "projects/_orchestrator/contracts/end-to-end-production-youtube-handoff-v1.json").read_text(encoding="utf-8")
    )
    thumbnail_policy = json.loads(
        (repo / "projects/_orchestrator/contracts/thumbnail-era-policy-v1.json").read_text(encoding="utf-8")
    )

    for marker in (
        "run_to_next_human_gate",
        "CONSOLIDATED_MEDIA_AUTHORIZATION_REQUIRED",
        "AUTHORIZED_MEDIA_QUEUE",
        "execute_runware_item",
        "execute_elevenlabs_item",
        "run_sfx_audio_mix",
        "run_structural_montage_final_render",
        "run_automatic_qa_and_partial_repair",
    ):
        require(marker in engine, "ENGINE_MARKER_MISSING:" + marker)

    for marker in (
        "READY_FOR_MANUAL_YOUTUBE_UPLOAD",
        "youtube-chapters.txt",
        "youtube-subtitles-ar.srt",
        "altered_content_disclosure",
        "NOT_MADE_FOR_KIDS",
        "Open YouTube Studio.url",
        "STATIC_TEMPLATE_PER_HISTORICAL_ERA",
        "youtube_api_requests",
    ):
        require(marker in handoff, "HANDOFF_MARKER_MISSING:" + marker)

    for marker in (
        "EndToEndCompletionThread",
        "endToEndCompletionProgress",
        "_start_end_to_end_completion",
        "pending_media_maximum_usd",
        "تفويض واحد",
    ):
        require(marker in console, "CONSOLE_MARKER_MISSING:" + marker)

    require("suggest_complete_publish_metadata" in review, "FULL_METADATA_SUGGESTION_NOT_WIRED")
    require("complete_youtube_publish_handoff" in review, "HANDOFF_NOT_WIRED_TO_FINAL_APPROVAL")
    require("openYouTubeStudioButton" in dialog, "YOUTUBE_STUDIO_BUTTON_MISSING")
    require(contract["single_consolidated_media_authorization"] is True, "CONSOLIDATED_AUTH_POLICY_CHANGED")
    require(contract["automatic_youtube_upload"] == "FORBIDDEN", "AUTOMATIC_UPLOAD_POLICY_CHANGED")
    require(contract["youtube_api_draft_upload"] == "DEFERRED_UNTIL_VERIFIED_API_PROJECT", "UNVERIFIED_API_UPLOAD_POLICY_CHANGED")
    require(contract["human_gates"] == ["HUMAN_SCOPE_REVIEW", "HUMAN_FINAL_REVIEW"], "HUMAN_GATES_CHANGED")
    require(thumbnail_policy["selection_policy"] == "STATIC_TEMPLATE_PER_HISTORICAL_ERA", "THUMBNAIL_POLICY_CHANGED")

    planner_smoke = run_end_to_end_planner_smoke_test(output / "planner-smoke")
    handoff_smoke = run_youtube_handoff_smoke_test(output / "handoff-smoke")
    require(planner_smoke["status"] == "PASS", "PLANNER_SMOKE_FAILED")
    require(handoff_smoke["status"] == "PASS", "HANDOFF_SMOKE_FAILED")
    require(handoff_smoke["youtube_api_requests"] == 0, "YOUTUBE_API_REQUEST_DETECTED")

    (output / "planner-smoke.json").write_text(
        json.dumps(planner_smoke, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output / "handoff-smoke.json").write_text(
        json.dumps(handoff_smoke, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    report = output / "audit.txt"
    report.write_text(
        "\n".join(
            (
                "STATUS=PASS_SIRAJ_END_TO_END_PRODUCTION_AND_YOUTUBE_HANDOFF_V1",
                "TOPIC_TO_YOUTUBE_HANDOFF=COMPLETE",
                "HUMAN_SCOPE_GATE=REQUIRED",
                "CONSOLIDATED_MEDIA_AUTHORIZATION=ENABLED",
                "PAID_RETRY_WITHOUT_CONFIRMATION=FORBIDDEN",
                "LOCAL_STAGES_AUTO_CHAIN=SFX_MONTAGE_QA",
                "HUMAN_FINAL_REVIEW_GATE=REQUIRED",
                "YOUTUBE_CHAPTERS=GENERATED",
                "ARABIC_SRT=GENERATED_FROM_LOCKED_TTS_TIMELINE",
                "ALTERED_CONTENT_DISCLOSURE=YES",
                "AUDIENCE_DEFAULT=NOT_MADE_FOR_KIDS",
                "THUMBNAIL_POLICY=STATIC_PER_ERA_DESIGN_DEFERRED",
                "MANUAL_YOUTUBE_UPLOAD=REQUIRED",
                "YOUTUBE_API_REQUESTS=0",
                "YOUTUBE_API_DRAFT_UPLOAD=DEFERRED_UNTIL_VERIFIED_API_PROJECT",
                "NEXT_STAGE=END_TO_END_ACCEPTANCE_RUN",
            )
        ) + "\n",
        encoding="utf-8",
    )
    print(report.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
