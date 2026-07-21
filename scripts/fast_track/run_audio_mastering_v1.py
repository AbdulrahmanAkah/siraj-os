from __future__ import annotations

import json
from pathlib import Path
import sys


REPO = Path(__file__).resolve().parents[2]

PROJECT_ROOT = Path(
    r"C:\SIRAJ\Workspace\first-project"
)

if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


from src.application.local_video_production.audio_mastering_v1 import (
    master_audio,
)


def main() -> int:
    result = master_audio(
        project_root=PROJECT_ROOT,
        input_relative_path=(
            "working/voice-v1/"
            "diagnostic-narration.wav"
        ),
        output_relative_path=(
            "working/voice-v1/"
            "diagnostic-narration-mastered.wav"
        ),
        report_relative_path=(
            "manifests/"
            "diagnostic-voice-v1-mastering-report.json"
        ),
        target_lufs=-19.0,
        true_peak_dbtp=-2.0,
        target_lra=7.0,
    )

    print(
        json.dumps(
            {
                "status": result.status,
                "input": result.input_path,
                "output": result.output_path,
                "report": result.report_path,
                "input_lufs": (
                    result.input_integrated_lufs
                ),
                "output_lufs": (
                    result.output_integrated_lufs
                ),
                "output_true_peak": (
                    result.output_true_peak_dbtp
                ),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    if result.status != "VALID":
        raise RuntimeError(
            "AUDIO_MASTERING_OUTPUT_INVALID"
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())