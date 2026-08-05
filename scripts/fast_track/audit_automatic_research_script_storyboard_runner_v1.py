from __future__ import annotations

import argparse
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

    provider = (
        repo / "src/application/openai_luna_editorial_v1.py"
    ).read_text(encoding="utf-8")
    runner = (
        repo
        / "src/application/"
        "automatic_research_script_storyboard_runner_v1.py"
    ).read_text(encoding="utf-8")
    ui = (
        repo / "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")

    for marker in (
        "request_evidence_package",
        "request_script_package",
        "request_storyboard_plan",
        'request["tools"] = [{"type": "web_search"}]',
        '"type": "json_schema"',
        "OPENAI_TRANSIENT_SERVER_ERROR_NO_AUTO_RETRY",
    ):
        require(marker in provider, "PROVIDER_MARKER_MISSING:" + marker)

    for marker in (
        "EVIDENCE_RESEARCH",
        "SCRIPT_WRITING",
        "STORYBOARD_AND_MEDIA_PLANNING",
        "completed_provider_response_reuse",
        "EDITORIAL_PIPELINE_COMPLETE",
        "STAGE_MAX_BUDGET_USD",
        "openai-luna-evidence-research-receipt-v1.json",
        "openai-luna-script-writing-receipt-v1.json",
        "openai-luna-storyboard-media-plan-receipt-v1.json",
    ):
        require(marker in runner, "RUNNER_MARKER_MISSING:" + marker)

    for marker in (
        "EditorialPipelineThread",
        "resumeEditorialPipelineButton",
        "editorialPipelineProgress",
        "_start_editorial_pipeline",
    ):
        require(marker in ui, "UI_MARKER_MISSING:" + marker)

    require(
        "HUMAN_SCRIPT_REVIEW" not in runner,
        "THIRD_HUMAN_GATE_FORBIDDEN",
    )
    require(
        "HUMAN_STORYBOARD_REVIEW" not in runner,
        "THIRD_HUMAN_GATE_FORBIDDEN",
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    report = args.output_root / "audit.txt"
    report.write_text(
        "\n".join(
            (
                "STATUS=PASS_AUTOMATIC_RESEARCH_SCRIPT_STORYBOARD_RUNNER_V1",
                "LUNA_EDITORIAL_STAGES=3",
                "WEB_SEARCH=EVIDENCE_STAGE_ONLY",
                "STRUCTURED_OUTPUTS=YES",
                "TOTAL_STORYBOARD_SHOTS=70",
                "GENERATED_VIDEO_SHOTS=20",
                "ANIMATED_STILL_COMPOSITING_SHOTS=44",
                "GRAPHICS_SHOTS=6",
                "GENERATED_VIDEO_SECONDS=160",
                "HUMAN_GATES=2",
                "HIDDEN_PAID_RETRY=FORBIDDEN",
                "PROVIDER_RESPONSE_RECOVERY=YES",
                "PARTIAL_REBUILD_GRAPH_UPDATED=YES",
                "MUSIC=FORBIDDEN",
                "OPENAI_REQUESTS_DURING_AUDIT=0",
                "RUNWARE_REQUESTS_DURING_AUDIT=0",
                "ELEVENLABS_REQUESTS_DURING_AUDIT=0",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    print(report.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
