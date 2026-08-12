"""SIRAJ Series Autopilot V6.0.1 — resume-aware control plane.

This revision adds two non-negotiable invariants:

1) Existing episodes resume from the first incomplete stage. Completed stages
   are immutable and are never rerun automatically.
2) A brand-new episode starts from TOPIC_SELECTION only after the active
   episode has reached READY_FOR_FINAL_HUMAN_REVIEW.

For Episode 002 the already completed pre-audio-production work is recognized
from its canonical V5 artifacts. Its resume anchor is FINAL_TTS, not
TOPIC_SELECTION.

No paid action is performed by this module.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

RELEASE = "SIRAJ_SERIES_AUTOPILOT_V6_0_1"
POLICY_VERSION = "siraj-series-autopilot-policy-v6.0.1"

SERIES_ROOT = Path("projects/_series")
POLICY_REL = SERIES_ROOT / "siraj-series-autopilot-policy-v6.0.1.json"
COMPAT_REL = SERIES_ROOT / "siraj-series-autopilot-backend-compatibility-v6.0.1.json"
RUNTIME_REL = SERIES_ROOT / "siraj-series-autopilot-runtime-v6.0.1.json"
ACTIVE_REL = SERIES_ROOT / "siraj-series-autopilot-active-episode-v6.0.1.json"

EP2_ID = "episode-002-adam-temptation-fall-repentance"
EP2 = Path("projects") / EP2_ID

STAGES = (
    "TOPIC_SELECTION",
    "SOURCE_RESEARCH_FROM_ZERO",
    "SOURCE_CLAIM_MATRIX",
    "STORY_ARCHITECTURE",
    "ICONIC_CINEMATIC_REVIEW",
    "FINAL_SCRIPT",
    "PRONUNCIATION_AND_PERFORMANCE_GATE",
    "FINAL_TTS",
    "AUDIO_TIMESTAMPS_AND_BEATS",
    "AUDIO_BOUND_STORYBOARD",
    "LUNA_SEMANTIC_PROMPT_DIRECTION",
    "NARRATION_VISUAL_ALIGNMENT_GATE",
    "PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
    "MEDIA_COST_PREFLIGHT",
    "PROVIDER_EXECUTION",
    "LOCAL_ASSEMBLY_AND_MONTAGE",
    "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA",
    "READY_FOR_FINAL_HUMAN_REVIEW",
)

KINDS = {
    "TOPIC_SELECTION": "PAID_LUNA",
    "SOURCE_RESEARCH_FROM_ZERO": "PAID_LUNA_AND_OPTIONAL_WEB",
    "SOURCE_CLAIM_MATRIX": "PAID_LUNA",
    "STORY_ARCHITECTURE": "PAID_LUNA",
    "ICONIC_CINEMATIC_REVIEW": "PAID_LUNA",
    "FINAL_SCRIPT": "PAID_LUNA",
    "PRONUNCIATION_AND_PERFORMANCE_GATE": "PAID_LUNA",
    "FINAL_TTS": "PAID_ELEVENLABS",
    "AUDIO_TIMESTAMPS_AND_BEATS": "LOCAL",
    "AUDIO_BOUND_STORYBOARD": "PAID_LUNA",
    "LUNA_SEMANTIC_PROMPT_DIRECTION": "PAID_LUNA",
    "NARRATION_VISUAL_ALIGNMENT_GATE": "PAID_LUNA",
    "PROMPT_SIMILARITY_AND_DUPLICATE_GATE": "LOCAL_AND_LUNA_REVIEW",
    "MEDIA_COST_PREFLIGHT": "LOCAL",
    "PROVIDER_EXECUTION": "PAID_MEDIA_PROVIDER",
    "LOCAL_ASSEMBLY_AND_MONTAGE": "LOCAL",
    "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA": "LOCAL_AND_LUNA_REVIEW",
    "READY_FOR_FINAL_HUMAN_REVIEW": "HUMAN_GATE",
}

# Candidate discovery tokens. A candidate is not certified merely by name;
# the compatibility report preserves the distinction.
CAPABILITY_TOKENS = {
    "TOPIC_SELECTION": ("autonomous_episode_orchestrator", "episode_scope"),
    "SOURCE_RESEARCH_FROM_ZERO": ("luna_research_gateway", "research_gateway"),
    "SOURCE_CLAIM_MATRIX": ("source_claim_matrix",),
    "STORY_ARCHITECTURE": ("story_architecture",),
    "ICONIC_CINEMATIC_REVIEW": ("iconic_cinematic",),
    "FINAL_SCRIPT": ("luna_final_script", "final_script"),
    "PRONUNCIATION_AND_PERFORMANCE_GATE": ("pronunciation_performance_gate",),
    "FINAL_TTS": ("siraj_final_tts_elevenlabs_v5_4_3",),
    "AUDIO_TIMESTAMPS_AND_BEATS": ("audio_timestamp", "audio_beat", "timeline"),
    "AUDIO_BOUND_STORYBOARD": ("audio_bound_storyboard",),
    "LUNA_SEMANTIC_PROMPT_DIRECTION": ("semantic_prompt", "prompt_direction"),
    "NARRATION_VISUAL_ALIGNMENT_GATE": ("narration_visual_alignment", "alignment_gate"),
    "PROMPT_SIMILARITY_AND_DUPLICATE_GATE": ("prompt_similarity", "duplicate_gate"),
    "MEDIA_COST_PREFLIGHT": ("cost_preflight", "attempt_ledger"),
    "PROVIDER_EXECUTION": ("desktop_media_execution", "runware_execution"),
    "LOCAL_ASSEMBLY_AND_MONTAGE": ("montage", "production_assembly"),
    "SEMANTIC_EDITORIAL_AND_TECHNICAL_QA": ("automatic_qa", "technical_qa"),
}

PAID_TOKENS = (
    "PAID",
    "AUTHORIZATION_REQUIRED",
    "RETRY_AUTH",
    "PROVIDER_REJECTED",
    "RATE_LIMIT",
    "QUOTA",
    "CREDIT",
    "PAYMENT",
    "NETWORK_RESULT_UNKNOWN",
    "NO_AUTOMATIC_RESUBMISSION",
)
STRUCTURAL_TOKENS = (
    "SCHEMA",
    "ARCHITECTURE",
    "POLICY",
    "CONTRACT",
    "MIGRATION",
    "VOICE_CHANGED",
    "MODEL_CHANGED",
    "PROVIDER_CHANGED",
    "CANONICAL",
)
SAFE_LOCAL_TOKENS = (
    "JSONDECODEERROR",
    "UNICODEDECODEERROR",
    "FILENOTFOUNDERROR",
    "NO SUCH FILE",
    ".PART",
    "FFMPEG",
    "FFPROBE",
    "PYSIDE",
    "QT",
    "COMPILE",
    "PYTEST",
    "ASSERTIONERROR",
    "VALUEERROR",
    "KEYERROR",
    "ATTRIBUTEERROR",
    "TYPEERROR",
    "NAMEERROR",
    "IMPORTERROR",
    "MODULENOTFOUNDERROR",
)


class AutopilotError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class ResumeState:
    episode_id: str
    mode: str
    resume_stage: str
    completed_stages: tuple[str, ...]
    protected_completed_stages: tuple[str, ...]
    new_episode_start_stage: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class FailureDecision:
    classification: str
    automatic_repair_allowed: bool
    automatic_paid_retry_allowed: bool
    human_action_required: bool
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise AutopilotError("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def _stage_index(stage: str) -> int:
    try:
        return STAGES.index(stage)
    except ValueError as exc:
        raise AutopilotError("UNKNOWN_STAGE:" + stage) from exc


def _pass_json(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        value = _read(path)
    except Exception:
        return False
    if value.get("status") == "PASS":
        return True
    summary = value.get("_siraj_stage_summary")
    return isinstance(summary, Mapping) and summary.get("status") == "PASS"


def _ep2_resume(repo: Path) -> ResumeState | None:
    ep = repo / EP2
    pron = ep / "orchestration/pronunciation-local-recovery-v5-3-4r2.json"
    queue_path = ep / "orchestration/final-tts-queue-v5-4-3.json"

    if not (_pass_json(pron) and queue_path.is_file()):
        return None

    queue = _read(queue_path)
    qstatus = str(queue.get("status") or "")

    completed = (
        "TOPIC_SELECTION",
        "SOURCE_RESEARCH_FROM_ZERO",
        "SOURCE_CLAIM_MATRIX",
        "STORY_ARCHITECTURE",
        "ICONIC_CINEMATIC_REVIEW",
        "FINAL_SCRIPT",
        "PRONUNCIATION_AND_PERFORMANCE_GATE",
    )

    if qstatus == "COMPLETE":
        resume_stage = "AUDIO_TIMESTAMPS_AND_BEATS"
        completed = completed + ("FINAL_TTS",)
        reason = (
            "Episode 002 already completed all pre-TTS stages and FINAL_TTS. "
            "Resume after generated narration."
        )
    else:
        resume_stage = "FINAL_TTS"
        reason = (
            "Episode 002 has canonical PASS through pronunciation/performance "
            "and an existing FINAL_TTS queue. Preproduction must not rerun."
        )

    return ResumeState(
        episode_id=EP2_ID,
        mode="RESUME_EXISTING_EPISODE",
        resume_stage=resume_stage,
        completed_stages=completed,
        protected_completed_stages=completed,
        new_episode_start_stage="TOPIC_SELECTION",
        reason=reason,
    )


def resolve_resume_state(repo_root: Path) -> ResumeState:
    repo = repo_root.resolve()

    # Strong current-project evidence wins over generic discovery.
    current = _ep2_resume(repo)
    if current is not None:
        _write(
            repo / ACTIVE_REL,
            {
                "schema_version": "siraj-series-autopilot-active-episode-v6.0.1",
                "status": "ACTIVE",
                **current.as_dict(),
                "completed_stage_rerun_policy": "FORBIDDEN_UNLESS_EXPLICIT_HUMAN_RESET",
                "future_episode_policy": (
                    "AFTER_READY_FOR_FINAL_HUMAN_REVIEW_START_NEW_EPISODE_AT_TOPIC_SELECTION"
                ),
                "updated_at_utc": _now(),
            },
        )
        return current

    active_path = repo / ACTIVE_REL
    if active_path.is_file():
        active = _read(active_path)
        if active.get("status") == "ACTIVE":
            stage = str(active.get("resume_stage") or "")
            episode_id = str(active.get("episode_id") or "")
            if stage in STAGES and episode_id:
                completed = tuple(
                    str(x)
                    for x in active.get("completed_stages", [])
                    if str(x) in STAGES
                )
                return ResumeState(
                    episode_id=episode_id,
                    mode="RESUME_EXISTING_EPISODE",
                    resume_stage=stage,
                    completed_stages=completed,
                    protected_completed_stages=completed,
                    new_episode_start_stage="TOPIC_SELECTION",
                    reason="Persisted active-episode resume state.",
                )

    # No active unfinished episode: next run is a brand-new episode.
    return ResumeState(
        episode_id="NEXT_NEW_EPISODE",
        mode="START_NEW_EPISODE",
        resume_stage="TOPIC_SELECTION",
        completed_stages=(),
        protected_completed_stages=(),
        new_episode_start_stage="TOPIC_SELECTION",
        reason="No active unfinished episode. Start a new episode from topic selection.",
    )


def assert_stage_may_run(resume: ResumeState, requested_stage: str) -> None:
    if requested_stage in resume.protected_completed_stages:
        raise AutopilotError(
            "COMPLETED_STAGE_RERUN_FORBIDDEN:"
            + requested_stage
            + ":EXPLICIT_HUMAN_RESET_REQUIRED"
        )
    if _stage_index(requested_stage) < _stage_index(resume.resume_stage):
        raise AutopilotError(
            "STAGE_BEFORE_RESUME_ANCHOR_FORBIDDEN:"
            + requested_stage
            + ":resume="
            + resume.resume_stage
        )


def classify_failure(exc: BaseException | str) -> FailureDecision:
    text = str(exc).upper()

    if any(token in text for token in PAID_TOKENS):
        return FailureDecision(
            "PAID_OR_PROVIDER_GATE",
            False,
            False,
            True,
            "Paid/provider failures require explicit authorization and never auto-retry.",
        )

    if any(token in text for token in STRUCTURAL_TOKENS):
        return FailureDecision(
            "STRUCTURAL_CHANGE_REQUIRED",
            False,
            False,
            True,
            "Architecture/schema/policy/canonical changes require human review.",
        )

    if any(token in text for token in SAFE_LOCAL_TOKENS):
        return FailureDecision(
            "SAFE_LOCAL_TECHNICAL_FAILURE",
            True,
            False,
            False,
            "Safe local repair is allowed without changing production contracts.",
        )

    return FailureDecision(
        "UNCLASSIFIED_FAIL_CLOSED",
        False,
        False,
        True,
        "Unknown failure stops rather than guessing.",
    )


def failure_fingerprint(
    stage: str,
    exc: BaseException | str,
    state_digest: str,
) -> str:
    raw = (
        stage
        + "\n"
        + type(exc).__name__
        + "\n"
        + str(exc)
        + "\n"
        + state_digest
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def repeated_no_progress(
    previous_fingerprints: Sequence[str],
    current_fingerprint: str,
) -> bool:
    return current_fingerprint in set(previous_fingerprints)


def _inventory(repo: Path) -> list[dict[str, Any]]:
    roots = (repo / "src/application", repo / "src/presentation/desktop")
    result = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            try:
                text = path.read_text(encoding="utf-8-sig", errors="replace")
            except OSError:
                continue
            result.append(
                {
                    "path": str(path.relative_to(repo)).replace("\\", "/"),
                    "name": path.stem,
                    "contains_v5": "v5" in path.stem.lower() or "V5" in text,
                    "contains_v6": "v6" in path.stem.lower() or "V6" in text,
                }
            )
    return result


def _matches(
    inventory: Sequence[Mapping[str, Any]],
    tokens: Sequence[str],
) -> list[dict[str, Any]]:
    found = []
    for item in inventory:
        blob = (str(item["path"]) + " " + str(item["name"])).lower()
        if any(token.lower() in blob for token in tokens):
            found.append(dict(item))
    return found


def audit_backend_compatibility(repo_root: Path) -> dict[str, Any]:
    repo = repo_root.resolve()
    resume = resolve_resume_state(repo)
    inventory = _inventory(repo)

    stage_rows = {}
    full_uncertified = []
    current_uncertified = []

    resume_index = _stage_index(resume.resume_stage)

    for stage in STAGES[:-1]:
        tokens = CAPABILITY_TOKENS.get(stage, ())
        matches = _matches(inventory, tokens)

        if stage == "FINAL_TTS":
            exact = repo / "src/application/siraj_final_tts_elevenlabs_v5_4_3.py"
            certified = exact.is_file()
            certification = (
                "CERTIFIED_CURRENT_V5_BACKEND"
                if certified
                else "MISSING"
            )
        else:
            # Candidates are reported but must be explicitly adapted/certified.
            certified = False
            certification = (
                "CANDIDATE_REQUIRES_ADAPTER_CERTIFICATION"
                if matches
                else "MISSING"
            )

        if not certified:
            full_uncertified.append(stage)
            if _stage_index(stage) >= resume_index:
                current_uncertified.append(stage)

        stage_rows[stage] = {
            "stage": stage,
            "kind": KINDS[stage],
            "certified": certified,
            "certification": certification,
            "candidate_count": len(matches),
            "candidates": matches[:20],
            "required_for_current_episode": _stage_index(stage) >= resume_index,
            "already_completed_for_current_episode": stage in resume.completed_stages,
        }

    current_ready = len(current_uncertified) == 0
    future_ready = len(full_uncertified) == 0

    report = {
        "schema_version": "siraj-series-autopilot-backend-compatibility-v6.0.1",
        "release": RELEASE,
        "status": (
            "READY_FOR_CURRENT_AND_FUTURE_ONE_CLICK_PRODUCTION"
            if current_ready and future_ready
            else (
                "CURRENT_EPISODE_REQUIRES_DOWNSTREAM_ADAPTERS"
                if not current_ready
                else "CURRENT_EPISODE_READY_FUTURE_EPISODES_REQUIRE_UPSTREAM_ADAPTERS"
            )
        ),
        "active_episode": resume.as_dict(),
        "current_episode_resume_stage": resume.resume_stage,
        "current_episode_preproduction_rerun": "FORBIDDEN",
        "next_new_episode_start_stage": "TOPIC_SELECTION",
        "automatic_safe_local_repair": True,
        "automatic_paid_retry": False,
        "paid_operation_requires_explicit_authorization": True,
        "structural_change_requires_human": True,
        "current_episode_start_locked": not current_ready,
        "future_new_episode_start_locked": not future_ready,
        "current_episode_uncertified_stage_count": len(current_uncertified),
        "current_episode_uncertified_stages": current_uncertified,
        "future_full_pipeline_uncertified_stage_count": len(full_uncertified),
        "future_full_pipeline_uncertified_stages": full_uncertified,
        "stages": stage_rows,
        "created_at_utc": _now(),
    }
    _write(repo / COMPAT_REL, report)

    runtime = {
        "schema_version": "siraj-series-autopilot-runtime-v6.0.1",
        "release": RELEASE,
        "active_episode_id": resume.episode_id,
        "mode": resume.mode,
        "resume_stage": resume.resume_stage,
        "completed_stage_rerun": "FORBIDDEN",
        "current_episode_start_locked": not current_ready,
        "future_new_episode_start_locked": not future_ready,
        "target_terminal_state": "READY_FOR_FINAL_HUMAN_REVIEW",
        "compatibility_report": str(COMPAT_REL).replace("\\", "/"),
        "updated_at_utc": _now(),
    }
    _write(repo / RUNTIME_REL, runtime)
    return report


def stage_graph() -> tuple[dict[str, Any], ...]:
    return tuple(
        {
            "index": index,
            "stage": stage,
            "kind": KINDS.get(stage, "UNKNOWN"),
            "human_gate": stage == "READY_FOR_FINAL_HUMAN_REVIEW",
        }
        for index, stage in enumerate(STAGES, 1)
    )
