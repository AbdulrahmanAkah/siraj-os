from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

EPISODE_ID = "episode-001-adam"
SCHEMA = "siraj-adam-deterministic-topic-prefilter-v1"
CANDIDATE_SCHEMA = "siraj-adam-topic-candidate-v1"
ATTRIBUTION_SCHEMA = "siraj-adam-attribution-candidate-v1"

DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
SPACE = re.compile(r"\s+")

LEXICON: dict[str, dict[str, Any]] = {
    "ADAM_PRIMARY": {
        "weight": 18,
        "phrases": ["آدم", "يا آدم", "آدم عليه السلام", "أبو البشر", "أبي البشر"],
    },
    "CREATION_DECREE": {
        "weight": 10,
        "phrases": [
            "إني جاعل في الأرض خليفة", "جاعل في الأرض خليفة", "خلق آدم",
            "لما خلق الله آدم", "خلق الله آدم", "خلقته بيدي", "خلقت بيدي",
            "سواه", "سويته", "صور آدم",
        ],
    },
    "CREATION_MATERIAL": {
        "weight": 7,
        "phrases": [
            "من تراب", "من طين", "طينا", "صلصال", "حمإ مسنون",
            "حمأ مسنون", "سلالة من طين", "قبضة من جميع الأرض",
            "قبضة من الأرض", "أديم الأرض",
        ],
    },
    "SPIRIT_AND_FORM": {
        "weight": 8,
        "phrases": [
            "نفخت فيه من روحي", "نفخ فيه من روحه", "نفخ فيه الروح",
            "الروح في آدم", "طوله ستون ذراعا", "ستون ذراعا", "على صورته",
        ],
    },
    "TEACHING_NAMES": {
        "weight": 11,
        "phrases": [
            "علم آدم الأسماء", "وعلم آدم الأسماء", "الأسماء كلها",
            "أنبئهم بأسمائهم", "أنبئوني بأسماء هؤلاء", "تعليم الأسماء",
        ],
    },
    "ANGELIC_PROSTRATION": {
        "weight": 11,
        "phrases": [
            "اسجدوا لآدم", "فسجدوا إلا إبليس", "سجود الملائكة",
            "سجد الملائكة", "أبى واستكبر", "إبليس",
        ],
    },
    "HONOUR_AND_STATUS": {
        "weight": 7,
        "phrases": [
            "كرم آدم", "تكريم آدم", "اصطفى آدم", "صفوة الله",
            "خليفة في الأرض", "فضل آدم", "كرامة آدم",
        ],
    },
    "PARADISE_RESIDENCE": {
        "weight": 10,
        "phrases": [
            "اسكن أنت وزوجك الجنة", "اسكن الجنة", "سكن آدم الجنة",
            "أدخل آدم الجنة", "زوجك الجنة", "خلق حواء", "زوج آدم",
        ],
    },
    "HADITH_ANCHORS": {
        "weight": 9,
        "phrases": [
            "اذهب فسلم على أولئك النفر", "ذهب فسلم على أولئك النفر",
            "فكل من يدخل الجنة على صورة آدم", "إن الله خلق آدم من قبضة قبضها",
            "لما خلق الله آدم تركه ما شاء",
        ],
    },
}

OUT_OF_SCOPE = {
    "وسوس": 7,
    "الشجرة": 4,
    "فأكلا منها": 8,
    "بدت لهما سوآتهما": 8,
    "اهبطوا": 8,
    "فتلقى آدم": 7,
    "تاب عليه": 5,
    "قابيل": 10,
    "هابيل": 10,
    "قتل أخاه": 10,
    "احتج آدم وموسى": 9,
}

ATTRIBUTIONS = {
    "WAHB_IBN_MUNABBIH": ["وهب بن منبه", "قال وهب", "عن وهب", "ذكر وهب"],
    "KAB_AL_AHBAR": ["كعب الأحبار", "كعب الاحبار", "قال كعب", "عن كعب", "ذكر كعب"],
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalize(text: str) -> str:
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي").replace("ـ", "")
    text = DIACRITICS.sub("", text)
    return SPACE.sub(" ", text).strip().casefold()


def contains_phrase(text: str, phrase: str) -> bool:
    """Use word boundaries for one-token Arabic anchors such as Adam."""
    if not phrase:
        return False
    if " " in phrase:
        return phrase in text
    return re.search(rf"(?<!\w){re.escape(phrase)}(?!\w)", text) is not None


NLEX = {
    category: {
        "weight": int(config["weight"]),
        "phrases": [(phrase, normalize(phrase)) for phrase in config["phrases"]],
    }
    for category, config in LEXICON.items()
}
NOOS = [(phrase, normalize(phrase), penalty) for phrase, penalty in OUT_OF_SCOPE.items()]
NATTR = {
    profile: [(phrase, normalize(phrase)) for phrase in phrases]
    for profile, phrases in ATTRIBUTIONS.items()
}


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_no, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL_OBJECT_REQUIRED:{path}:{line_no}")
            yield value


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            line = json.dumps(
                row, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ) + "\n"
            stream.write(line)
            digest.update(line.encode("utf-8"))
    return len(rows), digest.hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def record_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def load_headings(path: Path) -> dict[int, list[str]]:
    headings: dict[int, list[str]] = defaultdict(list)
    for row in iter_jsonl(path):
        page_id = row.get("page_segment_id")
        title = str(row.get("title_text") or "").strip()
        if page_id is not None and title:
            headings[int(page_id)].append(title)
    return dict(headings)


def match_text(text: str, heading: str) -> tuple[list[dict[str, Any]], int, int]:
    matched: list[dict[str, Any]] = []
    raw_score = 0
    heading_bonus = 0
    for category, config in NLEX.items():
        body_hits = [raw for raw, value in config["phrases"] if contains_phrase(text, value)]
        heading_hits = [raw for raw, value in config["phrases"] if contains_phrase(heading, value)]
        if body_hits or heading_hits:
            category_score = config["weight"] + min(max(len(body_hits) - 1, 0), 4) * 2
            raw_score += category_score
            if heading_hits:
                heading_bonus += min(config["weight"], 8)
            matched.append({
                "category": category,
                "phrases": sorted(set(body_hits)),
                "heading_phrases": sorted(set(heading_hits)),
                "category_score": category_score,
            })
    return matched, raw_score, heading_bonus


def out_scope(text: str) -> tuple[int, list[str]]:
    penalty = 0
    hits: list[str] = []
    for raw, value, amount in NOOS:
        if contains_phrase(text, value):
            penalty += int(amount)
            hits.append(raw)
    return penalty, hits


def attribution_hits(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for profile, phrases in NATTR.items():
        hits = [raw for raw, value in phrases if contains_phrase(text, value)]
        if hits:
            rows.append({"profile": profile, "matched_phrases": sorted(set(hits))})
    return rows


def excerpt(text: str, phrases: list[str], width: int = 1200) -> str:
    compact = SPACE.sub(" ", text).strip()
    if not compact:
        return ""
    normalized = normalize(compact)
    positions = [
        normalized.find(normalize(phrase))
        for phrase in phrases
        if normalize(phrase) and normalized.find(normalize(phrase)) >= 0
    ]
    center = min(positions) if positions else 0
    start = max(center - width // 3, 0)
    end = min(start + width, len(compact))
    if end - start < width and start:
        start = max(end - width, 0)
    value = compact[start:end]
    return ("…" if start else "") + value + ("…" if end < len(compact) else "")


def tier(exact_adam: bool, category_count: int, score: int) -> str:
    if exact_adam and category_count >= 3 and score >= 35:
        return "A"
    if exact_adam and category_count >= 2:
        return "B"
    if exact_adam or score >= 24:
        return "C"
    return "D"


def keep(exact_adam: bool, category_count: int, score: int, heading_hit: bool) -> bool:
    return exact_adam or (heading_hit and score >= 15) or (category_count >= 2 and score >= 18)


def scan_book(
    project: Path,
    output_root: Path,
    book: dict[str, Any],
    per_book_limit: int,
) -> dict[str, Any]:
    work_source_id = str(book["work_source_id"])
    book_id = int(book["book_id"])
    pages_path = project / book["normalized_files"]["pages"]["project_path"]
    toc_path = project / book["normalized_files"]["toc"]["project_path"]

    if sha256_file(pages_path) != book["normalized_files"]["pages"]["sha256"]:
        raise ValueError(f"PAGES_CHECKSUM_MISMATCH:{work_source_id}")
    if sha256_file(toc_path) != book["normalized_files"]["toc"]["sha256"]:
        raise ValueError(f"TOC_CHECKSUM_MISMATCH:{work_source_id}")

    headings = load_headings(toc_path)
    candidates: list[dict[str, Any]] = []
    attribution_rows: list[dict[str, Any]] = []
    scanned = 0
    category_counts: Counter[str] = Counter()

    for page in iter_jsonl(pages_path):
        scanned += 1
        page_id = int(page["shamela_page_id"])
        body = str(page.get("content_text") or "")
        heading_context = headings.get(page_id, [])
        nbody = normalize(body)
        nheading = normalize(" | ".join(heading_context))

        matches, base, heading_bonus = match_text(nbody, nheading)
        categories = {item["category"] for item in matches}
        penalty, scope_hits = out_scope(nbody)
        exact_adam = contains_phrase(nbody, normalize("آدم"))
        heading_hit = any(item["heading_phrases"] for item in matches)
        cooccurrence = max(len(categories) - 1, 0) * 4
        score = max(base + heading_bonus + cooccurrence - penalty, 0)

        if not keep(exact_adam, len(categories), score, heading_hit):
            continue

        phrases = sorted({
            phrase
            for item in matches
            for phrase in item["phrases"] + item["heading_phrases"]
        })
        for category in categories:
            category_counts[category] += 1

        candidate_id = record_hash([
            work_source_id, book_id, page_id, page["canonical_locator"]
        ])[:24]
        row = {
            "schema_version": CANDIDATE_SCHEMA,
            "episode_id": EPISODE_ID,
            "candidate_id": candidate_id,
            "work_source_id": work_source_id,
            "book_id": book_id,
            "book_title": book.get("book_title", ""),
            "shamela_page_id": page_id,
            "volume": page.get("volume"),
            "page_num": page.get("page_num"),
            "page_label": page.get("page_label"),
            "canonical_locator": page["canonical_locator"],
            "candidate_tier": tier(exact_adam, len(categories), score),
            "score": score,
            "score_components": {
                "category_score": base,
                "heading_bonus": heading_bonus,
                "cooccurrence_bonus": cooccurrence,
                "out_of_scope_penalty": penalty,
            },
            "matched_categories": sorted(categories),
            "matched_phrases": phrases,
            "out_of_scope_signals": sorted(scope_hits),
            "heading_context": heading_context,
            "excerpt": excerpt(body, phrases),
            "source_page_record_sha256": page.get("record_sha256"),
            "permissions": {
                "candidate_only": True,
                "approved_for_evidence": False,
                "approved_for_quotation": False,
                "allowed_for_gemini": False,
            },
        }
        attributions = attribution_hits(nbody)
        row["attribution_profiles"] = [item["profile"] for item in attributions]
        row["candidate_record_sha256"] = record_hash(row)
        candidates.append(row)

        for item in attributions:
            attribution = {
                "schema_version": ATTRIBUTION_SCHEMA,
                "episode_id": EPISODE_ID,
                "candidate_id": candidate_id,
                "work_source_id": work_source_id,
                "book_id": book_id,
                "shamela_page_id": page_id,
                "canonical_locator": page["canonical_locator"],
                "profile": item["profile"],
                "matched_phrases": item["matched_phrases"],
                "candidate_tier": row["candidate_tier"],
                "candidate_score": score,
                "excerpt": row["excerpt"],
                "classification_status": "CANDIDATE_UNREVIEWED",
                "permissions": {
                    "allowed_for_gemini": False,
                    "report_classification_changed": False,
                    "israiliyyat_classification_changed": False,
                },
            }
            attribution["record_sha256"] = record_hash(attribution)
            attribution_rows.append(attribution)

    order = {"A": 0, "B": 1, "C": 2, "D": 3}
    candidates.sort(key=lambda item: (
        order[item["candidate_tier"]],
        -int(item["score"]),
        int(item["shamela_page_id"]),
    ))
    before_cap = len(candidates)
    candidates = candidates[:per_book_limit]
    kept = {item["candidate_id"] for item in candidates}
    attribution_rows = [item for item in attribution_rows if item["candidate_id"] in kept]

    book_root = output_root / work_source_id
    candidate_path = book_root / "candidates.jsonl"
    attribution_path = book_root / "attribution-candidates.jsonl"
    candidate_count, candidate_sha = write_jsonl(candidate_path, candidates)
    attribution_count, attribution_sha = write_jsonl(attribution_path, attribution_rows)
    tier_counts = Counter(item["candidate_tier"] for item in candidates)

    manifest = {
        "work_source_id": work_source_id,
        "book_id": book_id,
        "book_title": book.get("book_title", ""),
        "scanned_page_count": scanned,
        "candidate_count_before_cap": before_cap,
        "candidate_count": candidate_count,
        "candidate_limit": per_book_limit,
        "tier_counts": dict(sorted(tier_counts.items())),
        "category_counts": dict(sorted(category_counts.items())),
        "attribution_candidate_count": attribution_count,
        "outputs": {
            "candidates": {
                "project_path": candidate_path.relative_to(project).as_posix(),
                "rows": candidate_count,
                "sha256": candidate_sha,
            },
            "attributions": {
                "project_path": attribution_path.relative_to(project).as_posix(),
                "rows": attribution_count,
                "sha256": attribution_sha,
            },
        },
    }
    write_json(book_root / "manifest.json", manifest)
    return manifest


def write_summary(path: Path, books: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "work_source_id", "book_id", "book_title", "scanned_pages",
        "candidates_before_cap", "candidates", "tier_a", "tier_b",
        "tier_c", "tier_d", "attribution_candidates",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for book in books:
            tiers = book["tier_counts"]
            writer.writerow({
                "work_source_id": book["work_source_id"],
                "book_id": book["book_id"],
                "book_title": book["book_title"],
                "scanned_pages": book["scanned_page_count"],
                "candidates_before_cap": book["candidate_count_before_cap"],
                "candidates": book["candidate_count"],
                "tier_a": tiers.get("A", 0),
                "tier_b": tiers.get("B", 0),
                "tier_c": tiers.get("C", 0),
                "tier_d": tiers.get("D", 0),
                "attribution_candidates": book["attribution_candidate_count"],
            })


def write_test(repo: Path) -> Path:
    path = repo / "tests" / "integration" / "test_adam_deterministic_topic_prefilter_v1.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '''from __future__ import annotations

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
''',
        encoding="utf-8",
        newline="\n",
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--per-book-limit", type=int, default=800)
    args = parser.parse_args()

    if not 50 <= args.per_book_limit <= 5000:
        raise ValueError("PER_BOOK_LIMIT_OUT_OF_RANGE")

    repo = Path(args.repo_root).resolve()
    project = repo / "projects" / EPISODE_ID
    secondary = project / "sources" / "secondary"
    source_manifest_path = secondary / "normalized-export-manifest-v1.json"
    source_manifest = read_json(source_manifest_path)

    if source_manifest.get("status") != "PASS_READY_FOR_BOUNDED_LOCAL_SEARCH":
        raise ValueError("NORMALIZED_EXPORT_NOT_READY")
    if source_manifest.get("storage_contract") != "HYBRID_SQLITE_AND_LUCENE":
        raise ValueError("UNEXPECTED_STORAGE_CONTRACT")
    if int(source_manifest.get("book_count", 0)) != 9:
        raise ValueError("EXPECTED_NINE_NORMALIZED_BOOKS")

    output_root = secondary / "topic-prefilter"
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    (output_root / ".gitignore").write_text(
        "*/candidates.jsonl\n*/attribution-candidates.jsonl\n",
        encoding="ascii",
        newline="\n",
    )

    lexicon_path = output_root / "adam-topic-lexicon-v1.json"
    write_json(lexicon_path, {
        "schema_version": "siraj-adam-topic-lexicon-v1",
        "episode_id": EPISODE_ID,
        "scope_end": "BEFORE_WHISPERING",
        "categories": LEXICON,
        "out_of_scope_signals": OUT_OF_SCOPE,
        "attribution_profiles": ATTRIBUTIONS,
        "notes": [
            "Deterministic retrieval vocabulary only.",
            "Matches do not approve reports, quotations, or narrative use.",
            "Out-of-scope signals reduce ranking but do not remove a page.",
        ],
    })

    books: list[dict[str, Any]] = []
    for book in source_manifest["books"]:
        print(json.dumps({
            "event": "PREFILTER_BOOK_START",
            "work_source_id": book["work_source_id"],
            "book_id": book["book_id"],
        }, ensure_ascii=False), flush=True)
        result = scan_book(project, output_root, book, args.per_book_limit)
        books.append(result)
        print(json.dumps({
            "event": "PREFILTER_BOOK_PASS",
            "work_source_id": result["work_source_id"],
            "book_id": result["book_id"],
            "scanned_pages": result["scanned_page_count"],
            "candidates": result["candidate_count"],
            "tier_counts": result["tier_counts"],
            "attribution_candidates": result["attribution_candidate_count"],
        }, ensure_ascii=False), flush=True)

    books.sort(key=lambda item: item["work_source_id"])
    scanned = sum(int(item["scanned_page_count"]) for item in books)
    before_cap = sum(int(item["candidate_count_before_cap"]) for item in books)
    candidates = sum(int(item["candidate_count"]) for item in books)
    attributions = sum(int(item["attribution_candidate_count"]) for item in books)
    tiers: Counter[str] = Counter()
    for item in books:
        tiers.update(item["tier_counts"])

    summary_path = output_root / "topic-prefilter-summary-v1.csv"
    write_summary(summary_path, books)

    manifest = {
        "schema_version": SCHEMA,
        "episode_id": EPISODE_ID,
        "status": "PASS_CANDIDATE_ONLY",
        "scope": {
            "episode_title": "آدم عليه السلام: الخلق والتكريم والسكن في الجنة",
            "scope_end": "BEFORE_WHISPERING",
            "filter_type": "DETERMINISTIC_LEXICAL_AND_COOCCURRENCE",
        },
        "source_manifest": source_manifest_path.relative_to(project).as_posix(),
        "source_manifest_sha256": sha256_file(source_manifest_path),
        "lexicon": {
            "project_path": lexicon_path.relative_to(project).as_posix(),
            "sha256": sha256_file(lexicon_path),
        },
        "book_count": len(books),
        "scanned_page_count": scanned,
        "candidate_count_before_cap": before_cap,
        "candidate_count": candidates,
        "candidate_limit_per_book": args.per_book_limit,
        "tier_counts": dict(sorted(tiers.items())),
        "attribution_candidate_count": attributions,
        "summary_csv": {
            "project_path": summary_path.relative_to(project).as_posix(),
            "sha256": sha256_file(summary_path),
        },
        "books": books,
        "permissions": {
            "candidate_only": True,
            "gemini_execution_enabled": False,
            "source_approval_changed": False,
            "quotation_approval_changed": False,
            "evidence_approval_changed": False,
            "report_classification_changed": False,
            "israiliyyat_classification_changed": False,
        },
        "next_gate": "HUMAN_PREFILTER_REVIEW_AND_BOUNDED_WINDOW_PACKAGING",
        "created_at": now_utc(),
    }
    manifest_path = output_root / "topic-prefilter-manifest-v1.json"
    write_json(manifest_path, manifest)
    test_path = write_test(repo)

    print(json.dumps({
        "status": "PASS",
        "manifest": str(manifest_path),
        "summary_csv": str(summary_path),
        "integration_test": str(test_path),
        "counts": {
            "books": len(books),
            "scanned_pages": scanned,
            "candidates_before_cap": before_cap,
            "candidates": candidates,
            "tiers": dict(sorted(tiers.items())),
            "attribution_candidates": attributions,
        },
        "gemini_execution_enabled": False,
        "source_approval_changed": False,
        "quotation_approval_changed": False,
        "report_classification_changed": False,
        "next_gate": manifest["next_gate"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
