import json
from pathlib import Path


def _read_jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def test_adam_exact_source_registry_phase1_contracts() -> None:
    root = Path(__file__).resolve().parents[2]
    project = root / "projects" / "episode-001-adam"
    registry = _read_jsonl(project / "sources" / "exact-source-registry-v1.jsonl")
    plan = json.loads((project / "sources" / "acquisition-plan-v1.json").read_text(encoding="utf-8-sig"))
    package = json.loads((project / "contracts" / "source-package-v1.exact-draft.json").read_text(encoding="utf-8-sig"))
    assert len(registry) == 20
    assert len({item["exact_source_id"] for item in registry}) == 20
    assert sum(item["source_kind"] == "QURAN_PASSAGE" for item in registry) == 11
    assert sum(item["source_kind"] == "HADITH_REPORT" for item in registry) == 9
    assert all(item["allowed_for_extraction"] is False for item in registry)
    assert all(item["allowed_for_quotation"] is False for item in registry)
    assert plan["status"] == "READY_FOR_LOCAL_ASSET_ACQUISITION"
    assert plan["asset_family_count"] == 5
    exact_ids = {item["exact_source_id"] for item in registry}
    package_ids = {item["source_id"] for item in package["source_items"]}
    assert exact_ids <= package_ids
    assert package["package_status"] == "DRAFT_EXACT_LOCATORS_ASSETS_PENDING"
    assert all(item["access_status"] == "PLANNED" for item in package["source_items"])
