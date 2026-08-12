"""SIRAJ V4+ audio-first episode pipeline.

This module owns the post-Episode-001 stage order. It does not call any network
provider. It validates artifact dependencies and fails closed if a storyboard,
Luna prompt plan, media queue, or paid authorization is attempted before final
TTS and its exact timing map exist.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.application.siraj_v4_plus_contract_v1 import (
    EpisodeContext,
    PHASE_ORDER,
    require_audio_markers,
    require_narration_bound_shot,
)

STATE_REL = Path("orchestration/v4-plus-episode-state-v1.json")
ARTIFACTS = {
    "SOURCE_RESEARCH_FROM_ZERO": Path("research/source-research-package-v4.json"),
    "SOURCE_CLAIM_MATRIX": Path("research/source-claim-matrix-v3.json"),
    "FINAL_SCRIPT": Path("script/final-script-v3.json"),
    "PRONUNCIATION_AND_PERFORMANCE_GATE": Path(
        "audio/pronunciation-performance-gate-v1.json"
    ),
    "FINAL_TTS": Path("audio/final-tts-manifest-v3.json"),
    "AUDIO_TIMESTAMPS_AND_BEATS": Path("audio/audio-beat-map-v3.json"),
    "AUDIO_BOUND_STORYBOARD": Path("cinematic/audio-bound-storyboard-v3.json"),
    "LUNA_SEMANTIC_PROMPT_DIRECTION": Path(
        "cinematic/luna-certified-storyboard-v3.json"
    ),
    "NARRATION_VISUAL_ALIGNMENT_GATE": Path(
        "qa/narration-visual-alignment-gate-v1.json"
    ),
    "PROMPT_SIMILARITY_AND_DUPLICATE_GATE": Path(
        "qa/prompt-similarity-duplicate-gate-v1.json"
    ),
    "COST_PREFLIGHT_AND_ATTEMPT_LEDGER": Path(
        "orchestration/cost-preflight-v3.json"
    ),
    "EXPLICIT_PAID_AUTHORIZATION": Path(
        "orchestration/paid-authorization-v3.json"
    ),
    "PROVIDER_EXECUTION": Path(
        "orchestration/provider-execution-v3/provider-execution-state-v1.json"
    ),
    "LOCAL_ASSEMBLY_AND_QA": Path("qa/final-local-assembly-qa-v4.json"),
}

class V4PlusEpisodePipelineError(RuntimeError):
    pass

def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        raise V4PlusEpisodePipelineError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise V4PlusEpisodePipelineError(f"JSON_OBJECT_REQUIRED:{path}")
    return value

def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)

def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()

def load_state(repo_root: Path, context_rel: Path) -> tuple[EpisodeContext, Path, dict[str, Any]]:
    repo = repo_root.resolve()
    ctx = EpisodeContext.from_json(repo / context_rel)
    root = repo / ctx.episode_root_rel
    state_path = root / STATE_REL
    if not state_path.is_file():
        raise V4PlusEpisodePipelineError("V4_PLUS_EPISODE_STATE_MISSING")
    state = _read(state_path)
    if str(state.get("episode_id") or "") != ctx.episode_id:
        raise V4PlusEpisodePipelineError("V4_PLUS_STATE_EPISODE_MISMATCH")
    return ctx, root, state

def artifact_for_stage(root: Path, stage: str) -> Path:
    try:
        return root / ARTIFACTS[stage]
    except KeyError as exc:
        raise V4PlusEpisodePipelineError(f"UNKNOWN_STAGE:{stage}") from exc

def _require_status(payload: Mapping[str, Any], allowed: set[str], code: str) -> None:
    status = str(payload.get("status") or "")
    if status not in allowed:
        raise V4PlusEpisodePipelineError(f"{code}:{status}")

def validate_stage_artifact(root: Path, stage: str) -> dict[str, Any]:
    path = artifact_for_stage(root, stage)
    if not path.is_file():
        raise V4PlusEpisodePipelineError(f"STAGE_ARTIFACT_MISSING:{stage}:{path}")
    payload = _read(path)

    if stage == "SOURCE_RESEARCH_FROM_ZERO":
        _require_status(payload, {"PASS"}, "SOURCE_RESEARCH_NOT_PASS")
        if payload.get("old_pre_v4_source_reuse") is not False:
            raise V4PlusEpisodePipelineError("OLD_PRE_V4_SOURCE_REUSE_MUST_BE_FALSE")
        sources = payload.get("sources")
        if not isinstance(sources, list) or not sources:
            raise V4PlusEpisodePipelineError("FRESH_SOURCE_REGISTER_REQUIRED")

    elif stage == "SOURCE_CLAIM_MATRIX":
        _require_status(payload, {"PASS"}, "CLAIM_MATRIX_NOT_PASS")
        claims = payload.get("claims")
        if not isinstance(claims, list) or not claims:
            raise V4PlusEpisodePipelineError("CLAIM_MATRIX_CLAIMS_REQUIRED")
        for claim in claims:
            if not isinstance(claim, Mapping):
                raise V4PlusEpisodePipelineError("CLAIM_MATRIX_CLAIM_INVALID")
            if not str(claim.get("claim_id") or ""):
                raise V4PlusEpisodePipelineError("CLAIM_ID_REQUIRED")
            if not list(claim.get("source_ids") or []):
                raise V4PlusEpisodePipelineError(
                    f"CLAIM_SOURCE_BINDING_REQUIRED:{claim.get('claim_id')}"
                )

    elif stage == "FINAL_SCRIPT":
        _require_status(payload, {"FINAL"}, "FINAL_SCRIPT_NOT_FINAL")
        if payload.get("target_duration_seconds") not in (None, ""):
            raise V4PlusEpisodePipelineError("SCRIPT_FIXED_TARGET_DURATION_FORBIDDEN")
        narration = payload.get("narration_blocks")
        if not isinstance(narration, list) or not narration:
            raise V4PlusEpisodePipelineError("FINAL_SCRIPT_NARRATION_BLOCKS_REQUIRED")
        for block in narration:
            if not str(block.get("text_ar") or "").strip():
                raise V4PlusEpisodePipelineError("NARRATION_TEXT_REQUIRED")

    elif stage == "PRONUNCIATION_AND_PERFORMANCE_GATE":
        _require_status(payload, {"PASS"}, "PRONUNCIATION_GATE_NOT_PASS")
        if payload.get("all_ambiguous_terms_reviewed") is not True:
            raise V4PlusEpisodePipelineError("AMBIGUOUS_PRONUNCIATION_REVIEW_REQUIRED")
        if payload.get("hook_intro_pause_directed") is not True:
            raise V4PlusEpisodePipelineError("HOOK_INTRO_PERFORMANCE_DIRECTION_REQUIRED")
        if payload.get("closing_performance_directed") is not True:
            raise V4PlusEpisodePipelineError("CLOSING_PERFORMANCE_DIRECTION_REQUIRED")
        if payload.get("pre_outro_pause_directed") is not True:
            raise V4PlusEpisodePipelineError("PRE_OUTRO_PERFORMANCE_DIRECTION_REQUIRED")

    elif stage == "FINAL_TTS":
        _require_status(payload, {"FINAL"}, "FINAL_TTS_NOT_FINAL")
        require_audio_markers(payload)
        if not str(payload.get("tts_sha256") or ""):
            raise V4PlusEpisodePipelineError("FINAL_TTS_SHA256_REQUIRED")

    elif stage == "AUDIO_TIMESTAMPS_AND_BEATS":
        _require_status(payload, {"PASS"}, "AUDIO_BEAT_MAP_NOT_PASS")
        tts = _read(root / ARTIFACTS["FINAL_TTS"])
        if str(payload.get("source_tts_sha256") or "") != str(tts.get("tts_sha256") or ""):
            raise V4PlusEpisodePipelineError("AUDIO_BEAT_MAP_TTS_HASH_MISMATCH")
        beats = payload.get("beats")
        if not isinstance(beats, list) or not beats:
            raise V4PlusEpisodePipelineError("AUDIO_BEATS_REQUIRED")
        previous_end = 0.0
        for beat in beats:
            start = float(beat.get("start_seconds") or 0)
            end = float(beat.get("end_seconds") or 0)
            if start < previous_end - 0.001 or end <= start:
                raise V4PlusEpisodePipelineError("AUDIO_BEAT_TIMELINE_INVALID")
            if not str(beat.get("narration_text_ar") or "").strip():
                raise V4PlusEpisodePipelineError("AUDIO_BEAT_NARRATION_TEXT_REQUIRED")
            previous_end = end

    elif stage == "AUDIO_BOUND_STORYBOARD":
        _require_status(payload, {"PASS"}, "AUDIO_BOUND_STORYBOARD_NOT_PASS")
        tts = _read(root / ARTIFACTS["FINAL_TTS"])
        if str(payload.get("source_tts_sha256") or "") != str(tts.get("tts_sha256") or ""):
            raise V4PlusEpisodePipelineError("STORYBOARD_TTS_HASH_MISMATCH")
        shots = payload.get("shots")
        if not isinstance(shots, list) or not shots:
            raise V4PlusEpisodePipelineError("STORYBOARD_SHOTS_REQUIRED")
        for shot in shots:
            require_narration_bound_shot(shot)

    elif stage == "LUNA_SEMANTIC_PROMPT_DIRECTION":
        _require_status(payload, {"PASS"}, "LUNA_STORYBOARD_NOT_PASS")
        source = _read(root / ARTIFACTS["AUDIO_BOUND_STORYBOARD"])
        if str(payload.get("source_storyboard_sha256") or "") != _file_sha256(
            root / ARTIFACTS["AUDIO_BOUND_STORYBOARD"]
        ):
            raise V4PlusEpisodePipelineError("LUNA_SOURCE_STORYBOARD_HASH_MISMATCH")
        shots = payload.get("shots")
        if not isinstance(shots, list) or len(shots) != len(source.get("shots") or []):
            raise V4PlusEpisodePipelineError("LUNA_SHOT_SET_MISMATCH")
        for shot in shots:
            require_narration_bound_shot(shot)
            if str(shot.get("luna_certification_status") or "") != "PASS":
                raise V4PlusEpisodePipelineError(
                    f"LUNA_CERTIFICATION_REQUIRED:{shot.get('shot_id')}"
                )

    elif stage == "NARRATION_VISUAL_ALIGNMENT_GATE":
        _require_status(payload, {"PASS"}, "NARRATION_VISUAL_ALIGNMENT_NOT_PASS")
        if int(payload.get("blocking_issue_count") or 0) != 0:
            raise V4PlusEpisodePipelineError("NARRATION_VISUAL_ALIGNMENT_BLOCKED")

    elif stage == "PROMPT_SIMILARITY_AND_DUPLICATE_GATE":
        _require_status(payload, {"PASS"}, "DUPLICATE_GATE_NOT_PASS")
        if int(payload.get("blocking_duplicate_count") or 0) != 0:
            raise V4PlusEpisodePipelineError("PROMPT_OR_PERCEPTUAL_DUPLICATES_BLOCKING")

    elif stage == "COST_PREFLIGHT_AND_ATTEMPT_LEDGER":
        _require_status(payload, {"PASS"}, "COST_PREFLIGHT_NOT_PASS")
        if payload.get("automatic_paid_retry") is not False:
            raise V4PlusEpisodePipelineError("AUTOMATIC_PAID_RETRY_MUST_BE_FALSE")
        if payload.get("explicit_paid_authorization_required") is not True:
            raise V4PlusEpisodePipelineError("EXPLICIT_PAID_AUTHORIZATION_REQUIRED")

    elif stage == "EXPLICIT_PAID_AUTHORIZATION":
        _require_status(payload, {"ACTIVE"}, "PAID_AUTHORIZATION_NOT_ACTIVE")
        if payload.get("automatic_paid_retry") is not False:
            raise V4PlusEpisodePipelineError("PAID_AUTH_AUTOMATIC_RETRY_FORBIDDEN")

    return payload

def validate_prerequisites(repo_root: Path, context_rel: Path, target_stage: str) -> dict[str, Any]:
    ctx, root, state = load_state(repo_root, context_rel)
    if target_stage not in PHASE_ORDER:
        raise V4PlusEpisodePipelineError(f"UNKNOWN_TARGET_STAGE:{target_stage}")
    target_index = PHASE_ORDER.index(target_stage)
    passed = []
    for stage in PHASE_ORDER[:target_index]:
        validate_stage_artifact(root, stage)
        passed.append(stage)
    return {
        "status": "PASS",
        "episode_id": ctx.episode_id,
        "generation_id": ctx.generation_id,
        "target_stage": target_stage,
        "validated_prerequisites": passed,
        "current_stage": state.get("current_stage"),
    }

def mark_stage_complete(repo_root: Path, context_rel: Path, stage: str) -> dict[str, Any]:
    ctx, root, state = load_state(repo_root, context_rel)
    expected = str(state.get("current_stage") or "")
    if stage != expected:
        raise V4PlusEpisodePipelineError(
            f"STAGE_ORDER_VIOLATION:expected={expected}:received={stage}"
        )
    validate_prerequisites(repo_root, context_rel, stage)
    validate_stage_artifact(root, stage)
    completed = list(state.get("completed_stages") or [])
    if stage not in completed:
        completed.append(stage)
    index = PHASE_ORDER.index(stage)
    next_stage = PHASE_ORDER[index + 1] if index + 1 < len(PHASE_ORDER) else None
    state.update({
        "status": "COMPLETE" if next_stage is None else "ACTIVE",
        "completed_stages": completed,
        "current_stage": next_stage,
        "next_stage": next_stage,
        "updated_at_utc": _now(),
    })
    _write(root / STATE_REL, state)
    return state
