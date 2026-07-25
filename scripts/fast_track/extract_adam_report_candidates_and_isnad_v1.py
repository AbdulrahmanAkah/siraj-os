from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import unicodedata
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


EPISODE_ID = "episode-001-adam"
SCHEMA_VERSION = "siraj-adam-report-level-extraction-v1"
OUTPUT_DIR_NAME = "report-level-extraction"

POST_BOUNDARY_PATTERNS = [
    "فوسوس",
    "وسوس لهما",
    "وسوس إليه",
    "فأزلهما",
    "فازلهما",
    "فأكلا",
    "فاكلا",
    "اهبطوا",
    "فتلقى آدم",
    "فتلقي آدم",
]

PROPHETIC_PATTERNS = [
    "قال رسول الله",
    "عن رسول الله",
    "أن رسول الله",
    "ان رسول الله",
    "عن النبي",
    "أن النبي",
    "ان النبي",
    "قال النبي",
    "مرفوعا",
    "مرفوعًا",
]

TRANSMISSION_MARKERS = [
    "حدثنا",
    "حدثني",
    "أخبرنا",
    "اخبرنا",
    "أخبرني",
    "اخبرني",
    "ثنا",
    "سمعت",
    "عن",
    "قال",
]

AUTHORIAL_START_PATTERNS = [
    "قال أبو جعفر",
    "قال ابو جعفر",
    "قال ابن جرير",
    "قال ابن كثير",
    "قال المصنف",
    "قلت",
    "والصواب",
    "والظاهر",
    "وهذا",
]

REPORT_START_PATTERNS = [
    "حدثنا",
    "حدثني",
    "أخبرنا",
    "اخبرنا",
    "أخبرني",
    "اخبرني",
    "ثنا",
    "ذكر من قال",
    "ذكرُ من قال",
    "وروى",
    "وروي",
    "روي",
    "وأخرج",
    "واخرج",
    "أخرج",
    "اخرج",
    "قال أبو جعفر",
    "قال ابو جعفر",
    "قال ابن جرير",
    "قال ابن كثير",
    "قال المصنف",
]

EARLY_ATTRIBUTION_NAMES = {
    "وهب بن منبه": "WAHB_IBN_MUNABBIH",
    "وهب": "WAHB_IBN_MUNABBIH",
    "كعب الأحبار": "KAB_AL_AHBAR",
    "كعب الاحبار": "KAB_AL_AHBAR",
    "كعب الحبر": "KAB_AL_AHBAR",
}


def now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(
                    f"JSONL_OBJECT_REQUIRED:{path}:{line_number}"
                )
            yield value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(
                json.dumps(row, ensure_ascii=False, sort_keys=True)
                + "\n"
            )
            count += 1
    return count


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_id(prefix: str, *parts: Any, length: int = 24) -> str:
    payload = "\x1f".join(str(part) for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{prefix}_{digest[:length]}"


def normalize_arabic(value: str) -> str:
    value = "".join(
        character
        for character in unicodedata.normalize("NFKD", value)
        if not unicodedata.combining(character)
    )
    value = value.translate(
        str.maketrans(
            {
                "أ": "ا",
                "إ": "ا",
                "آ": "ا",
                "ى": "ي",
                "ؤ": "و",
                "ئ": "ي",
                "ـ": "",
            }
        )
    )
    return re.sub(r"\s+", " ", value).strip().casefold()


def normalized_with_map(value: str) -> tuple[str, list[int]]:
    normalized_chars: list[str] = []
    source_indices: list[int] = []
    replacements = {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ـ": "",
    }
    for index, character in enumerate(value):
        decomposed = unicodedata.normalize("NFKD", character)
        for item in decomposed:
            if unicodedata.combining(item):
                continue
            replacement = replacements.get(item, item)
            for replacement_character in replacement:
                normalized_chars.append(replacement_character.casefold())
                source_indices.append(index)
    return "".join(normalized_chars), source_indices


def find_original_offset(
    value: str,
    patterns: list[str],
) -> tuple[int | None, str | None]:
    normalized, index_map = normalized_with_map(value)
    best_position: int | None = None
    best_pattern: str | None = None
    for pattern in patterns:
        normalized_pattern = normalize_arabic(pattern)
        position = normalized.find(normalized_pattern)
        if position < 0:
            continue
        if best_position is None or position < best_position:
            best_position = position
            best_pattern = pattern
    if best_position is None or not index_map:
        return None, None
    return index_map[best_position], best_pattern


def strip_html_titles(value: str) -> tuple[str, list[str]]:
    headings: list[str] = []

    def replace(match: re.Match[str]) -> str:
        heading = re.sub(r"<[^>]+>", "", match.group(0)).strip()
        if heading:
            headings.append(heading)
        return "\n" + heading + "\n"

    cleaned = re.sub(
        r"<span\b[^>]*data-type=[\"']title[\"'][^>]*>.*?</span>",
        replace,
        value,
        flags=re.IGNORECASE | re.DOTALL,
    )
    cleaned = re.sub(r"<[^>]+>", "", cleaned)
    return cleaned, headings


def clean_page_text(
    page: dict[str, Any],
) -> tuple[str, str, list[str]]:
    raw = str(
        page.get("text")
        or page.get("content_raw")
        or page.get("content_text")
        or ""
    ).replace("\r\n", "\n").replace("\r", "\n")

    explicit_footnotes = str(page.get("footnote_raw") or "")
    headings = list(page.get("headings") or [])

    raw, embedded_headings = strip_html_titles(raw)
    headings.extend(
        heading for heading in embedded_headings
        if heading not in headings
    )

    lines = raw.splitlines()
    retained_lines: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if index == 0 and stripped.startswith("LOCATOR:"):
            continue
        if index <= 1 and stripped.startswith("HEADINGS:"):
            heading_value = stripped.partition(":")[2].strip()
            if heading_value and heading_value not in headings:
                headings.append(heading_value)
            continue
        retained_lines.append(line)

    joined = "\n".join(retained_lines)
    body, separator, embedded_footnotes = joined.partition(
        "\nFOOTNOTES:\n"
    )
    footnotes = explicit_footnotes
    if separator:
        footnotes = "\n".join(
            item for item in [embedded_footnotes, explicit_footnotes]
            if item.strip()
        )

    body = re.sub(r"[ \t]+\n", "\n", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    footnotes = re.sub(r"\n{3,}", "\n\n", footnotes).strip()
    return body, footnotes, headings


def report_start_offsets(value: str) -> list[int]:
    normalized, index_map = normalized_with_map(value)
    if not normalized or not index_map:
        return [0]

    patterns = "|".join(
        re.escape(normalize_arabic(pattern))
        for pattern in sorted(
            REPORT_START_PATTERNS,
            key=len,
            reverse=True,
        )
    )
    regex = re.compile(
        rf"(?:(?<=\n)|(?<=\. )|(?<=؛ )|(?<=: ))"
        rf"\s*(?:{patterns})\b"
    )

    offsets = {0}
    for match in regex.finditer(normalized):
        offsets.add(index_map[match.start()])
    return sorted(offsets)


def split_long_unit(
    value: str,
    *,
    maximum_chars: int = 6000,
) -> list[tuple[int, int, str]]:
    if len(value) <= maximum_chars:
        return [(0, len(value), value)]

    boundaries = [0]
    for match in re.finditer(r"\n\n+|(?<=[.!؟؛])\s+", value):
        boundaries.append(match.end())
    boundaries.append(len(value))
    boundaries = sorted(set(boundaries))

    chunks: list[tuple[int, int, str]] = []
    start = 0
    while start < len(value):
        ideal_end = min(len(value), start + maximum_chars)
        candidates = [
            boundary for boundary in boundaries
            if start + 600 <= boundary <= ideal_end
        ]
        end = max(candidates) if candidates else ideal_end
        if end <= start:
            end = min(len(value), start + maximum_chars)
        text = value[start:end].strip()
        if text:
            left_trim = len(value[start:end]) - len(
                value[start:end].lstrip()
            )
            right_trimmed_length = len(value[start:end].rstrip())
            actual_start = start + left_trim
            actual_end = start + right_trimmed_length
            chunks.append((actual_start, actual_end, text))
        start = end
    return chunks


def split_report_units(
    body: str,
) -> list[tuple[int, int, str]]:
    offsets = report_start_offsets(body)
    offsets.append(len(body))
    raw_units: list[tuple[int, int, str]] = []

    for left, right in zip(offsets, offsets[1:]):
        fragment = body[left:right]
        if not fragment.strip():
            continue
        leading = len(fragment) - len(fragment.lstrip())
        trailing_length = len(fragment.rstrip())
        actual_left = left + leading
        actual_right = left + trailing_length
        text = body[actual_left:actual_right]
        for sub_left, sub_right, sub_text in split_long_unit(text):
            raw_units.append(
                (
                    actual_left + sub_left,
                    actual_left + sub_right,
                    sub_text,
                )
            )

    merged: list[tuple[int, int, str]] = []
    for unit in raw_units:
        if (
            merged
            and len(unit[2]) < 120
            and len(merged[-1][2]) + len(unit[2]) <= 6000
        ):
            previous = merged.pop()
            merged.append(
                (
                    previous[0],
                    unit[1],
                    body[previous[0]:unit[1]].strip(),
                )
            )
        else:
            merged.append(unit)

    return merged or [(0, len(body), body)]


def detect_attribution_profiles(
    value: str,
    inherited: list[str],
) -> list[str]:
    profiles = set(inherited)
    normalized = normalize_arabic(value)
    for name, profile in EARLY_ATTRIBUTION_NAMES.items():
        if normalize_arabic(name) in normalized:
            profiles.add(profile)
    return sorted(profiles)


def extract_chain_surfaces(value: str) -> list[dict[str, str]]:
    normalized = normalize_arabic(value)
    marker_pattern = "|".join(
        re.escape(normalize_arabic(marker))
        for marker in sorted(
            TRANSMISSION_MARKERS,
            key=len,
            reverse=True,
        )
    )
    regex = re.compile(
        rf"(?:^|[،,:؛]\s+|\n)"
        rf"(?P<marker>{marker_pattern})\s+"
        rf"(?P<surface>[^،,:؛\n]{{2,120}})"
    )

    records: list[dict[str, str]] = []
    for match in regex.finditer(normalized[:2200]):
        surface = re.sub(r"\s+", " ", match.group("surface")).strip()
        if len(surface.split()) > 16:
            continue
        if any(
            phrase in surface
            for phrase in [
                "الله تعالى",
                "الله جل",
                "هذه الآية",
                "هذا القول",
                "ذلك",
                "في الأرض",
            ]
        ):
            continue
        records.append(
            {
                "marker": match.group("marker"),
                "surface_candidate": surface,
            }
        )
    return records[:20]


def extract_isnad_candidate(
    value: str,
    report_kind: str,
) -> tuple[str, str]:
    normalized = normalize_arabic(value)
    starts_with_chain = any(
        normalized.startswith(normalize_arabic(marker) + " ")
        for marker in [
            "حدثنا",
            "حدثني",
            "أخبرنا",
            "اخبرنا",
            "أخبرني",
            "اخبرني",
            "ثنا",
        ]
    )

    if report_kind == "PROPHETIC_HADITH_CANDIDATE":
        positions = []
        for pattern in PROPHETIC_PATTERNS:
            position = normalized.find(normalize_arabic(pattern))
            if position >= 0:
                positions.append(position)
        if positions:
            normalized_position = min(positions)
            _, index_map = normalized_with_map(value)
            original_position = (
                index_map[normalized_position]
                if index_map
                else 0
            )
            end = min(len(value), original_position + 180)
            prefix = value[:end].strip()
            status = (
                "CANDIDATE_PREFIX_EXTRACTED"
                if prefix
                else "NO_PREFIX"
            )
            return prefix, status

    if starts_with_chain:
        boundary_match = re.search(
            r"[،,:؛]\s*(?:قال|أنه|انّه|أنّه|أن|ان)\s+",
            value[:1600],
        )
        end = (
            boundary_match.end()
            if boundary_match
            else min(len(value), 1000)
        )
        return value[:end].strip(), "CANDIDATE_PREFIX_EXTRACTED"

    return "", "NO_ISNAD_PREFIX_DETECTED"


def classify_report_kind(value: str) -> str:
    normalized = normalize_arabic(value)
    if any(
        normalize_arabic(pattern) in normalized
        for pattern in PROPHETIC_PATTERNS
    ):
        return "PROPHETIC_HADITH_CANDIDATE"

    starts_authorial = any(
        normalized.startswith(normalize_arabic(pattern))
        for pattern in AUTHORIAL_START_PATTERNS
    )
    if starts_authorial:
        return "AUTHORIAL_COMMENTARY_CANDIDATE"

    chain_surfaces = extract_chain_surfaces(value)
    if chain_surfaces:
        return "EARLY_REPORT_CANDIDATE"

    if "﴿" in value and "﴾" in value:
        return "QURAN_EXEGESIS_CONTEXT_CANDIDATE"

    return "UNCLASSIFIED_SOURCE_PASSAGE_CANDIDATE"


def script_attribution_candidate(
    *,
    value: str,
    report_kind: str,
    chain_surfaces: list[dict[str, str]],
    policy: dict[str, Any],
) -> dict[str, Any]:
    if report_kind == "PROPHETIC_HADITH_CANDIDATE":
        nearest = (
            chain_surfaces[-1]["surface_candidate"]
            if chain_surfaces
            else None
        )
        return {
            "display_mode": (
                "PROPHET_WITH_COMPANION_OR_MARFU_TABII"
            ),
            "prophet_name": "محمد ﷺ",
            "nearest_upstream_narrator_candidate": nearest,
            "companion_or_marfu_tabii_resolution_status": (
                "HUMAN_REVIEW_REQUIRED"
            ),
            "full_isnad_in_script": False,
            "policy_id": policy.get("policy_id"),
        }

    speaker = (
        chain_surfaces[-1]["surface_candidate"]
        if chain_surfaces
        else None
    )
    return {
        "display_mode": "NON_PROPHET_SPEAKER_ONLY",
        "speaker_surface_candidate": speaker,
        "speaker_resolution_status": "HUMAN_REVIEW_REQUIRED",
        "full_isnad_in_script": False,
        "policy_id": policy.get("policy_id"),
    }


def load_window_registry(
    project: Path,
    bounded_manifest: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    registry: dict[str, dict[str, Any]] = {}
    for book in bounded_manifest["books"]:
        path = (
            project
            / book["outputs"]["review_windows"]["project_path"]
        )
        if sha256_file(path) != (
            book["outputs"]["review_windows"]["sha256"]
        ):
            raise ValueError(
                "BOUNDED_WINDOW_CHECKSUM_MISMATCH:"
                f"{book['work_source_id']}"
            )
        for row in iter_jsonl(path):
            registry[row["window_id"]] = row
    return registry


def load_candidate_registry(
    project: Path,
    prefilter_manifest: dict[str, Any],
) -> dict[str, dict[str, dict[str, Any]]]:
    result: dict[str, dict[str, dict[str, Any]]] = {}
    for book in prefilter_manifest["books"]:
        source_id = book["work_source_id"]
        path = (
            project
            / book["outputs"]["candidates"]["project_path"]
        )
        if sha256_file(path) != (
            book["outputs"]["candidates"]["sha256"]
        ):
            raise ValueError(
                f"PREFILTER_CHECKSUM_MISMATCH:{source_id}"
            )
        result[source_id] = {
            row["candidate_id"]: row for row in iter_jsonl(path)
        }
    return result


def load_normalized_pages(
    project: Path,
    normalized_manifest: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    pages_by_source: dict[str, list[dict[str, Any]]] = {}
    for book in normalized_manifest["books"]:
        source_id = book["work_source_id"]
        path = (
            project
            / book["normalized_files"]["pages"]["project_path"]
        )
        expected_sha = book["normalized_files"]["pages"].get(
            "sha256"
        )
        if expected_sha and sha256_file(path) != expected_sha:
            raise ValueError(
                f"NORMALIZED_PAGE_CHECKSUM_MISMATCH:{source_id}"
            )
        pages_by_source[source_id] = list(iter_jsonl(path))
    return pages_by_source


def source_pages_for_window(
    *,
    window: dict[str, Any],
    decision: dict[str, Any],
    candidate_registry: dict[str, dict[str, dict[str, Any]]],
    normalized_pages: dict[str, list[dict[str, Any]]],
    context_pages: int,
) -> tuple[list[dict[str, Any]], str]:
    source_id = window["work_source_id"]
    repair_review = decision.get("repair_review") or {}
    requires_candidate_centered = bool(
        window.get("text_truncated")
        or repair_review.get("text_complete_for_candidates")
    )

    if not requires_candidate_centered:
        return list(window.get("pages") or []), "BOUNDED_WINDOW"

    source_candidates = candidate_registry[source_id]
    candidate_rows = [
        source_candidates[candidate_id]
        for candidate_id in window.get("candidate_ids") or []
        if candidate_id in source_candidates
    ]

    pages = normalized_pages[source_id]
    by_sequence = {
        int(page["sequence_num"]): page for page in pages
    }
    sequence_by_page_id = {
        int(page["shamela_page_id"]): int(page["sequence_num"])
        for page in pages
    }

    target_sequences = sorted(
        {
            sequence_by_page_id[int(candidate["shamela_page_id"])]
            for candidate in candidate_rows
            if int(candidate["shamela_page_id"])
            in sequence_by_page_id
        }
    )

    selected_sequences: set[int] = set()
    maximum_sequence = max(by_sequence) if by_sequence else 0
    for sequence in target_sequences:
        for selected in range(
            max(1, sequence - context_pages),
            min(maximum_sequence, sequence + context_pages) + 1,
        ):
            selected_sequences.add(selected)

    selected_pages = [
        by_sequence[sequence]
        for sequence in sorted(selected_sequences)
        if sequence in by_sequence
    ]
    if not selected_pages:
        raise ValueError(
            f"CANDIDATE_CENTERED_PAGE_REBUILD_EMPTY:"
            f"{source_id}:{window['window_id']}"
        )

    return selected_pages, "CANDIDATE_CENTERED_REBUILD"


def create_candidate_record(
    *,
    decision: dict[str, Any],
    window: dict[str, Any],
    page: dict[str, Any],
    page_source_mode: str,
    body: str,
    footnotes: str,
    headings: list[str],
    start: int,
    end: int,
    text: str,
    report_index: int,
    policy: dict[str, Any],
    boundary_status: str,
    boundary_pattern: str | None,
) -> dict[str, Any]:
    report_kind = classify_report_kind(text)
    chain_surfaces = extract_chain_surfaces(text)
    isnad_text, isnad_status = extract_isnad_candidate(
        text,
        report_kind,
    )
    attribution_profiles = detect_attribution_profiles(
        text,
        list(window.get("attribution_profiles") or []),
    )

    locator = str(
        page.get("canonical_locator")
        or page.get("locator")
        or ""
    )
    report_id = stable_id(
        "adam_report_candidate",
        window["window_id"],
        locator,
        start,
        end,
        text,
    )

    text_sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    normalized_sha = hashlib.sha256(
        normalize_arabic(text).encode("utf-8")
    ).hexdigest()

    verification_requirements = set(
        decision.get("verification_requirements") or []
    )
    if report_kind == "PROPHETIC_HADITH_CANDIDATE":
        verification_requirements.update(
            {
                "FULL_ISNAD_PARSE_AND_CHAIN_RESEARCH",
                "HADITH_GRADING_REQUIRED",
                "COMPANION_OR_MARFU_TABII_RESOLUTION_REQUIRED",
            }
        )
    elif chain_surfaces:
        verification_requirements.add(
            "FULL_ISNAD_PARSE_AND_CHAIN_RESEARCH"
        )
    if attribution_profiles:
        verification_requirements.add(
            "EARLY_REPORT_OR_ISRAILIYYAT_CLASSIFICATION_REQUIRED"
        )

    return {
        "schema_version": (
            "siraj-adam-report-candidate-record-v1"
        ),
        "episode_id": EPISODE_ID,
        "report_candidate_id": report_id,
        "report_index_within_window": report_index,
        "window_id": window["window_id"],
        "work_source_id": window["work_source_id"],
        "book_id": window["book_id"],
        "book_title": window.get("book_title", ""),
        "source_page_mode": page_source_mode,
        "sequence_num": page.get("sequence_num"),
        "shamela_page_id": page.get("shamela_page_id"),
        "canonical_locator": locator,
        "headings": headings,
        "page_body_character_start": start,
        "page_body_character_end": end,
        "original_text": text,
        "original_text_sha256": text_sha,
        "normalized_text_sha256": normalized_sha,
        "footnote_context": footnotes,
        "report_kind_candidate": report_kind,
        "candidate_classification_status": "HUMAN_REVIEW_REQUIRED",
        "chain_surface_sequence_candidate": chain_surfaces,
        "isnad_text_candidate": isnad_text,
        "isnad_extraction_status": isnad_status,
        "attribution_profiles": attribution_profiles,
        "script_attribution_candidate": (
            script_attribution_candidate(
                value=text,
                report_kind=report_kind,
                chain_surfaces=chain_surfaces,
                policy=policy,
            )
        ),
        "event_ids": decision.get("event_ids") or [],
        "research_question_ids": (
            decision.get("research_question_ids") or []
        ),
        "window_scope_fit": decision["scope_fit"],
        "scope_boundary_status": boundary_status,
        "scope_boundary_pattern": boundary_pattern,
        "duplicate_window_group": decision.get(
            "duplicate_group"
        ),
        "verification_requirements": sorted(
            verification_requirements
        ),
        "review": {
            "report_boundary_status": "PENDING",
            "speaker_resolution_status": "PENDING",
            "isnad_resolution_status": "PENDING",
            "scope_status": "PENDING",
            "reviewer_notes": "",
        },
        "permissions": {
            "candidate_only": True,
            "allowed_for_gemini": False,
            "approved_for_evidence": False,
            "approved_for_quotation": False,
            "approved_for_hadith_grade": False,
            "approved_for_israiliyyat_classification": False,
            "approved_for_final_narrative": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    parser.add_argument("--context-pages", type=int, default=1)
    args = parser.parse_args()

    if not 0 <= args.context_pages <= 3:
        raise ValueError("CONTEXT_PAGES_OUT_OF_RANGE")

    repo = Path(args.repo_root).resolve()
    project = repo / "projects" / EPISODE_ID
    secondary = project / "sources" / "secondary"

    decisions_candidates = [
        secondary
        / "final-window-review"
        / "adam-human-window-decisions-v1.json",
        secondary
        / "human-window-review"
        / "adam-human-window-decisions-v1.json",
    ]
    decisions_path = next(
        (
            candidate
            for candidate in decisions_candidates
            if candidate.is_file()
        ),
        None,
    )
    if decisions_path is None:
        raise FileNotFoundError(
            "FINAL_WINDOW_DECISIONS_NOT_FOUND"
        )

    decisions_payload = read_json(decisions_path)
    if decisions_payload.get("review_status") != "FINAL_COMPLETE":
        raise ValueError("FINAL_WINDOW_REVIEW_NOT_COMPLETE")
    if decisions_payload.get("counts") != {
        "INCLUDE": 92,
        "EXCLUDE": 114,
        "DEFER": 1,
    }:
        raise ValueError("FINAL_WINDOW_COUNTS_MISMATCH")
    if (
        decisions_payload.get("technical_defer_count") != 0
    ):
        raise ValueError("TECHNICAL_DEFERS_REMAIN")

    permissions = decisions_payload.get("permissions") or {}
    if permissions.get("gemini_execution_enabled") is not False:
        raise ValueError("GEMINI_MUST_REMAIN_DISABLED")

    policy_candidates = [
        project
        / "editorial"
        / "narration-attribution-policy-v2.json",
        secondary
        / "final-window-review"
        / "adam-narration-attribution-policy-v2.json",
    ]
    policy_path = next(
        (
            candidate
            for candidate in policy_candidates
            if candidate.is_file()
        ),
        None,
    )
    if policy_path is None:
        raise FileNotFoundError(
            "NARRATION_ATTRIBUTION_POLICY_NOT_FOUND"
        )
    policy = read_json(policy_path)
    if policy.get("status") != "USER_APPROVED_IN_CONVERSATION":
        raise ValueError("ATTRIBUTION_POLICY_NOT_APPROVED")

    bounded_manifest_path = (
        secondary
        / "bounded-review-windows"
        / "bounded-review-window-manifest-v1.json"
    )
    prefilter_manifest_path = (
        secondary
        / "topic-prefilter"
        / "topic-prefilter-manifest-v1.json"
    )
    normalized_manifest_path = (
        secondary / "normalized-export-manifest-v1.json"
    )

    bounded_manifest = read_json(bounded_manifest_path)
    prefilter_manifest = read_json(prefilter_manifest_path)
    normalized_manifest = read_json(normalized_manifest_path)

    windows = load_window_registry(
        project,
        bounded_manifest,
    )
    candidates = load_candidate_registry(
        project,
        prefilter_manifest,
    )
    normalized_pages = load_normalized_pages(
        project,
        normalized_manifest,
    )

    included_decisions = [
        decision
        for decision in decisions_payload["decisions"]
        if decision["decision"] == "INCLUDE"
    ]
    if len(included_decisions) != 92:
        raise ValueError("EXPECTED_92_INCLUDED_WINDOWS")

    output_root = secondary / OUTPUT_DIR_NAME
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    global_candidates: list[dict[str, Any]] = []
    boundary_excluded: list[dict[str, Any]] = []
    isnad_queue: list[dict[str, Any]] = []
    source_summaries: list[dict[str, Any]] = []

    for source_id in sorted(
        {decision["work_source_id"] for decision in included_decisions}
    ):
        source_decisions = [
            decision
            for decision in included_decisions
            if decision["work_source_id"] == source_id
        ]
        source_records: list[dict[str, Any]] = []
        source_boundary_records: list[dict[str, Any]] = []
        source_isnad_records: list[dict[str, Any]] = []

        for decision in source_decisions:
            window_id = decision["window_id"]
            if window_id not in windows:
                raise ValueError(
                    f"WINDOW_NOT_FOUND:{window_id}"
                )
            window = windows[window_id]

            pages, page_source_mode = source_pages_for_window(
                window=window,
                decision=decision,
                candidate_registry=candidates,
                normalized_pages=normalized_pages,
                context_pages=args.context_pages,
            )

            post_boundary_reached = False
            report_index = 0

            for page in pages:
                body, footnotes, headings = clean_page_text(page)
                if not body:
                    continue

                for start, end, unit_text in split_report_units(body):
                    if not unit_text.strip():
                        continue

                    boundary_offset, boundary_pattern = (
                        find_original_offset(
                            unit_text,
                            POST_BOUNDARY_PATTERNS,
                        )
                        if decision["scope_fit"] == "MIXED"
                        else (None, None)
                    )

                    pieces: list[
                        tuple[str, int, int, str, str | None]
                    ] = []

                    if post_boundary_reached:
                        pieces.append(
                            (
                                "POST_EPISODE_BOUNDARY_EXCLUDED",
                                start,
                                end,
                                unit_text,
                                boundary_pattern,
                            )
                        )
                    elif boundary_offset is None:
                        pieces.append(
                            (
                                "PRE_BOUNDARY_OR_NOT_APPLICABLE",
                                start,
                                end,
                                unit_text,
                                None,
                            )
                        )
                    else:
                        pre_text = unit_text[:boundary_offset].strip()
                        post_text = unit_text[boundary_offset:].strip()

                        if pre_text:
                            pre_end = start + boundary_offset
                            pieces.append(
                                (
                                    "MIXED_BOUNDARY_PRE_SECTION",
                                    start,
                                    pre_end,
                                    pre_text,
                                    boundary_pattern,
                                )
                            )
                        if post_text:
                            post_start = start + boundary_offset
                            pieces.append(
                                (
                                    "POST_EPISODE_BOUNDARY_EXCLUDED",
                                    post_start,
                                    end,
                                    post_text,
                                    boundary_pattern,
                                )
                            )
                        post_boundary_reached = True

                    for (
                        boundary_status,
                        piece_start,
                        piece_end,
                        piece_text,
                        piece_boundary_pattern,
                    ) in pieces:
                        if len(piece_text.strip()) < 40:
                            continue
                        report_index += 1
                        record = create_candidate_record(
                            decision=decision,
                            window=window,
                            page=page,
                            page_source_mode=page_source_mode,
                            body=body,
                            footnotes=footnotes,
                            headings=headings,
                            start=piece_start,
                            end=piece_end,
                            text=piece_text,
                            report_index=report_index,
                            policy=policy,
                            boundary_status=boundary_status,
                            boundary_pattern=(
                                piece_boundary_pattern
                            ),
                        )

                        if boundary_status == (
                            "POST_EPISODE_BOUNDARY_EXCLUDED"
                        ):
                            source_boundary_records.append(record)
                            boundary_excluded.append(record)
                            continue

                        source_records.append(record)
                        global_candidates.append(record)

                        if (
                            record["isnad_text_candidate"]
                            or record["report_kind_candidate"]
                            == "PROPHETIC_HADITH_CANDIDATE"
                        ):
                            queue_record = {
                                "schema_version": (
                                    "siraj-adam-internal-isnad-"
                                    "research-record-v1"
                                ),
                                "episode_id": EPISODE_ID,
                                "isnad_research_id": stable_id(
                                    "adam_isnad_research",
                                    record[
                                        "report_candidate_id"
                                    ],
                                ),
                                "report_candidate_id": record[
                                    "report_candidate_id"
                                ],
                                "window_id": record["window_id"],
                                "work_source_id": record[
                                    "work_source_id"
                                ],
                                "book_id": record["book_id"],
                                "canonical_locator": record[
                                    "canonical_locator"
                                ],
                                "report_kind_candidate": record[
                                    "report_kind_candidate"
                                ],
                                "original_text": record[
                                    "original_text"
                                ],
                                "isnad_text_candidate": record[
                                    "isnad_text_candidate"
                                ],
                                "chain_surface_sequence_candidate": (
                                    record[
                                        "chain_surface_sequence_candidate"
                                    ]
                                ),
                                "script_attribution_candidate": (
                                    record[
                                        "script_attribution_candidate"
                                    ]
                                ),
                                "attribution_profiles": record[
                                    "attribution_profiles"
                                ],
                                "research_status": (
                                    "HUMAN_ISNAD_RESEARCH_REQUIRED"
                                ),
                                "narrator_identity_status": (
                                    "NOT_REVIEWED"
                                ),
                                "chain_continuity_status": (
                                    "NOT_REVIEWED"
                                ),
                                "marfu_mursal_status": "NOT_REVIEWED",
                                "hadith_grading_status": "NOT_GRADED",
                                "approved_authority_registry_status": (
                                    "PENDING_APPROVED_AUTHORITY_"
                                    "REGISTRY"
                                ),
                                "dorar_net_permitted_for_grading": False,
                                "full_isnad_internal_retention": True,
                                "full_isnad_in_script": False,
                                "permissions": {
                                    "candidate_only": True,
                                    "allowed_for_gemini": False,
                                    "approved_hadith_grade": False,
                                    "approved_for_narrative": False,
                                },
                            }
                            source_isnad_records.append(queue_record)
                            isnad_queue.append(queue_record)

        source_dir = output_root / source_id
        report_path = source_dir / "report-candidates.jsonl"
        boundary_path = (
            source_dir / "boundary-excluded-candidates.jsonl"
        )
        isnad_path = (
            source_dir / "internal-isnad-research-queue.jsonl"
        )

        write_jsonl(report_path, source_records)
        write_jsonl(boundary_path, source_boundary_records)
        write_jsonl(isnad_path, source_isnad_records)

        source_manifest = {
            "schema_version": (
                "siraj-adam-report-level-source-manifest-v1"
            ),
            "episode_id": EPISODE_ID,
            "work_source_id": source_id,
            "included_window_count": len(source_decisions),
            "report_candidate_count": len(source_records),
            "boundary_excluded_candidate_count": len(
                source_boundary_records
            ),
            "isnad_research_count": len(
                source_isnad_records
            ),
            "report_kind_counts": dict(
                sorted(
                    Counter(
                        record["report_kind_candidate"]
                        for record in source_records
                    ).items()
                )
            ),
            "outputs": {
                "report_candidates": {
                    "project_path": report_path.relative_to(
                        project
                    ).as_posix(),
                    "rows": len(source_records),
                    "sha256": sha256_file(report_path),
                },
                "boundary_excluded": {
                    "project_path": boundary_path.relative_to(
                        project
                    ).as_posix(),
                    "rows": len(source_boundary_records),
                    "sha256": sha256_file(boundary_path),
                },
                "internal_isnad_research": {
                    "project_path": isnad_path.relative_to(
                        project
                    ).as_posix(),
                    "rows": len(source_isnad_records),
                    "sha256": sha256_file(isnad_path),
                },
            },
            "permissions": {
                "candidate_only": True,
                "gemini_execution_enabled": False,
                "source_approval_changed": False,
                "evidence_approval_changed": False,
                "quotation_approval_changed": False,
                "hadith_grading_changed": False,
                "israiliyyat_classification_changed": False,
            },
        }
        source_manifest_path = source_dir / "manifest.json"
        write_json(source_manifest_path, source_manifest)

        source_summaries.append(
            {
                "work_source_id": source_id,
                "included_windows": len(source_decisions),
                "report_candidates": len(source_records),
                "boundary_excluded": len(
                    source_boundary_records
                ),
                "isnad_research": len(
                    source_isnad_records
                ),
                "manifest_project_path": (
                    source_manifest_path.relative_to(
                        project
                    ).as_posix()
                ),
                "manifest_sha256": sha256_file(
                    source_manifest_path
                ),
            }
        )

    if not global_candidates:
        raise ValueError("NO_REPORT_CANDIDATES_CREATED")

    # Exact duplicate candidates only; no independence inference.
    by_normalized_hash: dict[str, list[dict[str, Any]]] = (
        defaultdict(list)
    )
    for record in global_candidates:
        by_normalized_hash[
            record["normalized_text_sha256"]
        ].append(record)

    duplicate_groups = []
    for normalized_hash, records in sorted(
        by_normalized_hash.items()
    ):
        if len(records) < 2:
            continue
        duplicate_groups.append(
            {
                "duplicate_group_id": stable_id(
                    "adam_exact_report_duplicate",
                    normalized_hash,
                ),
                "normalized_text_sha256": normalized_hash,
                "report_candidate_ids": [
                    record["report_candidate_id"]
                    for record in records
                ],
                "source_ids": sorted(
                    {
                        record["work_source_id"]
                        for record in records
                    }
                ),
                "status": "EXACT_NORMALIZED_TEXT_MATCH",
                "independent_route_status": "NOT_ASSESSED",
                "instruction_ar": (
                    "التطابق النصي لا يثبت استقلال الطرق؛ "
                    "تراجع الأسانيد واعتماد الكتب المتأخرة."
                ),
            }
        )

    global_registry_path = (
        output_root / "report-candidate-registry-v1.jsonl"
    )
    global_isnad_path = (
        output_root / "internal-isnad-research-queue-v1.jsonl"
    )
    global_boundary_path = (
        output_root / "boundary-excluded-candidates-v1.jsonl"
    )
    duplicate_path = (
        output_root / "report-exact-duplicate-groups-v1.json"
    )
    policy_snapshot_path = (
        output_root / "narration-attribution-policy-snapshot-v2.json"
    )
    review_csv_path = (
        output_root / "report-review-queue-v1.csv"
    )
    source_csv_path = (
        output_root / "source-coverage-v1.csv"
    )

    write_jsonl(global_registry_path, global_candidates)
    write_jsonl(global_isnad_path, isnad_queue)
    write_jsonl(global_boundary_path, boundary_excluded)
    write_json(
        duplicate_path,
        {
            "schema_version": (
                "siraj-adam-report-exact-duplicate-groups-v1"
            ),
            "episode_id": EPISODE_ID,
            "group_count": len(duplicate_groups),
            "groups": duplicate_groups,
        },
    )
    write_json(policy_snapshot_path, policy)

    review_fields = [
        "report_candidate_id",
        "window_id",
        "work_source_id",
        "book_id",
        "canonical_locator",
        "report_kind_candidate",
        "scope_boundary_status",
        "attribution_profiles",
        "isnad_extraction_status",
        "chain_surface_count",
        "event_ids",
        "research_question_ids",
        "report_boundary_decision",
        "speaker_resolution",
        "isnad_resolution",
        "scope_decision",
        "reviewer_notes",
    ]
    with review_csv_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=review_fields,
        )
        writer.writeheader()
        for record in global_candidates:
            writer.writerow(
                {
                    "report_candidate_id": record[
                        "report_candidate_id"
                    ],
                    "window_id": record["window_id"],
                    "work_source_id": record[
                        "work_source_id"
                    ],
                    "book_id": record["book_id"],
                    "canonical_locator": record[
                        "canonical_locator"
                    ],
                    "report_kind_candidate": record[
                        "report_kind_candidate"
                    ],
                    "scope_boundary_status": record[
                        "scope_boundary_status"
                    ],
                    "attribution_profiles": " | ".join(
                        record["attribution_profiles"]
                    ),
                    "isnad_extraction_status": record[
                        "isnad_extraction_status"
                    ],
                    "chain_surface_count": len(
                        record[
                            "chain_surface_sequence_candidate"
                        ]
                    ),
                    "event_ids": " | ".join(
                        record["event_ids"]
                    ),
                    "research_question_ids": " | ".join(
                        record["research_question_ids"]
                    ),
                    "report_boundary_decision": "",
                    "speaker_resolution": "",
                    "isnad_resolution": "",
                    "scope_decision": "",
                    "reviewer_notes": "",
                }
            )

    with source_csv_path.open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        fields = [
            "work_source_id",
            "included_windows",
            "report_candidates",
            "boundary_excluded",
            "isnad_research",
            "manifest_project_path",
            "manifest_sha256",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(source_summaries)

    report_kind_counts = Counter(
        record["report_kind_candidate"]
        for record in global_candidates
    )
    attribution_count = sum(
        1
        for record in global_candidates
        if record["attribution_profiles"]
    )
    rebuilt_window_count = sum(
        1
        for decision in included_decisions
        if windows[decision["window_id"]].get("text_truncated")
        or (
            decision.get("repair_review") or {}
        ).get("text_complete_for_candidates")
    )

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "episode_id": EPISODE_ID,
        "status": "PASS_REPORT_CANDIDATES_READY",
        "created_at": now_utc(),
        "source_decisions": decisions_path.relative_to(
            project
        ).as_posix(),
        "source_decisions_sha256": sha256_file(
            decisions_path
        ),
        "source_policy": policy_path.relative_to(
            project
        ).as_posix(),
        "source_policy_sha256": sha256_file(policy_path),
        "included_window_count": len(included_decisions),
        "candidate_centered_rebuilt_window_count": (
            rebuilt_window_count
        ),
        "source_count": len(source_summaries),
        "report_candidate_count": len(global_candidates),
        "boundary_excluded_candidate_count": len(
            boundary_excluded
        ),
        "internal_isnad_research_count": len(isnad_queue),
        "attribution_report_candidate_count": attribution_count,
        "exact_duplicate_group_count": len(
            duplicate_groups
        ),
        "report_kind_counts": dict(
            sorted(report_kind_counts.items())
        ),
        "sources": source_summaries,
        "outputs": {
            "report_candidate_registry": {
                "project_path": (
                    global_registry_path.relative_to(
                        project
                    ).as_posix()
                ),
                "rows": len(global_candidates),
                "sha256": sha256_file(
                    global_registry_path
                ),
            },
            "internal_isnad_research_queue": {
                "project_path": (
                    global_isnad_path.relative_to(
                        project
                    ).as_posix()
                ),
                "rows": len(isnad_queue),
                "sha256": sha256_file(
                    global_isnad_path
                ),
            },
            "boundary_excluded_candidates": {
                "project_path": (
                    global_boundary_path.relative_to(
                        project
                    ).as_posix()
                ),
                "rows": len(boundary_excluded),
                "sha256": sha256_file(
                    global_boundary_path
                ),
            },
            "exact_duplicate_groups": {
                "project_path": duplicate_path.relative_to(
                    project
                ).as_posix(),
                "groups": len(duplicate_groups),
                "sha256": sha256_file(duplicate_path),
            },
            "report_review_queue": {
                "project_path": review_csv_path.relative_to(
                    project
                ).as_posix(),
                "rows": len(global_candidates),
                "sha256": sha256_file(review_csv_path),
            },
            "source_coverage": {
                "project_path": source_csv_path.relative_to(
                    project
                ).as_posix(),
                "rows": len(source_summaries),
                "sha256": sha256_file(source_csv_path),
            },
            "policy_snapshot": {
                "project_path": (
                    policy_snapshot_path.relative_to(
                        project
                    ).as_posix()
                ),
                "sha256": sha256_file(
                    policy_snapshot_path
                ),
            },
        },
        "permissions": {
            "candidate_only": True,
            "gemini_execution_enabled": False,
            "source_approval_changed": False,
            "evidence_approval_changed": False,
            "quotation_approval_changed": False,
            "hadith_grading_changed": False,
            "israiliyyat_classification_changed": False,
            "final_narrative_approval_changed": False,
        },
        "next_gate": (
            "HUMAN_REPORT_BOUNDARY_AND_ISNAD_REVIEW"
        ),
    }

    manifest_path = (
        output_root / "report-level-extraction-manifest-v1.json"
    )
    write_json(manifest_path, manifest)

    print(
        json.dumps(
            {
                "status": "PASS",
                "manifest": str(manifest_path),
                "counts": {
                    "included_windows": len(
                        included_decisions
                    ),
                    "rebuilt_windows": (
                        rebuilt_window_count
                    ),
                    "sources": len(source_summaries),
                    "report_candidates": len(
                        global_candidates
                    ),
                    "boundary_excluded": len(
                        boundary_excluded
                    ),
                    "isnad_research": len(isnad_queue),
                    "attribution_candidates": (
                        attribution_count
                    ),
                    "exact_duplicate_groups": len(
                        duplicate_groups
                    ),
                    "report_kinds": dict(
                        sorted(report_kind_counts.items())
                    ),
                },
                "gemini_execution_enabled": False,
                "hadith_grading_changed": False,
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
