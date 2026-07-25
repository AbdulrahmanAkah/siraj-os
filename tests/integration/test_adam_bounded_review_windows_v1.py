from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_adam_bounded_review_windows_v1() -> None:
    repo = Path(__file__).resolve().parents[2]
    project = repo / "projects" / "episode-001-adam"
    manifest_path = project / "sources" / "secondary" / "bounded-review-windows" / "bounded-review-window-manifest-v1.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))

    assert manifest["status"] == "PASS_HUMAN_REVIEW_QUEUE_READY"
    assert manifest["book_count"] == 9
    assert manifest["review_window_count"] > 0
    assert manifest["permissions"]["gemini_execution_enabled"] is False
    assert manifest["permissions"]["source_approval_changed"] is False
    assert manifest["permissions"]["quotation_approval_changed"] is False
    assert manifest["permissions"]["report_classification_changed"] is False
    assert manifest["permissions"]["israiliyyat_classification_changed"] is False

    for book in manifest["books"]:
        assert book["review_window_count"] <= book["review_window_limit"]
        assert book["review_window_character_count"] <= book["book_character_limit"]
        windows_path = project / book["outputs"]["review_windows"]["project_path"]
        draft_path = project / book["outputs"]["gemini_input_draft"]["project_path"]
        assert windows_path.is_file()
        assert draft_path.is_file()
        assert _sha256(windows_path) == book["outputs"]["review_windows"]["sha256"]
        assert _sha256(draft_path) == book["outputs"]["gemini_input_draft"]["sha256"]

        for line in windows_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            window = json.loads(line)
            assert window["character_count"] <= book["window_character_limit"] + 30
            assert window["permissions"]["allowed_for_gemini"] is False
            assert window["permissions"]["candidate_only"] is True
            assert window["human_review"]["status"] == "PENDING"

        for line in draft_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            draft = json.loads(line)
            assert draft["permissions"]["allowed_for_gemini"] is False
            assert draft["instruction_status"] == "BLOCKED_PENDING_HUMAN_WINDOW_APPROVAL"
