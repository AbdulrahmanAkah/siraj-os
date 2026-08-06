import json
from pathlib import Path

import pytest

import src.application.consolidated_episode_production_controller_v2 as controller


def _write(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False),
        encoding="utf-8",
    )


def _prepare(
    root: Path,
    *,
    status: str,
    authorization: bool = True,
) -> None:
    _write(
        root / controller.ORCHESTRATOR_STATE_REL,
        {
            "current_episode_id": controller.EPISODE_ID,
            "status": status,
            "stage": "AUTOMATIC_QA",
            "last_error": "old master failed QA",
        },
    )
    if authorization:
        _write(
            root / controller.AUTHORIZATION_REL,
            {
                "status": "ACTIVE",
                "maximum_authorized_usd": 34.864375,
            },
        )
    shots = [
        {
            "shot_id": f"SH-{index:03d}",
            "luna_prompt_certification_v2": {
                "status": "CERTIFIED",
            },
        }
        for index in range(1, 71)
    ]
    _write(
        root / controller.CERTIFIED_STORYBOARD_REL,
        {"shots": shots},
    )


def test_stale_automatic_qa_state_is_rebased_with_backup(
    tmp_path: Path,
) -> None:
    _prepare(tmp_path, status="AUTOMATIC_QA_BLOCKED")
    result = controller._prepare_orchestrator_for_v2_media_queue_materialization(
        tmp_path
    )
    assert result["state_changed"] is True
    state = json.loads(
        (tmp_path / controller.ORCHESTRATOR_STATE_REL)
        .read_text(encoding="utf-8")
    )
    assert state["status"] == (
        "EDITORIAL_PIPELINE_COMPLETE_BUDGET_PREFLIGHT_QUEUED"
    )
    assert state["stage"] == "BUDGET_PREFLIGHT"
    assert state["last_error"] is None
    backup = tmp_path / controller.V2_STATE_REBASE_BACKUP_REL
    assert backup.is_file()
    old = json.loads(backup.read_text(encoding="utf-8"))
    assert old["status"] == "AUTOMATIC_QA_BLOCKED"


def test_compatible_queue_state_is_idempotent(
    tmp_path: Path,
) -> None:
    _prepare(tmp_path, status="MEDIA_QUEUE_READY")
    result = controller._prepare_orchestrator_for_v2_media_queue_materialization(
        tmp_path
    )
    assert result["state_changed"] is False
    assert result["status"] == "ALREADY_COMPATIBLE"


def test_unrelated_active_state_is_not_rebased(
    tmp_path: Path,
) -> None:
    _prepare(tmp_path, status="RUNNING_EVIDENCE_RESEARCH")
    with pytest.raises(
        controller.ConsolidatedProductionError,
        match="V2_MEDIA_QUEUE_STATE_REBASE_NOT_ALLOWED",
    ):
        controller._prepare_orchestrator_for_v2_media_queue_materialization(
            tmp_path
        )


def test_rebase_requires_existing_explicit_authorization(
    tmp_path: Path,
) -> None:
    _prepare(
        tmp_path,
        status="AUTOMATIC_QA_BLOCKED",
        authorization=False,
    )
    with pytest.raises(
        controller.ConsolidatedProductionError,
        match="V2_MEDIA_QUEUE_STATE_REBASE_AUTHORIZATION_REQUIRED",
    ):
        controller._prepare_orchestrator_for_v2_media_queue_materialization(
            tmp_path
        )
