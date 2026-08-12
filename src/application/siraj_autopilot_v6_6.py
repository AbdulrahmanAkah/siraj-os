"""SIRAJ V6.6 episode autonomy wrapper.

Adds:
- one episode-wide authorization instead of per-stage authorizations;
- future-episode event review gate after SOURCE_CLAIM_MATRIX;
- automatic continuation after event approval;
- explicit paid retry exception only after failed/unknown paid attempt.

The certified V6.4 stage implementations remain the execution backends.
"""

from __future__ import annotations

from dataclasses import replace
import hashlib
import json
from pathlib import Path

from src.application import siraj_one_click_autopilot_v6_4 as v64
from src.application.artifact_provenance_v1 import record_invalidation
from src.application.episode_transition_ledger_v1 import (
    ledger_path as transition_ledger_path,
    migration_approval_active,
)
# SIRAJ_TRUE_EXECUTION_TELEMETRY_V6_6_R9
from src.application.siraj_live_telemetry_v6_6_r9 import emit_event
# SIRAJ_STALE_LUNA_AUTH_AUTOREFRESH_V6_6_R5
from src.application.siraj_luna_upstream_transport_v6_3 import (
    authorization_path as luna_authorization_path,
)
from src.application.siraj_episode_master_authorization_v6_6 import (
    FULL_EPISODE_CONFIRMATION_PHRASE,
    NEXT_EPISODE_ID,
    PAID_RETRY_CONFIRMATION_PHRASE,
    authorize_episode_cycle,
    authorize_paid_retry,
    consume_paid_retry_authorization,
    mark_paid_failure,
    master_authorization_active,
    master_authorization_path,
    master_authorization_reference,
    migrate_next_episode_authorization,
    resolve_paid_retry_guard,
    retry_authorized,
    retry_required,
)
# SIRAJ_ALIGNMENT_SEMANTIC_AUTOREPAIR_V6_6_R3
from src.application.siraj_alignment_semantic_autorepair_v6_6_r3 import (
    is_semantic_alignment_fail,
    resolve_until_pass,
)
# SIRAJ_VISUAL_TIMELINE_COVERAGE_AUTOREPAIR_V6_6_R4
from src.application.siraj_visual_timeline_coverage_autorepair_v6_6_r4 import (
    is_visual_timeline_coverage_failure,
    repair_visual_timeline_coverage,
)
# SIRAJ_PRE_SPEND_PROMPT_AUTOREPAIR_V6_6_R7
from src.application.siraj_pre_spend_prompt_autorepair_v6_6_r7 import (
    is_pre_spend_duplicate_failure,
    repair_pre_spend_duplicate_gate,
)
from src.application.siraj_event_review_v6_6 import (
    EP2_ID,
    events_approved,
    materialize_event_plan,
)

EVENTS_REVIEW_STAGE = "EVENTS_REVIEW_AND_APPROVAL"
STAGES = v64.STAGES
LUNA_STAGES = v64.LUNA_STAGES
PAID_STAGES = v64.PAID_STAGES
LOCAL_STAGES = v64.LOCAL_STAGES
AutopilotInspection = v64.AutopilotInspection
RunUntilGateResult = v64.RunUntilGateResult


class AutopilotV66Error(RuntimeError):
    pass


def _read(path: Path):
    return v64._read(path)


def _write(path: Path, value):
    return v64._write(path, value)


def _event_review_required(
    repo: Path,
    inspection: AutopilotInspection,
) -> bool:
    if (
        inspection.episode_id in {
            NEXT_EPISODE_ID,
            EP2_ID,
        }
        or inspection.stage != "STORY_ARCHITECTURE"
        or "SOURCE_CLAIM_MATRIX" not in inspection.completed_stages
    ):
        return False
    if events_approved(
        repo,
        inspection.episode_id,
    ):
        return False
    return True


def inspect_autopilot(
    repo_root: Path,
) -> AutopilotInspection:
    repo = Path(repo_root).resolve()
    base = v64.inspect_autopilot(repo)

    if _event_review_required(repo, base):
        return AutopilotInspection(
            episode_id=base.episode_id,
            mode=base.mode,
            stage=EVENTS_REVIEW_STAGE,
            stage_index=base.stage_index,
            completed_stages=base.completed_stages,
            paid_stage=False,
            authorized=True,
            action="EVENTS_REVIEW_REQUIRED",
            detail=(
                "Human review of canonical episode events is required "
                "before story architecture."
            ),
            terminal=False,
        )

    if (
        base.episode_id != NEXT_EPISODE_ID
        and not transition_ledger_path(repo, base.episode_id).is_file()
        and not migration_approval_active(repo, base.episode_id)
    ):
        return replace(
            base,
            paid_stage=False,
            authorized=False,
            action="MIGRATION_APPROVAL_REQUIRED",
            detail=(
                "Legacy episode artifacts are preserved. A reviewed migration "
                "proposal and explicit human approval are required before resume."
            ),
        )

    if (
        base.episode_id != NEXT_EPISODE_ID
        and base.stage in PAID_STAGES
        and retry_required(
            repo,
            base.episode_id,
            base.stage,
        )
    ):
        authorized = retry_authorized(
            repo,
            base.episode_id,
            base.stage,
        )
        return replace(
            base,
            authorized=authorized,
            action=(
                "RUN"
                if authorized
                else "EXPLICIT_PAID_RETRY_AUTHORIZATION_REQUIRED"
            ),
            detail=(
                "Paid stage previously failed or became unknown. "
                "A separate explicit retry authorization is required."
            ),
        )

    episode_auth_id = base.episode_id
    master = master_authorization_active(
        repo,
        episode_auth_id,
    )

    if base.terminal:
        return base

    if base.stage in PAID_STAGES:
        return replace(
            base,
            authorized=master,
            action=(
                "RUN"
                if master
                else "FULL_EPISODE_AUTHORIZATION_REQUIRED"
            ),
            detail=(
                "Covered by the episode-wide authorization."
                if master
                else (
                    "One episode-wide authorization is required. "
                    "It covers all initial paid operations through final "
                    "human review; paid retries remain excluded."
                )
            ),
        )

    return base


def authorization_phrase_for(
    repo_root: Path,
) -> tuple[str, str]:
    inspection = inspect_autopilot(repo_root)

    if (
        inspection.episode_id != NEXT_EPISODE_ID
        and retry_required(
            repo_root,
            inspection.episode_id,
            inspection.stage,
        )
    ):
        return (
            inspection.stage,
            PAID_RETRY_CONFIRMATION_PHRASE,
        )

    if inspection.terminal:
        raise AutopilotV66Error(
            "TERMINAL_STAGE_HAS_NO_AUTHORIZATION"
        )
    return (
        inspection.stage,
        FULL_EPISODE_CONFIRMATION_PHRASE,
    )


def authorize_current_stage(
    repo_root: Path,
    confirmation_phrase: str,
) -> Path:
    repo = Path(repo_root).resolve()
    inspection = inspect_autopilot(repo)

    if inspection.action == "MIGRATION_APPROVAL_REQUIRED":
        raise AutopilotV66Error(
            "EPISODE_TRANSITION_LEDGER_MIGRATION_APPROVAL_REQUIRED:"
            + inspection.episode_id
        )

    if inspection.stage == EVENTS_REVIEW_STAGE:
        raise AutopilotV66Error(
            "EVENTS_REVIEW_IS_EDITORIAL_NOT_A_PAID_AUTHORIZATION_GATE"
        )

    if (
        inspection.episode_id != NEXT_EPISODE_ID
        and retry_required(
            repo,
            inspection.episode_id,
            inspection.stage,
        )
    ):
        return authorize_paid_retry(
            repo,
            inspection.episode_id,
            inspection.stage,
            confirmation_phrase,
        )

    return authorize_episode_cycle(
        repo,
        inspection.episode_id,
        inspection.stage,
        confirmation_phrase,
    )


def full_episode_authorization_active(
    repo_root: Path,
    episode_id: str,
) -> bool:
    return master_authorization_active(
        repo_root,
        episode_id,
    )


def master_auth_path(
    repo_root: Path,
    episode_id: str,
) -> Path:
    return master_authorization_path(
        repo_root,
        episode_id,
    )


def _annotate_derived_authorization(
    repo: Path,
    auth_path: Path,
    episode_id: str,
) -> None:
    if not auth_path.is_file():
        raise AutopilotV66Error(
            "DERIVED_AUTHORIZATION_FILE_MISSING:"
            + str(auth_path)
        )
    value = _read(auth_path)
    reference_id = (
        NEXT_EPISODE_ID
        if episode_id == NEXT_EPISODE_ID
        else episode_id
    )
    master = master_authorization_reference(
        repo,
        reference_id,
    )
    value[
        "authorization_source"
    ] = "DERIVED_FROM_EPISODE_MASTER_AUTHORIZATION"
    value[
        "episode_master_authorization_path"
    ] = master["path"]
    value[
        "episode_master_authorization_sha256"
    ] = master["sha256"]
    value["automatic_retry"] = False
    value["automatic_resubmission"] = False
    _write(auth_path, value)


def _ensure_legacy_stage_authorized(
    repo: Path,
    inspection: AutopilotInspection,
) -> None:
    stage = inspection.stage
    episode_id = inspection.episode_id

    base = v64.inspect_autopilot(repo)
    if base.stage != stage:
        raise AutopilotV66Error(
            "LEGACY_STAGE_MISMATCH:"
            + base.stage
            + "!="
            + stage
        )
    if base.authorized:
        return

    master_id = episode_id
    if not master_authorization_active(
        repo,
        master_id,
    ):
        raise AutopilotV66Error(
            "EPISODE_MASTER_AUTHORIZATION_REQUIRED:"
            + stage
        )

    if stage in LUNA_STAGES:
        target_id = (
            v64.BOOTSTRAP_ID
            if stage == "TOPIC_SELECTION"
            else episode_id
        )
        payload = v64._paid_luna_input(
            repo,
            episode_id,
            stage,
        )
        path = v64.authorize_luna_stage(
            repo,
            target_id,
            stage,
            payload,
            v64.LUNA_CONFIRMATION_PHRASE,
        )
        # TOPIC_SELECTION's concrete transport path sits under bootstrap, but
        # its authority derives from the NEXT_NEW_EPISODE master authorization.
        _annotate_derived_authorization(
            repo,
            path,
            master_id,
        )
        return

    if stage == "FINAL_TTS":
        if episode_id == v64.EP2_ID:
            path = v64.authorize_ep2_final_tts(
                repo,
                v64.EP2_TTS_CONFIRMATION_PHRASE,
            )
        else:
            v64.build_future_tts_queue(
                repo,
                episode_id,
            )
            path = v64.authorize_future_tts_queue(
                repo,
                episode_id,
                v64.TTS_CONFIRMATION_PHRASE,
            )
        _annotate_derived_authorization(
            repo,
            path,
            master_id,
        )
        return

    if stage == "PROVIDER_EXECUTION":
        path = v64.authorize_media_queue(
            repo,
            episode_id,
            v64.MEDIA_CONFIRMATION_PHRASE,
        )
        _annotate_derived_authorization(
            repo,
            path,
            master_id,
        )
        return

    raise AutopilotV66Error(
        "DERIVED_STAGE_AUTHORIZATION_NOT_IMPLEMENTED:"
        + stage
    )



def _is_pre_network_luna_authorization_invalid(
    exc: Exception,
    stage: str,
) -> bool:
    return (
        "LUNA_STAGE_AUTHORIZATION_INVALID:" + stage
    ) in str(exc)


def _archive_stale_luna_authorization(
    repo: Path,
    episode_id: str,
    stage: str,
) -> str:
    target_id = (
        v64.BOOTSTRAP_ID
        if stage == "TOPIC_SELECTION"
        else episode_id
    )
    path = luna_authorization_path(
        repo,
        target_id,
        stage,
    )
    if not path.is_file():
        return "NOT_PRESENT"

    payload = path.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    root = (
        repo
        / "projects"
        / (
            "_series"
            if episode_id == NEXT_EPISODE_ID
            else episode_id
        )
        / "orchestration/"
        "derived-luna-authorization-refresh-v6-6-r5"
    )
    root.mkdir(
        parents=True,
        exist_ok=True,
    )
    destination = (
        root
        / (
            stage.lower()
            + "-"
            + digest[:16]
            + ".stale-authorization.json"
        )
    )
    if not destination.is_file():
        destination.write_bytes(payload)
    record_invalidation(
        repo,
        episode_id if episode_id != NEXT_EPISODE_ID else target_id,
        path,
        reason="STALE_DERIVED_LUNA_AUTHORIZATION",
        classification="SUPERSEDED",
    )
    return "ARCHIVED_AND_PRESERVED"


def _execute_paid_stage_with_master_auth_refresh(
    repo: Path,
    base: AutopilotInspection,
) -> str:
    try:
        return v64.execute_current_stage(repo)
    except Exception as exc:
        if (
            base.stage not in LUNA_STAGES
            or not _is_pre_network_luna_authorization_invalid(
                exc,
                base.stage,
            )
        ):
            raise

        if not master_authorization_active(
            repo,
            base.episode_id,
        ):
            raise

        _archive_stale_luna_authorization(
            repo,
            base.episode_id,
            base.stage,
        )

        fresh = v64.inspect_autopilot(repo)
        if fresh.stage != base.stage:
            raise AutopilotV66Error(
                "LUNA_AUTH_REFRESH_STAGE_CHANGED:"
                + base.stage
                + "->"
                + fresh.stage
            ) from exc

        _ensure_legacy_stage_authorized(
            repo,
            fresh,
        )

        return v64.execute_current_stage(repo)


def execute_current_stage(
    repo_root: Path,
) -> str:
    repo = Path(repo_root).resolve()
    inspection = inspect_autopilot(repo)

    # The migrated EP002 paid stage is now executable only from the full
    # Desktop controller.  The legacy/autopilot API remains available for
    # inspection and historical compatibility, but cannot resume production.
    if (
        inspection.stage == "PROVIDER_EXECUTION"
        and inspection.episode_id == "episode-002-adam-temptation-fall-repentance"
    ):
        raise AutopilotV66Error(
            "PRODUCTION_RESUME_ENTRYPOINT_DESKTOP_UI_ONLY"
        )

    if inspection.stage == EVENTS_REVIEW_STAGE:
        raise AutopilotV66Error(
            "EVENTS_REVIEW_REQUIRED_BEFORE_AUTOPILOT_CONTINUES"
        )
    if inspection.terminal:
        return "READY_FOR_FINAL_HUMAN_REVIEW"

    base = v64.inspect_autopilot(repo)
    if base.stage != inspection.stage:
        raise AutopilotV66Error(
            "AUTOPILOT_STAGE_DESYNC"
        )

    if base.stage in PAID_STAGES:
        if not master_authorization_active(
            repo,
            base.episode_id,
        ):
            raise AutopilotV66Error(
                "FULL_EPISODE_AUTHORIZATION_REQUIRED:"
                + base.stage
            )

        retry_mode = (
            base.episode_id != NEXT_EPISODE_ID
            and retry_required(
                repo,
                base.episode_id,
                base.stage,
            )
        )
        if retry_mode:
            if not retry_authorized(
                repo,
                base.episode_id,
                base.stage,
            ):
                raise AutopilotV66Error(
                    "EXPLICIT_PAID_RETRY_AUTHORIZATION_REQUIRED:"
                    + base.stage
                )
            consume_paid_retry_authorization(
                repo,
                base.episode_id,
                base.stage,
            )

        _ensure_legacy_stage_authorized(
            repo,
            base,
        )

        try:
            result = _execute_paid_stage_with_master_auth_refresh(
                repo,
                base,
            )
        except Exception as exc:
            if (
                base.stage == "NARRATION_VISUAL_ALIGNMENT_GATE"
                and is_semantic_alignment_fail(
                    repo,
                    base.episode_id,
                    exc,
                )
            ):
                payload = v64._paid_luna_input(
                    repo,
                    base.episode_id,
                    base.stage,
                )
                result = resolve_until_pass(
                    repo,
                    base.episode_id,
                    payload["script"],
                    lambda: v64.execute_current_stage(repo),
                )
            else:
                if base.episode_id != NEXT_EPISODE_ID:
                    mark_paid_failure(
                        repo,
                        base.episode_id,
                        base.stage,
                        str(exc),
                    )
                raise

        if base.stage == "TOPIC_SELECTION":
            episode_id = str(result)
            migrate_next_episode_authorization(
                repo,
                episode_id,
            )

        if base.episode_id != NEXT_EPISODE_ID:
            resolve_paid_retry_guard(
                repo,
                base.episode_id,
                base.stage,
            )
        return result

    return v64.execute_current_stage(
        repo
    )


def run_until_gate(
    repo_root: Path,
    progress=None,
) -> RunUntilGateResult:
    repo = Path(repo_root).resolve()
    completed_this_run: list[str] = []
    fingerprints: set[str] = set()

    while True:
        inspection = inspect_autopilot(repo)

        if progress:
            progress(
                inspection.stage,
                len(inspection.completed_stages),
                len(STAGES),
                inspection.action,
            )

        if inspection.terminal:
            return RunUntilGateResult(
                "READY_FOR_FINAL_HUMAN_REVIEW",
                inspection.episode_id,
                inspection.stage,
                tuple(completed_this_run),
                inspection.detail,
            )

        if inspection.stage == EVENTS_REVIEW_STAGE:
            return RunUntilGateResult(
                "EVENTS_REVIEW_REQUIRED",
                inspection.episode_id,
                inspection.stage,
                tuple(completed_this_run),
                (
                    "Review and discuss episode events with Luna, then "
                    "approve them. Existing episode master authorization "
                    "will continue production automatically afterwards."
                ),
            )

        if (
            inspection.paid_stage
            and not inspection.authorized
        ):
            status = (
                "PAID_RETRY_AUTHORIZATION_REQUIRED"
                if inspection.action
                == "EXPLICIT_PAID_RETRY_AUTHORIZATION_REQUIRED"
                else "FULL_EPISODE_AUTHORIZATION_REQUIRED"
            )
            return RunUntilGateResult(
                status,
                inspection.episode_id,
                inspection.stage,
                tuple(completed_this_run),
                inspection.detail,
            )

        episode_for_digest = (
            v64.EP2_ID
            if inspection.episode_id
            == NEXT_EPISODE_ID
            else inspection.episode_id
        )
        digest = v64._state_digest(
            repo,
            episode_for_digest,
            inspection.stage,
        )

        emit_event(
            repo,
            inspection.episode_id,
            "STAGE_STARTED",
            stage=inspection.stage,
            message_ar="بدأ التنفيذ الفعلي للمرحلة",
            operation="تنفيذ المرحلة",
            progress_current=len(inspection.completed_stages),
            progress_total=len(STAGES),
            status="RUNNING",
        )
        try:
            execute_current_stage(
                repo
            )
        except Exception as exc:
            emit_event(
                repo,
                inspection.episode_id,
                "STAGE_FAILED",
                stage=inspection.stage,
                message_ar="توقفت المرحلة بخطأ",
                operation=str(exc),
                status="FAILED",
            )
            if (
                inspection.stage == "MEDIA_COST_PREFLIGHT"
                and is_visual_timeline_coverage_failure(exc)
            ):
                # A deterministic queue materialization found an
                # uncovered narration tail. This is a planning
                # correction under the active episode master auth,
                # not a provider retry.
                repair_visual_timeline_coverage(
                    repo,
                    inspection.episode_id,
                )

                # The prompt plan changed, so prior PASS artifacts
                # for alignment/duplicates are stale. Re-run them
                # before any media spend.
                ep = repo / "projects" / inspection.episode_id
                alignment_path = (
                    ep
                    / "preproduction/"
                    "narration-visual-alignment-gate-v6-2-1.json"
                )
                duplicate_path = (
                    ep
                    / "preproduction/"
                    "prompt-similarity-duplicate-gate-v6-1.json"
                )
                queue_path = (
                    ep
                    / "orchestration/"
                    "media-production-queue-v6-2-1.json"
                )
                cost_path = (
                    ep
                    / "orchestration/"
                    "media-cost-preflight-v6-2-1.json"
                )
                for stale in (
                    alignment_path,
                    duplicate_path,
                    queue_path,
                    cost_path,
                ):
                    if stale.is_file():
                        record_invalidation(
                            repo,
                            inspection.episode_id,
                            stale,
                            reason="VISUAL_TIMELINE_REPAIR_CHANGED_UPSTREAM_INPUT",
                            classification="STALE_BUT_PRESERVED",
                        )

                # Return the state machine to alignment so the
                # certified Luna alignment gate and deterministic
                # duplicate gate both run again automatically.
                continue

            if (
                inspection.stage == "MEDIA_COST_PREFLIGHT"
                and is_pre_spend_duplicate_failure(exc)
            ):
                repair_pre_spend_duplicate_gate(
                    repo,
                    inspection.episode_id,
                )
                continue

            decision = v64.classify_failure(exc)
            if (
                decision.automatic_repair_allowed
                and inspection.stage in LOCAL_STAGES
            ):
                fingerprint = hashlib.sha256(
                    (
                        inspection.stage
                        + "\n"
                        + str(exc)
                        + "\n"
                        + digest
                    ).encode("utf-8")
                ).hexdigest()
                if fingerprint in fingerprints:
                    raise AutopilotV66Error(
                        "SAFE_LOCAL_REPAIR_NO_PROGRESS_STOP:"
                        + inspection.stage
                        + ":"
                        + str(exc)
                    ) from exc
                fingerprints.add(fingerprint)
                if v64._safe_local_repair(
                    repo,
                    episode_for_digest,
                ):
                    continue
            raise

        completed_this_run.append(
            inspection.stage
        )
        emit_event(
            repo,
            inspection.episode_id,
            "STAGE_COMPLETED",
            stage=inspection.stage,
            message_ar="اكتملت المرحلة فعليًا",
            operation="اكتملت المرحلة",
            progress_current=len(inspect_autopilot(repo).completed_stages),
            progress_total=len(STAGES),
            status="COMPLETE",
        )

        if progress:
            new = inspect_autopilot(repo)
            progress(
                inspection.stage,
                len(new.completed_stages),
                len(STAGES),
                "COMPLETE",
            )
