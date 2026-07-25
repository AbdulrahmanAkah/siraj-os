from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

EPISODE_ID = "episode-001-adam"
WORK_REGISTRY_SCHEMA = "siraj-secondary-work-source-registry-v1"
CANDIDATE_REPORT_SCHEMA = "siraj-shamela-book-candidate-report-v1"
SELECTION_SCHEMA = "siraj-secondary-source-selection-v1"
DISCOVERY_PLAN_SCHEMA = "siraj-secondary-source-discovery-plan-v1"
GEMINI_TEMPLATE_SCHEMA = "siraj-gemini-locator-discovery-template-v1"
LOCATOR_OUTPUT_SCHEMA = "siraj-candidate-locator-package-v1"
DISCOVERY_PACKAGE_FILENAME = "source-package-v1.discovery-draft.json"


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


def write_jsonl(path: Path, values: list[dict[str, Any]], *, force: bool) -> None:
    write_text(path, "\n".join(canonical_json(item) for item in values) + "\n", force=force)


_ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]")
_NON_WORD = re.compile(r"[^0-9\u0621-\u063a\u0641-\u064a]+")


def normalize_arabic(value: str) -> str:
    text = unicodedata.normalize("NFKC", str(value or ""))
    text = _ARABIC_DIACRITICS.sub("", text)
    text = text.replace("ـ", "")
    text = text.translate(str.maketrans({
        "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",
        "ى": "ي", "ؤ": "و", "ئ": "ي", "ة": "ه",
    }))
    return " ".join(_NON_WORD.sub(" ", text).split())


def tokens(value: str) -> set[str]:
    return {token for token in normalize_arabic(value).split() if len(token) > 1}


def token_overlap(left: str, right: str) -> float:
    a, b = tokens(left), tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def work_specs() -> list[dict[str, Any]]:
    common_terms = [
        "آدم", "خلق آدم", "تراب", "طين", "حمأ مسنون", "صلصال", "نفخ الروح",
        "الأسماء كلها", "اسجدوا لآدم", "إبليس", "الجن", "ميثاق الذر",
        "ذرية آدم", "ظهر آدم", "حواء", "الضلع", "جنة آدم", "الشجرة",
    ]
    specs = [
        {
            "work_source_id": "SRC-TAFSIR-TABARI-ADAM",
            "source_kind": "TAFSIR_WORK",
            "title": "جامع البيان عن تأويل آي القرآن",
            "author": "محمد بن جرير الطبري",
            "title_aliases": ["جامع البيان عن تأويل آي القرآن", "جامع البيان في تأويل القرآن", "تفسير الطبري", "جامع البيان"],
            "author_aliases": ["محمد بن جرير الطبري", "ابن جرير الطبري", "الطبري"],
            "expected_category_terms": ["التفسير", "علوم القرآن"],
            "penalty_title_terms": ["مختصر تفسير الطبري", "تهذيب تفسير الطبري"],
            "isnad_expectation": "FREQUENT",
            "israiliyyat_risk": "POSSIBLE_REPORT_LEVEL",
            "priority": 10,
        },
        {
            "work_source_id": "SRC-TAFSIR-IBN-ABI-HATIM-ADAM",
            "source_kind": "TAFSIR_WORK",
            "title": "تفسير القرآن العظيم",
            "author": "ابن أبي حاتم",
            "title_aliases": ["تفسير القرآن العظيم لابن أبي حاتم", "تفسير ابن أبي حاتم", "تفسير القرآن العظيم"],
            "author_aliases": ["ابن أبي حاتم", "عبد الرحمن بن محمد ابن أبي حاتم", "أبو محمد الرازي"],
            "expected_category_terms": ["التفسير", "علوم القرآن"],
            "penalty_title_terms": ["مختصر", "منتخب"],
            "isnad_expectation": "FREQUENT",
            "israiliyyat_risk": "POSSIBLE_REPORT_LEVEL",
            "priority": 20,
            "author_match_required_for_selection": True,
        },
        {
            "work_source_id": "SRC-TAFSIR-BAGHAWI-ADAM",
            "source_kind": "TAFSIR_WORK",
            "title": "معالم التنزيل",
            "author": "الحسين بن مسعود البغوي",
            "title_aliases": ["معالم التنزيل في تفسير القرآن", "معالم التنزيل", "تفسير البغوي"],
            "author_aliases": ["الحسين بن مسعود البغوي", "البغوي"],
            "expected_category_terms": ["التفسير", "علوم القرآن"],
            "penalty_title_terms": ["مختصر"],
            "isnad_expectation": "MIXED",
            "israiliyyat_risk": "POSSIBLE_REPORT_LEVEL",
            "priority": 30,
        },
        {
            "work_source_id": "SRC-TAFSIR-IBN-KATHIR-ADAM",
            "source_kind": "TAFSIR_WORK",
            "title": "تفسير القرآن العظيم",
            "author": "إسماعيل بن كثير",
            "title_aliases": ["تفسير القرآن العظيم لابن كثير", "تفسير ابن كثير", "تفسير القرآن العظيم"],
            "author_aliases": ["إسماعيل بن عمر ابن كثير", "إسماعيل بن كثير", "ابن كثير"],
            "expected_category_terms": ["التفسير", "علوم القرآن"],
            "penalty_title_terms": ["مختصر تفسير ابن كثير", "عمدة التفسير"],
            "isnad_expectation": "MIXED",
            "israiliyyat_risk": "POSSIBLE_REPORT_LEVEL",
            "priority": 40,
            "author_match_required_for_selection": True,
        },
        {
            "work_source_id": "SRC-TAFSIR-SAADI-ADAM",
            "source_kind": "TAFSIR_WORK",
            "title": "تيسير الكريم الرحمن في تفسير كلام المنان",
            "author": "عبد الرحمن السعدي",
            "title_aliases": ["تيسير الكريم الرحمن في تفسير كلام المنان", "تيسير الكريم الرحمن", "تفسير السعدي"],
            "author_aliases": ["عبد الرحمن بن ناصر السعدي", "عبد الرحمن السعدي", "السعدي"],
            "expected_category_terms": ["التفسير", "علوم القرآن"],
            "penalty_title_terms": [],
            "isnad_expectation": "NONE",
            "israiliyyat_risk": "LOW",
            "priority": 50,
        },
        {
            "work_source_id": "SRC-HISTORY-TABARI-ADAM",
            "source_kind": "HISTORICAL_WORK",
            "title": "تاريخ الرسل والملوك",
            "author": "محمد بن جرير الطبري",
            "title_aliases": ["تاريخ الرسل والملوك", "تاريخ الطبري", "تاريخ الطبري تاريخ الرسل والملوك"],
            "author_aliases": ["محمد بن جرير الطبري", "ابن جرير الطبري", "الطبري"],
            "expected_category_terms": ["التاريخ", "التراجم"],
            "penalty_title_terms": ["تكملة تاريخ الطبري", "صحيح وضعيف تاريخ الطبري"],
            "isnad_expectation": "FREQUENT",
            "israiliyyat_risk": "HIGH_REPORT_LEVEL",
            "priority": 60,
        },
        {
            "work_source_id": "SRC-HISTORY-BIDAYAH-ADAM",
            "source_kind": "HISTORICAL_WORK",
            "title": "البداية والنهاية",
            "author": "إسماعيل بن كثير",
            "title_aliases": ["البداية والنهاية"],
            "author_aliases": ["إسماعيل بن عمر ابن كثير", "إسماعيل بن كثير", "ابن كثير"],
            "expected_category_terms": ["التاريخ", "التراجم"],
            "penalty_title_terms": ["السيرة النبوية من البداية والنهاية", "مختصر البداية والنهاية"],
            "isnad_expectation": "MIXED",
            "israiliyyat_risk": "HIGH_REPORT_LEVEL",
            "priority": 70,
        },
        {
            "work_source_id": "SRC-HISTORY-QASAS-IBN-KATHIR-ADAM",
            "source_kind": "PROPHETIC_HISTORY_WORK",
            "title": "قصص الأنبياء",
            "author": "إسماعيل بن كثير",
            "title_aliases": ["قصص الأنبياء لابن كثير", "قصص الأنبياء"],
            "author_aliases": ["إسماعيل بن عمر ابن كثير", "إسماعيل بن كثير", "ابن كثير"],
            "expected_category_terms": ["التاريخ", "قصص الأنبياء", "السيرة"],
            "penalty_title_terms": ["مختصر قصص الأنبياء", "قصص الأنبياء للأطفال"],
            "isnad_expectation": "MIXED",
            "israiliyyat_risk": "HIGH_REPORT_LEVEL",
            "priority": 80,
        },
        {
            "work_source_id": "SRC-HISTORY-MUNTAZAM-ADAM",
            "source_kind": "HISTORICAL_WORK",
            "title": "المنتظم في تاريخ الملوك والأمم",
            "author": "ابن الجوزي",
            "title_aliases": ["المنتظم في تاريخ الملوك والأمم", "المنتظم في التاريخ", "المنتظم"],
            "author_aliases": ["عبد الرحمن بن علي ابن الجوزي", "ابن الجوزي"],
            "expected_category_terms": ["التاريخ", "التراجم"],
            "penalty_title_terms": ["مختصر المنتظم"],
            "isnad_expectation": "MIXED",
            "israiliyyat_risk": "POSSIBLE_REPORT_LEVEL",
            "priority": 90,
        },
        {
            "work_source_id": "SRC-HISTORY-KAMIL-ADAM",
            "source_kind": "HISTORICAL_WORK",
            "title": "الكامل في التاريخ",
            "author": "ابن الأثير",
            "title_aliases": ["الكامل في التاريخ"],
            "author_aliases": ["علي بن محمد ابن الأثير", "ابن الأثير"],
            "expected_category_terms": ["التاريخ", "التراجم"],
            "penalty_title_terms": ["مختصر الكامل"],
            "isnad_expectation": "MIXED",
            "israiliyyat_risk": "POSSIBLE_REPORT_LEVEL",
            "priority": 100,
        },
    ]
    for item in specs:
        item["discovery_method"] = "SHAMELA_LOCAL_CATALOG_AND_BOUNDED_TEXT_SCAN"
        item["query_lexicon"] = list(common_terms)
        item["selection_status"] = "PENDING_HUMAN_SELECTION"
        item["allowed_for_extraction"] = False
        item["allowed_for_quotation"] = False
        item["usage_policy"] = [
            "DISCOVERY_CANDIDATES_ONLY",
            "CLASSIFY_EACH_REPORT_INDIVIDUALLY",
            "NO_AUTOMATIC_TRUTH_OR_AUTHENTICITY_DECISION",
            "NO_EPISODE_USAGE_BEFORE_HUMAN_REVIEW",
        ]
    specs.extend([
        {
            "work_source_id": "SRC-ISRAILIYYAT-WAHB-ADAM",
            "source_kind": "ISRAILIYYAT_ATTRIBUTION_PROFILE",
            "title": "مرويات وهب بن منبه في قصة آدم",
            "author": "وهب بن منبه",
            "discovery_method": "ATTRIBUTION_SCAN_ACROSS_SELECTED_WORKS",
            "attribution_aliases": ["وهب بن منبه", "قال وهب", "عن وهب", "ذكر وهب"],
            "query_lexicon": ["آدم", "حواء", "إبليس", "الشجرة", "الجنة", "الذرية", "وهب بن منبه", "قال وهب", "عن وهب"],
            "depends_on_work_source_ids": [item["work_source_id"] for item in specs],
            "isnad_expectation": "VARIES",
            "israiliyyat_risk": "EXPLICIT",
            "priority": 110,
            "selection_status": "BLOCKED_SELECTED_WORKS_PENDING",
            "allowed_for_extraction": False,
            "allowed_for_quotation": False,
            "usage_policy": ["MUST_BE_LABELED_ISRAILIYYAT", "NO_ASSERTION_AS_FACT", "REVELATION_CONFLICT_REQUIRES_REJECTION", "HUMAN_CLASSIFICATION_REQUIRED"],
        },
        {
            "work_source_id": "SRC-ISRAILIYYAT-KAAB-ADAM",
            "source_kind": "ISRAILIYYAT_ATTRIBUTION_PROFILE",
            "title": "مرويات كعب الأحبار في قصة آدم",
            "author": "كعب الأحبار",
            "discovery_method": "ATTRIBUTION_SCAN_ACROSS_SELECTED_WORKS",
            "attribution_aliases": ["كعب الأحبار", "قال كعب", "عن كعب", "ذكر كعب"],
            "query_lexicon": ["آدم", "حواء", "إبليس", "الشجرة", "الجنة", "الذرية", "كعب الأحبار", "قال كعب", "عن كعب"],
            "depends_on_work_source_ids": [item["work_source_id"] for item in specs],
            "isnad_expectation": "VARIES",
            "israiliyyat_risk": "EXPLICIT",
            "priority": 120,
            "selection_status": "BLOCKED_SELECTED_WORKS_PENDING",
            "allowed_for_extraction": False,
            "allowed_for_quotation": False,
            "usage_policy": ["MUST_BE_LABELED_ISRAILIYYAT", "NO_ASSERTION_AS_FACT", "REVELATION_CONFLICT_REQUIRES_REJECTION", "HUMAN_CLASSIFICATION_REQUIRED"],
        },
    ])
    return specs


def catalog_from_shamela(master_db: Path, shamela_root: Path) -> list[dict[str, Any]]:
    if not master_db.is_file():
        raise FileNotFoundError(f"SHAMELA_MASTER_DB_NOT_FOUND:{master_db}")
    connection = sqlite3.connect(f"file:{master_db.as_posix()}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    try:
        tables = {str(row[0]) for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if "book" not in tables:
            raise ValueError("SHAMELA_BOOK_TABLE_MISSING")
        book_columns = {str(row[1]) for row in connection.execute("PRAGMA table_info(book)")}
        required = {"book_id", "book_name"}
        if not required <= book_columns:
            raise ValueError("SHAMELA_BOOK_COLUMNS_INVALID")
        has_author = "author" in tables
        has_category = "category" in tables
        select = ["b.book_id AS book_id", "b.book_name AS book_name"]
        select.append("b.authors AS embedded_authors" if "authors" in book_columns else "'' AS embedded_authors")
        select.append("b.main_author AS main_author" if "main_author" in book_columns else "NULL AS main_author")
        select.append("b.meta_data AS meta_data" if "meta_data" in book_columns else "'' AS meta_data")
        select.append("b.hidden AS hidden" if "hidden" in book_columns else "0 AS hidden")
        joins: list[str] = []
        if has_author and "main_author" in book_columns:
            select.append("a.author_name AS author_name")
            joins.append("LEFT JOIN author a ON a.author_id = b.main_author")
        else:
            select.append("'' AS author_name")
        if has_category and "book_category" in book_columns:
            select.append("c.category_name AS category_name")
            joins.append("LEFT JOIN category c ON c.category_id = b.book_category")
        else:
            select.append("'' AS category_name")
        sql = "SELECT " + ", ".join(select) + " FROM book b " + " ".join(joins)
        rows = connection.execute(sql).fetchall()
    finally:
        connection.close()
    catalog: list[dict[str, Any]] = []
    for row in rows:
        book_id = int(row["book_id"])
        suffix = f"{book_id % 1000:03d}"
        db_path = shamela_root / "database" / "book" / suffix / f"{book_id}.db"
        author = " ".join(part for part in [str(row["author_name"] or "").strip(), str(row["embedded_authors"] or "").strip()] if part)
        catalog.append({
            "book_id": book_id,
            "book_title": str(row["book_name"] or "").strip(),
            "author": author,
            "category": str(row["category_name"] or "").strip(),
            "hidden": bool(row["hidden"] or False),
            "book_database_path": str(db_path),
            "book_database_exists": db_path.is_file(),
            "metadata_excerpt": str(row["meta_data"] or "")[:1000],
        })
    return sorted(catalog, key=lambda item: item["book_id"])


def candidate_score(spec: dict[str, Any], book: dict[str, Any]) -> tuple[float, dict[str, Any]]:
    book_title = normalize_arabic(book["book_title"])
    book_author = normalize_arabic(book.get("author", ""))
    category = normalize_arabic(book.get("category", ""))
    best_alias = ""
    best_title_score = 0.0
    for alias in spec.get("title_aliases", []):
        normalized_alias = normalize_arabic(alias)
        if not normalized_alias:
            continue
        ratio = SequenceMatcher(None, normalized_alias, book_title).ratio()
        overlap = token_overlap(normalized_alias, book_title)
        contains = normalized_alias in book_title or book_title in normalized_alias
        title_score = ratio * 48.0 + overlap * 22.0 + (22.0 if contains else 0.0)
        if normalized_alias == book_title:
            title_score = 92.0
        if title_score > best_title_score:
            best_title_score, best_alias = title_score, alias
    author_match = False
    author_strength = 0.0
    matched_author_alias = ""
    for alias in spec.get("author_aliases", []):
        norm = normalize_arabic(alias)
        if norm and (norm in book_author or token_overlap(norm, book_author) >= 0.5):
            author_match = True
            strength = 22.0 + 8.0 * token_overlap(norm, book_author)
            if strength > author_strength:
                author_strength = strength
                matched_author_alias = alias
    category_match = any(normalize_arabic(term) in category for term in spec.get("expected_category_terms", []))
    category_score = 5.0 if category_match else 0.0
    penalties: list[str] = []
    penalty = 0.0
    for term in spec.get("penalty_title_terms", []):
        if normalize_arabic(term) in book_title:
            penalty += 35.0
            penalties.append(term)
    if spec.get("author_match_required_for_selection") and book_author and not author_match:
        penalty += 28.0
        penalties.append("AUTHOR_MISMATCH_FOR_AMBIGUOUS_TITLE")
    if book.get("hidden"):
        penalty += 10.0
        penalties.append("HIDDEN_BOOK")
    if not book.get("book_database_exists"):
        penalty += 8.0
        penalties.append("BOOK_DATABASE_MISSING")
    total = max(0.0, min(100.0, best_title_score + author_strength + category_score - penalty))
    details = {
        "matched_title_alias": best_alias,
        "title_component": round(best_title_score, 3),
        "author_match": author_match,
        "matched_author_alias": matched_author_alias,
        "author_component": round(author_strength, 3),
        "category_match": category_match,
        "category_component": category_score,
        "penalties": penalties,
    }
    return round(total, 3), details


def rank_candidates(spec: dict[str, Any], catalog: list[dict[str, Any]], *, top_n: int = 10) -> list[dict[str, Any]]:
    ranked: list[dict[str, Any]] = []
    for book in catalog:
        score, details = candidate_score(spec, book)
        if score < 38.0:
            continue
        ranked.append({**book, "score": score, "score_details": details})
    ranked.sort(key=lambda item: (-item["score"], not item["book_database_exists"], item["book_id"]))
    return ranked[:top_n]


def locator_output_schema() -> dict[str, Any]:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": LOCATOR_OUTPUT_SCHEMA,
        "title": "SIRAJ Candidate Locator Package v1",
        "type": "object",
        "additionalProperties": False,
        "required": ["schema_version", "episode_id", "work_source_id", "selected_book_id", "source_asset_checksum", "candidates", "coverage_gaps", "warnings"],
        "properties": {
            "schema_version": {"const": LOCATOR_OUTPUT_SCHEMA},
            "episode_id": {"const": EPISODE_ID},
            "work_source_id": {"type": "string", "minLength": 1},
            "selected_book_id": {"type": "integer", "minimum": 1},
            "source_asset_checksum": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
            "candidates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["candidate_id", "source_id", "exact_locator", "verbatim_text", "normalized_text", "heading_context", "attribution", "isnad_present", "supports_event_ids", "supports_question_ids", "candidate_classification", "israiliyyat_indicator", "confidence", "verification_status"],
                    "properties": {
                        "candidate_id": {"type": "string", "minLength": 1},
                        "source_id": {"type": "string", "minLength": 1},
                        "exact_locator": {"type": "string", "pattern": "^shamela://local/"},
                        "verbatim_text": {"type": "string", "minLength": 1},
                        "normalized_text": {"type": "string", "minLength": 1},
                        "heading_context": {"type": "string"},
                        "attribution": {"type": "string"},
                        "isnad_present": {"enum": [True, False, "UNCLEAR"]},
                        "supports_event_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                        "supports_question_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                        "candidate_classification": {"enum": ["QURANIC_INTERPRETATION", "PROPHETIC_REPORT", "COMPANION_OR_SUCCESSOR_REPORT", "HISTORICAL_REPORT", "ISRAILIYYAT_CANDIDATE", "AUTHOR_ANALYSIS", "UNCLASSIFIED"]},
                        "israiliyyat_indicator": {"enum": ["NONE", "POSSIBLE", "EXPLICIT_ATTRIBUTION", "CONTRADICTS_REVELATION_CANDIDATE", "UNCLEAR"]},
                        "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                        "verification_status": {"const": "CANDIDATE"},
                    },
                },
            },
            "coverage_gaps": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
    }


def build_test() -> str:
    return '''from __future__ import annotations\n\nimport json\nfrom pathlib import Path\n\n\ndef _read_jsonl(path: Path):\n    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]\n\n\ndef test_adam_secondary_source_discovery_phase2_contracts() -> None:\n    root = Path(__file__).resolve().parents[2]\n    project = root / "projects" / "episode-001-adam"\n    secondary = project / "sources" / "secondary"\n    registry = _read_jsonl(secondary / "work-source-registry-v1.jsonl")\n    candidates = json.loads((secondary / "shamela-book-candidates-v1.json").read_text(encoding="utf-8-sig"))\n    selection = json.loads((secondary / "asset-selection.template.json").read_text(encoding="utf-8-sig"))\n    package = json.loads((project / "contracts" / "source-package-v1.discovery-draft.json").read_text(encoding="utf-8-sig"))\n    assert len(registry) == 12\n    assert len({item["work_source_id"] for item in registry}) == 12\n    assert sum(item["source_kind"].endswith("WORK") for item in registry) == 10\n    assert sum(item["source_kind"] == "ISRAILIYYAT_ATTRIBUTION_PROFILE" for item in registry) == 2\n    assert all(item["allowed_for_extraction"] is False for item in registry)\n    assert all(item["allowed_for_quotation"] is False for item in registry)\n    assert candidates["target_work_count"] == 10\n    assert candidates["catalog_book_count"] > 0\n    assert len(selection["selections"]) == 10\n    assert all(item["selected_book_id"] is None for item in selection["selections"].values())\n    assert package["package_status"] == "DRAFT_SECONDARY_WORK_SELECTION_PENDING"\n    assert all(item["allowed_for_extraction"] is False for item in package["source_items"] if item["source_id"].startswith("SRC-TAFSIR-") or item["source_id"].startswith("SRC-HISTORY-") or item["source_id"].startswith("SRC-ISRAILIYYAT-"))\n'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--shamela-root", default=r"C:\shamela4")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    project = repo / "projects" / EPISODE_ID
    editorial = project / "editorial"
    contracts = project / "contracts"
    sources_root = project / "sources"
    secondary = sources_root / "secondary"
    shamela_root = Path(args.shamela_root).resolve()
    master_db = shamela_root / "database" / "master.db"

    required = [
        editorial / "source-acquisition-register.jsonl",
        editorial / "event-map.json",
        editorial / "research-questions.json",
        contracts / "source-package-v1.exact-draft.json",
        sources_root / "exact-source-registry-v1.jsonl",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("MISSING_PHASE1_FILES:\n" + "\n".join(missing))

    seed_sources = {item["source_id"]: item for item in read_jsonl(editorial / "source-acquisition-register.jsonl")}
    events = read_json(editorial / "event-map.json")
    questions = read_json(editorial / "research-questions.json")
    event_ids = [str(item["event_id"]) for item in events]
    question_ids = [str(item["question_id"]) for item in questions]
    specs = work_specs()
    spec_ids = [item["work_source_id"] for item in specs]
    if len(spec_ids) != len(set(spec_ids)):
        raise ValueError("DUPLICATE_WORK_SOURCE_ID")
    missing_seed = sorted(set(spec_ids) - set(seed_sources))
    if missing_seed:
        raise ValueError("WORK_SOURCE_NOT_IN_EDITORIAL_REGISTER:" + ",".join(missing_seed))

    catalog = catalog_from_shamela(master_db, shamela_root)
    work_targets = [item for item in specs if item["discovery_method"].startswith("SHAMELA_LOCAL")]
    candidate_targets: list[dict[str, Any]] = []
    registry: list[dict[str, Any]] = []
    for spec in specs:
        record = dict(spec)
        record["schema_version"] = WORK_REGISTRY_SCHEMA
        record["supports_event_ids"] = event_ids
        record["supports_question_ids"] = question_ids
        record["candidate_count"] = 0
        record["top_candidate_score"] = 0.0
        record["selected_book_id"] = None
        if spec in work_targets:
            ranked = rank_candidates(spec, catalog)
            record["candidate_count"] = len(ranked)
            record["top_candidate_score"] = ranked[0]["score"] if ranked else 0.0
            candidate_targets.append({
                "work_source_id": spec["work_source_id"],
                "expected_title": spec["title"],
                "expected_author": spec["author"],
                "selection_status": "REQUIRES_HUMAN_SELECTION",
                "candidates": ranked,
            })
        registry.append(record)

    created_at = now_utc()
    candidate_report = {
        "schema_version": CANDIDATE_REPORT_SCHEMA,
        "episode_id": EPISODE_ID,
        "status": "CANDIDATES_DISCOVERED_HUMAN_SELECTION_REQUIRED",
        "shamela_root": str(shamela_root),
        "master_db": str(master_db),
        "master_db_sha256": hashlib.sha256(master_db.read_bytes()).hexdigest(),
        "catalog_book_count": len(catalog),
        "target_work_count": len(work_targets),
        "targets_with_candidates": sum(bool(item["candidates"]) for item in candidate_targets),
        "targets_without_candidates": [item["work_source_id"] for item in candidate_targets if not item["candidates"]],
        "targets": candidate_targets,
        "selection_policy": [
            "NO_AUTOMATIC_BOOK_SELECTION",
            "SELECT_THE_ORIGINAL_WORK_NOT_A_SUMMARY_OR_DERIVATIVE",
            "VERIFY_AUTHOR_AND_EDITION_METADATA",
            "BOOK_DATABASE_MUST_EXIST",
            "HUMAN_APPROVAL_REQUIRED",
        ],
        "created_at": created_at,
    }
    selection = {
        "schema_version": SELECTION_SCHEMA,
        "episode_id": EPISODE_ID,
        "status": "PENDING_HUMAN_SELECTION",
        "shamela_root": str(shamela_root),
        "selections": {
            item["work_source_id"]: {
                "selected_book_id": None,
                "selection_basis": "",
                "edition_or_export_notes": "",
                "rights_reviewed": False,
                "allow_local_extraction": False,
                "allow_quotation": False,
                "approved_by_user": False,
            }
            for item in work_targets
        },
    }
    plan = {
        "schema_version": DISCOVERY_PLAN_SCHEMA,
        "episode_id": EPISODE_ID,
        "plan_id": "adam-01-secondary-source-discovery-plan-v1",
        "status": "READY_FOR_BOOK_SELECTION",
        "work_target_count": len(work_targets),
        "attribution_profile_count": 2,
        "phases": [
            {"phase_id": "SECONDARY-01-CATALOG", "order": 10, "status": "COMPLETED", "action": "Discover and rank local Shamela books."},
            {"phase_id": "SECONDARY-02-SELECTION", "order": 20, "status": "PENDING_HUMAN_SELECTION", "action": "Select one original work asset per target."},
            {"phase_id": "SECONDARY-03-MATERIALIZATION", "order": 30, "status": "BLOCKED", "action": "Export selected books to project-local normalized artifacts and record checksums."},
            {"phase_id": "SECONDARY-04-GEMINI-LOCATORS", "order": 40, "status": "BLOCKED", "action": "Run bounded candidate-locator discovery against selected local assets."},
            {"phase_id": "SECONDARY-05-VERIFICATION", "order": 50, "status": "BLOCKED", "action": "Verify text and locators deterministically, then review reports individually."},
        ],
        "prohibitions": [
            "NO_GEMINI_WEB_BROWSING",
            "NO_AUTOMATIC_SOURCE_APPROVAL",
            "NO_AUTOMATIC_ISRAILIYYAT_ACCEPTANCE",
            "NO_AUTOMATIC_HADITH_GRADING",
            "NO_CANDIDATE_USAGE_IN_NARRATIVE",
        ],
        "created_at": created_at,
    }
    gemini_tasks = []
    for item in registry:
        gemini_tasks.append({
            "task_id": "LOCATE-" + item["work_source_id"],
            "work_source_id": item["work_source_id"],
            "task_type": "ATTRIBUTION_SCAN" if item["source_kind"] == "ISRAILIYYAT_ATTRIBUTION_PROFILE" else "BOUNDED_WORK_LOCATOR_DISCOVERY",
            "status": "BLOCKED_LOCAL_ASSET_PENDING",
            "supports_event_ids": item["supports_event_ids"],
            "supports_question_ids": item["supports_question_ids"],
            "query_lexicon": item["query_lexicon"],
            "maximum_candidates": 80 if item["source_kind"] == "TAFSIR_WORK" else 60,
        })
    gemini_template = {
        "schema_version": GEMINI_TEMPLATE_SCHEMA,
        "episode_id": EPISODE_ID,
        "work_package_id": "adam-01-secondary-locator-discovery-template-v1",
        "status": "BLOCKED_BOOK_SELECTION_AND_MATERIALIZATION_PENDING",
        "execution_mode": "ONE_SELECTED_LOCAL_WORK_PER_REQUEST",
        "purpose": "Discover candidate passages and exact local locators from selected tafsir and historical works; no candidate is approved evidence.",
        "required_inputs": [
            "selected local Shamela work artifact",
            "source asset SHA-256",
            "episode event map",
            "research questions",
            "editorial policy",
            "work-source registry record",
            "candidate locator output schema",
        ],
        "model_instructions": [
            "Use only the supplied local source content and do not browse the web.",
            "Return candidate passages only; never approve a report or assert historical truth.",
            "Preserve the exact local locator, verbatim Arabic text, heading context, attribution and apparent isnad.",
            "Do not invent a page, part, heading, chain, narrator, quotation, chronology or source relationship.",
            "Classify each report individually and mark possible or explicit Isra'iliyyat.",
            "Material attributed to Wahb ibn Munabbih or Ka'b al-Ahbar must be labeled explicitly.",
            "A report that may contradict revelation must be flagged, not reconciled or used.",
            "Do not treat repeated quotations across derivative works as independent corroboration.",
            "Do not import material belonging to later Adam episodes unless it is required to understand Episode 1; list it under exclusions.",
        ],
        "tasks": gemini_tasks,
        "output_schema": "sources/secondary/candidate-locator-schema-v1.json",
        "human_review_required": True,
        "source_approval_changed": False,
        "gemini_execution_enabled": False,
        "created_at": created_at,
    }

    exact_package = read_json(contracts / "source-package-v1.exact-draft.json")
    secondary_ids = set(spec_ids)
    package = json.loads(json.dumps(exact_package))
    package["source_package_id"] = "adam-01-source-package-discovery-draft-v1"
    package["title"] = "Adam Episode 1 source package with secondary-work discovery governance"
    for item in package["source_items"]:
        if item.get("source_id") not in secondary_ids:
            continue
        reg = next(record for record in registry if record["work_source_id"] == item["source_id"])
        item["access_status"] = "PLANNED"
        item["path"] = ""
        item["checksum"] = ""
        item["allowed_for_extraction"] = False
        item["allowed_for_quotation"] = False
        item["page/section availability"] = "WORK_SELECTION_PENDING"
        previous_notes = item.get("notes") if isinstance(item.get("notes"), dict) else {"legacy_notes": item.get("notes")}
        item["notes"] = {
            **previous_notes,
            "secondary_discovery": {
                "source_kind": reg["source_kind"],
                "selection_status": reg["selection_status"],
                "candidate_count": reg["candidate_count"],
                "top_candidate_score": reg["top_candidate_score"],
                "isnad_expectation": reg["isnad_expectation"],
                "israiliyyat_risk": reg["israiliyyat_risk"],
                "usage_policy": reg["usage_policy"],
            },
        }
    package["package_status"] = "DRAFT_SECONDARY_WORK_SELECTION_PENDING"
    package["updated_at"] = created_at
    package["input_fingerprint"] = ""
    package["input_fingerprint"] = fingerprint({key: value for key, value in package.items() if key != "input_fingerprint"})

    write_jsonl(secondary / "work-source-registry-v1.jsonl", registry, force=args.force)
    write_json(secondary / "shamela-book-candidates-v1.json", candidate_report, force=args.force)
    write_json(secondary / "asset-selection.template.json", selection, force=args.force)
    write_json(secondary / "secondary-discovery-plan-v1.json", plan, force=args.force)
    write_json(secondary / "gemini-locator-discovery-template-v1.json", gemini_template, force=args.force)
    write_json(secondary / "candidate-locator-schema-v1.json", locator_output_schema(), force=args.force)
    write_json(contracts / DISCOVERY_PACKAGE_FILENAME, package, force=args.force)
    write_text(repo / "tests" / "integration" / "test_adam_secondary_source_discovery_v1.py", build_test(), force=args.force)

    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from src.application.research_verification_episode_v1.runtime import validate_source_package
    errors = validate_source_package(package, project_root=project, episode_id=EPISODE_ID)
    if errors:
        raise SystemExit(json.dumps({"status": "FAIL", "source_package_errors": errors}, ensure_ascii=False, indent=2))

    print(json.dumps({
        "status": "PASS",
        "work_registry": str(secondary / "work-source-registry-v1.jsonl"),
        "candidate_report": str(secondary / "shamela-book-candidates-v1.json"),
        "selection_template": str(secondary / "asset-selection.template.json"),
        "discovery_source_package": str(contracts / DISCOVERY_PACKAGE_FILENAME),
        "counts": {
            "catalog_books": len(catalog),
            "work_targets": len(work_targets),
            "attribution_profiles": 2,
            "targets_with_candidates": candidate_report["targets_with_candidates"],
            "targets_without_candidates": len(candidate_report["targets_without_candidates"]),
            "total_ranked_candidates": sum(len(item["candidates"]) for item in candidate_targets),
        },
        "source_approval_changed": False,
        "gemini_execution_enabled": False,
        "next_gate": "HUMAN_BOOK_SELECTION",
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
