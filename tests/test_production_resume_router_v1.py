from __future__ import annotations

from src.application.production_resume_router_v1 import (
    resolve_resume_directive_from_state,
)


def test_idle_routes_to_scope_generation() -> None:
    directive = resolve_resume_directive_from_state(
        {"status": "IDLE_READY_FOR_NEXT_EPISODE", "stage": "TOPIC_AND_EVENT_PROPOSAL"}
    )
    assert directive.action == "GENERATE_SCOPE"
    assert directive.target_tab == "orchestrator"
    assert directive.can_run_automatically is True


def test_scope_review_remains_human_gate() -> None:
    directive = resolve_resume_directive_from_state(
        {"status": "AWAITING_HUMAN_SCOPE_REVIEW", "stage": "HUMAN_SCOPE_REVIEW"}
    )
    assert directive.action == "REVIEW_SCOPE"
    assert directive.requires_human is True


def test_media_execution_keeps_paid_confirmation() -> None:
    directive = resolve_resume_directive_from_state(
        {"status": "MEDIA_QUEUE_READY", "stage": "RUNWARE_VIDEO_GENERATION"}
    )
    assert directive.action == "OPEN_MEDIA_EXECUTION"
    assert directive.requires_paid_confirmation is True


def test_local_stages_are_resumable() -> None:
    sfx = resolve_resume_directive_from_state(
        {"status": "MEDIA_EXECUTION_COMPLETE", "stage": "SFX_DESIGN"}
    )
    montage = resolve_resume_directive_from_state(
        {"status": "SFX_MIX_READY", "stage": "STRUCTURAL_MONTAGE"}
    )
    qa = resolve_resume_directive_from_state(
        {"status": "FINAL_RENDER_READY_FOR_QA", "stage": "AUTOMATIC_QA"}
    )
    assert sfx.action == "RUN_SFX"
    assert montage.action == "RUN_MONTAGE"
    assert qa.action == "RUN_QA"
    assert all(item.can_run_automatically for item in (sfx, montage, qa))


def test_final_review_and_publish_are_explicit() -> None:
    review = resolve_resume_directive_from_state(
        {"status": "AWAITING_HUMAN_FINAL_REVIEW", "stage": "HUMAN_FINAL_REVIEW"}
    )
    ready = resolve_resume_directive_from_state(
        {"status": "READY_TO_PUBLISH", "stage": "READY_TO_PUBLISH"}
    )
    assert review.action == "OPEN_FINAL_REVIEW"
    assert review.requires_human is True
    assert ready.action == "OPEN_PUBLISH_PACKAGE"
    assert ready.ready_to_publish is True
