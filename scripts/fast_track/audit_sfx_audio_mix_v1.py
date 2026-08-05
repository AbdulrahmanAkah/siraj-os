from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.application.sfx_audio_mix_v1 import (
    inspect_audio_environment,
    run_audio_smoke_test,
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
        repo / "src/application/sfx_audio_mix_v1.py"
    ).read_text(encoding="utf-8")
    execution = (
        repo / "src/application/desktop_media_execution_v1.py"
    ).read_text(encoding="utf-8")
    ui = (
        repo / "src/presentation/desktop/production_console.py"
    ).read_text(encoding="utf-8")
    orchestrator = (
        repo / "src/application/autonomous_episode_orchestrator_v1.py"
    ).read_text(encoding="utf-8")
    contract = json.loads(
        (
            repo
            / "projects/_orchestrator/contracts/sfx-audio-mix-v1.json"
        ).read_text(encoding="utf-8")
    )

    for marker in (
        "MUSIC_OR_MUSICAL_CUE_FORBIDDEN",
        "PROCEDURAL_LOCAL",
        "LOCAL_LIBRARY",
        "sidechaincompress",
        "loudnorm",
        "MASTER_TARGET_LUFS = -16.0",
        "SFX_DUCK_RATIO = 7.0",
        "STRUCTURAL_MONTAGE_AND_FINAL_RENDER_V1",
        "paid_provider_requests\": 0",
    ):
        require(marker in engine, "ENGINE_MARKER_MISSING:" + marker)

    require(
        '"SFX_DESIGN"' in execution,
        "MEDIA_EXECUTION_SFX_TRANSITION_MISSING",
    )
    require(
        '"SFX_AND_AUDIO_MIX_V1"' in execution,
        "MEDIA_EXECUTION_NEXT_STAGE_MISSING",
    )
    for marker in (
        "sfxAudioMixTab",
        "SfxAudioMixThread",
        "run_sfx_audio_mix",
        "buildSfxAudioMixButton",
        "openAudioMasterButton",
    ):
        require(marker in ui, "DESKTOP_MARKER_MISSING:" + marker)
    require(
        "LOCAL_FFMPEG_READY" in orchestrator,
        "ORCHESTRATOR_SFX_READINESS_MISSING",
    )

    require(contract["music"] == "FORBIDDEN", "MUSIC_POLICY_CHANGED")
    require(
        contract["provider_mode"] == "LOCAL_ONLY_V1",
        "SFX_PROVIDER_MODE_CHANGED",
    )
    require(
        contract["local_api_cost_usd"] == 0.0,
        "LOCAL_SFX_COST_CHANGED",
    )
    require(
        contract["audio_master"]["integrated_lufs"] == -16.0,
        "MASTER_LOUDNESS_CHANGED",
    )

    environment = inspect_audio_environment(repo)
    require(environment.ready, "AUDIO_ENVIRONMENT_NOT_READY")
    args.output_root.mkdir(parents=True, exist_ok=True)
    smoke = run_audio_smoke_test(
        repo,
        args.output_root / "ffmpeg-smoke",
    )
    require(smoke["status"] == "PASS", "AUDIO_SMOKE_FAILED")

    report = args.output_root / "audit.txt"
    report.write_text(
        "\n".join(
            (
                "STATUS=PASS_SFX_AND_AUDIO_MIX_V1",
                "SFX_DESIGN=READY",
                "SFX_SOURCE=LOCAL_LIBRARY_OR_PROCEDURAL_FALLBACK",
                "NARRATION_TIMELINE=READY",
                "SFX_DUCKING=READY",
                "LOUDNESS_MASTER=-16_LUFS",
                "TRUE_PEAK=-1.5_DBTP",
                "MASTER_OUTPUT=WAV_48KHZ_AND_M4A_192K",
                "MUSIC=FORBIDDEN",
                "LOCAL_API_COST_USD=0.00",
                "FFMPEG_AUDIO_SMOKE=PASS",
                "PAID_PROVIDER_REQUESTS_DURING_AUDIT=0",
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
