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

    from src.application.runware_execution_v1 import (
        build_video_inference_payload,
        load_execution_spec,
    )

    spec = load_execution_spec(repo)
    task_uuid = str(uuid.uuid4())
    payload = build_video_inference_payload(spec, task_uuid)
    require(len(payload) == 1, "EXACTLY_ONE_TASK_REQUIRED")
    task = payload[0]
    require(task["taskType"] == "videoInference", "TASK_TYPE_CHANGED")
    require(task["model"] == "google:veo@3.1-lite", "MODEL_CHANGED")
    require(task["width"] == 1280 and task["height"] == 720, "DIMENSIONS_CHANGED")
    require(task["duration"] == 8, "DURATION_CHANGED")
    require(task["seed"] == 3256281284, "SEED_CHANGED")
    require(task["numberResults"] == 1, "RESULT_COUNT_CHANGED")
    require(task["deliveryMethod"] == "async", "ASYNC_DELIVERY_REQUIRED")
    require(task["includeCost"] is True, "COST_RECEIPT_REQUIRED")
    require("resolution" not in task, "RESOLUTION_MUST_BE_OMITTED_WITH_WIDTH_HEIGHT")
    require("negativePrompt" not in task, "UNSUPPORTED_NEGATIVE_PROMPT_ENABLED")
    google = task["providerSettings"]["google"]
    require(google["generateAudio"] is False, "AUDIO_MUST_REMAIN_OFF")
    require(google["personGeneration"] == "dont_allow", "PERSON_GENERATION_CHANGED")

    authorization = json.loads(
        spec.authorization_path.read_text(encoding="utf-8-sig")
    )
    attempts = authorization["attempt_policy"]
    require(attempts["maximum_submission_attempts"] == 1, "ONE_ATTEMPT_REQUIRED")
    require(attempts["automatic_retry"] == "BLOCKED", "AUTO_RETRY_OPENED")
    require(
        attempts["beat_02_execution"] == "BLOCKED_UNTIL_BEAT_01_HUMAN_REVIEW",
        "BEAT_02_OPENED",
    )

    main_window = (
        repo / "src/presentation/desktop/main_window.py"
    ).read_text(encoding="utf-8-sig")
    console_source = (
        repo / "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8-sig")
    core_source = (
        repo / "src/application/runware_execution_v1.py"
    ).read_text(encoding="utf-8-sig")

    for marker in (
        "ProductionConsoleDialog",
        "_open_production_console",
        'label == "الفيديو"',
    ):
        require(marker in main_window, "MAIN_WINDOW_MARKER_MISSING:" + marker)
    for marker in (
        "executeBeat01Button",
        "recoverBeat01Button",
        "saveBeat01ReviewButton",
        "paidExecutionConfirmation",
    ):
        require(marker in console_source, "CONSOLE_MARKER_MISSING:" + marker)
    require("api_key_persisted" in core_source, "KEY_PERSISTENCE_AUDIT_MISSING")
    require(
        '"api_key_persisted": False' in core_source,
        "API_KEY_PERSISTENCE_NOT_FALSE",
    )
    require(
        "SUBMISSION_LOCKED_BEFORE_NETWORK" in core_source,
        "PRE_NETWORK_LOCK_MISSING",
    )
    require(
        "SUBMISSION_ALREADY_LOCKED_USE_RECOVERY" in core_source,
        "DUPLICATE_SUBMISSION_GUARD_MISSING",
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    result = {
        "status": "PASS_SIRAJ_DESKTOP_PRODUCTION_CONSOLE_V1",
        "episode_id": spec.episode_id,
        "shot_id": spec.shot_id,
        "beat_id": spec.beat_id,
        "model": spec.model,
        "duration": spec.duration,
        "dimensions": f"{spec.width}x{spec.height}",
        "maximum_authorised_cost_usd": spec.max_cost_usd,
        "maximum_submission_attempts": 1,
        "automatic_retry": "BLOCKED",
        "beat_02": "BLOCKED",
        "api_key_persisted": False,
        "network_execution_during_publish": False,
        "next_stage": "USER_OPERATED_DESKTOP_BEAT_01_EXECUTION",
    }
    report = args.output_root / "siraj-desktop-production-console-v1-audit.json"
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
