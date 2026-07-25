from __future__ import annotations

import hashlib
import json
from pathlib import Path


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_adam_secondary_lucene_normalized_export_v2() -> None:
    repo = Path(__file__).resolve().parents[2]
    project = repo / "projects" / "episode-001-adam"
    path = (
        project
        / "sources"
        / "secondary"
        / "normalized-export-manifest-v1.json"
    )
    manifest = json.loads(path.read_text(encoding="utf-8-sig"))

    assert manifest["status"] == "PASS_READY_FOR_BOUNDED_LOCAL_SEARCH"
    assert manifest["storage_contract"] == "HYBRID_SQLITE_AND_LUCENE"
    assert manifest["book_count"] == 9
    assert manifest["total_page_records"] > 0
    assert manifest["permissions"]["gemini_execution_enabled"] is False

    for book in manifest["books"]:
        assert book["validation"]["status"] == "VALID"
        assert book["normalized_files"]["pages"]["rows"] > 0
        assert (
            book["source_integrity"]["materialized_database_sha256"]
            == book["source_integrity"]["installation_database_sha256"]
        )
        pages = project / book["normalized_files"]["pages"]["project_path"]
        toc = project / book["normalized_files"]["toc"]["project_path"]
        assert pages.is_file()
        assert toc.is_file()
        assert sha256_file(pages) == book["normalized_files"]["pages"]["sha256"]
        assert sha256_file(toc) == book["normalized_files"]["toc"]["sha256"]
        first = json.loads(
            pages.read_text(encoding="utf-8").splitlines()[0]
        )
        assert first["content_raw"].strip()
        assert first["canonical_locator"].startswith("shamela://local/")
