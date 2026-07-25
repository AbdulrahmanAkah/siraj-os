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
ARABIC_DIACRITICS = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")
WHITESPACE = re.compile(r"\s+")
TABARI_PATTERNS = [
    "صلة تاريخ الطبري",
    "صلة الطبري",
    "عريب بن سعد",
    "عريب القرطبي",
]


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"JSONL_OBJECT_REQUIRED:{path}:{line_number}")
            yield value


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> tuple[int, str]:
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            line = json.dumps(
                row,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ) + "\n"
            stream.write(line)
            digest.update(line.encode("utf-8"))
            count += 1
    return count, digest.hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_arabic(text: str) -> str:
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ؤ", "و").replace("ئ", "ي")
    text = text.replace("ـ", "")
    text = ARABIC_DIACRITICS.sub("", text)
    return WHITESPACE.sub(" ", text).strip().casefold()


def load_pages(path: Path) -> tuple[list[dict[str, Any]], dict[int, int], dict[int, dict[str, Any]]]:
    pages = list(iter_jsonl(path))
    pages.sort(key=lambda row: safe_int(row.get("sequence_num")))
    sequence_by_page: dict[int, int] = {}
    page_by_sequence: dict[int, dict[str, Any]] = {}
    for index, page in enumerate(pages, start=1):
        page_id = safe_int(page["shamela_page_id"])
        sequence = safe_int(page.get("sequence_num"), index)
        sequence_by_page[page_id] = sequence
        page_by_sequence[sequence] = page
    return pages, sequence_by_page, page_by_sequence


def load_headings(path: Path) -> tuple[dict[int, list[str]], list[dict[str, Any]]]:
    headings: dict[int, list[str]] = defaultdict(list)
    rows = list(iter_jsonl(path))
    for row in rows:
        page_id = row.get("page_segment_id")
        title = str(row.get("title_text") or "").strip()
        if page_id is not None and title:
            headings[safe_int(page_id)].append(title)
    return dict(headings), rows


def detect_tabari_boundary(
    work_source_id: str,
    pages: list[dict[str, Any]],
    toc_rows: list[dict[str, Any]],
    sequence_by_page: dict[int, int],
) -> dict[str, Any]:
    if work_source_id != "SRC-HISTORY-TABARI-ADAM":
        return {"status": "NOT_APPLICABLE", "boundary_sequence_num": None}

    normalized_patterns = [(raw, normalize_arabic(raw)) for raw in TABARI_PATTERNS]
    hits: list[dict[str, Any]] = []

    for row in toc_rows:
        text = str(row.get("title_text") or "")
        normalized = normalize_arabic(text)
        for raw, pattern in normalized_patterns:
            if pattern and pattern in normalized:
                page_id = safe_int(row.get("page_segment_id"), -1)
                sequence = sequence_by_page.get(page_id)
                if sequence is not None:
                    hits.append(
                        {
                            "source": "TOC",
                            "sequence_num": sequence,
                            "page_id": page_id,
                            "matched_pattern": raw,
                            "matched_text": text[:500],
                        }
                    )

    for page in pages:
        text = str(page.get("content_text") or "")
        normalized = normalize_arabic(text)
        for raw, pattern in normalized_patterns:
            if pattern and pattern in normalized:
                hits.append(
                    {
                        "source": "PAGE",
                        "sequence_num": safe_int(page.get("sequence_num")),
                        "page_id": safe_int(page.get("shamela_page_id")),
                        "matched_pattern": raw,
                        "matched_text": WHITESPACE.sub(" ", text).strip()[:500],
                    }
                )
                break

    hits.sort(key=lambda item: (item["sequence_num"], 0 if item["source"] == "TOC" else 1))
    if not hits:
        return {
            "status": "NOT_DETECTED_HUMAN_REVIEW_REQUIRED",
            "boundary_sequence_num": None,
            "hits": [],
        }

    first = hits[0]
    return {
        "status": "DETECTED_CANDIDATE_BOUNDARY",
        "boundary_sequence_num": first["sequence_num"],
        "boundary_page_id": first["page_id"],
        "matched_pattern": first["matched_pattern"],
        "matched_text": first["matched_text"],
        "source": first["source"],
        "hits": hits[:50],
        "policy": "Windows starting at or after this candidate boundary are excluded pending human confirmation.",
    }


def choose_candidates(rows: list[dict[str, Any]], c_limit: int) -> list[dict[str, Any]]:
    tier_ab = [row for row in rows if row.get("candidate_tier") in {"A", "B"}]
    tier_c = [row for row in rows if row.get("candidate_tier") == "C"]
    tier_d = [
        row
        for row in rows
        if row.get("candidate_tier") == "D" and row.get("attribution_profiles")
    ]
    tier_ab.sort(key=lambda row: (0 if row.get("candidate_tier") == "A" else 1, -safe_int(row.get("score"))))
    tier_c.sort(key=lambda row: -safe_int(row.get("score")))
    chosen = tier_ab + tier_c[:c_limit] + tier_d
    unique: dict[str, dict[str, Any]] = {}
    for row in chosen:
        unique[str(row["candidate_id"])] = row
    return list(unique.values())


def candidate_ranges(
    selected: list[dict[str, Any]],
    sequence_by_page: dict[int, int],
    page_count: int,
    maximum_gap: int,
    context_pages: int,
) -> list[dict[str, Any]]:
    rows = []
    for candidate in selected:
        page_id = safe_int(candidate.get("shamela_page_id"))
        sequence = sequence_by_page.get(page_id)
        if sequence is not None:
            rows.append((sequence, candidate))
    rows.sort(key=lambda item: (item[0], -safe_int(item[1].get("score"))))

    clusters: list[list[tuple[int, dict[str, Any]]]] = []
    current: list[tuple[int, dict[str, Any]]] = []
    previous: int | None = None
    for sequence, candidate in rows:
        if current and previous is not None and sequence - previous > maximum_gap:
            clusters.append(current)
            current = []
        current.append((sequence, candidate))
        previous = sequence
    if current:
        clusters.append(current)

    ranges: list[dict[str, Any]] = []
    for cluster in clusters:
        sequences = [item[0] for item in cluster]
        ranges.append(
            {
                "start": max(min(sequences) - context_pages, 1),
                "end": min(max(sequences) + context_pages, page_count),
                "candidates": [item[1] for item in cluster],
            }
        )

    ranges.sort(key=lambda item: (item["start"], item["end"]))
    merged: list[dict[str, Any]] = []
    for item in ranges:
        if not merged or item["start"] > merged[-1]["end"] + 1:
            merged.append(item)
            continue
        merged[-1]["end"] = max(merged[-1]["end"], item["end"])
        existing = {str(row["candidate_id"]) for row in merged[-1]["candidates"]}
        for row in item["candidates"]:
            if str(row["candidate_id"]) not in existing:
                merged[-1]["candidates"].append(row)
                existing.add(str(row["candidate_id"]))
    return merged


def format_page(page: dict[str, Any], headings: list[str]) -> str:
    header = [f"LOCATOR: {page['canonical_locator']}"]
    if page.get("volume") not in (None, ""):
        header.append(f"VOLUME: {page['volume']}")
    if page.get("page_num") not in (None, ""):
        header.append(f"PAGE: {page['page_num']}")
    sections = [" | ".join(header)]
    if headings:
        sections.append("HEADINGS: " + " | ".join(headings))
    body = str(page.get("content_raw") or "").strip()
    foot = str(page.get("footnote_raw") or "").strip()
    if body:
        sections.append(body)
    if foot:
        sections.append("FOOTNOTES:\n" + foot)
    return "\n".join(sections).strip()


def build_book(
    project: Path,
    output_root: Path,
    prefilter_book: dict[str, Any],
    normalized_book: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    work_source_id = str(prefilter_book["work_source_id"])
    book_id = safe_int(prefilter_book["book_id"])

    candidates_path = project / prefilter_book["outputs"]["candidates"]["project_path"]
    pages_path = project / normalized_book["normalized_files"]["pages"]["project_path"]
    toc_path = project / normalized_book["normalized_files"]["toc"]["project_path"]

    if sha256_file(candidates_path) != prefilter_book["outputs"]["candidates"]["sha256"]:
        raise ValueError(f"CANDIDATE_CHECKSUM_MISMATCH:{work_source_id}")
    if sha256_file(pages_path) != normalized_book["normalized_files"]["pages"]["sha256"]:
        raise ValueError(f"PAGES_CHECKSUM_MISMATCH:{work_source_id}")
    if sha256_file(toc_path) != normalized_book["normalized_files"]["toc"]["sha256"]:
        raise ValueError(f"TOC_CHECKSUM_MISMATCH:{work_source_id}")

    candidates = list(iter_jsonl(candidates_path))
    pages, sequence_by_page, page_by_sequence = load_pages(pages_path)
    headings_by_page, toc_rows = load_headings(toc_path)
    boundary = detect_tabari_boundary(
        work_source_id,
        pages,
        toc_rows,
        sequence_by_page,
    )

    selected = choose_candidates(candidates, args.c_tier_limit_per_book)
    ranges = candidate_ranges(
        selected,
        sequence_by_page,
        len(pages),
        args.maximum_gap,
        args.context_pages,
    )

    windows: list[dict[str, Any]] = []
    excluded_after_boundary = 0
    for item in ranges:
        boundary_sequence = boundary.get("boundary_sequence_num")
        if boundary_sequence is not None and item["start"] >= safe_int(boundary_sequence):
            excluded_after_boundary += 1
            continue

        page_entries: list[dict[str, Any]] = []
        total_chars = 0
        truncated = False
        for sequence in range(item["start"], item["end"] + 1):
            page = page_by_sequence.get(sequence)
            if page is None:
                continue
            page_id = safe_int(page["shamela_page_id"])
            text = format_page(page, headings_by_page.get(page_id, []))
            remaining = args.maximum_characters_per_window - total_chars
            if remaining <= 0:
                truncated = True
                break
            if len(text) > remaining:
                text = text[:remaining].rstrip() + "\n[WINDOW_TEXT_TRUNCATED]"
                truncated = True
            page_entries.append(
                {
                    "sequence_num": sequence,
                    "shamela_page_id": page_id,
                    "canonical_locator": page["canonical_locator"],
                    "headings": headings_by_page.get(page_id, []),
                    "text": text,
                }
            )
            total_chars += len(text)
            if truncated:
                break

        if not page_entries:
            continue

        candidate_rows = sorted(
            item["candidates"],
            key=lambda row: (
                {"A": 0, "B": 1, "C": 2, "D": 3}.get(str(row.get("candidate_tier")), 4),
                -safe_int(row.get("score")),
            ),
        )
        tier_counts = Counter(str(row.get("candidate_tier")) for row in candidate_rows)
        categories = sorted(
            {
                category
                for row in candidate_rows
                for category in row.get("matched_categories", [])
            }
        )
        attributions = sorted(
            {
                profile
                for row in candidate_rows
                for profile in row.get("attribution_profiles", [])
            }
        )
        maximum_score = max(safe_int(row.get("score")) for row in candidate_rows)
        aggregate_score = (
            maximum_score
            + tier_counts.get("A", 0) * 30
            + tier_counts.get("B", 0) * 12
            + tier_counts.get("C", 0) * 4
            + len(categories) * 5
        )
        window = {
            "schema_version": "siraj-adam-bounded-review-window-v1",
            "episode_id": EPISODE_ID,
            "work_source_id": work_source_id,
            "book_id": book_id,
            "book_title": normalized_book.get("book_title", ""),
            "window_id": canonical_hash(
                [work_source_id, book_id, item["start"], item["end"], [row["candidate_id"] for row in candidate_rows]]
            )[:24],
            "sequence_start": item["start"],
            "sequence_end": item["end"],
            "page_count": len(page_entries),
            "candidate_count": len(candidate_rows),
            "candidate_ids": [row["candidate_id"] for row in candidate_rows],
            "candidate_tier_counts": dict(sorted(tier_counts.items())),
            "maximum_candidate_score": maximum_score,
            "aggregate_window_score": aggregate_score,
            "matched_categories": categories,
            "attribution_profiles": attributions,
            "character_count": total_chars,
            "text_truncated": truncated,
            "pages": page_entries,
            "human_review": {
                "status": "PENDING",
                "include_for_gemini": None,
                "scope_fit": None,
                "duplicate_group": None,
                "notes": "",
            },
            "permissions": {
                "candidate_only": True,
                "allowed_for_gemini": False,
                "approved_for_evidence": False,
                "approved_for_quotation": False,
                "report_classification_changed": False,
                "israiliyyat_classification_changed": False,
            },
        }
        window["record_sha256"] = canonical_hash(window)
        windows.append(window)

    windows.sort(key=lambda row: (-safe_int(row["aggregate_window_score"]), safe_int(row["sequence_start"])))

    selected_windows: list[dict[str, Any]] = []
    used_chars = 0
    excluded_by_budget = 0
    for window in windows:
        if len(selected_windows) >= args.maximum_windows_per_book:
            excluded_by_budget += 1
            continue
        if used_chars + safe_int(window["character_count"]) > args.maximum_characters_per_book:
            excluded_by_budget += 1
            continue
        selected_windows.append(window)
        used_chars += safe_int(window["character_count"])

    book_root = output_root / work_source_id
    windows_path = book_root / "review-windows.jsonl"
    drafts_path = book_root / "gemini-input-draft.jsonl"
    manifest_path = book_root / "manifest.json"

    window_count, windows_sha = write_jsonl(windows_path, selected_windows)
    drafts = [
        {
            "schema_version": "siraj-adam-gemini-input-draft-v1",
            "episode_id": EPISODE_ID,
            "work_source_id": work_source_id,
            "book_id": book_id,
            "window_id": window["window_id"],
            "instruction_status": "BLOCKED_PENDING_HUMAN_WINDOW_APPROVAL",
            "task": (
                "Locate candidate passages and organise attribution, isnad, repetition, conflict, and research-question relevance. "
                "Do not grade hadith, decide theology, approve reports, approve quotations, or classify Isra'iliyyat."
            ),
            "matched_categories": window["matched_categories"],
            "attribution_profiles": window["attribution_profiles"],
            "pages": window["pages"],
            "permissions": {
                "allowed_for_gemini": False,
                "human_approval_required": True,
                "candidate_only": True,
            },
        }
        for window in selected_windows
    ]
    draft_count, drafts_sha = write_jsonl(drafts_path, drafts)

    tier_counts: Counter[str] = Counter()
    attribution_counts: Counter[str] = Counter()
    for window in selected_windows:
        tier_counts.update(window["candidate_tier_counts"])
        attribution_counts.update(window["attribution_profiles"])

    manifest = {
        "work_source_id": work_source_id,
        "book_id": book_id,
        "book_title": normalized_book.get("book_title", ""),
        "input_candidate_count": len(candidates),
        "selected_candidate_count": len(selected),
        "raw_window_count": len(windows),
        "review_window_count": window_count,
        "review_window_character_count": used_chars,
        "review_window_limit": args.maximum_windows_per_book,
        "book_character_limit": args.maximum_characters_per_book,
        "window_character_limit": args.maximum_characters_per_window,
        "excluded_after_tabari_boundary": excluded_after_boundary,
        "excluded_by_book_budget": excluded_by_budget,
        "tier_counts": dict(sorted(tier_counts.items())),
        "attribution_profile_counts": dict(sorted(attribution_counts.items())),
        "tabari_continuation_boundary": boundary,
        "outputs": {
            "review_windows": {
                "project_path": windows_path.relative_to(project).as_posix(),
                "rows": window_count,
                "sha256": windows_sha,
            },
            "gemini_input_draft": {
                "project_path": drafts_path.relative_to(project).as_posix(),
                "rows": draft_count,
                "sha256": drafts_sha,
                "execution_status": "BLOCKED_PENDING_HUMAN_WINDOW_APPROVAL",
            },
        },
    }
    write_json(manifest_path, manifest)
    manifest["manifest_project_path"] = manifest_path.relative_to(project).as_posix()
    manifest["manifest_sha256"] = sha256_file(manifest_path)
    return manifest


def write_review_csv(project: Path, path: Path, books: list[dict[str, Any]]) -> None:
    fields = [
        "work_source_id",
        "book_id",
        "book_title",
        "window_id",
        "sequence_start",
        "sequence_end",
        "page_count",
        "candidate_count",
        "maximum_candidate_score",
        "aggregate_window_score",
        "tier_A",
        "tier_B",
        "tier_C",
        "tier_D",
        "matched_categories",
        "attribution_profiles",
        "character_count",
        "text_truncated",
        "human_status",
        "include_for_gemini",
        "scope_fit",
        "duplicate_group",
        "reviewer_notes",
        "first_locator",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for book in books:
            windows_path = project / book["outputs"]["review_windows"]["project_path"]
            for window in iter_jsonl(windows_path):
                tiers = window["candidate_tier_counts"]
                first_locator = ""
                if window.get("pages"):
                    first_locator = str(window["pages"][0].get("canonical_locator") or "")
                writer.writerow(
                    {
                        "work_source_id": window["work_source_id"],
                        "book_id": window["book_id"],
                        "book_title": window["book_title"],
                        "window_id": window["window_id"],
                        "sequence_start": window["sequence_start"],
                        "sequence_end": window["sequence_end"],
                        "page_count": window["page_count"],
                        "candidate_count": window["candidate_count"],
                        "maximum_candidate_score": window["maximum_candidate_score"],
                        "aggregate_window_score": window["aggregate_window_score"],
                        "tier_A": tiers.get("A", 0),
                        "tier_B": tiers.get("B", 0),
                        "tier_C": tiers.get("C", 0),
                        "tier_D": tiers.get("D", 0),
                        "matched_categories": " | ".join(window["matched_categories"]),
                        "attribution_profiles": " | ".join(window["attribution_profiles"]),
                        "character_count": window["character_count"],
                        "text_truncated": window["text_truncated"],
                        "human_status": "PENDING",
                        "include_for_gemini": "",
                        "scope_fit": "",
                        "duplicate_group": "",
                        "reviewer_notes": "",
                        "first_locator": first_locator,
                    }
                )


def write_test(repo: Path) -> Path:
    path = repo / "tests" / "integration" / "test_adam_bounded_review_windows_v1.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        """from __future__ import annotations

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
""",
        encoding="utf-8",
        newline="\n",
    )
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--c-tier-limit-per-book", type=int, default=140)
    parser.add_argument("--maximum-gap", type=int, default=2)
    parser.add_argument("--context-pages", type=int, default=1)
    parser.add_argument("--maximum-windows-per-book", type=int, default=45)
    parser.add_argument("--maximum-characters-per-window", type=int, default=18000)
    parser.add_argument("--maximum-characters-per-book", type=int, default=240000)
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    project = repo / "projects" / EPISODE_ID
    secondary = project / "sources" / "secondary"
    prefilter_path = secondary / "topic-prefilter" / "topic-prefilter-manifest-v1.json"
    normalized_path = secondary / "normalized-export-manifest-v1.json"

    prefilter = read_json(prefilter_path)
    normalized = read_json(normalized_path)
    if prefilter.get("status") != "PASS_CANDIDATE_ONLY":
        raise ValueError("PREFILTER_NOT_READY")
    if normalized.get("status") != "PASS_READY_FOR_BOUNDED_LOCAL_SEARCH":
        raise ValueError("NORMALIZED_EXPORT_NOT_READY")
    if safe_int(prefilter.get("book_count")) != 9 or safe_int(normalized.get("book_count")) != 9:
        raise ValueError("EXPECTED_NINE_BOOKS")

    normalized_by_source = {str(book["work_source_id"]): book for book in normalized["books"]}
    output_root = secondary / "bounded-review-windows"
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)
    (output_root / ".gitignore").write_text(
        "*/review-windows.jsonl\n*/gemini-input-draft.jsonl\n",
        encoding="ascii",
        newline="\n",
    )

    books: list[dict[str, Any]] = []
    for prefilter_book in prefilter["books"]:
        work_source_id = str(prefilter_book["work_source_id"])
        normalized_book = normalized_by_source.get(work_source_id)
        if normalized_book is None:
            raise ValueError(f"NORMALIZED_BOOK_NOT_FOUND:{work_source_id}")
        print(json.dumps({"event": "WINDOW_PACKAGING_START", "work_source_id": work_source_id, "book_id": prefilter_book["book_id"]}, ensure_ascii=False), flush=True)
        result = build_book(project, output_root, prefilter_book, normalized_book, args)
        books.append(result)
        print(
            json.dumps(
                {
                    "event": "WINDOW_PACKAGING_PASS",
                    "work_source_id": work_source_id,
                    "book_id": result["book_id"],
                    "review_windows": result["review_window_count"],
                    "characters": result["review_window_character_count"],
                    "tabari_boundary_status": result["tabari_continuation_boundary"]["status"],
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    books.sort(key=lambda item: item["work_source_id"])
    review_csv = output_root / "human-review-queue-v1.csv"
    write_review_csv(project, review_csv, books)

    total_windows = sum(safe_int(book["review_window_count"]) for book in books)
    total_chars = sum(safe_int(book["review_window_character_count"]) for book in books)
    tier_counts: Counter[str] = Counter()
    attribution_windows = 0
    for book in books:
        tier_counts.update(book["tier_counts"])
        windows_path = project / book["outputs"]["review_windows"]["project_path"]
        attribution_windows += sum(1 for row in iter_jsonl(windows_path) if row.get("attribution_profiles"))

    manifest = {
        "schema_version": "siraj-adam-bounded-review-window-manifest-v1",
        "episode_id": EPISODE_ID,
        "status": "PASS_HUMAN_REVIEW_QUEUE_READY",
        "source_prefilter_manifest": prefilter_path.relative_to(project).as_posix(),
        "source_prefilter_manifest_sha256": sha256_file(prefilter_path),
        "source_normalized_manifest": normalized_path.relative_to(project).as_posix(),
        "source_normalized_manifest_sha256": sha256_file(normalized_path),
        "book_count": len(books),
        "review_window_count": total_windows,
        "review_window_character_count": total_chars,
        "attribution_window_count": attribution_windows,
        "tier_counts": dict(sorted(tier_counts.items())),
        "configuration": {
            "c_tier_limit_per_book": args.c_tier_limit_per_book,
            "maximum_gap": args.maximum_gap,
            "context_pages": args.context_pages,
            "maximum_windows_per_book": args.maximum_windows_per_book,
            "maximum_characters_per_window": args.maximum_characters_per_window,
            "maximum_characters_per_book": args.maximum_characters_per_book,
        },
        "human_review_queue": {
            "project_path": review_csv.relative_to(project).as_posix(),
            "sha256": sha256_file(review_csv),
            "status": "PENDING_HUMAN_REVIEW",
        },
        "books": books,
        "permissions": {
            "candidate_only": True,
            "gemini_execution_enabled": False,
            "source_approval_changed": False,
            "evidence_approval_changed": False,
            "quotation_approval_changed": False,
            "report_classification_changed": False,
            "israiliyyat_classification_changed": False,
        },
        "next_gate": "HUMAN_WINDOW_APPROVAL_FOR_GEMINI",
        "created_at": now_utc(),
    }
    manifest_path = output_root / "bounded-review-window-manifest-v1.json"
    write_json(manifest_path, manifest)
    test_path = write_test(repo)

    print(
        json.dumps(
            {
                "status": "PASS",
                "manifest": str(manifest_path),
                "human_review_queue": str(review_csv),
                "integration_test": str(test_path),
                "counts": {
                    "books": len(books),
                    "review_windows": total_windows,
                    "characters": total_chars,
                    "attribution_windows": attribution_windows,
                    "tiers": dict(sorted(tier_counts.items())),
                },
                "gemini_execution_enabled": False,
                "source_approval_changed": False,
                "quotation_approval_changed": False,
                "report_classification_changed": False,
                "israiliyyat_classification_changed": False,
                "next_gate": manifest["next_gate"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
