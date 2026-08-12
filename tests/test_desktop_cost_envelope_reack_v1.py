from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from src.application.artifact_provenance_v1 import read_jsonl
from src.application.desktop_cost_envelope_reack_v1 import (
    CostEnvelopeReackError,
    DesktopCostEnvelopeReackService,
    REACK_RECEIPT_LEDGER,
    VALID_STATUS,
    reack_receipt_path,
)
from src.application.desktop_media_cost_preflight_v1 import (
    read_persisted_media_cost_preflight,
)
from src.application.desktop_resume_readiness_v1 import (
    DESKTOP_SOURCE,
    EPISODE_002,
    DesktopProductionResumeController,
)
from src.application.artifact_provenance_v1 import sha256_file


REPO = Path(__file__).resolve().parents[1]


def _fixture(tmp_path: Path) -> Path:
    root = tmp_path / "siraj-reack-fixture"
    source = REPO / "projects" / EPISODE_002
    target = root / "projects" / EPISODE_002
    # The real fixture may now contain the human's valid re-ack receipt.  The
    # tests below intentionally exercise the pre-ack branch, so do not copy
    # that real receipt into the isolated fixture.
    shutil.copytree(
        source,
        target,
        ignore=shutil.ignore_patterns(
            REACK_RECEIPT_LEDGER,
            "provider-execution-v1",
        ),
    )
    return root


def _review_snapshot(fixture: Path) -> dict[str, object]:
    review = read_persisted_media_cost_preflight(fixture, EPISODE_002)
    snapshot = review.as_dict()
    snapshot["reviewed_at_utc"] = "2026-08-10T00:00:00Z"
    return snapshot


def test_review_is_read_only_and_cancel_has_no_receipt(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    snapshot = _review_snapshot(fixture)
    assert snapshot["production_authorization"] == (
        "ACTIVE_BUT_UNBOUND_REACK_REQUIRED"
    )
    assert not reack_receipt_path(fixture, EPISODE_002).exists()


def test_confirmation_binds_exact_review_without_provider_execution(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    snapshot = _review_snapshot(fixture)
    before_ledger = sha256_file(
        fixture / "projects" / EPISODE_002 / "orchestration" / "episode-transition-ledger-v1.jsonl"
    )
    outcome = DesktopCostEnvelopeReackService(fixture, EPISODE_002).confirm(
        snapshot,
        source=DESKTOP_SOURCE,
    )
    assert outcome.status == "COMMITTED"
    assert outcome.authorization_status == VALID_STATUS
    assert outcome.cost_envelope_reack_required is False
    assert outcome.provider_execution_allowed is True
    assert outcome.provider_calls == 0
    assert outcome.paid_attempts_created == 0
    assert outcome.provider_execution_started is False
    assert sha256_file(
        fixture / "projects" / EPISODE_002 / "orchestration" / "episode-transition-ledger-v1.jsonl"
    ) == before_ledger
    receipt_path = reack_receipt_path(fixture, EPISODE_002)
    rows = read_jsonl(receipt_path)
    assert len(rows) == 1
    receipt = rows[0]
    assert receipt["binding"]["maximum_cost_envelope"] == {
        "amount": 25.9009,
        "currency": "USD",
    }
    assert receipt["binding"]["media_plan_sha256"] == (
        "50efe3d6e9b1f49a4d9867781a371cb80c3cd567799aa96af520212674fb3bf9"
    )
    assert receipt["binding"]["provider_request_plan_sha256"] == (
        "d602f3b61665baeccb6b27b42c23fe2857bd84b65620cc40dbf0b48f24eb87d3"
    )
    assert receipt["binding"]["preflight_result"]["payload_sha256"] == (
        "72757a01104f4bbe4a6a3a202c31174ace37090a5d4ce6bad475cd7d52e6b88c"
    )
    assert receipt["binding"]["creative_overlay_sha256"] == (
        "254c600144032f621d44ff38b33409fc0875da1aaf9310f106fb347b86205509"
    )
    assert receipt["binding"]["structural_fingerprint"] == (
        "94471a3ce54826460cc41d3c15b6d430c6a23b58d5f20b34f21db69cccd32f42"
    )
    review = read_persisted_media_cost_preflight(fixture, EPISODE_002)
    assert review.production_authorization == VALID_STATUS
    assert review.provider_execution_allowed is True


def test_stale_review_is_rejected_before_receipt(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    snapshot = _review_snapshot(fixture)
    envelope = dict(snapshot["cost_envelope_usd"])
    envelope["upper_bound"] = 25.9008
    snapshot["cost_envelope_usd"] = envelope
    with pytest.raises(CostEnvelopeReackError, match="STALE_STATE_REVIEW_REQUIRED"):
        DesktopCostEnvelopeReackService(fixture, EPISODE_002).confirm(
            snapshot,
            source=DESKTOP_SOURCE,
        )
    assert not reack_receipt_path(fixture, EPISODE_002).exists()


def test_exact_duplicate_acknowledgement_is_idempotent(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    snapshot = _review_snapshot(fixture)
    service = DesktopCostEnvelopeReackService(fixture, EPISODE_002)
    first = service.confirm(snapshot, source=DESKTOP_SOURCE)
    second = service.confirm(snapshot, source=DESKTOP_SOURCE)
    assert first.status == "COMMITTED"
    assert second.status == "ALREADY_COMMITTED"
    assert second.receipt_id == first.receipt_id
    assert len(read_jsonl(reack_receipt_path(fixture, EPISODE_002))) == 1


def test_non_desktop_source_is_rejected(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    with pytest.raises(CostEnvelopeReackError, match="DESKTOP_UI_ONLY"):
        DesktopCostEnvelopeReackService(fixture, EPISODE_002).confirm(
            _review_snapshot(fixture),
            source="CLI",
        )


def test_resume_before_ack_is_blocked_and_after_ack_uses_provider_stage(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    controller = DesktopProductionResumeController(fixture, EPISODE_002)
    with pytest.raises(Exception, match="COST_ENVELOPE_REACK_REQUIRED"):
        controller.simulate_offline_resume(
            source=DESKTOP_SOURCE,
            stage_runner=lambda stage: stage,
        )
    DesktopCostEnvelopeReackService(fixture, EPISODE_002).confirm(
        _review_snapshot(fixture),
        source=DESKTOP_SOURCE,
    )
    observed: list[str] = []
    result = controller.simulate_offline_resume(
        source=DESKTOP_SOURCE,
        stage_runner=lambda stage: observed.append(stage) or "FAKE_PROVIDER_GATEWAY",
    )
    assert result == "FAKE_PROVIDER_GATEWAY"
    assert observed == ["PROVIDER_EXECUTION"]


def test_ui_confirmation_and_active_policy_wording_are_explicit() -> None:
    dialog = (
        REPO / "src" / "presentation" / "desktop" / "media_preflight_review_v1.py"
    ).read_text(encoding="utf-8")
    window = (
        REPO / "src" / "presentation" / "desktop" / "main_window.py"
    ).read_text(encoding="utf-8")
    assert "Confirm cost envelope" in dialog
    assert "Cancel" in dialog
    assert "This action authorizes the reviewed cost envelope." in dialog
    assert "It DOES NOT submit provider requests." in dialog
    assert "PASS — mandatory range / directorial selection" in dialog
    assert "DesktopCostEnvelopeReackService" in window
    assert "CostEnvelopeReackConfirmationDialog" in window
    assert REACK_RECEIPT_LEDGER in (
        REPO / "src" / "application" / "desktop_cost_envelope_reack_v1.py"
    ).read_text(encoding="utf-8")
