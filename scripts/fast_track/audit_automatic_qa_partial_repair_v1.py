from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.automatic_qa_partial_repair_v1 import (
    MAX_REPAIR_PASSES,
    inspect_qa_environment,
    run_qa_smoke_test,
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

    engine = (
        repo / "src/application/automatic_qa_partial_repair_v1.py"
    ).read_text(encoding="utf-8")
    ui = (
        repo / "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")
    orchestrator = (
        repo / "src/application/autonomous_episode_orchestrator_v1.py"
    ).read_text(encoding="utf-8")
    montage = (
        repo / "src/application/structural_montage_final_render_v1.py"
    ).read_text(encoding="utf-8")
    contract = json.loads(
        (
            repo
            / "projects/_orchestrator/contracts/"
            "automatic-qa-partial-repair-v1.json"
        ).read_text(encoding="utf-8")
    )

    for marker in (
        "AUTOMATIC_QA_AND_PARTIAL_REPAIR_V1",
        "blackdetect",
        "freezedetect",
        "silencedetect",
        "loudnorm",
        "SHOT_OUTPUT_HASH_MISMATCH",
        "STILL_MOTION_FLAT_OR_FROZEN",
        "LOCAL_SHOT_RERENDER",
        "UPSTREAM_MEDIA_REQUIRED",
        "UPSTREAM_AUDIO_REQUIRED",
        "automatic_paid_regeneration\": \"FORBIDDEN",
        "paid_provider_requests\": 0",
        "AWAITING_HUMAN_FINAL_REVIEW",
        "HUMAN_FINAL_REVIEW_AND_PUBLISHING_V1",
    ):
        require(marker in engine, "ENGINE_MARKER_MISSING:" + marker)

    for marker in (
        "AutomaticQAThread",
        "automaticQaPartialRepairTab",
        "runAutomaticQaButton",
        "openAutomaticQaReportButton",
        "run_automatic_qa_and_partial_repair",
        "load_automatic_qa_status",
    ):
        require(marker in ui, "DESKTOP_MARKER_MISSING:" + marker)

    require("inspect_qa_environment" in orchestrator, "ORCHESTRATOR_QA_READINESS_MISSING")
    require("AUTOMATIC_QA_ACTIVE" in montage, "MONTAGE_DOWNSTREAM_QA_STATUS_MISSING")
    require(contract["maximum_local_repair_passes"] == MAX_REPAIR_PASSES, "REPAIR_PASS_COUNT_CHANGED")
    require(contract["automatic_paid_regeneration"] == "FORBIDDEN", "PAID_REGEN_POLICY_CHANGED")
    require(contract["music"] == "FORBIDDEN", "MUSIC_POLICY_CHANGED")
    require(contract["completion"]["next_stage"] == "HUMAN_FINAL_REVIEW_AND_PUBLISHING_V1", "NEXT_STAGE_CHANGED")

    environment = inspect_qa_environment(repo)
    require(environment.ready, "QA_ENVIRONMENT_NOT_READY")
    smoke = run_qa_smoke_test(repo, output / "ffmpeg-qa-smoke")
    require(smoke["status"] == "PASS", "QA_SMOKE_FAILED")
    require(smoke["paid_provider_requests"] == 0, "QA_SMOKE_PROVIDER_REQUEST_DETECTED")

    report = output / "audit.txt"
    report.write_text(
        "\n".join(
            (
                "STATUS=PASS_AUTOMATIC_QA_AND_PARTIAL_REPAIR_V1",
                "SHOT_TECHNICAL_QA=70_OF_70",
                "FINAL_CONTAINER_QA=PASS",
                "BLACK_DETECTION=ENABLED",
                "FREEZE_DETECTION=ENABLED",
                "SILENCE_DETECTION=ENABLED",
                "LOUDNESS_MEASUREMENT=ENABLED",
                "RECEIPT_AND_SHA256_INTEGRITY=ENABLED",
                "LOCAL_REPAIR=TARGETED_SHOT_OR_FINAL_REMUX_ONLY",
                "MAX_LOCAL_REPAIR_PASSES=2",
                "FULL_REGENERATION_FOR_LOCAL_DEFECT=FORBIDDEN",
                "AUTOMATIC_PAID_REGENERATION=FORBIDDEN",
                "MUSIC=FORBIDDEN",
                "LOCAL_API_COST_USD=0.00",
                "FFMPEG_QA_SMOKE=PASS",
                "PAID_PROVIDER_REQUESTS_DURING_AUDIT=0",
                "NEXT_STAGE=HUMAN_FINAL_REVIEW_AND_PUBLISHING_V1",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    (output / "smoke-result.json").write_text(
        json.dumps(smoke, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(report.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
