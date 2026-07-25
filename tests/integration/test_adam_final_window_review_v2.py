from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def test_adam_final_window_review_v2() -> None:
    repo = Path(__file__).resolve().parents[2]
    project = repo / "projects" / "episode-001-adam"
    root = project / "sources" / "secondary" / "final-window-review"
    decisions = json.loads((root / "adam-human-window-decisions-v1.json").read_text(encoding="utf-8-sig"))
    policy = json.loads((project / "editorial" / "narration-attribution-policy-v2.json").read_text(encoding="utf-8-sig"))
    assert decisions["review_status"] == "FINAL_COMPLETE"
    assert decisions["source_window_count"] == 207
    assert decisions["repaired_window_count"] == 39
    assert decisions["technical_defer_count"] == 0
    assert decisions["editorial_defer_count"] == 1
    assert Counter(row["decision"] for row in decisions["decisions"]) == Counter({"INCLUDE": 92, "EXCLUDE": 114, "DEFER": 1})
    assert len(decisions["decisions"]) == 207
    assert not any(row["reason_code"] == "WINDOW_TEXT_TRUNCATED_REEXPORT_REQUIRED" for row in decisions["decisions"])
    assert not any(row["scope_fit"] == "UNRESOLVED_INCOMPLETE_TEXT" for row in decisions["decisions"])
    assert decisions["permissions"]["gemini_execution_enabled"] is False
    assert decisions["permissions"]["hadith_grading_changed"] is False
    assert decisions["permissions"]["israiliyyat_classification_changed"] is False
    assert policy["status"] == "USER_APPROVED_IN_CONVERSATION"
    cases = {row["case"] for row in policy["narrative_rules"]}
    assert {"NON_PROPHET_SPEAKER", "PROPHETIC_HADITH_WITH_COMPANION", "MARFU_REPORT_THROUGH_TABII"} <= cases
    assert "يحفظ السند كاملًا كما ورد في المصدر." in policy["internal_research_rules"]
