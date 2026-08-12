"""Pre-spend gate for SIRAJ V4+ narration-first production."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from src.application.siraj_v4_plus_contract_v1 import (
    EpisodeContext,
    require_audio_markers,
    require_narration_bound_shot,
    require_provider_prompt_text_policy,
)

class SirajV4PlusPreflightError(RuntimeError):
    pass

def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise SirajV4PlusPreflightError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise SirajV4PlusPreflightError(f"JSON_OBJECT_REQUIRED:{path}")
    return value

def run_pre_spend_gate(repo_root: Path, context_rel: Path) -> dict[str, Any]:
    repo = repo_root.resolve()
    ctx = EpisodeContext.from_json(repo / context_rel)
    root = repo / ctx.episode_root_rel
    required = {
        "claim_matrix": root / "research/source-claim-matrix-v3.json",
        "script": root / "script/final-script-v3.json",
        "pronunciation": root / "audio/pronunciation-performance-gate-v1.json",
        "tts": root / "audio/final-tts-manifest-v3.json",
        "beats": root / "audio/audio-beat-map-v3.json",
        "storyboard": root / "cinematic/audio-bound-storyboard-v3.json",
        "luna": root / "cinematic/luna-certified-storyboard-v3.json",
        "duplicates": root / "qa/prompt-similarity-duplicate-gate-v1.json",
        "cost": root / "orchestration/cost-preflight-v3.json",
    }
    missing = [key for key, path in required.items() if not path.is_file()]
    if missing:
        raise SirajV4PlusPreflightError(
            "PREFLIGHT_ARTIFACTS_MISSING:" + ",".join(missing)
        )
    claim = _read(required["claim_matrix"])
    pron = _read(required["pronunciation"])
    tts = _read(required["tts"])
    beats = _read(required["beats"])
    story = _read(required["storyboard"])
    luna = _read(required["luna"])
    dup = _read(required["duplicates"])
    cost = _read(required["cost"])

    if str(claim.get("status")) != "PASS":
        raise SirajV4PlusPreflightError("SOURCE_CLAIM_MATRIX_NOT_PASS")
    if str(pron.get("status")) != "PASS":
        raise SirajV4PlusPreflightError("PRONUNCIATION_PERFORMANCE_NOT_PASS")
    if str(tts.get("status")) != "FINAL":
        raise SirajV4PlusPreflightError("FINAL_TTS_REQUIRED")
    require_audio_markers(tts)
    if str(beats.get("source_tts_sha256") or "") != str(tts.get("tts_sha256") or ""):
        raise SirajV4PlusPreflightError("BEAT_MAP_NOT_BOUND_TO_FINAL_TTS")
    if str(story.get("source_tts_sha256") or "") != str(tts.get("tts_sha256") or ""):
        raise SirajV4PlusPreflightError("STORYBOARD_NOT_BOUND_TO_FINAL_TTS")

    shots = story.get("shots")
    if not isinstance(shots, list) or not shots:
        raise SirajV4PlusPreflightError("STORYBOARD_SHOTS_REQUIRED")
    for shot in shots:
        require_narration_bound_shot(shot)

    luna_shots = luna.get("shots")
    if not isinstance(luna_shots, list) or len(luna_shots) != len(shots):
        raise SirajV4PlusPreflightError("LUNA_SHOT_SET_MISMATCH")
    for shot in luna_shots:
        require_narration_bound_shot(shot)
        require_provider_prompt_text_policy(shot)
        if str(shot.get("luna_certification_status") or "") != "PASS":
            raise SirajV4PlusPreflightError(
                f"LUNA_CERTIFICATION_REQUIRED:{shot.get('shot_id')}"
            )

    if str(dup.get("status")) != "PASS":
        raise SirajV4PlusPreflightError("DUPLICATE_GATE_NOT_PASS")
    if str(cost.get("status")) != "PASS":
        raise SirajV4PlusPreflightError("COST_PREFLIGHT_NOT_PASS")
    if cost.get("automatic_paid_retry") is not False:
        raise SirajV4PlusPreflightError("AUTOMATIC_PAID_RETRY_MUST_BE_FALSE")
    if cost.get("explicit_paid_authorization_required") is not True:
        raise SirajV4PlusPreflightError("EXPLICIT_PAID_AUTHORIZATION_GATE_REQUIRED")

    return {
        "status": "PASS",
        "episode_id": ctx.episode_id,
        "generation_id": ctx.generation_id,
        "shot_count": len(shots),
        "final_tts_duration_seconds": tts.get("final_tts_duration_seconds"),
    }
