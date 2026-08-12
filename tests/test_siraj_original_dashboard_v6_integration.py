from pathlib import Path

from src.application.siraj_one_click_autopilot_v6_4 import (
    inspect_autopilot,
)
from src.presentation.desktop.v6_dashboard_state_adapter import (
    V6_STAGE_AR,
    build_v6_dashboard_snapshot,
)
from src.presentation.desktop.v6_dashboard_integration import (
    MACRO_LABELS,
    install_v6_runtime_bridge,
)


def test_v6_stage_labels_are_complete_for_current_pipeline():
    assert V6_STAGE_AR["FINAL_TTS"] == "الصوت النهائي"
    assert (
        V6_STAGE_AR["READY_FOR_FINAL_HUMAN_REVIEW"]
        == "جاهزة للمراجعة البشرية النهائية"
    )


def test_original_workflow_is_reframed_to_v6_macro_stages():
    install_v6_runtime_bridge()
    from src.presentation.desktop.widgets import WorkflowStrip

    assert WorkflowStrip._LABELS == MACRO_LABELS
    assert "النطق والصوت" in WorkflowStrip._LABELS
    assert "المونتاج والجودة" in WorkflowStrip._LABELS


def test_actual_repository_snapshot_tracks_current_v6_stage():
    repo = Path(__file__).resolve().parents[1]
    inspection = inspect_autopilot(repo)
    snapshot = build_v6_dashboard_snapshot(repo)

    assert snapshot.active_episode_id == (
        "episode-002-adam-temptation-fall-repentance"
    )
    assert inspection.episode_id == snapshot.active_episode_id

    active = snapshot.active_episode
    assert active is not None

    expected_label = V6_STAGE_AR.get(
        inspection.stage,
        inspection.stage,
    )
    assert active.stage_label_ar == expected_label

    if inspection.stage == "FINAL_TTS":
        assert active.provider == "ELEVENLABS"
        assert active.model == "eleven_multilingual_v2"
        assert active.next_action_ar.startswith("تفويض")
    elif inspection.stage in {
        "AUDIO_TIMESTAMPS_AND_BEATS",
        "PROMPT_SIMILARITY_AND_DUPLICATE_GATE",
        "MEDIA_COST_PREFLIGHT",
        "LOCAL_ASSEMBLY_AND_MONTAGE",
    }:
        assert active.provider == "LOCAL"
        assert active.model == "Deterministic V6"
    elif inspection.stage == "PROVIDER_EXECUTION":
        assert active.provider == "RUNWARE"
    elif inspection.stage == "READY_FOR_FINAL_HUMAN_REVIEW":
        assert active.provider == "HUMAN"


def test_original_main_window_contains_embedded_v6_center():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo / "src/presentation/desktop/main_window.py"
    ).read_text(encoding="utf-8-sig")

    assert "V6CommandCenter" in source
    assert "build_v6_dashboard_snapshot" in source
    assert "self.v6_command_center" in source
    assert "primary_action_callback=self._open_production_console" in source
    assert "canonical_state_reader=self._read_authoritative_state" in source
    assert "self.v6_command_center.primary_action()" not in source


def test_old_40_dollar_policy_removed_from_original_settings():
    repo = Path(__file__).resolve().parents[1]
    source = (
        repo / "src/presentation/desktop/complete_workspace_v1.py"
    ).read_text(encoding="utf-8-sig")

    assert "حد الحلقة 40$" not in source
    assert "الفيديو المولد لا يتجاوز ثلثي الحلقة" in source
    assert "لا إعادة محاولة مدفوعة تلقائية" in source
