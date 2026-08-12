from __future__ import annotations
import json
from pathlib import Path

FINAL_TTS_CERTIFICATION = (
    "src.application.siraj_generic_final_tts_v6_3_2:"
    "build_or_prepare_final_tts"
)


def certify_generic_final_tts(repo_root: Path) -> Path:
    repo = Path(repo_root).resolve()
    path = (
        repo
        / "projects/_series/"
        "siraj-series-autopilot-backend-certifications-v6.1.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    payload.setdefault("certified", {})["FINAL_TTS"] = (
        FINAL_TTS_CERTIFICATION
    )
    payload["final_tts_episode002_backend"] = (
        "CANONICAL_V5_4_3_PRESERVED"
    )
    payload["final_tts_future_episode_backend"] = (
        "GENERIC_V6_3_2_CERTIFIED"
    )
    payload["future_final_tts_queue_materializer"] = "CERTIFIED"
    payload["automatic_paid_retry"] = False
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
