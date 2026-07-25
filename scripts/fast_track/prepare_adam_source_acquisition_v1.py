from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EPISODE_ID = "episode-001-adam"
REGISTRY_SCHEMA = "siraj-exact-source-registry-v1"
PLAN_SCHEMA = "siraj-source-acquisition-plan-v1"
GEMINI_TEMPLATE_SCHEMA = "siraj-gemini-research-work-package-template-v1"
MATERIALIZATION_SCHEMA = "siraj-source-materialization-state-v1"
EXACT_PACKAGE_FILENAME = "source-package-v1.exact-draft.json"


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, raw in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        if not raw.strip():
            continue
        value = json.loads(raw)
        if not isinstance(value, dict):
            raise ValueError(f"JSONL_RECORD_NOT_OBJECT:{path}:{line_number}")
        records.append(value)
    return records


def write_text(path: Path, text: str, *, force: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = text.replace("\r\n", "\n")
    if path.exists():
        current = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n")
        if current == payload:
            return
        if not force:
            raise FileExistsError(f"DIVERGENT_FILE_EXISTS:{path}")
    path.write_text(payload, encoding="utf-8", newline="\n")


def write_json(path: Path, value: Any, *, force: bool) -> None:
    write_text(path, json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", force=force)


def write_jsonl(path: Path, records: list[dict[str, Any]], *, force: bool) -> None:
    write_text(path, "\n".join(canonical_json(item) for item in records) + "\n", force=force)


def exact_quran_records(seed_records: dict[str, dict[str, Any]], event_questions: dict[str, list[str]]) -> list[dict[str, Any]]:
    quran_specs = [
        ("SRC-QURAN-HUD-007", 11, "هود", 7, 7),
        ("SRC-QURAN-HIJR-026-027", 15, "الحجر", 26, 27),
        ("SRC-QURAN-BAQARAH-029-035", 2, "البقرة", 29, 35),
        ("SRC-QURAN-ARAF-011-019", 7, "الأعراف", 11, 19),
        ("SRC-QURAN-HIJR-028-043", 15, "الحجر", 28, 43),
        ("SRC-QURAN-ISRA-061-065", 17, "الإسراء", 61, 65),
        ("SRC-QURAN-KAHF-050", 18, "الكهف", 50, 50),
        ("SRC-QURAN-TAHA-115-120", 20, "طه", 115, 120),
        ("SRC-QURAN-SAD-071-085", 38, "ص", 71, 85),
        ("SRC-QURAN-NISA-001", 4, "النساء", 1, 1),
        ("SRC-QURAN-ARAF-172", 7, "الأعراف", 172, 172),
    ]
    result: list[dict[str, Any]] = []
    for parent_id, surah_number, surah_name, start, end in quran_specs:
        seed = seed_records[parent_id]
        events = sorted(set(seed.get("supports_event_ids", [])))
        questions = sorted({qid for event_id in events for qid in event_questions.get(event_id, [])})
        verse_range = str(start) if start == end else f"{start}-{end}"
        result.append({
            "exact_source_id": f"EXACT-{parent_id}",
            "parent_source_id": parent_id,
            "source_kind": "QURAN_PASSAGE",
            "work_title": "القرآن الكريم",
            "author": "",
            "asset_key": "QURAN_HAFS_UTHMANI",
            "canonical_locator": {
                "scheme": "QURAN_SURAH_AYAH",
                "surah_number": surah_number,
                "surah_name_ar": surah_name,
                "ayah_start": start,
                "ayah_end": end,
                "display": f"{surah_name} {verse_range}",
            },
            "parallel_locators": [],
            "supports_event_ids": events,
            "supports_question_ids": questions,
            "locator_status": "VERIFIED",
            "report_grading_status": "NOT_APPLICABLE",
            "final_usage_status": "LOCAL_ASSET_AND_CHECKSUM_REQUIRED",
            "acquisition_status": "LOCATOR_VERIFIED_ASSET_PENDING",
            "allowed_for_extraction": False,
            "allowed_for_quotation": False,
            "locator_verification_references": [
                "https://qurancomplex.gov.sa/quran-dev/",
                "https://tanzil.net/docs/uthmani",
            ],
            "notes": [
                "Use a locally stored UTF-8 Uthmani Hafs corpus matching the Medina Mushaf.",
                "Do not enable extraction or quotation until the local file and SHA-256 checksum are recorded.",
            ],
        })
    return result


def hadith_record(
    *,
    exact_id: str,
    parent_id: str,
    work_title: str,
    collection_key: str,
    canonical_number: str,
    book_ar: str,
    chapter_ar: str,
    events: list[str],
    event_questions: dict[str, list[str]],
    reference_url: str,
    parallel: list[dict[str, str]] | None = None,
    notes: list[str] | None = None,
) -> dict[str, Any]:
    questions = sorted({qid for event_id in events for qid in event_questions.get(event_id, [])})
    return {
        "exact_source_id": exact_id,
        "parent_source_id": parent_id,
        "source_kind": "HADITH_REPORT",
        "work_title": work_title,
        "author": "",
        "asset_key": collection_key,
        "canonical_locator": {
            "scheme": "COLLECTION_CANONICAL_NUMBER",
            "canonical_number": canonical_number,
            "book_ar": book_ar,
            "chapter_ar": chapter_ar,
            "display": f"{work_title} {canonical_number}",
        },
        "parallel_locators": parallel or [],
        "supports_event_ids": events,
        "supports_question_ids": questions,
        "locator_status": "VERIFIED",
        "report_grading_status": "PENDING_AUTHORIZED_HADITH_GRADING_POLICY",
        "final_usage_status": "HUMAN_HADITH_REVIEW_REQUIRED",
        "acquisition_status": "LOCATOR_VERIFIED_ASSET_PENDING",
        "allowed_for_extraction": False,
        "allowed_for_quotation": False,
        "locator_verification_references": [reference_url],
        "notes": (notes or []) + [
            "The locator is recorded; this artifact does not issue a final hadith grade.",
            "Final episode usage remains blocked pending the user-approved hadith grading authorities.",
        ],
    }


def exact_hadith_records(event_questions: dict[str, list[str]]) -> list[dict[str, Any]]:
    return [
        hadith_record(
            exact_id="EXACT-HADITH-BUKHARI-3191",
            parent_id="SRC-HADITH-BEGINNING-CREATION-001",
            work_title="صحيح البخاري",
            collection_key="SAHIH_AL_BUKHARI",
            canonical_number="3191",
            book_ar="كتاب بدء الخلق",
            chapter_ar="باب ما جاء في قول الله تعالى وهو الذي يبدأ الخلق ثم يعيده",
            events=["EV-ADAM-001", "EV-ADAM-002", "EV-ADAM-004"],
            event_questions=event_questions,
            reference_url="https://sunnah.com/bukhari:3191",
            parallel=[{"work_title": "صحيح البخاري", "canonical_number": "7418", "reference_url": "https://sunnah.com/bukhari:7418"}],
            notes=["Do not use this record alone as proof that the Pen preceded every created thing; the Pen report is recorded separately."],
        ),
        hadith_record(
            exact_id="EXACT-HADITH-ABUDAWUD-4700",
            parent_id="SRC-HADITH-BEGINNING-CREATION-001",
            work_title="سنن أبي داود",
            collection_key="SUNAN_ABI_DAWUD",
            canonical_number="4700",
            book_ar="كتاب السنة",
            chapter_ar="باب في القدر",
            events=["EV-ADAM-003"],
            event_questions=event_questions,
            reference_url="https://sunnah.com/abudawud:4700",
            parallel=[{"work_title": "جامع الترمذي", "canonical_number": "2155", "reference_url": "https://sunnah.com/tirmidhi:2155"}],
            notes=["Chronological synthesis with the Throne, water, decree-writing, heavens and earth requires a separate scholarly analysis."],
        ),
        hadith_record(
            exact_id="EXACT-HADITH-MUSLIM-2996",
            parent_id="SRC-HADITH-CREATION-MATERIALS-001",
            work_title="صحيح مسلم",
            collection_key="SAHIH_MUSLIM",
            canonical_number="2996",
            book_ar="كتاب الزهد والرقائق",
            chapter_ar="باب في أحاديث متفرقة",
            events=["EV-ADAM-005", "EV-ADAM-006", "EV-ADAM-020"],
            event_questions=event_questions,
            reference_url="https://sunnah.com/muslim:2996",
        ),
        hadith_record(
            exact_id="EXACT-HADITH-ABUDAWUD-4693",
            parent_id="SRC-HADITH-ADAM-EARTH-HANDFUL-001",
            work_title="سنن أبي داود",
            collection_key="SUNAN_ABI_DAWUD",
            canonical_number="4693",
            book_ar="كتاب السنة",
            chapter_ar="باب في القدر",
            events=["EV-ADAM-020", "EV-ADAM-021"],
            event_questions=event_questions,
            reference_url="https://sunnah.com/abudawud:4693",
        ),
        hadith_record(
            exact_id="EXACT-HADITH-MUSLIM-2611A",
            parent_id="SRC-HADITH-IBLIS-HOLLOW-001",
            work_title="صحيح مسلم",
            collection_key="SAHIH_MUSLIM",
            canonical_number="2611a",
            book_ar="كتاب البر والصلة والآداب",
            chapter_ar="باب خلق الإنسان خلقا لا يتمالك",
            events=["EV-ADAM-023", "EV-ADAM-024"],
            event_questions=event_questions,
            reference_url="https://sunnah.com/muslim:2611a",
        ),
        hadith_record(
            exact_id="EXACT-HADITH-BUKHARI-3326",
            parent_id="SRC-HADITH-ADAM-HEIGHT-SALAM-001",
            work_title="صحيح البخاري",
            collection_key="SAHIH_AL_BUKHARI",
            canonical_number="3326",
            book_ar="كتاب أحاديث الأنبياء",
            chapter_ar="باب خلق آدم صلوات الله عليه وذريته",
            events=["EV-ADAM-032", "EV-ADAM-033"],
            event_questions=event_questions,
            reference_url="https://sunnah.com/bukhari:3326",
            parallel=[
                {"work_title": "صحيح مسلم", "canonical_number": "2841", "reference_url": "https://sunnah.com/muslim:2841"},
                {"work_title": "صحيح البخاري", "canonical_number": "6227", "reference_url": "https://sunnah.com/bukhari:6227"},
            ],
            notes=["Parallel locators may represent the same report route and must not be counted automatically as independent corroboration."],
        ),
        hadith_record(
            exact_id="EXACT-HADITH-TIRMIDHI-3075",
            parent_id="SRC-HADITH-COVENANT-PROGENY-001",
            work_title="جامع الترمذي",
            collection_key="JAMI_AL_TIRMIDHI",
            canonical_number="3075",
            book_ar="كتاب تفسير القرآن عن رسول الله صلى الله عليه وسلم",
            chapter_ar="باب ومن سورة الأعراف",
            events=["EV-ADAM-060", "EV-ADAM-061"],
            event_questions=event_questions,
            reference_url="https://sunnah.com/tirmidhi:3075",
            notes=["The report's relation to Qur'an 7:172 and its chronology must be reviewed report-by-report."],
        ),
        hadith_record(
            exact_id="EXACT-HADITH-TIRMIDHI-3076",
            parent_id="SRC-HADITH-COVENANT-PROGENY-001",
            work_title="جامع الترمذي",
            collection_key="JAMI_AL_TIRMIDHI",
            canonical_number="3076",
            book_ar="كتاب تفسير القرآن عن رسول الله صلى الله عليه وسلم",
            chapter_ar="باب ومن سورة الأعراف",
            events=["EV-ADAM-061"],
            event_questions=event_questions,
            reference_url="https://sunnah.com/tirmidhi:3076",
            notes=["This report also contains material about Adam and Dawud that belongs to later story units and must not be imported automatically into Episode 1."],
        ),
        hadith_record(
            exact_id="EXACT-HADITH-BUKHARI-3331",
            parent_id="SRC-HADITH-WOMAN-RIB-001",
            work_title="صحيح البخاري",
            collection_key="SAHIH_AL_BUKHARI",
            canonical_number="3331",
            book_ar="كتاب أحاديث الأنبياء",
            chapter_ar="باب خلق آدم صلوات الله عليه وذريته",
            events=["EV-ADAM-070"],
            event_questions=event_questions,
            reference_url="https://sunnah.com/bukhari:3331",
            parallel=[
                {"work_title": "صحيح مسلم", "canonical_number": "1468a", "reference_url": "https://sunnah.com/muslim:1468a"},
                {"work_title": "صحيح مسلم", "canonical_number": "1467b", "reference_url": "https://sunnah.com/muslim:1467b"},
            ],
            notes=["The report states that woman was created from a rib; identifying the exact anatomical circumstance or chronology requires separate evidence."],
        ),
    ]


def exact_package_item(record: dict[str, Any]) -> dict[str, Any]:
    source_kind = record["source_kind"]
    authority = "REVELATION_PRIMARY" if source_kind == "QURAN_PASSAGE" else "HADITH_PENDING_AUTHORIZED_GRADING"
    return {
        "source_id": record["exact_source_id"],
        "source_type": "QURAN" if source_kind == "QURAN_PASSAGE" else "HADITH",
        "title": record["work_title"],
        "author": record.get("author", ""),
        "publisher": "",
        "publication_date": "",
        "edition": "",
        "language": "ar",
        "path": "",
        "checksum": "",
        "page/section availability": "LOCATOR_VERIFIED_ASSET_PENDING",
        "access_status": "PLANNED",
        "authority_class": authority,
        "primary_or_secondary": "PRIMARY",
        "allowed_for_extraction": False,
        "allowed_for_quotation": False,
        "copyright_or_usage_notes": "Local asset acquisition and rights review pending.",
        "notes": {
            "parent_source_id": record["parent_source_id"],
            "asset_key": record["asset_key"],
            "exact_locator": record["canonical_locator"],
            "parallel_locators": record["parallel_locators"],
            "supports_event_ids": record["supports_event_ids"],
            "supports_question_ids": record["supports_question_ids"],
            "locator_status": record["locator_status"],
            "report_grading_status": record["report_grading_status"],
            "final_usage_status": record["final_usage_status"],
        },
    }


def build_acquisition_plan(records: list[dict[str, Any]], created_at: str) -> dict[str, Any]:
    asset_specs = [
        {
            "asset_key": "QURAN_HAFS_UTHMANI",
            "title": "Qur'an Uthmani Hafs corpus",
            "priority": "CRITICAL",
            "preferred_authority": "King Fahd Glorious Qur'an Printing Complex developer platform",
            "acceptable_fallback": "Tanzil Uthmani text matching the Medina Mushaf",
            "normalized_target_path": "sources/normalized/quran/quran-uthmani-hafs-v1.jsonl",
            "record_count": sum(1 for item in records if item["asset_key"] == "QURAN_HAFS_UTHMANI"),
        },
        {
            "asset_key": "SAHIH_AL_BUKHARI",
            "title": "Sahih al-Bukhari Arabic text",
            "priority": "CRITICAL",
            "preferred_authority": "Verified local Shamela or authenticated Arabic edition export",
            "acceptable_fallback": "A rights-cleared, edition-identified Arabic digital text",
            "normalized_target_path": "sources/normalized/hadith/sahih-al-bukhari-v1.jsonl",
            "record_count": sum(1 for item in records if item["asset_key"] == "SAHIH_AL_BUKHARI"),
        },
        {
            "asset_key": "SAHIH_MUSLIM",
            "title": "Sahih Muslim Arabic text",
            "priority": "CRITICAL",
            "preferred_authority": "Verified local Shamela or authenticated Arabic edition export",
            "acceptable_fallback": "A rights-cleared, edition-identified Arabic digital text",
            "normalized_target_path": "sources/normalized/hadith/sahih-muslim-v1.jsonl",
            "record_count": sum(1 for item in records if item["asset_key"] == "SAHIH_MUSLIM"),
        },
        {
            "asset_key": "SUNAN_ABI_DAWUD",
            "title": "Sunan Abi Dawud Arabic text",
            "priority": "HIGH",
            "preferred_authority": "Verified local Shamela or authenticated Arabic edition export",
            "acceptable_fallback": "A rights-cleared, edition-identified Arabic digital text",
            "normalized_target_path": "sources/normalized/hadith/sunan-abi-dawud-v1.jsonl",
            "record_count": sum(1 for item in records if item["asset_key"] == "SUNAN_ABI_DAWUD"),
        },
        {
            "asset_key": "JAMI_AL_TIRMIDHI",
            "title": "Jami al-Tirmidhi Arabic text",
            "priority": "HIGH",
            "preferred_authority": "Verified local Shamela or authenticated Arabic edition export",
            "acceptable_fallback": "A rights-cleared, edition-identified Arabic digital text",
            "normalized_target_path": "sources/normalized/hadith/jami-al-tirmidhi-v1.jsonl",
            "record_count": sum(1 for item in records if item["asset_key"] == "JAMI_AL_TIRMIDHI"),
        },
    ]
    for item in asset_specs:
        item.update({
            "acquisition_method": "LOCAL_LIBRARY_EXPORT_OR_AUTHORIZED_DOWNLOAD",
            "required_normalized_format": "UTF8_JSONL",
            "required_fields": [
                "document_id", "work_title", "book", "chapter", "canonical_number",
                "arabic_text", "isnad", "matn", "source_locator",
            ],
            "acceptance_checks": [
                "FILE_INSIDE_EPISODE_PROJECT",
                "SHA256_RECORDED",
                "UTF8_DECODABLE",
                "REQUIRED_LOCATORS_PRESENT",
                "ARABIC_TEXT_NOT_EMPTY",
                "NO_COMMENTARY_MIXED_WITH_SOURCE_TEXT",
                "EDITION_OR_EXPORT_PROVENANCE_RECORDED",
            ],
            "status": "PENDING",
        })
    return {
        "schema_version": PLAN_SCHEMA,
        "episode_id": EPISODE_ID,
        "plan_id": "adam-01-source-acquisition-plan-v1",
        "status": "READY_FOR_LOCAL_ASSET_ACQUISITION",
        "scope": "PHASE_1_QURAN_AND_HADITH",
        "exact_record_count": len(records),
        "asset_family_count": len(asset_specs),
        "batches": [
            {"batch_id": "BATCH-01-QURAN", "order": 10, "asset_keys": ["QURAN_HAFS_UTHMANI"], "gate": "QURAN_TEXT_INTEGRITY"},
            {"batch_id": "BATCH-02-SAHIHAYN", "order": 20, "asset_keys": ["SAHIH_AL_BUKHARI", "SAHIH_MUSLIM"], "gate": "HADITH_LOCATOR_COVERAGE"},
            {"batch_id": "BATCH-03-SUNAN", "order": 30, "asset_keys": ["SUNAN_ABI_DAWUD", "JAMI_AL_TIRMIDHI"], "gate": "AUTHORIZED_HADITH_GRADING_POLICY_REQUIRED_BEFORE_FINAL_USAGE"},
        ],
        "asset_targets": asset_specs,
        "prohibitions": [
            "NO_AUTOMATIC_SOURCE_APPROVAL",
            "NO_AUTOMATIC_HADITH_GRADING",
            "NO_DORAR_HADITH_GRADING",
            "NO_GEMINI_WEB_SEARCH_AS_EVIDENCE",
            "NO_EXTRACTION_BEFORE_LOCAL_PATH_AND_CHECKSUM",
        ],
        "created_at": created_at,
        "updated_at": created_at,
        "input_fingerprint": "",
    }


def build_gemini_template(records: list[dict[str, Any]], created_at: str) -> dict[str, Any]:
    return {
        "schema_version": GEMINI_TEMPLATE_SCHEMA,
        "episode_id": EPISODE_ID,
        "work_package_id": "adam-01-gemini-research-template-v1",
        "status": "BLOCKED_SOURCE_ASSETS_PENDING",
        "purpose": "Extract evidence only from locally approved and checksummed source assets.",
        "source_selection_rule": {
            "require_access_status": "AVAILABLE",
            "require_allowed_for_extraction": True,
            "require_nonempty_path": True,
            "require_sha256_match": True,
            "exact_registry_record_count": len(records),
        },
        "supplied_context": [
            "episode definition",
            "research questions",
            "event map",
            "exact source registry",
            "selected local source passages",
            "editorial and religious methodology constraints",
        ],
        "model_instructions": [
            "Use only the supplied source content; do not browse the web.",
            "Do not invent a source, report, page, chapter, number, quotation, chain, or chronology.",
            "Every extracted passage must preserve source_id and exact_locator.",
            "Do not issue final hadith grades or final religious rulings.",
            "Do not treat parallel editions or duplicate routes as independent corroboration automatically.",
            "Label interpretive claims, historical reports, Isra'iliyyat, disagreements, and uncertainty explicitly.",
            "Return uncovered research questions as coverage gaps rather than guessing.",
            "Do not import material from later Adam story units merely because it occurs in the same report.",
        ],
        "required_output": {
            "extractor_version": "string",
            "extracted_passages": [
                {"passage_id": "string", "source_id": "string", "exact_locator": "string", "normalized_text": "string", "verbatim": True}
            ],
            "claims": [
                {"claim_id": "string", "claim_text": "string", "evidence_refs": ["passage_id"], "source_refs": ["source_id"], "verification_status": "CANDIDATE", "dispute_status": "UNDISPUTED_OR_PENDING", "uncertainty_language_requirement": "string"}
            ],
            "events": [],
            "entities": [],
            "locations": [],
            "chronology": [],
            "quotations": [],
            "disputed_points": [],
            "source_relationships": [],
            "unresolved_questions": [],
            "coverage_gaps": [],
            "warnings": [],
            "exclusions": [],
        },
        "human_review_required": True,
        "created_at": created_at,
    }


def build_readme() -> str:
    return """# Adam Episode Exact Source Registry v1

This directory separates source governance from Gemini extraction.

## Files

- `exact-source-registry-v1.jsonl`: exact Qur'an passages and exact hadith reports for Phase 1.
- `acquisition-plan-v1.json`: local asset families, order, and acceptance checks.
- `source-package-v1.exact-draft.json`: normalized draft source package with one item per exact record plus deferred tafsir/history/Isra'iliyyat work-level records.
- `source-materialization-state-v1.json`: records that no source asset is available yet.
- `gemini-work-package-template-v1.json`: bounded extraction instructions; it is blocked until local assets are checksummed and explicitly enabled.
- `asset-map.template.json`: paths remain empty until local source assets are prepared.

## Governance

Locator verification is not source acquisition, hadith grading, source approval, or evidence approval.
No item may be extracted or quoted until its local project-relative path and SHA-256 checksum are recorded.
The Tirmidhi and Abu Dawud reports remain subject to the user-approved hadith grading authorities.
Parallel locators must not be treated automatically as independent corroboration.
"""


def build_test() -> str:
    return '''import json\nfrom pathlib import Path\n\n\ndef _read_jsonl(path: Path):\n    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]\n\n\ndef test_adam_exact_source_registry_phase1_contracts() -> None:\n    root = Path(__file__).resolve().parents[2]\n    project = root / "projects" / "episode-001-adam"\n    registry = _read_jsonl(project / "sources" / "exact-source-registry-v1.jsonl")\n    plan = json.loads((project / "sources" / "acquisition-plan-v1.json").read_text(encoding="utf-8-sig"))\n    package = json.loads((project / "contracts" / "source-package-v1.exact-draft.json").read_text(encoding="utf-8-sig"))\n    assert len(registry) == 20\n    assert len({item["exact_source_id"] for item in registry}) == 20\n    assert sum(item["source_kind"] == "QURAN_PASSAGE" for item in registry) == 11\n    assert sum(item["source_kind"] == "HADITH_REPORT" for item in registry) == 9\n    assert all(item["allowed_for_extraction"] is False for item in registry)\n    assert all(item["allowed_for_quotation"] is False for item in registry)\n    assert plan["status"] == "READY_FOR_LOCAL_ASSET_ACQUISITION"\n    assert plan["asset_family_count"] == 5\n    exact_ids = {item["exact_source_id"] for item in registry}\n    package_ids = {item["source_id"] for item in package["source_items"]}\n    assert exact_ids <= package_ids\n    assert package["package_status"] == "DRAFT_EXACT_LOCATORS_ASSETS_PENDING"\n    assert all(item["access_status"] == "PLANNED" for item in package["source_items"])\n'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    project = repo / "projects" / EPISODE_ID
    editorial = project / "editorial"
    contracts = project / "contracts"
    sources_root = project / "sources"

    required = [
        editorial / "source-acquisition-register.jsonl",
        editorial / "event-map.json",
        editorial / "research-questions.json",
        contracts / "source-package-v1.draft.json",
        contracts / "episode-definition-v1.json",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_REQUIRED_FILES:\n" + "\n".join(missing))

    seed_list = read_jsonl(editorial / "source-acquisition-register.jsonl")
    seed_records = {str(item["source_id"]): item for item in seed_list}
    if len(seed_records) != len(seed_list):
        raise ValueError("DUPLICATE_PARENT_SOURCE_ID")

    events = read_json(editorial / "event-map.json")
    questions = read_json(editorial / "research-questions.json")
    event_questions = {str(item["event_id"]): list(item.get("question_ids", [])) for item in events}
    event_ids = set(event_questions)
    question_ids = {str(item["question_id"]) for item in questions}

    records = exact_quran_records(seed_records, event_questions) + exact_hadith_records(event_questions)
    exact_ids = [item["exact_source_id"] for item in records]
    if len(exact_ids) != len(set(exact_ids)):
        raise ValueError("DUPLICATE_EXACT_SOURCE_ID")
    parent_ids = {item["parent_source_id"] for item in records}
    missing_parents = sorted(parent_ids - set(seed_records))
    if missing_parents:
        raise ValueError("MISSING_PARENT_SOURCE_IDS:" + ",".join(missing_parents))
    dangling_events = sorted({eid for item in records for eid in item["supports_event_ids"] if eid not in event_ids})
    dangling_questions = sorted({qid for item in records for qid in item["supports_question_ids"] if qid not in question_ids})
    if dangling_events or dangling_questions:
        raise ValueError(f"DANGLING_REFS:events={dangling_events}:questions={dangling_questions}")

    base_package = read_json(contracts / "source-package-v1.draft.json")
    existing_plan_path = sources_root / "acquisition-plan-v1.json"
    existing_plan = read_json(existing_plan_path) if existing_plan_path.is_file() else {}
    created_at = str(existing_plan.get("created_at") or base_package.get("updated_at") or now_utc())
    plan = build_acquisition_plan(records, created_at)
    plan["input_fingerprint"] = fingerprint({key: value for key, value in plan.items() if key != "input_fingerprint"})
    gemini_template = build_gemini_template(records, created_at)

    exact_parent_ids = parent_ids
    deferred_items = [item for item in base_package["source_items"] if item["source_id"] not in exact_parent_ids]
    exact_items = [exact_package_item(item) for item in records]
    exact_package = dict(base_package)
    exact_package["source_package_id"] = "adam-01-source-package-exact-draft-v1"
    exact_package["title"] = "Adam Episode 1 exact-locator source package draft"
    exact_package["source_items"] = exact_items + deferred_items
    exact_package["package_status"] = "DRAFT_EXACT_LOCATORS_ASSETS_PENDING"
    exact_package["updated_at"] = created_at
    exact_package["input_fingerprint"] = ""
    exact_package["input_fingerprint"] = fingerprint({key: value for key, value in exact_package.items() if key != "input_fingerprint"})

    materialization_state = {
        "schema_version": MATERIALIZATION_SCHEMA,
        "episode_id": EPISODE_ID,
        "status": "NO_ASSETS_MATERIALIZED",
        "exact_record_count": len(records),
        "available_record_count": 0,
        "extractable_record_count": 0,
        "quotable_record_count": 0,
        "asset_families": {key: {"path": "", "checksum": "", "status": "PENDING"} for key in [
            "QURAN_HAFS_UTHMANI", "SAHIH_AL_BUKHARI", "SAHIH_MUSLIM", "SUNAN_ABI_DAWUD", "JAMI_AL_TIRMIDHI"
        ]},
        "updated_at": created_at,
    }
    asset_map = {
        "schema_version": "siraj-source-asset-map-v1",
        "episode_id": EPISODE_ID,
        "assets": {
            key: {"external_source_path": "", "copy_into_project": True, "rights_reviewed": False, "enable_extraction": False, "enable_quotation": False}
            for key in materialization_state["asset_families"]
        },
    }

    write_jsonl(sources_root / "exact-source-registry-v1.jsonl", records, force=args.force)
    write_json(sources_root / "acquisition-plan-v1.json", plan, force=args.force)
    write_json(sources_root / "gemini-work-package-template-v1.json", gemini_template, force=args.force)
    write_json(sources_root / "source-materialization-state-v1.json", materialization_state, force=args.force)
    write_json(sources_root / "asset-map.template.json", asset_map, force=args.force)
    write_text(sources_root / "README.md", build_readme(), force=args.force)
    write_json(contracts / EXACT_PACKAGE_FILENAME, exact_package, force=args.force)
    write_text(repo / "tests" / "integration" / "test_adam_exact_source_registry_v1.py", build_test(), force=args.force)

    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from src.application.research_verification_episode_v1.runtime import validate_source_package
    validation_errors = validate_source_package(exact_package, project_root=project, episode_id=EPISODE_ID)
    if validation_errors:
        raise SystemExit(json.dumps({"status": "FAIL", "source_package_errors": validation_errors}, ensure_ascii=False, indent=2))

    print(json.dumps({
        "status": "PASS",
        "exact_registry": str(sources_root / "exact-source-registry-v1.jsonl"),
        "acquisition_plan": str(sources_root / "acquisition-plan-v1.json"),
        "exact_source_package": str(contracts / EXACT_PACKAGE_FILENAME),
        "gemini_template": str(sources_root / "gemini-work-package-template-v1.json"),
        "counts": {
            "quran_passages": sum(item["source_kind"] == "QURAN_PASSAGE" for item in records),
            "hadith_reports": sum(item["source_kind"] == "HADITH_REPORT" for item in records),
            "exact_records": len(records),
            "deferred_work_level_sources": len(deferred_items),
            "exact_package_items": len(exact_package["source_items"]),
        },
        "source_approval_changed": False,
        "gemini_execution_enabled": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
