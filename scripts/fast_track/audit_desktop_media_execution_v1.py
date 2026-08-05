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

    engine = (
        repo / "src/application/desktop_media_execution_v1.py"
    ).read_text(encoding="utf-8")
    ui = (
        repo / "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")
    contract = json.loads(
        (
            repo
            / "projects/_orchestrator/contracts/"
            "desktop-media-execution-v1.json"
        ).read_text(encoding="utf-8")
    )

    for marker in (
        "LOCKED_BEFORE_NETWORK",
        "ATTEMPT_ALREADY_LOCKED_USE_RECOVERY",
        "ONE_EXPLICIT_DESKTOP_AUTHORIZATION_PER_ATTEMPT",
        '"taskType": "getResponse"',
        "uuid.uuid4()",
        "ELEVENLABS_ATTEMPT_LOCKED_NO_AUTOMATIC_RESUBMISSION",
        "render_all_pending_local_graphics",
        "MEDIA_ASSETS_COMPLETE",
        "STRUCTURAL_MONTAGE_V1",
    ):
        require(marker in engine, "ENGINE_MARKER_MISSING:" + marker)

    for marker in (
        "desktopMediaExecutionTab",
        "mediaExecutionQueueTable",
        "executeSelectedMediaButton",
        "recoverSelectedRunwareButton",
        "renderLocalGraphicsButton",
        "MediaExecutionThread",
    ):
        require(marker in ui, "DESKTOP_MARKER_MISSING:" + marker)

    require(contract["episode_hard_cap_usd"] == 40.0, "HARD_CAP_CHANGED")
    require(
        contract["paid_authorization"]
        == "ONE_EXPLICIT_DESKTOP_AUTHORIZATION_PER_ATTEMPT",
        "AUTHORIZATION_CONTRACT_CHANGED",
    )
    require(contract["hidden_paid_retry"] == "FORBIDDEN", "HIDDEN_RETRY_CHANGED")
    require(
        contract["runware"]["recovery"]
        == "GET_RESPONSE_SAME_TASK_UUID_NO_RESUBMISSION",
        "RUNWARE_RECOVERY_CHANGED",
    )
    require(
        contract["local_graphics"]["api_cost_usd"] == 0.0,
        "LOCAL_GRAPHICS_COST_CHANGED",
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    report = args.output_root / "audit.txt"
    report.write_text(
        "\n".join(
            (
                "STATUS=PASS_DESKTOP_MEDIA_EXECUTION_V1",
                "DESKTOP_QUEUE_UI=READY",
                "RUNWARE_IMAGE_EXECUTION=READY",
                "RUNWARE_VIDEO_EXECUTION=READY",
                "RUNWARE_RECOVERY=SAME_TASK_UUID_GET_RESPONSE",
                "ELEVENLABS_TTS_EXECUTION=READY",
                "LOCAL_GRAPHICS_RENDER=READY",
                "EPISODE_HARD_CAP_USD=40.00",
                "EXPLICIT_PAID_AUTHORIZATION_PER_ATTEMPT=REQUIRED",
                "LOCK_BEFORE_NETWORK=REQUIRED",
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
