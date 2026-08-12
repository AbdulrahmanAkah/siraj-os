"""SIRAJ V6.4 one-click Autopilot execution engine."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
import threading
import uuid
from pathlib import Path
import shutil
from typing import Any, Mapping

from src.application.artifact_provenance_v1 import (
    atomic_write_json,
    canonical_sha256,
    is_currently_valid,
    record_invalidation,
)
from src.application.episode_transition_ledger_v1 import (
    ledger_path as transition_ledger_path,
    project_state as project_transition_state,
)

from src.application.siraj_series_autopilot_v6_0_1 import STAGES, classify_failure
from src.application.siraj_luna_upstream_transport_v6_3 import (
    authorization_path as luna_authorization_path,
    authorize_stage as authorize_luna_stage,
)
from src.application.siraj_upstream_autopilot_v6_3 import (
    FIXED_CTA_AR,
    materialize_selected_episode,
    run_final_script,
    run_iconic_cinematic_review,
    run_pronunciation_performance_gate,
    run_source_claim_matrix,
    run_source_research,
    run_story_architecture,
    run_topic_selection,
    source_research_input,
    topic_selection_input,
)
from src.application.siraj_generic_final_tts_v6_3_2 import (
    CONFIRMATION_PHRASE as TTS_CONFIRMATION_PHRASE,
    auth_path as future_tts_auth_path,
    authorize_future_tts_queue,
    build_future_tts_queue,
    execute_future_tts_queue,
)
from src.application.siraj_final_tts_queue_selector_v6_3_2 import resolve_final_tts_queue_path
from src.application.siraj_production_studio_controller_v5_4_4 import (
    EXPLICIT_CONFIRMATION_PHRASE as EP2_TTS_CONFIRMATION_PHRASE,
    authorize_final_tts as authorize_ep2_final_tts,
    execute_one_authorized_item as execute_ep2_tts_item,
    pending_authorized_queue_ids as ep2_pending_tts_items,
)
from src.application.siraj_audio_timeline_v6_1 import build_audio_timestamps_and_beats
from src.application.siraj_downstream_luna_adapters_v6_4 import (
    audio_bound_storyboard,
    narration_visual_alignment,
    semantic_editorial_qa,
    semantic_prompt_direction,
)
from src.application.siraj_duplicate_gates_v6_2_1 import validate_pre_spend_duplicates
from src.application.siraj_media_queue_v6_2_1 import materialize_v6_media_queue
from src.application.siraj_media_cost_preflight_v6_2_1 import build_media_cost_preflight
from src.application.siraj_provider_execution_v6_2_1 import (
    authorize_media_queue,
    execute_queue as execute_media_queue,
)
from src.application.siraj_local_assembly_montage_v6_2_1 import assemble_episode_master

EP2_ID = "episode-002-adam-temptation-fall-repentance"
BOOTSTRAP_ID = "_next-episode-bootstrap-v6-4"
SERIES_ROOT = Path("projects/_series")
ACTIVE_REL = SERIES_ROOT / "siraj-series-autopilot-active-episode-v6-4.json"
RUNTIME_REL = SERIES_ROOT / "siraj-series-autopilot-runtime-v6-4.json"

# SIRAJ_RUNTIME_JSON_CONTENTION_REPAIR_V6_6_R2
_JSON_IO_LOCK = threading.RLock()
READY_REL_NAME = "ready-for-final-human-review-v6-4.json"

LUNA_CONFIRMATION_PHRASE = "أوافق على تنفيذ مرحلة لونا المدفوعة"
MEDIA_CONFIRMATION_PHRASE = "أوافق على إنتاج الوسائط المدفوع"

LUNA_STAGES = {
    "TOPIC_SELECTION",
    "SOURCE_RESEARCH_FROM_ZERO",
    "SOURCE_CLAIM_MATRIX",
    "STORY_ARCHITECTURE",
    "ICONIC_CINEMATIC_REVIEW",
    "FINAL_SCRIPT",
    "PRONUNCIATION_AND_PERFORMANCE_GATE",
    "AUDIO_BOUND_STORYBOARD",
    "LUNA_SEMANTIC_PROMPT_DIRECTION",
    "NARRATION_VISUAL_ALIGNMENT_GATE",
    "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA",
}
PAID_STAGES = LUNA_STAGES | {"FINAL_TTS", "PROVIDER_EXECUTION"}
LOCAL_STAGES = {
    "AUDIO_TIMESTAMPS_AND_BEATS",
    "PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
    "MEDIA_COST_PREFLIGHT",
    "LOCAL_ASSEMBLY_AND_MONTAGE",
}


class OneClickAutopilotV64Error(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AutopilotInspection:
    episode_id: str
    mode: str
    stage: str
    stage_index: int
    completed_stages: tuple[str, ...]
    paid_stage: bool
    authorized: bool
    action: str
    detail: str
    terminal: bool

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class RunUntilGateResult:
    status: str
    episode_id: str
    stage: str
    completed_this_run: tuple[str, ...]
    detail: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    with _JSON_IO_LOCK:
        value = json.loads(
            path.read_text(encoding="utf-8-sig")
        )
    if not isinstance(value, dict):
        raise OneClickAutopilotV64Error(
            "JSON_OBJECT_REQUIRED:" + str(path)
        )
    return value

def _write(path: Path, value: Mapping[str, Any]) -> None:
    with _JSON_IO_LOCK:
        atomic_write_json(path, value, preserve_previous=True)

def _pass_json(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        return _read(path).get("status") == "PASS"
    except Exception:
        return False


def _queue_complete(repo: Path, episode_id: str) -> bool:
    try:
        queue = _read(resolve_final_tts_queue_path(repo, episode_id))
    except Exception:
        return False
    return queue.get("status") == "COMPLETE"


def _episode_ready(repo: Path, episode_id: str) -> bool:
    marker = repo / "projects" / episode_id / "orchestration" / READY_REL_NAME
    if not marker.is_file():
        return False
    try:
        value = _read(marker)
    except Exception:
        return False
    return (
        value.get("status") == "PASS"
        and value.get("episode_id") in {None, episode_id}
        and (
            value.get("master_sha256") is None
            or (
                isinstance(value.get("master_sha256"), str)
                and len(str(value.get("master_sha256"))) == 64
            )
        )
    )


def _legacy_stage_complete(repo: Path, episode_id: str, stage: str) -> bool:
    """Read-only compatibility projection for accepted pre-ledger artifacts."""

    ep = repo / "projects" / episode_id
    paths = {
        "TOPIC_SELECTION": ep / "contracts/topic-scope-v4.json",
        "SOURCE_RESEARCH_FROM_ZERO": ep / "research/luna-research-final-v4.json",
        "SOURCE_CLAIM_MATRIX": ep / "research/source-claim-matrix-v5.json",
        "STORY_ARCHITECTURE": ep / "preproduction/luna-story-architecture-v5.json",
        "ICONIC_CINEMATIC_REVIEW": ep / "preproduction/luna-story-architecture-iconic-reviewed-v5-1.json",
        "FINAL_SCRIPT": ep / "preproduction/luna-final-script-v5-1.json",
        "PRONUNCIATION_AND_PERFORMANCE_GATE": ep / "preproduction/luna-pronunciation-performance-gate-v5-3-4r2.json",
    }
    path = paths.get(stage)
    if path is None or not path.is_file():
        return False
    try:
        value = _read(path)
    except Exception:
        return False
    if value.get("episode_id") not in {None, episode_id}:
        return False
    if stage == "TOPIC_SELECTION":
        return str(value.get("status") or "").startswith("TOPIC_ONLY_APPROVED")
    return value.get("status") == "PASS"


def stage_complete(repo_root: Path, episode_id: str, stage: str) -> bool:
    repo = Path(repo_root).resolve()
    ep = repo / "projects" / episode_id

    ledger = transition_ledger_path(repo, episode_id)
    if ledger.is_file():
        try:
            return stage in project_transition_state(repo, episode_id).completed_stages
        except Exception:
            return False

    if stage in STAGES[:7]:
        return _legacy_stage_complete(repo, episode_id, stage)

    if stage == "FINAL_TTS":
        return _queue_complete(repo, episode_id)
    if stage == "PROVIDER_EXECUTION":
        path = ep / "orchestration/media-production-queue-v6-2-1.json"
        return path.is_file() and _read(path).get("status") == "COMPLETE"
    if stage == "READY_FOR_FINAL_HUMAN_REVIEW":
        return _episode_ready(repo, episode_id)

    paths = {
        "TOPIC_SELECTION": ep / "preproduction/topic-selection-v6-3.json",
        "SOURCE_RESEARCH_FROM_ZERO": ep / "research/source-research-from-zero-v6-3.json",
        "SOURCE_CLAIM_MATRIX": ep / "research/source-claim-matrix-v6-3.json",
        "STORY_ARCHITECTURE": ep / "preproduction/story-architecture-v6-3.json",
        "ICONIC_CINEMATIC_REVIEW": ep / "preproduction/story-architecture-iconic-reviewed-v6-3.json",
        "FINAL_SCRIPT": ep / "preproduction/final-script-v6-3.json",
        "PRONUNCIATION_AND_PERFORMANCE_GATE": ep / "orchestration/pronunciation-audit-v6-3.json",
        "AUDIO_TIMESTAMPS_AND_BEATS": ep / "preproduction/audio-timestamps-and-beats-v6-1.json",
        "AUDIO_BOUND_STORYBOARD": ep / "preproduction/audio-bound-storyboard-v6-1.json",
        "LUNA_SEMANTIC_PROMPT_DIRECTION": ep / "preproduction/luna-semantic-prompt-direction-v6-2-1.json",
        "NARRATION_VISUAL_ALIGNMENT_GATE": ep / "preproduction/narration-visual-alignment-gate-v6-2-1.json",
        "PROMPT_SIMILARITY_AND_DUPLICATE_GATE": ep / "orchestration/prompt-duplicate-gate-v6-4.json",
        "MEDIA_COST_PREFLIGHT": ep / "orchestration/media-cost-preflight-v6-2-1.json",
        "LOCAL_ASSEMBLY_AND_MONTAGE": ep / "deliverables/autopilot-v6-2-1/episode-master-autopilot-v6-2-1-receipt.json",
        "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA": ep / "deliverables/final-semantic-editorial-qa-v6-4.json",
    }
    path = paths.get(stage)
    if not path or not is_currently_valid(repo, episode_id, path):
        return False
    if stage == "PROMPT_SIMILARITY_AND_DUPLICATE_GATE" and path.is_file():
        try:
            gate = _read(path)
            prompts_path = ep / "preproduction/luna-semantic-prompt-direction-v6-2-1.json"
            current_input = canonical_sha256(_read(prompts_path))
            return (
                gate.get("status") == "PASS"
                and gate.get("input_prompt_plan_sha256") == current_input
            )
        except Exception:
            return False
    return _pass_json(path)


def _candidate_active_episode(repo: Path) -> str | None:
    if (repo / "projects" / EP2_ID).is_dir() and not _episode_ready(repo, EP2_ID):
        return EP2_ID

    active = repo / ACTIVE_REL
    if active.is_file():
        try:
            episode_id = str(_read(active).get("episode_id") or "")
            if (
                episode_id
                and episode_id != "NEXT_NEW_EPISODE"
                and (repo / "projects" / episode_id).is_dir()
                and not _episode_ready(repo, episode_id)
            ):
                return episode_id
        except Exception:
            pass

    candidates = []
    for contract in (repo / "projects").glob("episode-*/contracts/episode-definition-v6-3.json"):
        episode_id = contract.parents[1].name
        if not _episode_ready(repo, episode_id):
            candidates.append(episode_id)
    return sorted(candidates)[-1] if candidates else None


def _completed(repo: Path, episode_id: str) -> tuple[str, ...]:
    completed: list[str] = []
    for stage in STAGES:
        if not stage_complete(repo, episode_id, stage):
            break
        completed.append(stage)
    return tuple(completed)


def _first_incomplete(repo: Path, episode_id: str) -> str:
    completed = _completed(repo, episode_id)
    if len(completed) < len(STAGES):
        return STAGES[len(completed)]
    return "READY_FOR_FINAL_HUMAN_REVIEW"


def _stage_authorized(repo: Path, episode_id: str, stage: str) -> bool:
    if stage in LUNA_STAGES:
        target_id = BOOTSTRAP_ID if stage == "TOPIC_SELECTION" else episode_id
        path = luna_authorization_path(repo, target_id, stage)
        if not path.is_file():
            return False
        try:
            auth = _read(path)
        except Exception:
            return False
        return (
            auth.get("status") == "ACTIVE"
            and auth.get("stage") == stage
            and auth.get("automatic_retry") is False
        )

    if stage == "FINAL_TTS":
        path = (
            repo / "projects" / EP2_ID / "orchestration/final-tts-paid-authorization-v5-4-3.json"
            if episode_id == EP2_ID
            else future_tts_auth_path(repo, episode_id)
        )
        return path.is_file() and _read(path).get("status") == "ACTIVE"

    if stage == "PROVIDER_EXECUTION":
        path = repo / "projects" / episode_id / "orchestration/media-production-paid-authorization-v6-2-1.json"
        return path.is_file() and _read(path).get("status") == "ACTIVE"

    return True


def _persist(repo: Path, inspection: AutopilotInspection) -> None:
    _write(
        repo / RUNTIME_REL,
        {
            "schema_version": "siraj-series-autopilot-runtime-v6.4",
            **inspection.as_dict(),
            "completed_stage_rerun_policy": "FORBIDDEN_UNLESS_EXPLICIT_HUMAN_RESET",
            "automatic_paid_retry": False,
            "automatic_paid_resubmission": False,
            "target_terminal_state": "READY_FOR_FINAL_HUMAN_REVIEW",
            "updated_at_utc": _now(),
        },
    )
    if inspection.episode_id != "NEXT_NEW_EPISODE":
        _write(
            repo / ACTIVE_REL,
            {
                "schema_version": "siraj-series-autopilot-active-episode-v6.4",
                "status": "READY_FOR_FINAL_HUMAN_REVIEW" if inspection.terminal else "ACTIVE",
                "episode_id": inspection.episode_id,
                "resume_stage": inspection.stage,
                "completed_stages": list(inspection.completed_stages),
                "updated_at_utc": _now(),
            },
        )


def inspect_autopilot(repo_root: Path) -> AutopilotInspection:
    repo = Path(repo_root).resolve()
    episode_id = _candidate_active_episode(repo)

    if episode_id is None:
        stage = "TOPIC_SELECTION"
        authorized = _stage_authorized(repo, "NEXT_NEW_EPISODE", stage)
        result = AutopilotInspection(
            episode_id="NEXT_NEW_EPISODE",
            mode="START_NEW_EPISODE",
            stage=stage,
            stage_index=1,
            completed_stages=(),
            paid_stage=True,
            authorized=authorized,
            action="RUN" if authorized else "EXPLICIT_PAID_AUTHORIZATION_REQUIRED",
            detail="No unfinished episode. Start from TOPIC_SELECTION.",
            terminal=False,
        )
        return result

    completed = _completed(repo, episode_id)
    stage = _first_incomplete(repo, episode_id)
    terminal = stage == "READY_FOR_FINAL_HUMAN_REVIEW"
    paid = stage in PAID_STAGES
    authorized = True if terminal else _stage_authorized(repo, episode_id, stage)
    result = AutopilotInspection(
        episode_id=episode_id,
        mode="RESUME_EXISTING_EPISODE",
        stage=stage,
        stage_index=STAGES.index(stage) + 1,
        completed_stages=completed,
        paid_stage=paid,
        authorized=authorized,
        action=(
            "READY_FOR_FINAL_HUMAN_REVIEW"
            if terminal
            else "EXPLICIT_PAID_AUTHORIZATION_REQUIRED"
            if paid and not authorized
            else "RUN"
        ),
        detail=f"Resume at {stage}; completed stages are protected.",
        terminal=terminal,
    )
    return result


def _ep2_script(repo: Path) -> dict[str, Any]:
    for path in (
        repo / "projects" / EP2_ID / "preproduction/luna-final-script-v5-1.json",
        repo / "projects" / EP2_ID / "preproduction/final-script-v5-1.json",
    ):
        if path.is_file():
            return _read(path)
    raise OneClickAutopilotV64Error("EPISODE_002_FINAL_SCRIPT_NOT_FOUND")


def _script(repo: Path, episode_id: str) -> dict[str, Any]:
    if episode_id == EP2_ID:
        return _ep2_script(repo)
    return _read(repo / "projects" / episode_id / "preproduction/final-script-v6-3.json")




def _final_qa_manifest(repo: Path, episode_id: str) -> dict:
    path = (
        Path(repo).resolve()
        / "projects"
        / episode_id
        / "orchestration"
        / "final-qa-evidence-package-v11-compact.json"
    )
    if not path.is_file():
        raise RuntimeError("FINAL_QA_EVIDENCE_V11_COMPACT_REQUIRED")
    value = _read(path)
    if (
        not isinstance(value, dict)
        or value.get("status") != "PASS"
        or value.get("episode_id") != episode_id
        or value.get("qa_contract_version")
        != "FINAL_QA_EVIDENCE_V11_COMPACT"
    ):
        raise RuntimeError("FINAL_QA_EVIDENCE_V11_COMPACT_INVALID")
    return value




def _paid_luna_input(repo: Path, episode_id: str, stage: str) -> dict[str, Any]:
    ep = repo / "projects" / episode_id
    if stage == "TOPIC_SELECTION":
        return topic_selection_input(repo)
    if stage == "SOURCE_RESEARCH_FROM_ZERO":
        return source_research_input(repo, episode_id)
    if stage == "SOURCE_CLAIM_MATRIX":
        return {
            "task": "BUILD_CANONICAL_SOURCE_CLAIM_MATRIX",
            "research": _read(ep / "research/source-research-from-zero-v6-3.json"),
            "law": {
                "every_allowed_claim_requires_traceable_source_ids": True,
                "no_source_invention": True,
                "exclude_unsupported_material": True,
                "qualification_required_for_disputed_material": True,
                "canonical_events_must_be_claim_backed": True,
            },
        }
    if stage == "STORY_ARCHITECTURE":
        return {
            "task": "DESIGN_STORY_ARCHITECTURE",
            "episode_definition": _read(ep / "contracts/episode-definition-v6-3.json"),
            "source_claim_matrix": _read(ep / "research/source-claim-matrix-v6-3.json"),
            "creative_law": {
                "truth_before_drama": True,
                "no_fixed_act_count": True,
                "no_fixed_beat_count": True,
                "no_fixed_duration": True,
                "build_cinematic_causality": True,
                "one_memorable_visual_idea_per_major_beat": True,
            },
        }
    if stage == "ICONIC_CINEMATIC_REVIEW":
        return {
            "task": "ICONIC_CINEMATIC_MAX_REVIEW",
            "architecture": _read(ep / "preproduction/story-architecture-v6-3.json"),
            "source_claim_matrix": _read(ep / "research/source-claim-matrix-v6-3.json"),
        }
    if stage == "FINAL_SCRIPT":
        return {
            "task": "WRITE_FINAL_SCRIPT",
            "episode_definition": _read(ep / "contracts/episode-definition-v6-3.json"),
            "source_claim_matrix": _read(ep / "research/source-claim-matrix-v6-3.json"),
            "iconic_review": _read(ep / "preproduction/story-architecture-iconic-reviewed-v6-3.json"),
            "fixed_series_cta_excluded_from_script": FIXED_CTA_AR,
            "script_law": {
                "no_fixed_word_count": True,
                "no_fixed_segment_count": True,
                "no_fixed_duration": True,
                "exact_claim_traceability": True,
                "exact_beat_traceability": True,
                "qualified_claims_keep_qualification": True,
                "cta_is_separate_reusable_asset": True,
            },
        }
    if stage == "PRONUNCIATION_AND_PERFORMANCE_GATE":
        return {
            "task": "FULL_ARABIC_PRONUNCIATION_AND_PERFORMANCE_GATE",
            "final_script": _read(ep / "preproduction/final-script-v6-3.json"),
            "global_pronunciation_law": {
                "scope": "ALL_EPISODES_LEGACY_AND_FUTURE",
                "full_pronunciation_oriented_diacritization": True,
                "selective_only_diacritization": "FORBIDDEN",
                "bare_multi_letter_arabic_word_in_tts": "FORBIDDEN",
                "lexical_script_rewrite": "FORBIDDEN",
                "pause_aware_endings": True,
                "quran_direct_quote_prefers_canonical_vocalization": True,
                "hadith_direct_quote_preserve_wording": True,
                "madda_is_self_vocalized_carrier": True,
            },
        }
    if stage == "AUDIO_BOUND_STORYBOARD":
        return {
            "timeline": _read(ep / "preproduction/audio-timestamps-and-beats-v6-1.json"),
            "script": _script(repo, episode_id),
        }
    if stage == "LUNA_SEMANTIC_PROMPT_DIRECTION":
        return _read(ep / "preproduction/audio-bound-storyboard-v6-1.json")
    if stage == "NARRATION_VISUAL_ALIGNMENT_GATE":
        return {
            "script": _script(repo, episode_id),
            "prompts": _read(ep / "preproduction/luna-semantic-prompt-direction-v6-2-1.json"),
        }
    if stage == "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA":
        return _final_qa_manifest(repo, episode_id)
    raise OneClickAutopilotV64Error("PAID_LUNA_INPUT_NOT_IMPLEMENTED:" + stage)


def authorization_phrase_for(repo_root: Path) -> tuple[str, str]:
    inspection = inspect_autopilot(repo_root)
    if inspection.stage in LUNA_STAGES:
        return inspection.stage, LUNA_CONFIRMATION_PHRASE
    if inspection.stage == "FINAL_TTS":
        return inspection.stage, (
            EP2_TTS_CONFIRMATION_PHRASE
            if inspection.episode_id == EP2_ID
            else TTS_CONFIRMATION_PHRASE
        )
    if inspection.stage == "PROVIDER_EXECUTION":
        return inspection.stage, MEDIA_CONFIRMATION_PHRASE
    raise OneClickAutopilotV64Error("CURRENT_STAGE_IS_NOT_A_PAID_GATE")


def authorize_current_stage(repo_root: Path, confirmation_phrase: str) -> Path:
    repo = Path(repo_root).resolve()
    inspection = inspect_autopilot(repo)
    stage = inspection.stage
    if not inspection.paid_stage:
        raise OneClickAutopilotV64Error("CURRENT_STAGE_IS_NOT_PAID:" + stage)
    if inspection.authorized:
        raise OneClickAutopilotV64Error("CURRENT_STAGE_ALREADY_AUTHORIZED:" + stage)

    if stage in LUNA_STAGES:
        target_id = BOOTSTRAP_ID if stage == "TOPIC_SELECTION" else inspection.episode_id
        payload = _paid_luna_input(repo, inspection.episode_id, stage)
        return authorize_luna_stage(repo, target_id, stage, payload, confirmation_phrase)
    if stage == "FINAL_TTS":
        if inspection.episode_id == EP2_ID:
            return authorize_ep2_final_tts(repo, confirmation_phrase)
        build_future_tts_queue(repo, inspection.episode_id)
        return authorize_future_tts_queue(repo, inspection.episode_id, confirmation_phrase)
    if stage == "PROVIDER_EXECUTION":
        return authorize_media_queue(repo, inspection.episode_id, confirmation_phrase)
    raise OneClickAutopilotV64Error("PAID_AUTHORIZATION_NOT_IMPLEMENTED:" + stage)


def _run_topic_selection_stage(repo: Path) -> str:
    bootstrap = repo / "projects" / BOOTSTRAP_ID
    bootstrap.mkdir(parents=True, exist_ok=True)
    (bootstrap / "preproduction").mkdir(parents=True, exist_ok=True)
    (bootstrap / "orchestration").mkdir(parents=True, exist_ok=True)
    run_topic_selection(repo, BOOTSTRAP_ID)
    episode_id, _ = materialize_selected_episode(repo, BOOTSTRAP_ID)
    destination = repo / "projects" / episode_id / "orchestration/topic-selection-bootstrap-v6-4"
    if destination.exists():
        raise OneClickAutopilotV64Error("TOPIC_SELECTION_BOOTSTRAP_ARCHIVE_ALREADY_EXISTS")
    shutil.copytree(bootstrap, destination)
    record_invalidation(
        repo,
        episode_id,
        bootstrap,
        reason="TOPIC_SELECTION_BOOTSTRAP_SUPERSEDED_AFTER_CHECKSUMMED_COPY",
        classification="SUPERSEDED",
    )
    _write(
        repo / ACTIVE_REL,
        {
            "schema_version": "siraj-series-autopilot-active-episode-v6.4",
            "status": "ACTIVE",
            "episode_id": episode_id,
            "resume_stage": "SOURCE_RESEARCH_FROM_ZERO",
            "completed_stages": ["TOPIC_SELECTION"],
            "updated_at_utc": _now(),
        },
    )
    return episode_id


def _write_duplicate_gate(repo: Path, episode_id: str) -> Path:
    ep = repo / "projects" / episode_id
    prompts = _read(ep / "preproduction/luna-semantic-prompt-direction-v6-2-1.json")
    items = prompts.get("items")
    if not isinstance(items, list) or not items:
        raise OneClickAutopilotV64Error("PROMPT_PLAN_ITEMS_REQUIRED")
    problems = validate_pre_spend_duplicates(items)
    payload = {
        "schema_version": "siraj-prompt-duplicate-gate-v6.4",
        "status": "PASS" if not problems else "FAIL",
        "episode_id": episode_id,
        "problem_count": len(problems),
        "problems": problems,
        "perceptual_post_generation_gate": "REQUIRED",
        "created_at_utc": _now(),
        "input_prompt_plan_sha256": canonical_sha256(prompts),
    }
    path = ep / "orchestration/prompt-duplicate-gate-v6-4.json"
    _write(path, payload)
    if problems:
        raise OneClickAutopilotV64Error(
            "PROMPT_SEMANTIC_DUPLICATE_GATE_FAILED:"
            + json.dumps(problems[:20], ensure_ascii=False, separators=(",", ":"))
        )
    return path


def _mark_ready(repo: Path, episode_id: str) -> Path:
    ep = repo / "projects" / episode_id
    qa = _read(ep / "deliverables/final-semantic-editorial-qa-v11.json")
    if qa.get("status") != "PASS" or qa.get("ready_for_final_human_review") is False:
        raise OneClickAutopilotV64Error("FINAL_QA_NOT_READY")
    receipt = _read(ep / "deliverables/autopilot-v6-2-1/episode-master-autopilot-v6-2-1-receipt.json")
    path = ep / "orchestration" / READY_REL_NAME
    _write(
        path,
        {
            "schema_version": "siraj-ready-for-final-human-review-v6.4",
            "status": "PASS",
            "episode_id": episode_id,
            "master_path_relative": receipt.get("master_path_relative"),
            "master_sha256": receipt.get("master_sha256"),
            "publishing": "HUMAN_ONLY",
            "created_at_utc": _now(),
        },
    )
    return path



def execute_current_stage(repo_root: Path) -> str:
    repo = Path(repo_root).resolve()
    inspection = inspect_autopilot(repo)
    stage = inspection.stage
    # EP002 provider execution is owned exclusively by the canonical Desktop
    # controller.  Keeping this legacy dispatcher inspectable but unable to
    # spend prevents a CLI/direct-script bypass of the supported UI path.
    if stage == "PROVIDER_EXECUTION" and inspection.episode_id == EP2_ID:
        raise OneClickAutopilotV64Error(
            "PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY"
        )
    if inspection.terminal:
        return "READY_FOR_FINAL_HUMAN_REVIEW"
    if inspection.paid_stage and not inspection.authorized:
        raise OneClickAutopilotV64Error("EXPLICIT_PAID_AUTHORIZATION_REQUIRED:" + stage)

    episode_id = inspection.episode_id
    if stage == "TOPIC_SELECTION":
        return _run_topic_selection_stage(repo)
    if stage == "SOURCE_RESEARCH_FROM_ZERO":
        run_source_research(repo, episode_id)
    elif stage == "SOURCE_CLAIM_MATRIX":
        run_source_claim_matrix(repo, episode_id)
    elif stage == "STORY_ARCHITECTURE":
        run_story_architecture(repo, episode_id)
    elif stage == "ICONIC_CINEMATIC_REVIEW":
        run_iconic_cinematic_review(repo, episode_id)
    elif stage == "FINAL_SCRIPT":
        run_final_script(repo, episode_id)
    elif stage == "PRONUNCIATION_AND_PERFORMANCE_GATE":
        run_pronunciation_performance_gate(repo, episode_id)
    elif stage == "FINAL_TTS":
        if episode_id == EP2_ID:
            queue_ids = ep2_pending_tts_items(repo)
            if not queue_ids and not _queue_complete(repo, episode_id):
                raise OneClickAutopilotV64Error("EP2_FINAL_TTS_NO_AUTHORIZED_ITEMS")
            for queue_id in queue_ids:
                execute_ep2_tts_item(repo, queue_id)
        else:
            if not (repo / "projects" / episode_id / "orchestration/final-tts-queue-v6-3-2.json").is_file():
                build_future_tts_queue(repo, episode_id)
            execute_future_tts_queue(repo, episode_id)
    elif stage == "AUDIO_TIMESTAMPS_AND_BEATS":
        build_audio_timestamps_and_beats(repo, episode_id)
    elif stage == "AUDIO_BOUND_STORYBOARD":
        payload = _paid_luna_input(repo, episode_id, stage)
        audio_bound_storyboard(repo, episode_id, payload["timeline"], payload["script"])
    elif stage == "LUNA_SEMANTIC_PROMPT_DIRECTION":
        semantic_prompt_direction(repo, episode_id, _paid_luna_input(repo, episode_id, stage))
    elif stage == "NARRATION_VISUAL_ALIGNMENT_GATE":
        payload = _paid_luna_input(repo, episode_id, stage)
        narration_visual_alignment(repo, episode_id, payload["script"], payload["prompts"])
    elif stage == "PROMPT_SIMILARITY_AND_DUPLICATE_GATE":
        _write_duplicate_gate(repo, episode_id)
    elif stage == "MEDIA_COST_PREFLIGHT":
        queue_path = repo / "projects" / episode_id / "orchestration/media-production-queue-v6-2-1.json"
        if not queue_path.is_file():
            materialize_v6_media_queue(repo, episode_id)
        build_media_cost_preflight(repo, episode_id)
    elif stage == "PROVIDER_EXECUTION":
        execute_media_queue(repo, episode_id)
    elif stage == "LOCAL_ASSEMBLY_AND_MONTAGE":
        assemble_episode_master(repo, episode_id)
    elif stage == "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA":
        semantic_editorial_qa(repo, episode_id, _paid_luna_input(repo, episode_id, stage))
        _mark_ready(repo, episode_id)
    else:
        raise OneClickAutopilotV64Error("STAGE_EXECUTION_NOT_IMPLEMENTED:" + stage)

    if stage != "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA" and not stage_complete(repo, episode_id, stage):
        raise OneClickAutopilotV64Error("STAGE_DID_NOT_PRODUCE_PASS:" + stage)
    return stage


def _state_digest(repo: Path, episode_id: str, stage: str) -> str:
    ep = repo / "projects" / episode_id
    entries = []
    if ep.is_dir():
        for path in sorted(ep.rglob("*.json")):
            try:
                stat = path.stat()
            except OSError:
                continue
            entries.append((str(path.relative_to(ep)), stat.st_size, stat.st_mtime_ns))
    return hashlib.sha256(
        json.dumps({"stage": stage, "files": entries}, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _safe_local_repair(repo: Path, episode_id: str) -> bool:
    ep = repo / "projects" / episode_id
    changed = False
    if not ep.is_dir():
        return False
    for pattern in ("*.part", "*.tmp"):
        for path in ep.rglob(pattern):
            if path.is_file():
                record_invalidation(
                    repo,
                    episode_id,
                    path,
                    reason="LOCAL_REPAIR_PARTIAL_OR_TEMP_PRESERVED",
                    classification="STALE_BUT_PRESERVED",
                )
                changed = True
    return changed


def run_until_gate(repo_root: Path, progress=None) -> RunUntilGateResult:
    repo = Path(repo_root).resolve()
    completed_this_run: list[str] = []
    fingerprints: set[str] = set()

    while True:
        inspection = inspect_autopilot(repo)
        if progress:
            progress(inspection.stage, len(inspection.completed_stages), len(STAGES), inspection.action)

        if inspection.terminal:
            return RunUntilGateResult(
                "READY_FOR_FINAL_HUMAN_REVIEW",
                inspection.episode_id,
                inspection.stage,
                tuple(completed_this_run),
                inspection.detail,
            )
        if inspection.paid_stage and not inspection.authorized:
            return RunUntilGateResult(
                "PAID_AUTHORIZATION_REQUIRED",
                inspection.episode_id,
                inspection.stage,
                tuple(completed_this_run),
                "Explicit human authorization required before paid execution.",
            )

        digest = _state_digest(
            repo,
            EP2_ID if inspection.episode_id == "NEXT_NEW_EPISODE" else inspection.episode_id,
            inspection.stage,
        )
        try:
            execute_current_stage(repo)
        except Exception as exc:
            decision = classify_failure(exc)
            if decision.automatic_repair_allowed and inspection.stage in LOCAL_STAGES:
                fingerprint = hashlib.sha256(
                    (inspection.stage + "\n" + str(exc) + "\n" + digest).encode("utf-8")
                ).hexdigest()
                if fingerprint in fingerprints:
                    raise OneClickAutopilotV64Error(
                        "SAFE_LOCAL_REPAIR_NO_PROGRESS_STOP:" + inspection.stage + ":" + str(exc)
                    ) from exc
                fingerprints.add(fingerprint)
                episode_id = inspection.episode_id if inspection.episode_id != "NEXT_NEW_EPISODE" else EP2_ID
                if _safe_local_repair(repo, episode_id):
                    continue
            raise

        completed_this_run.append(inspection.stage)
        if progress:
            new = inspect_autopilot(repo)
            progress(inspection.stage, len(new.completed_stages), len(STAGES), "COMPLETE")
