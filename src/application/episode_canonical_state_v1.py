from __future__ import annotations

import argparse
import hashlib
import json
import os
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "siraj-canonical-episode-state-v1"

LEGACY_PROFILE = "LEGACY_PROVIDER_VISUAL_V1"
MANUAL_VISUAL_PROFILE = "CANONICAL_NEXT_EPISODE_MANUAL_VISUAL_V1"

CONSTITUTION_ID = "SIRAJ_UNIFIED_PRODUCTION_CONSTITUTION"
CONSTITUTION_VERSION = "1.2.0"
CONSTITUTION_SHA256 = "b390d8a61382ece4e8daeb5993fc89bb013a9b74cd8d06b2fb6e41f0b7d001d5"


class EpisodeStage(str, Enum):
    EPISODE_CREATED = "EPISODE_CREATED"
    RESEARCH_LOCKED = "RESEARCH_LOCKED"
    SCRIPT_LOCKED = "SCRIPT_LOCKED"
    AUDIO_LOCKED = "AUDIO_LOCKED"
    STORYBOARD_READY = "STORYBOARD_READY"
    PRE_GENERATION_REVIEW = "PRE_GENERATION_REVIEW"
    PRE_GENERATION_APPROVED = "PRE_GENERATION_APPROVED"
    GENERATION_IN_PROGRESS = "GENERATION_IN_PROGRESS"
    VISUALS_APPROVED = "VISUALS_APPROVED"
    ASSEMBLY = "ASSEMBLY"
    FINAL_REVIEW = "FINAL_REVIEW"
    FINAL_APPROVED = "FINAL_APPROVED"
    SHORTS_APPROVED = "SHORTS_APPROVED"
    ARCHIVED = "ARCHIVED"


class ManualVisualEpisodeStage(str, Enum):
    EPISODE_CREATE = "EPISODE_CREATE"
    RESEARCH = "RESEARCH"
    SOURCE_LOCK = "SOURCE_LOCK"
    TITLE_LOCK = "TITLE_LOCK"
    STORY_ARCHITECTURE = "STORY_ARCHITECTURE"
    SCRIPT = "SCRIPT"
    SCRIPT_QA = "SCRIPT_QA"
    NARRATION = "NARRATION"
    WORD_LEVEL_TIMING = "WORD_LEVEL_TIMING"
    STORYBOARD = "STORYBOARD"
    VISUAL_REQUIREMENT_CONTRACTS = "VISUAL_REQUIREMENT_CONTRACTS"
    COVERAGE_DIVERSITY_REUSE_VALIDATION = "COVERAGE_DIVERSITY_REUSE_VALIDATION"
    HUMAN_PRE_VISUAL_APPROVAL = "HUMAN_PRE_VISUAL_APPROVAL"
    MANUAL_VISUAL_HANDOFF_READY = "MANUAL_VISUAL_HANDOFF_READY"
    MANUAL_VISUAL_INGEST = "MANUAL_VISUAL_INGEST"
    ASSET_VALIDATION = "ASSET_VALIDATION"
    SHA_BOUND_VISUAL_LOCK = "SHA_BOUND_VISUAL_LOCK"
    AUTOMATED_ASSEMBLY = "AUTOMATED_ASSEMBLY"
    MONTAGE = "MONTAGE"
    AUDIO_SYNC = "AUDIO_SYNC"
    TECHNICAL_QA = "TECHNICAL_QA"
    CONSTITUTION_QA = "CONSTITUTION_QA"
    EDITORIAL_QA = "EDITORIAL_QA"
    HUMAN_FINAL_REVIEW = "HUMAN_FINAL_REVIEW"
    MASTER = "MASTER"
    SHORTS_DERIVATIVE = "SHORTS_DERIVATIVE"
    ARCHIVE = "ARCHIVE"


STAGE_ORDER = [stage.value for stage in EpisodeStage]
STAGE_INDEX = {stage: i for i, stage in enumerate(STAGE_ORDER)}
MANUAL_VISUAL_STAGE_ORDER = [stage.value for stage in ManualVisualEpisodeStage]

# One canonical slot per authority/artifact class.
# Other files may exist on disk, but they are not authoritative unless bound here.
ALLOWED_SLOTS = {
    "research",
    "sources_lock",
    "script",
    "narration",
    "audio",
    "timing",
    "storyboard",
    "references_manifest",
    "pre_generation_review",
    "pre_generation_approval",
    "generation_ledger",
    "renders_manifest",
    "visuals_approval",
    "montage",
    "final_master",
    "final_approval",
    "shorts_manifest",
    "shorts_approval",
    "archive_receipt",
}

# A slot may be revised freely before the stage that freezes it.
# At/after that stage, different bytes require explicit invalidation first.
SLOT_LOCK_STAGE = {
    "research": EpisodeStage.RESEARCH_LOCKED.value,
    "sources_lock": EpisodeStage.RESEARCH_LOCKED.value,
    "script": EpisodeStage.SCRIPT_LOCKED.value,
    "narration": EpisodeStage.AUDIO_LOCKED.value,
    "audio": EpisodeStage.AUDIO_LOCKED.value,
    "timing": EpisodeStage.AUDIO_LOCKED.value,
    "storyboard": EpisodeStage.STORYBOARD_READY.value,
    "references_manifest": EpisodeStage.PRE_GENERATION_REVIEW.value,
    "pre_generation_review": EpisodeStage.PRE_GENERATION_REVIEW.value,
    "pre_generation_approval": EpisodeStage.PRE_GENERATION_APPROVED.value,
    "generation_ledger": EpisodeStage.GENERATION_IN_PROGRESS.value,
    "renders_manifest": EpisodeStage.VISUALS_APPROVED.value,
    "visuals_approval": EpisodeStage.VISUALS_APPROVED.value,
    "montage": EpisodeStage.FINAL_REVIEW.value,
    "final_master": EpisodeStage.FINAL_REVIEW.value,
    "final_approval": EpisodeStage.FINAL_APPROVED.value,
    "shorts_manifest": EpisodeStage.SHORTS_APPROVED.value,
    "shorts_approval": EpisodeStage.SHORTS_APPROVED.value,
    "archive_receipt": EpisodeStage.ARCHIVED.value,
}

TRANSITION_REQUIREMENTS = {
    EpisodeStage.RESEARCH_LOCKED.value: {"research", "sources_lock"},
    EpisodeStage.SCRIPT_LOCKED.value: {"script"},
    EpisodeStage.AUDIO_LOCKED.value: {"narration", "audio", "timing"},
    EpisodeStage.STORYBOARD_READY.value: {"storyboard"},
    EpisodeStage.PRE_GENERATION_REVIEW.value: {"pre_generation_review"},
    EpisodeStage.PRE_GENERATION_APPROVED.value: {"pre_generation_approval"},
    EpisodeStage.GENERATION_IN_PROGRESS.value: {"generation_ledger"},
    EpisodeStage.VISUALS_APPROVED.value: {"renders_manifest", "visuals_approval"},
    EpisodeStage.ASSEMBLY.value: set(),
    EpisodeStage.FINAL_REVIEW.value: {"montage", "final_master"},
    EpisodeStage.FINAL_APPROVED.value: {"final_approval"},
    EpisodeStage.SHORTS_APPROVED.value: {"shorts_manifest", "shorts_approval"},
    EpisodeStage.ARCHIVED.value: {"archive_receipt"},
}

APPROVAL_SLOTS = {
    "pre_generation_approval",
    "visuals_approval",
    "final_approval",
    "shorts_approval",
}

MANUAL_VISUAL_ALLOWED_SLOTS = {
    "episode_manifest",
    "research",
    "source_registry",
    "claim_matrix",
    "sources_lock",
    "title_lock",
    "story_architecture",
    "script",
    "script_qa",
    "narration",
    "audio",
    "timing",
    "audio_timing_receipt",
    "storyboard",
    "visual_contracts",
    "coverage_validation",
    "pre_visual_approval",
    "manual_visual_pack",
    "manual_asset_ledger",
    "visual_lock",
    "assembly_plan",
    "montage",
    "assembly_candidate",
    "technical_qa",
    "constitution_qa",
    "editorial_qa",
    "final_review_approval",
    "final_master",
    "master_receipt",
    "shorts_manifest",
    "archive_receipt",
}

MANUAL_VISUAL_SLOT_LOCK_STAGE = {
    "episode_manifest": "EPISODE_CREATE",
    "research": "RESEARCH",
    "source_registry": "SOURCE_LOCK",
    "claim_matrix": "SOURCE_LOCK",
    "sources_lock": "SOURCE_LOCK",
    "title_lock": "TITLE_LOCK",
    "story_architecture": "STORY_ARCHITECTURE",
    "script": "SCRIPT",
    "script_qa": "SCRIPT_QA",
    "narration": "NARRATION",
    "audio": "WORD_LEVEL_TIMING",
    "timing": "WORD_LEVEL_TIMING",
    "audio_timing_receipt": "WORD_LEVEL_TIMING",
    "storyboard": "STORYBOARD",
    "visual_contracts": "VISUAL_REQUIREMENT_CONTRACTS",
    "coverage_validation": "COVERAGE_DIVERSITY_REUSE_VALIDATION",
    "pre_visual_approval": "HUMAN_PRE_VISUAL_APPROVAL",
    "manual_visual_pack": "MANUAL_VISUAL_HANDOFF_READY",
    "manual_asset_ledger": "ASSET_VALIDATION",
    "visual_lock": "SHA_BOUND_VISUAL_LOCK",
    "assembly_plan": "AUTOMATED_ASSEMBLY",
    "montage": "MONTAGE",
    "assembly_candidate": "AUDIO_SYNC",
    "technical_qa": "TECHNICAL_QA",
    "constitution_qa": "CONSTITUTION_QA",
    "editorial_qa": "EDITORIAL_QA",
    "final_review_approval": "HUMAN_FINAL_REVIEW",
    "final_master": "MASTER",
    "master_receipt": "MASTER",
    "shorts_manifest": "SHORTS_DERIVATIVE",
    "archive_receipt": "ARCHIVE",
}

MANUAL_VISUAL_TRANSITION_REQUIREMENTS = {
    "RESEARCH": {"episode_manifest", "research"},
    "SOURCE_LOCK": {"source_registry", "claim_matrix", "sources_lock"},
    "TITLE_LOCK": {"title_lock"},
    "STORY_ARCHITECTURE": {"story_architecture"},
    "SCRIPT": {"script"},
    "SCRIPT_QA": {"script_qa"},
    "NARRATION": {"narration"},
    "WORD_LEVEL_TIMING": {"audio", "timing", "audio_timing_receipt"},
    "STORYBOARD": {"storyboard"},
    "VISUAL_REQUIREMENT_CONTRACTS": {"visual_contracts"},
    "COVERAGE_DIVERSITY_REUSE_VALIDATION": {"coverage_validation"},
    "HUMAN_PRE_VISUAL_APPROVAL": {"pre_visual_approval"},
    "MANUAL_VISUAL_HANDOFF_READY": {"manual_visual_pack"},
    "MANUAL_VISUAL_INGEST": set(),
    "ASSET_VALIDATION": {"manual_asset_ledger"},
    "SHA_BOUND_VISUAL_LOCK": {"visual_lock"},
    "AUTOMATED_ASSEMBLY": {"assembly_plan"},
    "MONTAGE": {"montage"},
    "AUDIO_SYNC": {"assembly_candidate"},
    "TECHNICAL_QA": {"technical_qa"},
    "CONSTITUTION_QA": {"constitution_qa"},
    "EDITORIAL_QA": {"editorial_qa"},
    "HUMAN_FINAL_REVIEW": {"final_review_approval"},
    "MASTER": {"final_master", "master_receipt"},
    "SHORTS_DERIVATIVE": {"shorts_manifest"},
    "ARCHIVE": {"archive_receipt"},
}

MANUAL_VISUAL_APPROVAL_SLOTS = {
    "title_lock",
    "pre_visual_approval",
    "visual_lock",
    "final_review_approval",
}


class CanonicalStateError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    temp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def _event(kind: str, **details: Any) -> dict[str, Any]:
    return {"at": utc_now(), "kind": kind, **details}


def _profile(state: dict[str, Any]) -> str:
    return str(state.get("profile") or LEGACY_PROFILE)


def _stage_order(state: dict[str, Any]) -> list[str]:
    return MANUAL_VISUAL_STAGE_ORDER if _profile(state) == MANUAL_VISUAL_PROFILE else STAGE_ORDER


def _stage_index(state: dict[str, Any]) -> dict[str, int]:
    return {stage: index for index, stage in enumerate(_stage_order(state))}


def _allowed_slots(state: dict[str, Any]) -> set[str]:
    return MANUAL_VISUAL_ALLOWED_SLOTS if _profile(state) == MANUAL_VISUAL_PROFILE else ALLOWED_SLOTS


def _slot_lock_stages(state: dict[str, Any]) -> dict[str, str]:
    return MANUAL_VISUAL_SLOT_LOCK_STAGE if _profile(state) == MANUAL_VISUAL_PROFILE else SLOT_LOCK_STAGE


def _transition_requirements(state: dict[str, Any]) -> dict[str, set[str]]:
    return MANUAL_VISUAL_TRANSITION_REQUIREMENTS if _profile(state) == MANUAL_VISUAL_PROFILE else TRANSITION_REQUIREMENTS


def _approval_slots(state: dict[str, Any]) -> set[str]:
    return MANUAL_VISUAL_APPROVAL_SLOTS if _profile(state) == MANUAL_VISUAL_PROFILE else APPROVAL_SLOTS


def new_state(episode_id: str, *, profile: str = LEGACY_PROFILE) -> dict[str, Any]:
    if profile not in {LEGACY_PROFILE, MANUAL_VISUAL_PROFILE}:
        raise CanonicalStateError("UNKNOWN_EPISODE_PROFILE:" + profile)
    now = utc_now()
    initial_stage = (
        ManualVisualEpisodeStage.EPISODE_CREATE.value
        if profile == MANUAL_VISUAL_PROFILE
        else EpisodeStage.EPISODE_CREATED.value
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "episode_id": episode_id,
        "profile": profile,
        "visual_mode": (
            "MANUAL_USER_PRODUCTION"
            if profile == MANUAL_VISUAL_PROFILE
            else "LEGACY_COMPATIBILITY"
        ),
        "automatic_visual_generation": False if profile == MANUAL_VISUAL_PROFILE else None,
        "provider_visual_fallback": False if profile == MANUAL_VISUAL_PROFILE else None,
        "stage": initial_stage,
        "revision": 1,
        "blocked": False,
        "blockers": [],
        "constitution": {
            "id": CONSTITUTION_ID,
            "version": CONSTITUTION_VERSION,
            "bundle_manifest_sha256": CONSTITUTION_SHA256,
        },
        "artifacts": {},
        "created_at": now,
        "updated_at": now,
        "history": [
            {
                "at": now,
                "kind": "EPISODE_INITIALIZED",
                "stage": initial_stage,
                "profile": profile,
            }
        ],
    }


def validate_state(state: dict[str, Any]) -> None:
    if state.get("schema_version") != SCHEMA_VERSION:
        raise CanonicalStateError("SCHEMA_VERSION_MISMATCH")
    if not state.get("episode_id"):
        raise CanonicalStateError("EPISODE_ID_MISSING")
    profile = _profile(state)
    if profile not in {LEGACY_PROFILE, MANUAL_VISUAL_PROFILE}:
        raise CanonicalStateError("UNKNOWN_EPISODE_PROFILE:" + profile)
    if profile == MANUAL_VISUAL_PROFILE:
        if state.get("visual_mode") != "MANUAL_USER_PRODUCTION":
            raise CanonicalStateError("MANUAL_VISUAL_MODE_REQUIRED")
        if state.get("automatic_visual_generation") is not False:
            raise CanonicalStateError("AUTOMATIC_VISUAL_GENERATION_MUST_BE_DISABLED")
        if state.get("provider_visual_fallback") is not False:
            raise CanonicalStateError("PROVIDER_VISUAL_FALLBACK_MUST_BE_DISABLED")
    stage_index = _stage_index(state)
    stage = state.get("stage")
    if stage not in stage_index:
        raise CanonicalStateError(f"INVALID_STAGE:{stage}")
    if not isinstance(state.get("revision"), int) or state["revision"] < 1:
        raise CanonicalStateError("INVALID_REVISION")
    constitution = state.get("constitution") or {}
    expected = (CONSTITUTION_ID, CONSTITUTION_VERSION, CONSTITUTION_SHA256)
    actual = (
        constitution.get("id"),
        constitution.get("version"),
        constitution.get("bundle_manifest_sha256"),
    )
    if actual != expected:
        raise CanonicalStateError("CONSTITUTION_BINDING_MISMATCH")
    artifacts = state.get("artifacts")
    if not isinstance(artifacts, dict):
        raise CanonicalStateError("ARTIFACTS_NOT_OBJECT")
    unknown = sorted(set(artifacts) - _allowed_slots(state))
    if unknown:
        raise CanonicalStateError("UNKNOWN_ARTIFACT_SLOTS:" + ",".join(unknown))
    for slot, record in artifacts.items():
        if not isinstance(record, dict):
            raise CanonicalStateError(f"INVALID_ARTIFACT_RECORD:{slot}")
        if not record.get("path") or not record.get("sha256"):
            raise CanonicalStateError(f"INCOMPLETE_ARTIFACT_RECORD:{slot}")
        digest = str(record["sha256"])
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest.lower()):
            raise CanonicalStateError(f"INVALID_ARTIFACT_SHA256:{slot}")
    if bool(state.get("blocked")) != bool(state.get("blockers")):
        raise CanonicalStateError("BLOCKED_FLAG_INCONSISTENT")


def load_state(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise CanonicalStateError("CANONICAL_STATE_MISSING:" + str(path))
    state = json.loads(path.read_text(encoding="utf-8-sig"))
    validate_state(state)
    return state


def initialize(
    path: Path,
    episode_id: str,
    *,
    profile: str = LEGACY_PROFILE,
) -> dict[str, Any]:
    if path.exists():
        state = load_state(path)
        if state["episode_id"] != episode_id:
            raise CanonicalStateError("EXISTING_STATE_EPISODE_ID_MISMATCH")
        if _profile(state) != profile:
            raise CanonicalStateError("EXISTING_STATE_PROFILE_MISMATCH")
        return state
    state = new_state(episode_id, profile=profile)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            json.dump(state, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
    except FileExistsError:
        return initialize(path, episode_id, profile=profile)
    return state


def _save_next(path: Path, state: dict[str, Any], event: dict[str, Any]) -> dict[str, Any]:
    lock = path.with_name(path.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    try:
        descriptor = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise CanonicalStateError("CANONICAL_STATE_CONCURRENT_WRITE") from exc
    try:
        os.write(descriptor, f"pid={os.getpid()}\n".encode("ascii"))
        os.close(descriptor)
        current = load_state(path)
        if current["revision"] != state["revision"]:
            raise CanonicalStateError("CANONICAL_STATE_REVISION_CONFLICT")
        next_state = deepcopy(state)
        next_state["revision"] = int(state["revision"]) + 1
        next_state["updated_at"] = utc_now()
        next_state.setdefault("history", []).append(event)
        validate_state(next_state)
        atomic_write_json(path, next_state)
        return next_state
    finally:
        try:
            os.close(descriptor)
        except OSError:
            pass
        lock.unlink(missing_ok=True)


def bind_artifact(
    state_path: Path,
    slot: str,
    artifact_path: Path,
    *,
    status: str = "BOUND",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not artifact_path.is_file():
        raise CanonicalStateError("ARTIFACT_MISSING:" + str(artifact_path))
    state = load_state(state_path)
    if slot not in _allowed_slots(state):
        raise CanonicalStateError("UNKNOWN_ARTIFACT_SLOT:" + slot)
    digest = sha256_file(artifact_path)
    existing = state["artifacts"].get(slot)
    stage_index = _stage_index(state)
    lock_stage = _slot_lock_stages(state)[slot]
    locked_now = stage_index[state["stage"]] >= stage_index[lock_stage]

    if existing and existing["sha256"] == digest:
        return state

    if existing and existing["sha256"] != digest and locked_now:
        raise CanonicalStateError(
            "ARTIFACT_REPLACEMENT_REQUIRES_INVALIDATION:"
            f"{slot}:locked_at={lock_stage}:current={state['stage']}"
        )

    next_state = deepcopy(state)
    next_state["artifacts"][slot] = {
        "path": str(artifact_path.resolve()),
        "sha256": digest,
        "status": status,
        "bound_at_stage": state["stage"],
        "bound_at": utc_now(),
        "metadata": metadata or {},
    }
    if slot in _approval_slots(state) and status != "APPROVED":
        raise CanonicalStateError(f"APPROVAL_SLOT_REQUIRES_APPROVED_STATUS:{slot}")
    return _save_next(
        state_path,
        next_state,
        _event(
            "ARTIFACT_BOUND",
            slot=slot,
            path=str(artifact_path.resolve()),
            sha256=digest,
            status=status,
            replaced_sha256=existing["sha256"] if existing else None,
        ),
    )


def mark_blocked(state_path: Path, code: str, detail: str) -> dict[str, Any]:
    state = load_state(state_path)
    next_state = deepcopy(state)
    blockers = [b for b in next_state["blockers"] if b.get("code") != code]
    blockers.append({"code": code, "detail": detail, "at": utc_now()})
    next_state["blockers"] = blockers
    next_state["blocked"] = True
    return _save_next(
        state_path,
        next_state,
        _event("BLOCKER_ADDED", code=code, detail=detail),
    )


def clear_blocker(state_path: Path, code: str) -> dict[str, Any]:
    state = load_state(state_path)
    next_state = deepcopy(state)
    before = len(next_state["blockers"])
    next_state["blockers"] = [b for b in next_state["blockers"] if b.get("code") != code]
    if len(next_state["blockers"]) == before:
        return state
    next_state["blocked"] = bool(next_state["blockers"])
    return _save_next(
        state_path,
        next_state,
        _event("BLOCKER_CLEARED", code=code),
    )


def transition(state_path: Path, target_stage: str) -> dict[str, Any]:
    state = load_state(state_path)
    stage_index = _stage_index(state)
    if target_stage not in stage_index:
        raise CanonicalStateError("INVALID_TARGET_STAGE:" + target_stage)
    if target_stage == state["stage"]:
        return state
    current_i = stage_index[state["stage"]]
    target_i = stage_index[target_stage]
    if target_i != current_i + 1:
        raise CanonicalStateError(
            f"NON_SEQUENTIAL_TRANSITION:{state['stage']}->{target_stage}"
        )
    if state["blocked"]:
        codes = ",".join(b["code"] for b in state["blockers"])
        raise CanonicalStateError("TRANSITION_BLOCKED:" + codes)
    required = _transition_requirements(state).get(target_stage, set())
    missing = sorted(required - set(state["artifacts"]))
    if missing:
        raise CanonicalStateError(
            f"MISSING_REQUIRED_ARTIFACTS_FOR_{target_stage}:" + ",".join(missing)
        )
    # Every already-bound authority must still resolve to the exact bytes that
    # were accepted. A transition may not advance around a stale upstream file.
    for slot in sorted(state["artifacts"]):
        assert_canonical_bytes(state_path, slot)
    next_state = deepcopy(state)
    next_state["stage"] = target_stage
    return _save_next(
        state_path,
        next_state,
        _event(
            "STAGE_TRANSITION",
            from_stage=state["stage"],
            to_stage=target_stage,
        ),
    )


def invalidate_to(state_path: Path, target_stage: str, reason: str) -> dict[str, Any]:
    state = load_state(state_path)
    stage_index = _stage_index(state)
    if target_stage not in stage_index:
        raise CanonicalStateError("INVALID_INVALIDATION_TARGET:" + target_stage)
    if stage_index[target_stage] >= stage_index[state["stage"]]:
        raise CanonicalStateError(
            f"INVALIDATION_MUST_MOVE_BACKWARD:{state['stage']}->{target_stage}"
        )

    next_state = deepcopy(state)
    removed: dict[str, str] = {}
    # Remove any artifact whose freeze/authority point lies after the target.
    # Artifacts frozen at or before the target remain canonical.
    for slot in list(next_state["artifacts"]):
        lock_stage = _slot_lock_stages(state)[slot]
        if stage_index[lock_stage] > stage_index[target_stage]:
            removed[slot] = next_state["artifacts"][slot]["sha256"]
            del next_state["artifacts"][slot]

    next_state["stage"] = target_stage
    next_state["blocked"] = False
    next_state["blockers"] = []
    return _save_next(
        state_path,
        next_state,
        _event(
            "STATE_INVALIDATED",
            from_stage=state["stage"],
            to_stage=target_stage,
            reason=reason,
            removed_artifacts=removed,
        ),
    )


def canonical_artifact(state_path: Path, slot: str) -> dict[str, Any]:
    state = load_state(state_path)
    if slot not in state["artifacts"]:
        raise CanonicalStateError("CANONICAL_ARTIFACT_NOT_BOUND:" + slot)
    return deepcopy(state["artifacts"][slot])


def assert_canonical_bytes(state_path: Path, slot: str) -> None:
    record = canonical_artifact(state_path, slot)
    path = Path(record["path"])
    if not path.is_file():
        raise CanonicalStateError("CANONICAL_ARTIFACT_BYTES_MISSING:" + slot)
    actual = sha256_file(path)
    if actual != record["sha256"]:
        raise CanonicalStateError(
            f"CANONICAL_ARTIFACT_SHA_MISMATCH:{slot}:{actual}:expected={record['sha256']}"
        )


def summary(state: dict[str, Any]) -> str:
    lines = [
        f"EPISODE_ID={state['episode_id']}",
        f"PROFILE={_profile(state)}",
        f"VISUAL_MODE={state.get('visual_mode', 'LEGACY_COMPATIBILITY')}",
        f"STAGE={state['stage']}",
        f"REVISION={state['revision']}",
        f"BLOCKED={str(state['blocked']).upper()}",
        "CANONICAL_SLOTS=" + ",".join(sorted(state["artifacts"])) if state["artifacts"] else "CANONICAL_SLOTS=",
    ]
    if state["blockers"]:
        lines.append("BLOCKERS=" + ",".join(b["code"] for b in state["blockers"]))
    return "\n".join(lines)


def _json_metadata(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise CanonicalStateError("METADATA_MUST_BE_JSON_OBJECT")
    return value


def cli() -> int:
    p = argparse.ArgumentParser(description="SIRAJ canonical episode state v1")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_init = sub.add_parser("init")
    p_init.add_argument("--state", required=True)
    p_init.add_argument("--episode-id", required=True)
    p_init.add_argument(
        "--profile",
        choices=(LEGACY_PROFILE, MANUAL_VISUAL_PROFILE),
        default=LEGACY_PROFILE,
    )

    p_show = sub.add_parser("show")
    p_show.add_argument("--state", required=True)

    p_bind = sub.add_parser("bind")
    p_bind.add_argument("--state", required=True)
    p_bind.add_argument("--slot", required=True)
    p_bind.add_argument("--file", required=True)
    p_bind.add_argument("--status", default="BOUND")
    p_bind.add_argument("--metadata-json")

    p_transition = sub.add_parser("transition")
    p_transition.add_argument("--state", required=True)
    p_transition.add_argument("--to", required=True)

    p_invalidate = sub.add_parser("invalidate")
    p_invalidate.add_argument("--state", required=True)
    p_invalidate.add_argument("--to", required=True)
    p_invalidate.add_argument("--reason", required=True)

    p_block = sub.add_parser("block")
    p_block.add_argument("--state", required=True)
    p_block.add_argument("--code", required=True)
    p_block.add_argument("--detail", required=True)

    p_unblock = sub.add_parser("unblock")
    p_unblock.add_argument("--state", required=True)
    p_unblock.add_argument("--code", required=True)

    p_assert = sub.add_parser("assert")
    p_assert.add_argument("--state", required=True)
    p_assert.add_argument("--slot", required=True)

    args = p.parse_args()
    state_path = Path(args.state)

    if args.cmd == "init":
        state = initialize(state_path, args.episode_id, profile=args.profile)
    elif args.cmd == "show":
        state = load_state(state_path)
    elif args.cmd == "bind":
        state = bind_artifact(
            state_path,
            args.slot,
            Path(args.file),
            status=args.status,
            metadata=_json_metadata(args.metadata_json),
        )
    elif args.cmd == "transition":
        state = transition(state_path, args.to)
    elif args.cmd == "invalidate":
        state = invalidate_to(state_path, args.to, args.reason)
    elif args.cmd == "block":
        state = mark_blocked(state_path, args.code, args.detail)
    elif args.cmd == "unblock":
        state = clear_blocker(state_path, args.code)
    elif args.cmd == "assert":
        assert_canonical_bytes(state_path, args.slot)
        state = load_state(state_path)
    else:
        raise AssertionError(args.cmd)

    print(summary(state))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
