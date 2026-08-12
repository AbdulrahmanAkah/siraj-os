from pathlib import Path
import json

from src.application.siraj_episode_master_authorization_v6_6 import (
    FULL_EPISODE_CONFIRMATION_PHRASE,
    authorize_episode_cycle,
    master_authorization_active,
)
from src.application.siraj_event_review_v6_6 import (
    approve_events,
    events_approved,
    load_event_plan,
)
from src.application.siraj_autopilot_v6_6 import (
    EVENTS_REVIEW_STAGE,
)


def test_master_authorization_is_one_episode_scope(tmp_path):
    path = authorize_episode_cycle(
        tmp_path,
        "episode-003-test",
        "TOPIC_SELECTION",
        FULL_EPISODE_CONFIRMATION_PHRASE,
    )
    assert path.is_file()
    assert master_authorization_active(
        tmp_path,
        "episode-003-test",
    )
    payload = json.loads(
        path.read_text(encoding="utf-8")
    )
    assert payload["paid_retry_included"] is False
    assert payload["automatic_paid_retry"] is False
    assert payload["publishing"] == "HUMAN_ONLY"


def test_event_plan_gate_materializes_and_approves(tmp_path):
    repo = tmp_path
    episode = "episode-003-test"
    research = (
        repo
        / "projects"
        / episode
        / "research"
    )
    research.mkdir(parents=True)
    (
        research / "source-claim-matrix-v6-3.json"
    ).write_text(
        json.dumps(
            {
                "status": "PASS",
                "claims": [
                    {
                        "claim_id": "C001",
                        "text": "حدث أول",
                    },
                    {
                        "claim_id": "C002",
                        "text": "حدث ثان",
                    },
                ],
                "canonical_events": [
                    {
                        "event_id": "E1",
                        "title_ar": "الحدث الأول",
                        "summary_ar": "بداية الحدث",
                        "claim_ids": ["C001"],
                    },
                    {
                        "event_id": "E2",
                        "title_ar": "الحدث الثاني",
                        "summary_ar": "نتيجة الحدث",
                        "claim_ids": ["C002"],
                    },
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    plan = load_event_plan(repo, episode)
    assert plan["event_count"] == 2
    assert not events_approved(repo, episode)
    approve_events(repo, episode)
    assert events_approved(repo, episode)


def test_original_dashboard_uses_v66_wrapper_and_live_monitor():
    repo = Path(__file__).resolve().parents[1]
    integration = (
        repo
        / "src/presentation/desktop/v6_dashboard_integration.py"
    ).read_text(encoding="utf-8-sig")
    adapter = (
        repo
        / "src/presentation/desktop/v6_dashboard_state_adapter.py"
    ).read_text(encoding="utf-8-sig")

    assert "siraj_autopilot_v6_6" in integration
    assert "LiveProductionMonitorV66" in integration
    assert "EventReviewDialogV66" in integration
    assert "تفويض الإنتاج الكامل للحلقة" in integration
    assert "شاشة الإنتاج المباشر" in integration
    assert "siraj_autopilot_v6_6" in adapter
    assert EVENTS_REVIEW_STAGE == "EVENTS_REVIEW_AND_APPROVAL"


def test_policy_locks_one_auth_events_review_and_no_auto_retry():
    repo = Path(__file__).resolve().parents[1]
    policy = json.loads(
        (
            repo
            / "projects/_series/"
            "siraj-episode-autonomy-policy-v6.6.json"
        ).read_text(encoding="utf-8-sig")
    )
    assert policy["single_episode_authorization"] is True
    assert policy["paid_retry_is_separate_exception"] is True
    assert policy["automatic_paid_retry"] is False
    assert (
        policy["future_episode_event_review"]["human_approval_required"]
        is True
    )
    assert (
        policy["future_episode_event_review"]["post_approval_autopilot"]
        is True
    )
    assert policy["live_production_monitor"]["automatic_refresh"] is True
