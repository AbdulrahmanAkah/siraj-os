from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.final_review_publish_package_v1 import (
    REQUIRED_CHECKLIST_KEYS,
    run_final_review_smoke_test,
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
        repo / "src/application/final_review_publish_package_v1.py"
    ).read_text(encoding="utf-8")
    dialog = (
        repo / "src/presentation/desktop/final_review_publish_dialog_v1.py"
    ).read_text(encoding="utf-8")
    console = (
        repo / "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")
    qa = (
        repo / "src/application/automatic_qa_partial_repair_v1.py"
    ).read_text(encoding="utf-8")
    contract = json.loads(
        (
            repo
            / "projects/_orchestrator/contracts/"
            "final-review-publish-package-v1.json"
        ).read_text(encoding="utf-8")
    )

    for marker in (
        "FINAL_REVIEW_AND_PUBLISH_PACKAGE_V1",
        "approve_final_review_and_build_publish_package",
        "request_final_review_changes",
        "READY_TO_PUBLISH",
        "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED",
        "MANUAL_YOUTUBE_UPLOAD",
        '"automatic_upload": "FORBIDDEN"',
        '"youtube_api_requests": 0',
        '"provider_requests": 0',
        '"manual_youtube_upload": True',
        "AUTOMATIC_QA_RERUN_REQUIRED_AFTER_CHANGES",
        "SHA256SUMS.txt",
        "publish-metadata-v1.zip",
    ):
        require(marker in engine, "ENGINE_MARKER_MISSING:" + marker)

    for checklist_key in REQUIRED_CHECKLIST_KEYS:
        require(checklist_key in engine, "CHECKLIST_KEY_MISSING:" + checklist_key)
        require(checklist_key in dialog, "DIALOG_CHECKLIST_KEY_MISSING:" + checklist_key)

    for marker in (
        "FinalReviewPublishDialog",
        "approveFinalReviewButton",
        "requestFinalReviewChangesButton",
        "finalReviewPublishDialog",
    ):
        require(marker in dialog, "DIALOG_MARKER_MISSING:" + marker)

    for marker in (
        "openFinalReviewPublishButton",
        "_open_final_review_publish",
        "FinalReviewPublishDialog",
        "READY_TO_PUBLISH",
    ):
        require(marker in console, "CONSOLE_MARKER_MISSING:" + marker)

    require(
        "HUMAN_FINAL_REVIEW_CHANGES_REQUESTED" in qa,
        "QA_REENTRY_STATUS_MISSING",
    )
    for forbidden in (
        "urllib.request",
        "requests.post",
        "googleapiclient",
        "youtube.upload",
        "oauth2client",
    ):
        require(forbidden not in engine, "NETWORK_UPLOAD_SURFACE_FOUND:" + forbidden)

    require(contract["manual_youtube_upload"] is True, "MANUAL_UPLOAD_POLICY_CHANGED")
    require(contract["automatic_upload"] == "FORBIDDEN", "AUTOMATIC_UPLOAD_POLICY_CHANGED")
    require(contract["youtube_api_requests"] == 0, "YOUTUBE_API_POLICY_CHANGED")
    require(contract["provider_requests_during_review"] == 0, "PROVIDER_REQUEST_POLICY_CHANGED")
    require(contract["music"] == "FORBIDDEN", "MUSIC_POLICY_CHANGED")
    require(contract["completion"]["runtime_status"] == "READY_TO_PUBLISH", "RUNTIME_STATUS_CHANGED")

    smoke = run_final_review_smoke_test(output / "smoke")
    require(smoke["status"] == "PASS", "FINAL_REVIEW_SMOKE_FAILED")
    require(smoke["manual_youtube_upload"] is True, "SMOKE_MANUAL_UPLOAD_CHANGED")
    require(smoke["youtube_api_requests"] == 0, "SMOKE_YOUTUBE_REQUEST_DETECTED")
    require(smoke["provider_requests"] == 0, "SMOKE_PROVIDER_REQUEST_DETECTED")

    report = output / "audit.txt"
    report.write_text(
        "\n".join(
            (
                "STATUS=PASS_FINAL_REVIEW_AND_PUBLISH_PACKAGE_V1",
                "HUMAN_FINAL_REVIEW_GATE=ENABLED",
                "REQUIRED_CHECKLIST_ITEMS=7",
                "APPROVAL_INTEGRITY_RECHECK=QA_AND_FINAL_SHA256",
                "CHANGE_REQUEST=STRUCTURED_AND_STAGE_TARGETED",
                "NON_METADATA_CHANGE_REQUIRES_QA_RERUN=YES",
                "PUBLISH_PACKAGE=VIDEO_REFERENCE_METADATA_CHECKSUMS_AND_CHECKLIST",
                "MANUAL_YOUTUBE_UPLOAD=REQUIRED",
                "AUTOMATIC_UPLOAD=FORBIDDEN",
                "YOUTUBE_API_REQUESTS_DURING_AUDIT=0",
                "PROVIDER_REQUESTS_DURING_AUDIT=0",
                "MUSIC=FORBIDDEN",
                "LOCAL_API_COST_USD=0.00",
                "FINAL_REVIEW_SMOKE=PASS",
                "RUNTIME_COMPLETION=READY_TO_PUBLISH",
                "NEXT_STAGE=SIRAJ_PRODUCTION_V1_COMPLETE_READY_FOR_END_TO_END_RUN",
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
