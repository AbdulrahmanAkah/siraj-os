from dataclasses import replace
import json
from pathlib import Path
import shutil

import pytest

from src.application.artifact_provenance_v1 import sha256_file
from src.application.desktop_media_cost_preflight_v1 import (
    MediaCostPreflightError,
    read_persisted_media_cost_preflight,
    validate_persisted_media_cost_preflight_review,
)


REPO = Path(__file__).resolve().parents[1]
EPISODE = "episode-002-adam-temptation-fall-repentance"


def _post_preflight_fixture(tmp_path: Path) -> Path:
    fixture = tmp_path / "siraj-post-preflight"
    relative_files = [
        f"projects/{EPISODE}/orchestration/episode-transition-ledger-v1.jsonl",
        f"projects/{EPISODE}/orchestration/media-cost-preflight-v1.json",
        f"projects/{EPISODE}/orchestration/episode-creative-promotion-state-v1.json",
        f"projects/{EPISODE}/orchestration/prompt-similarity-duplicate-gate-promoted-v1.json",
        f"projects/{EPISODE}/orchestration/luna-gate-001-local-closure-v1.json",
        f"projects/{EPISODE}/orchestration/episode-master-paid-authorization-v6-6.json",
        f"projects/{EPISODE}/preproduction/audio-bound-storyboard-v6-1.json",
        f"projects/{EPISODE}/preproduction/audio-timestamps-and-beats-v6-1.json",
        f"projects/{EPISODE}/preproduction/siraj-creative-shot-direction-promoted-v1.json",
        f"projects/{EPISODE}/preproduction/siraj-promoted-provider-ready-prompt-plan-v1.json",
    ]
    for relative in relative_files:
        source = REPO / relative
        target = fixture / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    # Keep this legacy review fixture pre-V2: the live repository now has a
    # newer ledger-bound v2 result, while these assertions intentionally test
    # the historical v1 read model.
    ledger = fixture / f"projects/{EPISODE}/orchestration/episode-transition-ledger-v1.jsonl"
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows = rows[:21]
    ledger.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) for row in rows) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return fixture


def test_persisted_review_reads_exact_plan_without_recomputing(tmp_path: Path) -> None:
    fixture = _post_preflight_fixture(tmp_path)
    review = read_persisted_media_cost_preflight(fixture, EPISODE)
    assert review.result_file_sha256 == (
        "926dea2fc77cf25f2cec1726accc318e9d0d0039955a2e5f719dddacf72f7f05"
    )
    assert review.result_sha256 == (
        "fda41c50bdd5beaafb4b6bae27147bc41a8bf8b34c4b1ec57a8c93ab5e845de3"
    )
    assert review.summary["planned_provider_requests"] == 51
    assert review.summary["planned_image_requests"] == 37
    assert review.summary["planned_video_requests"] == 14
    assert review.summary["planned_local_graphics"] == 4
    assert review.summary["provider_requested_seconds"] == 112.0
    assert review.summary["generated_video_seconds"] == 21.669
    assert review.generated_video_percent == pytest.approx(3.474913, abs=1e-6)
    assert review.generated_video_ceiling_seconds == 415.723
    assert review.pricing_status == "UNKNOWN"
    assert review.estimated_total_cost_usd is None
    assert review.production_authorization == "VALID"
    assert review.provider_model_counts["RUNWARE/google:veo@3.1-lite"] == 14


def test_review_compare_and_set_rejects_stale_review(tmp_path: Path) -> None:
    fixture = _post_preflight_fixture(tmp_path)
    review = read_persisted_media_cost_preflight(fixture, EPISODE)
    stale = replace(review, current_ledger_head_sha256="0" * 64)
    with pytest.raises(MediaCostPreflightError, match="STALE_STATE_REVIEW_REQUIRED"):
        validate_persisted_media_cost_preflight_review(fixture, stale)


def test_review_ui_is_read_only_and_binds_dashboard_metrics(monkeypatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from src.presentation.desktop.main_window import SirajDesktopWindow
    from src.presentation.desktop.media_preflight_review_v1 import MediaPreflightReviewDialog

    ledger = REPO / "projects" / EPISODE / "orchestration" / "episode-transition-ledger-v1.jsonl"
    result = REPO / "projects" / EPISODE / "orchestration" / "media-cost-preflight-v1.json"
    auth = REPO / "projects" / EPISODE / "orchestration" / "episode-master-paid-authorization-v6-6.json"
    before = (sha256_file(ledger), sha256_file(result), sha256_file(auth))
    app = QApplication.instance() or QApplication([])
    window = SirajDesktopWindow(REPO)
    dialog = None
    try:
        assert window._canonical_state is not None
        assert window._canonical_state.current_stage == "PROVIDER_EXECUTION"
        assert window.v6_command_center.request_metric.text().endswith("95")
        assert "$25.900900" in window.v6_command_center.character_metric.text()
        review = read_persisted_media_cost_preflight(REPO, EPISODE)
        dialog = MediaPreflightReviewDialog(REPO, review, window)
        assert dialog.identity_labels["stage"].text() == "PROVIDER_EXECUTION"
        assert dialog.media_labels["requests"].text() == "95"
        assert dialog.cost_labels["authorization"].text() == "VALID_BOUND_TO_CURRENT_COST_ENVELOPE"
        assert not dialog.authorize_button.isVisible()
        assert (sha256_file(ledger), sha256_file(result), sha256_file(auth)) == before
    finally:
        if dialog is not None:
            dialog.close()
        window.close()
        app.processEvents()


def test_media_button_routes_provider_stage_to_review_not_resume(monkeypatch) -> None:
    pytest.importorskip("PySide6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from src.presentation.desktop.main_window import SirajDesktopWindow

    app = QApplication.instance() or QApplication([])
    window = SirajDesktopWindow(REPO)
    called: list[str] = []
    try:
        setattr(window, "_open_media_preflight_review", lambda: called.append("REVIEW"))
        active = window._active_episode()
        assert active is not None
        window._episode_action(active)
        assert called == ["REVIEW"]
        assert window._resume_worker is None
    finally:
        window.close()
        app.processEvents()
