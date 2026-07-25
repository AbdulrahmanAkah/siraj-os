from __future__ import annotations

import hashlib
import json
from pathlib import Path


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_adam_deterministic_topic_prefilter_v1() -> None:
    repo = Path(__file__).resolve().parents[2]
    project = repo / "projects" / "episode-001-adam"
    manifest_path = (
        project / "sources" / "secondary" / "topic-prefilter"
        / "topic-prefilter-manifest-v1.json"
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))

    assert manifest["status"] == "PASS_CANDIDATE_ONLY"
    assert manifest["book_count"] == 9
    assert manifest["scanned_page_count"] == 63900
    assert manifest["candidate_count"] > 0
    assert manifest["permissions"]["gemini_execution_enabled"] is False
    assert manifest["permissions"]["source_approval_changed"] is False
    assert manifest["permissions"]["quotation_approval_changed"] is False
    assert manifest["permissions"]["report_classification_changed"] is False

    for book in manifest["books"]:
        candidates = project / book["outputs"]["candidates"]["project_path"]
        attributions = project / book["outputs"]["attributions"]["project_path"]
        assert candidates.is_file()
        assert attributions.is_file()
        assert _sha256(candidates) == book["outputs"]["candidates"]["sha256"]
        assert _sha256(attributions) == book["outputs"]["attributions"]["sha256"]
        if book["candidate_count"]:
            first = json.loads(candidates.read_text(encoding="utf-8").splitlines()[0])
            assert first["candidate_tier"] in {"A", "B", "C", "D"}
            assert first["matched_categories"]
            assert first["canonical_locator"].startswith("shamela://local/")
            assert first["permissions"]["candidate_only"] is True
            assert first["permissions"]["allowed_for_gemini"] is False
