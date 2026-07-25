from __future__ import annotations

import json
from pathlib import Path


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def test_adam_secondary_source_discovery_phase2_contracts() -> None:
    root = Path(__file__).resolve().parents[2]
    project = root / "projects" / "episode-001-adam"
    secondary = project / "sources" / "secondary"
    registry = _read_jsonl(secondary / "work-source-registry-v1.jsonl")
    candidates = json.loads((secondary / "shamela-book-candidates-v1.json").read_text(encoding="utf-8-sig"))
    selection = json.loads((secondary / "asset-selection.template.json").read_text(encoding="utf-8-sig"))
    package = json.loads((project / "contracts" / "source-package-v1.discovery-draft.json").read_text(encoding="utf-8-sig"))
    assert len(registry) == 12
    assert len({item["work_source_id"] for item in registry}) == 12
    assert sum(item["source_kind"].endswith("WORK") for item in registry) == 10
    assert sum(item["source_kind"] == "ISRAILIYYAT_ATTRIBUTION_PROFILE" for item in registry) == 2
    assert all(item["allowed_for_extraction"] is False for item in registry)
    assert all(item["allowed_for_quotation"] is False for item in registry)
    assert candidates["target_work_count"] == 10
    assert candidates["catalog_book_count"] > 0
    assert len(selection["selections"]) == 10
    assert all(item["selected_book_id"] is None for item in selection["selections"].values())
    assert package["package_status"] == "DRAFT_SECONDARY_WORK_SELECTION_PENDING"
    assert all(item["allowed_for_extraction"] is False for item in package["source_items"] if item["source_id"].startswith("SRC-TAFSIR-") or item["source_id"].startswith("SRC-HISTORY-") or item["source_id"].startswith("SRC-ISRAILIYYAT-"))
