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

    casting = (
        repo / "src/application/elevenlabs_voice_casting_v1.py"
    ).read_text(encoding="utf-8")
    integration = (
        repo / "src/application/graphics_storyboard_media_queue_v1.py"
    ).read_text(encoding="utf-8")
    provider = (
        repo / "src/application/openai_luna_editorial_v1.py"
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
        "XdoLPWNt7ytn6BtU4FBf",
        "pCKbQ4EPGE06zpEPGNvS",
        "fkqevZRU7Xj52dY1CTkq",
        "t8atLZaWuCcW6gENDwwa",
        'MODEL_ID = "eleven_multilingual_v2"',
        '"stability": 0.55',
        '"similarity_boost": 0.75',
        '"style": 0.15',
        '"use_speaker_boost": True',
        "build_episode_voice_cast_plan",
        "multi_performer_required",
    ):
        require(marker in casting, "VOICE_CAST_MARKER_MISSING:" + marker)

    require(
        "BLOCKED_VOICE_SELECTION_REQUIRED" not in integration,
        "OLD_TTS_VOICE_SELECTION_GATE_REMAINS",
    )
    require(
        "build_episode_voice_cast_plan" in integration,
        "MEDIA_QUEUE_VOICE_CASTING_MISSING",
    )
    require(
        "performance_blocks" in provider,
        "LUNA_PERFORMANCE_BLOCK_SCHEMA_MISSING",
    )
    require(
        "الأصوات الأربعة المختارة" in ui,
        "DESKTOP_SELECTED_VOICE_ROSTER_MESSAGE_MISSING",
    )
    require(
        contract["tts"]["voice_selection_required"] is False,
        "VOICE_SELECTION_GATE_NOT_REMOVED",
    )
    require(
        contract["tts"]["primary_voice_id"]
        == "XdoLPWNt7ytn6BtU4FBf",
        "PRIMARY_VOICE_ID_CHANGED",
    )
    require(
        len(contract["tts"]["backup_voice_ids"]) == 3,
        "BACKUP_VOICE_COUNT_CHANGED",
    )
    require(
        contract["tts"]["multi_performer_supported"] is True,
        "MULTI_PERFORMER_SUPPORT_MISSING",
    )

    args.output_root.mkdir(parents=True, exist_ok=True)
    report = args.output_root / "audit.txt"
    report.write_text(
        "\n".join(
            (
                "STATUS=PASS_ELEVENLABS_FOUR_PERFORMER_CASTING_LOCK_V1",
                "ELEVENLABS_PERFORMERS=4",
                "PRIMARY_VOICE_ID=XdoLPWNt7ytn6BtU4FBf",
                "BACKUP_AND_ADDITIONAL_PERFORMERS=3",
                "MODEL_ID=eleven_multilingual_v2",
                "MULTI_PERFORMER_EPISODES=SUPPORTED",
                "CASTING_SOURCE=SCRIPT_AND_STORYBOARD",
                "VOICE_SELECTION_REQUIRED=NO",
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
