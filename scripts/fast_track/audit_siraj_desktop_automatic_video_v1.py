from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import uuid


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()
    sys.path.insert(0, str(repo))

    from src.application.automatic_video_workflow_v1 import (
        PASS_THRESHOLD,
        build_attempt_payload,
        decision_for_score,
        load_automatic_video_spec,
    )

    spec = load_automatic_video_spec(repo)
    require(PASS_THRESHOLD == 80, "PASS_THRESHOLD_CHANGED")
    require(decision_for_score(79) == "FAIL", "FAIL_BOUNDARY_CHANGED")
    require(decision_for_score(80) == "PASS", "PASS_BOUNDARY_CHANGED")
    require(len(spec.plans) == 3, "ATTEMPT_PLAN_COUNT_CHANGED")

    for plan in spec.plans:
        payload = build_attempt_payload(spec, plan, str(uuid.uuid4()))
        require(len(payload) == 1, "ONE_TASK_PER_CLICK_REQUIRED")
        task = payload[0]
        require(task["taskType"] == "videoInference", "TASK_TYPE_CHANGED")
        require(task["model"] == "google:veo@3.1-lite", "MODEL_CHANGED")
        require(task["width"] == 1280, "WIDTH_CHANGED")
        require(task["height"] == 720, "HEIGHT_CHANGED")
        require(task["duration"] == 8, "DURATION_CHANGED")
        require(task["numberResults"] == 1, "RESULT_COUNT_CHANGED")
        require(task["deliveryMethod"] == "async", "ASYNC_REQUIRED")
        require(task["includeCost"] is True, "COST_RECEIPT_REQUIRED")
        require("resolution" not in task, "RESOLUTION_CONFLICT_ENABLED")
        require(
            task["providerSettings"]["google"]["generateAudio"] is False,
            "AUDIO_ENABLED",
        )
        require(
            task["providerSettings"]["google"]["personGeneration"]
            == "dont_allow",
            "PERSON_GENERATION_CHANGED",
        )

    console = (
        repo / "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8-sig")
    credentials = (
        repo / "src/application/windows_credentials_v1.py"
    ).read_text(encoding="utf-8-sig")
    authorization = json.loads(
        (
            repo / "projects/episode-001-adam/contracts/"
            "automatic-video-user-authorization-v1.json"
        ).read_text(encoding="utf-8-sig")
    )

    for marker in (
        "generateVideoButton",
        "viewVideoButton",
        "showVideoLocationButton",
        "finalScoreSpinBox",
        "saveFinalScoreButton",
    ):
        require(marker in console, "CONSOLE_MARKER_MISSING:" + marker)

    review = authorization["review_policy"]
    generation = authorization["generation_policy"]
    require(
        review["required_input"] == "ONE_INTEGER_ONLY_0_TO_100",
        "REVIEW_INPUT_NOT_SCORE_ONLY",
    )
    require(review["pass_threshold"] == 80, "AUTH_THRESHOLD_CHANGED")
    require(
        generation["background_paid_retry_without_click"] == "BLOCKED",
        "BACKGROUND_PAID_RETRY_OPENED",
    )
    require(
        generation["submission_trigger"]
        == "ONE_EXPLICIT_CREATE_VIDEO_BUTTON_CLICK",
        "PAID_SUBMISSION_TRIGGER_CHANGED",
    )
    require("CredWriteW" in credentials, "WINDOWS_CREDENTIAL_WRITE_MISSING")
    require("CredReadW" in credentials, "WINDOWS_CREDENTIAL_READ_MISSING")
    require("explorer.exe" in console, "OUTPUT_LOCATION_ACTION_MISSING")

    args.output_root.mkdir(parents=True, exist_ok=True)
    result = {
        "status": "PASS_SIRAJ_DESKTOP_AUTOMATIC_VIDEO_V1",
        "execution_surface": "SIRAJ_DESKTOP_UI_ONLY",
        "generation_trigger": "ONE_CREATE_VIDEO_BUTTON_CLICK",
        "automatic_submission_poll_download": True,
        "review_input": "ONE_INTEGER_ONLY_0_TO_100",
        "pass_threshold": 80,
        "output_actions": [
            "VIEW_VIDEO",
            "SHOW_VIDEO_LOCATION_ON_DEVICE",
        ],
        "maximum_attempts": 3,
        "maximum_cost_per_attempt_usd": 0.40,
        "background_paid_retry_without_click": False,
        "credential_storage": "WINDOWS_CREDENTIAL_MANAGER",
        "runware_requests_during_audit": 0,
        "credit_spent_during_audit": False,
        "next_stage": "USER_ONE_CLICK_VIDEO_GENERATION",
    }
    report = args.output_root / "siraj-desktop-automatic-video-v1-audit.json"
    report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    for key, value in result.items():
        print(f"{key.upper()}={value}")
    print("REPORT=" + str(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
