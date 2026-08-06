import json
from pathlib import Path

import src.application.consolidated_episode_production_controller_v2 as controller


def _plan() -> controller.ConsolidatedProductionPlan:
    return controller.ConsolidatedProductionPlan(
        status="READY_FOR_CONSOLIDATED_FULL_EPISODE_AUTHORIZATION",
        episode_id=controller.EPISODE_ID,
        standard_status=(
            "READY_FOR_FULL_EPISODE_REBUILD_AUTHORIZATION"
        ),
        director_review_status="PASS",
        blocking_issue_count=0,
        prompt_status="ALL_LUNA_BATCHES_COMPLETE_READY_TO_CERTIFY",
        prompt_item_count=70,
        certified_prompt_count=70,
        prompt_batch_count=7,
        pending_prompt_batch_count=0,
        tts_status="READY_AWAITING_CONSOLIDATED_AUTHORIZATION",
        tts_block_count=43,
        generated_video_planned_usd=29.514375,
        prompt_direction_reserve_usd=0.35,
        tts_reserve_usd=3.0,
        other_media_reserve_usd=2.0,
        maximum_authorized_usd=35.064375,
        episode_hard_cap_usd=40.0,
        full_episode_production_authorized=False,
        next_stage="CONSOLIDATED_FULL_EPISODE_AUTHORIZATION",
    )


def test_snapshot_update_succeeds_normally(
    tmp_path: Path,
) -> None:
    path = tmp_path / controller.DESKTOP_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"standard_complete": True}),
        encoding="utf-8",
    )
    result = controller._update_desktop_snapshot(
        tmp_path,
        _plan(),
    )
    assert result["status"] == "PASS_DESKTOP_SNAPSHOT_UPDATED"
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["standard_complete"] is True
    assert value["consolidated_production_v2"][
        "certified_prompts"
    ] == 70


def test_permission_error_defers_without_stopping(
    tmp_path: Path,
    monkeypatch,
) -> None:
    path = tmp_path / controller.DESKTOP_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")

    def denied(*args, **kwargs):
        del args, kwargs
        raise PermissionError(13, "Permission denied", str(path))

    monkeypatch.setattr(
        controller,
        "_siraj_read_snapshot_with_windows_retry",
        denied,
    )
    result = controller._update_desktop_snapshot(
        tmp_path,
        _plan(),
    )
    assert result["status"] == "DEFERRED_DESKTOP_SNAPSHOT_UPDATE"
    pending = tmp_path / controller.DESKTOP_SNAPSHOT_PENDING_REL
    assert pending.is_file()
    value = json.loads(pending.read_text(encoding="utf-8"))
    assert value["provider_requests"] == 0
    assert value["paid_provider_requests"] == 0
    assert value["patch"]["consolidated_production_v2"][
        "certified_prompts"
    ] == 70


def test_invalid_derived_snapshot_is_rebuilt(
    tmp_path: Path,
) -> None:
    path = tmp_path / controller.DESKTOP_SNAPSHOT_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not-json", encoding="utf-8")
    result = controller._update_desktop_snapshot(
        tmp_path,
        _plan(),
    )
    assert result["status"] == "PASS_DESKTOP_SNAPSHOT_UPDATED"
    value = json.loads(path.read_text(encoding="utf-8"))
    assert value["consolidated_production_v2"][
        "prompt_batches_pending"
    ] == 0
