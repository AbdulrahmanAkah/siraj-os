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
OUTPUT_DIR_NAME = "report-resegmentation-chain-normalization"
MANIFEST_SCHEMA = "siraj-adam-report-resegmentation-chain-normalization-v1"

TRANSMISSION_CANONICAL = {
    "حدثنا": "HADDATHANA",
    "حدثني": "HADDATHANI",
    "أخبرنا": "AKHBARANA",
    "اخبرنا": "AKHBARANA",
    "أخبرني": "AKHBARANI",
    "اخبرني": "AKHBARANI",
    "أنبأنا": "ANBAANA",
    "انبأنا": "ANBAANA",
    "أنبأني": "ANBAANI",
    "انبأني": "ANBAANI",
    "ثنا": "HADDATHANA_ABBREVIATED",
    "نا": "TRANSMISSION_ABBREVIATION_CANDIDATE",
    "سمعت": "SAMI_TU",
    "عن": "AN",
    "قال": "QALA",
    "ذكر": "DHUKIRA",
}

STRONG_REPORT_STARTS = [
    "حدثنا",
    "حدثني",
    "أخبرنا",
    "اخبرنا",
    "أخبرني",
    "اخبرني",
    "أنبأنا",
    "انبأنا",
    "أنبأني",
    "انبأني",
    "ثنا",
    "وروى",
    "وروي",
    "ورُوي",
    "وأخرج",
    "واخرج",
    "أخرج",
    "اخرج",
    "ذكر من قال",
    "ذكرُ من قال",
    "وقال أبو جعفر",
    "وقال ابو جعفر",
    "قال أبو جعفر",
    "قال ابو جعفر",
    "وقال ابن جرير",
    "قال ابن جرير",
    "وقال ابن كثير",
    "قال ابن كثير",
    "وقال المصنف",
    "قال المصنف",
    "قلت",
]

COMMENTARY_STARTS = [
    "وهذا إسناد",
    "وهذا اسناد",
    "وهذا حديث",
    "وهذا أثر",
    "وهذا اثر",
    "والصحيح",
    "والظاهر",
    "والصواب",
    "قلت",
    "تفرد به",
    "تَفَرَّدَ بِهِ",
    "رواه مسلم",
    "ورواه مسلم",
    "رواه البخاري",
    "ورواه البخاري",
]

PROPHETIC_PATTERNS = [
    "قال رسول الله",
    "عن رسول الله",
    "أن رسول الله",
    "ان رسول الله",
    "قال النبي",
    "عن النبي",
    "أن النبي",
    "ان النبي",
    "مرفوعا",
    "مرفوعًا",
]

MID_FRAGMENT_PREFIXES = [
    "من ",
    "ثم ",
    "فقال ",
    "قالت ",
    "وهو ",
    "وهذا ",
    "بإسناده ",
    "باسناده ",
    "نحوه ",
    "مثله ",
    "وبه ",
]


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
                raise ValueError(f"JSONL_OBJECT_REQUIRED:{path}:{line_number}")
            yield value


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    with path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
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


def compact_text(value: str) -> str:
    value = value.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def candidate_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        str(row.get("work_source_id") or ""),
        int(row.get("book_id") or 0),
        int(row.get("sequence_num") or 0),
        int(row.get("page_body_character_start") or 0),
        int(row.get("report_index_within_window") or 0),
        str(row.get("report_candidate_id") or ""),
    )


class UnionFind:
    def __init__(self, items: Iterable[str]) -> None:
        self.parent = {item: item for item in items}

    def find(self, item: str) -> str:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: str, right: str) -> None:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root != right_root:
            self.parent[right_root] = left_root


def strong_start_offsets(value: str) -> list[int]:
    patterns = sorted(
        {normalize_arabic(pattern) for pattern in STRONG_REPORT_STARTS},
        key=len,
        reverse=True,
    )
    normalized = normalize_arabic(value)
    if not normalized:
        return [0]

    # Normalize while retaining source positions and meaningful spaces.
    mapped_chars: list[str] = []
    source_map: list[int] = []
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
        for item in unicodedata.normalize("NFKD", character):
            if unicodedata.combining(item):
                continue
            replacement = replacements.get(item, item).casefold()
            for normalized_character in replacement:
                mapped_chars.append(normalized_character)
                source_map.append(index)
    mapped = "".join(mapped_chars)

    regex_patterns = [
        re.escape(pattern).replace(r"\ ", r"\s+")
        for pattern in patterns
    ]
    boundary_prefix = r"(?:^|(?<=[\n.!؟؛:]))\s*"
    regex = re.compile(
        boundary_prefix + r"(?:" + "|".join(regex_patterns) + r")\b"
    )
    offsets = {0}
    for match in regex.finditer(mapped):
        if match.start() < len(source_map):
            offsets.add(source_map[match.start()])
    return sorted(offsets)


def split_by_offsets(value: str, offsets: list[int]) -> list[str]:
    boundaries = sorted(set([0, *offsets, len(value)]))
    fragments: list[str] = []
    for left, right in zip(boundaries, boundaries[1:]):
        text = compact_text(value[left:right])
        if text:
            fragments.append(text)
    return fragments


def split_long_fragment(value: str, maximum_chars: int = 7000) -> list[str]:
    if len(value) <= maximum_chars:
        return [value]

    boundaries = [0]
    for match in re.finditer(r"\n\n+|(?<=[.!؟؛])\s+", value):
        boundaries.append(match.end())
    boundaries.append(len(value))
    boundaries = sorted(set(boundaries))

    output: list[str] = []
    start = 0
    while start < len(value):
        ideal = min(len(value), start + maximum_chars)
        candidates = [boundary for boundary in boundaries if start + 500 <= boundary <= ideal]
        end = max(candidates) if candidates else ideal
        text = compact_text(value[start:end])
        if text:
            output.append(text)
        start = max(end, start + 1)
    return output


def merge_tiny_fragments(fragments: list[str]) -> list[str]:
    output: list[str] = []
    for fragment in fragments:
        if len(fragment) < 140 and output:
            output[-1] = compact_text(output[-1] + "\n" + fragment)
        else:
            output.append(fragment)
    if len(output) > 1 and len(output[0]) < 100:
        output[1] = compact_text(output[0] + "\n" + output[1])
        output = output[1:]
    return output


def deterministic_resegment(value: str) -> tuple[list[str], list[str]]:
    warnings: list[str] = []
    offsets = strong_start_offsets(value)
    fragments = split_by_offsets(value, offsets)

    expanded: list[str] = []
    for fragment in fragments:
        expanded.extend(split_long_fragment(fragment))
    fragments = merge_tiny_fragments(expanded)

    if len(fragments) == 1:
        warnings.append("NO_DETERMINISTIC_SPLIT_FOUND")
    if any(len(fragment) > 7000 for fragment in fragments):
        warnings.append("LONG_SEGMENT_REMAINS")
    if any(
        normalize_arabic(fragment).startswith(normalize_arabic(prefix))
        for fragment in fragments
        for prefix in MID_FRAGMENT_PREFIXES
    ):
        warnings.append("POSSIBLE_MID_REPORT_FRAGMENT")

    return fragments, sorted(set(warnings))


def extract_chain_nodes(value: str) -> list[dict[str, Any]]:
    markers = sorted(TRANSMISSION_CANONICAL, key=len, reverse=True)
    marker_pattern = "|".join(re.escape(marker) for marker in markers)
    regex = re.compile(
        rf"(?:^|[،,:؛\n]\s*)"
        rf"(?P<marker>{marker_pattern})\s+"
        rf"(?P<surface>[^،,:؛\n]{{2,160}})"
    )

    nodes: list[dict[str, Any]] = []
    for match in regex.finditer(value[:3500]):
        marker = match.group("marker")
        surface = re.sub(r"\s+", " ", match.group("surface")).strip()
        # Stop obvious content rather than narrator names.
        if len(surface.split()) > 18:
            continue
        if any(
            phrase in normalize_arabic(surface)
            for phrase in [
                "الله تعالي",
                "هذه الاية",
                "هذا القول",
                "في الارض خليفة",
                "رسول الله صلي الله عليه وسلم قال",
            ]
        ):
            continue
        nodes.append(
            {
                "sequence_index": len(nodes),
                "transmission_term_raw": marker,
                "transmission_term_canonical": TRANSMISSION_CANONICAL[marker],
                "narrator_surface_raw": surface,
                "narrator_surface_normalized": normalize_arabic(surface),
                "narrator_identity_id": None,
                "identity_resolution_status": "NOT_RESOLVED",
                "role_candidate": "CHAIN_NARRATOR_SURFACE",
            }
        )
    return nodes[:30]


def classify_kind(value: str, reviewed_kind: str | None) -> str:
    normalized = normalize_arabic(value)
    if any(normalize_arabic(pattern) in normalized for pattern in PROPHETIC_PATTERNS):
        return "PROPHETIC_HADITH_CANDIDATE"
    if any(
        normalized.startswith(normalize_arabic(pattern))
        for pattern in [
            "قال ابو جعفر",
            "قال ابن جرير",
            "قال ابن كثير",
            "قال المصنف",
            "قلت",
            "والصحيح",
            "والظاهر",
            "والصواب",
        ]
    ):
        return "AUTHORIAL_COMMENTARY_CANDIDATE"
    if extract_chain_nodes(value):
        return "EARLY_REPORT_CANDIDATE"
    if reviewed_kind:
        return reviewed_kind
    return "UNCLASSIFIED_SOURCE_PASSAGE_CANDIDATE"


def report_form_candidate(kind: str, value: str) -> str:
    normalized = normalize_arabic(value)
    if kind == "PROPHETIC_HADITH_CANDIDATE":
        if "مرفوع" in normalized:
            return "MARFU_EXPLICIT_CANDIDATE"
        return "MARFU_CONTEXT_CANDIDATE"
    if "قال ابن عباس" in normalized or "عن ابن عباس" in normalized:
        return "MAWQUF_OR_TAFSIR_REPORT_CANDIDATE"
    if "قال مجاهد" in normalized or "قال قتادة" in normalized or "قال الحسن" in normalized:
        return "MAQTU_OR_TAFSIR_REPORT_CANDIDATE"
    return "UNRESOLVED_REPORT_FORM_CANDIDATE"


def commentary_flags(value: str) -> list[str]:
    normalized = normalize_arabic(value)
    return [
        pattern
        for pattern in COMMENTARY_STARTS
        if normalize_arabic(pattern) in normalized
    ]


def unique_list(values: Iterable[Any]) -> list[Any]:
    output = []
    seen = set()
    for value in values:
        marker = json.dumps(value, ensure_ascii=False, sort_keys=True) if isinstance(value, (dict, list)) else str(value)
        if marker in seen:
            continue
        seen.add(marker)
        output.append(value)
    return output


def build_merged_source_record(
    records: list[dict[str, Any]],
    retained_ids: set[str],
) -> dict[str, Any]:
    ordered = sorted(records, key=candidate_sort_key)
    texts = [compact_text(str(record.get("original_text") or "")) for record in ordered]
    merged_text = "\n\n".join(text for text in texts if text)
    first = ordered[0]
    return {
        **first,
        "original_text": merged_text,
        "original_text_sha256": hashlib.sha256(merged_text.encode("utf-8")).hexdigest(),
        "normalized_text_sha256": hashlib.sha256(normalize_arabic(merged_text).encode("utf-8")).hexdigest(),
        "parent_report_candidate_ids": [record["report_candidate_id"] for record in ordered],
        "retained_parent_report_candidate_ids": [
            record["report_candidate_id"]
            for record in ordered
            if record["report_candidate_id"] in retained_ids
        ],
        "supporting_merge_fragment_ids": [
            record["report_candidate_id"]
            for record in ordered
            if record["report_candidate_id"] not in retained_ids
        ],
        "event_ids": unique_list(event for record in ordered for event in record.get("event_ids") or []),
        "research_question_ids": unique_list(question for record in ordered for question in record.get("research_question_ids") or []),
        "attribution_profiles": unique_list(profile for record in ordered for profile in record.get("attribution_profiles") or []),
        "verification_requirements": unique_list(requirement for record in ordered for requirement in record.get("verification_requirements") or []),
        "footnote_context": "\n\n".join(unique_list(str(record.get("footnote_context") or "") for record in ordered if str(record.get("footnote_context") or "").strip())),
        "headings": unique_list(heading for record in ordered for heading in record.get("headings") or []),
        "canonical_locators": unique_list(str(record.get("canonical_locator") or "") for record in ordered),
        "merge_source_count": len(ordered),
    }


def normalized_record(
    *,
    source_record: dict[str, Any],
    segment_text: str,
    segment_index: int,
    segment_count: int,
    lineage_action: str,
    warnings: list[str],
    reviewed_kind: str | None,
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    parent_ids = source_record.get("parent_report_candidate_ids") or [source_record["report_candidate_id"]]
    retained_parent_ids = (
        source_record.get("retained_parent_report_candidate_ids")
        or [source_record["report_candidate_id"]]
    )
    supporting_merge_fragment_ids = source_record.get(
        "supporting_merge_fragment_ids"
    ) or []
    kind = classify_kind(segment_text, reviewed_kind)
    chain_nodes = extract_chain_nodes(segment_text)
    form = report_form_candidate(kind, segment_text)
    normalized_id = stable_id(
        "adam_normalized_report",
        *parent_ids,
        segment_index,
        segment_text,
    )

    prophetic = kind == "PROPHETIC_HADITH_CANDIDATE"
    terminal_surface = chain_nodes[-1]["narrator_surface_raw"] if chain_nodes else None
    unresolved_flags = list(warnings)
    if len(segment_text) < 90:
        unresolved_flags.append("VERY_SHORT_REPORT_UNIT")
    if lineage_action == "RESEGMENTED" and segment_count == 1:
        unresolved_flags.append("REQUESTED_RESEGMENTATION_NOT_ACHIEVED")
    if normalize_arabic(segment_text).startswith(tuple(normalize_arabic(prefix) for prefix in MID_FRAGMENT_PREFIXES)):
        unresolved_flags.append("POSSIBLE_MID_REPORT_FRAGMENT")
    if len(strong_start_offsets(segment_text)) > 2:
        unresolved_flags.append("MULTIPLE_STRONG_STARTS_REMAIN")
    unresolved_flags = sorted(set(unresolved_flags))

    record = {
        "schema_version": "siraj-adam-normalized-report-record-v1",
        "episode_id": EPISODE_ID,
        "normalized_report_id": normalized_id,
        "parent_report_candidate_ids": parent_ids,
        "retained_parent_report_candidate_ids": retained_parent_ids,
        "supporting_merge_fragment_ids": supporting_merge_fragment_ids,
        "lineage_action": lineage_action,
        "segment_index": segment_index,
        "segment_count_from_source_unit": segment_count,
        "work_source_id": source_record["work_source_id"],
        "book_id": source_record["book_id"],
        "book_title": source_record.get("book_title", ""),
        "window_id": source_record["window_id"],
        "canonical_locators": source_record.get("canonical_locators") or [source_record.get("canonical_locator")],
        "sequence_num": source_record.get("sequence_num"),
        "shamela_page_id": source_record.get("shamela_page_id"),
        "headings": source_record.get("headings") or [],
        "original_text": segment_text,
        "original_text_sha256": hashlib.sha256(segment_text.encode("utf-8")).hexdigest(),
        "normalized_text_sha256": hashlib.sha256(normalize_arabic(segment_text).encode("utf-8")).hexdigest(),
        "footnote_context": source_record.get("footnote_context") or "",
        "corrected_report_kind_candidate": kind,
        "report_form_candidate": form,
        "chain_nodes_candidate": chain_nodes,
        "chain_node_count": len(chain_nodes),
        "terminal_speaker_surface_candidate": terminal_surface,
        "speaker_resolution_status": "HUMAN_REVIEW_REQUIRED",
        "isnad_internal_text_candidate": compact_text(str(source_record.get("isnad_text_candidate") or "")) or compact_text(segment_text[:1800]),
        "full_isnad_internal_retention": True,
        "full_isnad_in_script": False,
        "script_attribution_candidate": {
            "display_mode": "PROPHET_WITH_COMPANION_OR_MARFU_TABII" if prophetic else "NON_PROPHET_SPEAKER_ONLY",
            "prophet_name": "محمد ﷺ" if prophetic else None,
            "companion_or_marfu_tabii_surface_candidate": terminal_surface if prophetic else None,
            "non_prophet_speaker_surface_candidate": None if prophetic else terminal_surface,
            "resolution_status": "HUMAN_REVIEW_REQUIRED",
            "full_isnad_in_script": False,
        },
        "commentary_flags": commentary_flags(segment_text),
        "event_ids": source_record.get("event_ids") or [],
        "research_question_ids": source_record.get("research_question_ids") or [],
        "attribution_profiles": source_record.get("attribution_profiles") or [],
        "scope_boundary_status": source_record.get("scope_boundary_status"),
        "window_scope_fit": source_record.get("window_scope_fit"),
        "duplicate_window_group": source_record.get("duplicate_window_group"),
        "verification_requirements": unique_list([
            *(source_record.get("verification_requirements") or []),
            *( ["FULL_ISNAD_PARSE_AND_CHAIN_RESEARCH"] if chain_nodes or prophetic else [] ),
            *( ["HADITH_GRADING_REQUIRED", "COMPANION_OR_MARFU_TABII_RESOLUTION_REQUIRED"] if prophetic else [] ),
        ]),
        "normalization_warnings": unresolved_flags,
        "review": {
            "report_boundary_status": "PENDING_HUMAN_CONFIRMATION",
            "chain_normalization_status": "CANDIDATE_ONLY",
            "narrator_identity_status": "NOT_RESOLVED",
            "hadith_grading_status": "NOT_GRADED",
            "israiliyyat_classification_status": "NOT_CLASSIFIED",
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

    unresolved = None
    if unresolved_flags:
        unresolved = {
            "schema_version": "siraj-adam-unresolved-report-boundary-record-v1",
            "episode_id": EPISODE_ID,
            "normalized_report_id": normalized_id,
            "parent_report_candidate_ids": parent_ids,
            "retained_parent_report_candidate_ids": retained_parent_ids,
            "supporting_merge_fragment_ids": supporting_merge_fragment_ids,
            "work_source_id": source_record["work_source_id"],
            "book_id": source_record["book_id"],
            "canonical_locators": record["canonical_locators"],
            "warnings": unresolved_flags,
            "original_text": segment_text,
            "human_action_required": "CONFIRM_OR_REPAIR_REPORT_BOUNDARY",
            "permissions": record["permissions"],
        }
    return record, unresolved


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", required=True)
    args = parser.parse_args()

    repo = Path(args.repo_root).resolve()
    project = repo / "projects" / EPISODE_ID
    secondary = project / "sources" / "secondary"
    review_root = secondary / "report-boundary-isnad-review"

    decisions_path = review_root / "adam-report-boundary-isnad-decisions-v1.json"
    retained_path = review_root / "adam-retained-report-register-v1.jsonl"
    reseg_path = review_root / "adam-resegmentation-queue-v1.jsonl"
    merge_path = review_root / "adam-merge-queue-v1.jsonl"
    source_manifest_path = review_root / "manifest.json"
    report_registry_path = (
        secondary
        / "report-level-extraction"
        / "report-candidate-registry-v1.jsonl"
    )

    for path in [
        decisions_path,
        retained_path,
        reseg_path,
        merge_path,
        source_manifest_path,
        report_registry_path,
    ]:
        if not path.is_file():
            raise FileNotFoundError(f"REQUIRED_PHASE9_INPUT_MISSING:{path}")

    decisions = read_json(decisions_path)
    source_manifest = read_json(source_manifest_path)
    if decisions.get("status") != "PASS_REPORT_BOUNDARY_AND_ISNAD_REVIEW_COMPLETE":
        raise ValueError("REPORT_BOUNDARY_REVIEW_NOT_COMPLETE")
    if decisions.get("counts", {}).get("retained") != 732:
        raise ValueError("EXPECTED_732_RETAINED")
    if decisions.get("counts", {}).get("resegmentation_required") != 435:
        raise ValueError("EXPECTED_435_RESEGMENT")
    if decisions.get("counts", {}).get("merge_required") != 37:
        raise ValueError("EXPECTED_37_MERGE")
    if decisions.get("permissions", {}).get("gemini_execution_enabled") is not False:
        raise ValueError("GEMINI_MUST_REMAIN_DISABLED")

    retained = list(iter_jsonl(retained_path))
    reseg_rows = list(iter_jsonl(reseg_path))
    merge_rows = list(iter_jsonl(merge_path))
    if len(retained) != 732 or len(reseg_rows) != 435 or len(merge_rows) != 37:
        raise ValueError("SOURCE_QUEUE_COUNT_MISMATCH")

    retained_by_id = {row["report_candidate_id"]: row for row in retained}
    if len(retained_by_id) != 732:
        raise ValueError("DUPLICATE_RETAINED_CANDIDATE_IDS")
    source_registry_rows = list(iter_jsonl(report_registry_path))
    all_source_by_id = {
        row["report_candidate_id"]: row
        for row in source_registry_rows
    }
    all_source_by_id.update(retained_by_id)
    registry_by_window: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for source_row in all_source_by_id.values():
        registry_by_window[(
            str(source_row.get("work_source_id") or ""),
            str(source_row.get("window_id") or ""),
        )].append(source_row)
    for key in registry_by_window:
        registry_by_window[key].sort(key=candidate_sort_key)

    reseg_ids = {row["report_candidate_id"] for row in reseg_rows}
    merge_ids = {row["report_candidate_id"] for row in merge_rows}

    decision_by_id = {
        row["report_candidate_id"]: row
        for row in decisions.get("records", [])
        if row.get("report_candidate_id") in retained_by_id
    }

    # Build merge components using reviewed target IDs. A reviewed merge
    # target may be an excluded fragment from the source registry; it is
    # used only as supporting text and is not counted as a retained report.
    uf = UnionFind(all_source_by_id)
    merge_node_ids: set[str] = set()
    merge_edges = []
    for row in merge_rows:
        review = row["boundary_isnad_review"]
        source_id = row["report_candidate_id"]
        target_id = review.get("merge_target_candidate_id")
        if not target_id:
            merge_node_ids.add(source_id)
            merge_edges.append(
                {
                    "source_report_candidate_id": source_id,
                    "target_report_candidate_id": None,
                    "review_action": review["review_action"],
                    "target_resolution": "NO_EXPLICIT_TARGET_PRESERVED_AS_UNRESOLVED",
                }
            )
            continue
        if target_id not in all_source_by_id:
            raise ValueError(f"MERGE_TARGET_NOT_FOUND:{source_id}:{target_id}")
        uf.union(source_id, target_id)
        merge_node_ids.update({source_id, target_id})
        merge_edges.append(
            {
                "source_report_candidate_id": source_id,
                "target_report_candidate_id": target_id,
                "review_action": review["review_action"],
                "target_resolution": "EXPLICIT_REVIEW_TARGET",
            }
        )


    components: dict[str, list[str]] = defaultdict(list)
    for candidate_id in merge_node_ids:
        components[uf.find(candidate_id)].append(candidate_id)
    merge_components = list(components.values())
    merged_member_ids = {candidate_id for ids in merge_components for candidate_id in ids}

    output_root = secondary / OUTPUT_DIR_NAME
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True)

    normalized_records: list[dict[str, Any]] = []
    unresolved_records: list[dict[str, Any]] = []
    merge_lineage: list[dict[str, Any]] = []
    reseg_lineage: list[dict[str, Any]] = []
    chain_records: list[dict[str, Any]] = []
    consumed_ids: set[str] = set()

    # Process merge components first.
    for component_index, candidate_ids in enumerate(
        sorted(
            merge_components,
            key=lambda ids: min(
                candidate_sort_key(all_source_by_id[candidate_id])
                for candidate_id in ids
            ),
        ),
        start=1,
    ):
        records = [all_source_by_id[candidate_id] for candidate_id in candidate_ids]
        merged_source = build_merged_source_record(
            records,
            set(retained_by_id),
        )
        retained_component_ids = set(candidate_ids) & set(retained_by_id)
        consumed_ids.update(retained_component_ids)
        unresolved_merge_target = len(candidate_ids) == 1
        component_needs_resegment = (
            unresolved_merge_target
            or bool(set(candidate_ids) & reseg_ids)
        )
        if component_needs_resegment:
            fragments, warnings = deterministic_resegment(merged_source["original_text"])
            if unresolved_merge_target:
                warnings = sorted(set([*warnings, "MERGE_TARGET_NOT_RESOLVED"]))
                lineage_action = "UNRESOLVED_MERGE_TARGET_RESEGMENTED"
            else:
                lineage_action = "MERGED_THEN_RESEGMENTED"
        else:
            fragments = [merged_source["original_text"]]
            warnings = []
            lineage_action = "MERGED"

        normalized_ids = []
        reviewed_kind = next(
            (
                decision_by_id[candidate_id].get("corrected_report_kind_candidate")
                for candidate_id in candidate_ids
                if candidate_id in decision_by_id
            ),
            None,
        )
        for index, fragment in enumerate(fragments, start=1):
            record, unresolved = normalized_record(
                source_record=merged_source,
                segment_text=fragment,
                segment_index=index,
                segment_count=len(fragments),
                lineage_action=lineage_action,
                warnings=warnings,
                reviewed_kind=reviewed_kind,
            )
            normalized_records.append(record)
            normalized_ids.append(record["normalized_report_id"])
            if unresolved:
                unresolved_records.append(unresolved)

        merge_lineage.append(
            {
                "schema_version": "siraj-adam-merge-lineage-record-v1",
                "episode_id": EPISODE_ID,
                "merge_component_id": stable_id("adam_merge_component", *sorted(candidate_ids)),
                "source_report_candidate_ids": sorted(candidate_ids),
                "normalized_report_ids": normalized_ids,
                "source_count": len(candidate_ids),
                "result_segment_count": len(fragments),
                "resegmentation_applied_after_merge": component_needs_resegment,
                "unresolved_merge_target": unresolved_merge_target,
                "review_edges": [
                    edge
                    for edge in merge_edges
                    if edge["source_report_candidate_id"] in candidate_ids
                    or edge["target_report_candidate_id"] in candidate_ids
                ],
                "status": (
                    "PASS_WITH_UNRESOLVED_TARGET_CANDIDATE_ONLY"
                    if unresolved_merge_target
                    else "PASS_CANDIDATE_ONLY"
                ),
            }
        )

    # Process remaining retained reports.
    for candidate_id, source_record in sorted(retained_by_id.items(), key=lambda item: candidate_sort_key(item[1])):
        if candidate_id in consumed_ids:
            continue
        consumed_ids.add(candidate_id)
        reviewed_kind = (decision_by_id.get(candidate_id) or {}).get("corrected_report_kind_candidate")
        if candidate_id in reseg_ids:
            fragments, warnings = deterministic_resegment(source_record["original_text"])
            lineage_action = "RESEGMENTED"
        else:
            fragments = [compact_text(source_record["original_text"])]
            warnings = []
            lineage_action = "PASSTHROUGH_SINGLE"

        normalized_ids = []
        for index, fragment in enumerate(fragments, start=1):
            record, unresolved = normalized_record(
                source_record=source_record,
                segment_text=fragment,
                segment_index=index,
                segment_count=len(fragments),
                lineage_action=lineage_action,
                warnings=warnings,
                reviewed_kind=reviewed_kind,
            )
            normalized_records.append(record)
            normalized_ids.append(record["normalized_report_id"])
            if unresolved:
                unresolved_records.append(unresolved)

        if candidate_id in reseg_ids:
            reseg_lineage.append(
                {
                    "schema_version": "siraj-adam-resegmentation-lineage-record-v1",
                    "episode_id": EPISODE_ID,
                    "source_report_candidate_id": candidate_id,
                    "normalized_report_ids": normalized_ids,
                    "result_segment_count": len(fragments),
                    "warnings": warnings,
                    "status": "PASS_CANDIDATE_ONLY",
                }
            )

    if consumed_ids != set(retained_by_id):
        missing = sorted(set(retained_by_id) - consumed_ids)
        raise ValueError(f"NOT_ALL_RETAINED_CONSUMED:{missing[:10]}")

    normalized_records.sort(
        key=lambda row: (
            row["work_source_id"],
            int(row.get("book_id") or 0),
            int(row.get("sequence_num") or 0),
            row["normalized_report_id"],
        )
    )

    # Create chain-normalization records for all normalized reports with a chain or prophetic form.
    for record in normalized_records:
        if not record["chain_nodes_candidate"] and record["corrected_report_kind_candidate"] != "PROPHETIC_HADITH_CANDIDATE":
            continue
        chain_records.append(
            {
                "schema_version": "siraj-adam-normalized-isnad-chain-candidate-v1",
                "episode_id": EPISODE_ID,
                "chain_candidate_id": stable_id("adam_chain_candidate", record["normalized_report_id"]),
                "normalized_report_id": record["normalized_report_id"],
                "parent_report_candidate_ids": record["parent_report_candidate_ids"],
                "retained_parent_report_candidate_ids": record["retained_parent_report_candidate_ids"],
                "supporting_merge_fragment_ids": record["supporting_merge_fragment_ids"],
                "work_source_id": record["work_source_id"],
                "book_id": record["book_id"],
                "canonical_locators": record["canonical_locators"],
                "corrected_report_kind_candidate": record["corrected_report_kind_candidate"],
                "report_form_candidate": record["report_form_candidate"],
                "chain_nodes_candidate": record["chain_nodes_candidate"],
                "terminal_speaker_surface_candidate": record["terminal_speaker_surface_candidate"],
                "isnad_internal_text_candidate": record["isnad_internal_text_candidate"],
                "full_isnad_internal_retention": True,
                "full_isnad_in_script": False,
                "narrator_identity_resolution_status": "NOT_RESOLVED",
                "chain_continuity_status": "NOT_REVIEWED",
                "hadith_grading_status": "NOT_GRADED",
                "israiliyyat_classification_status": "NOT_CLASSIFIED",
                "approved_authority_registry_status": "PENDING",
                "dorar_net_permitted_for_grading": False,
                "script_attribution_candidate": record["script_attribution_candidate"],
                "research_tasks": unique_list([
                    "RESOLVE_NARRATOR_IDENTITIES",
                    "CONFIRM_CHAIN_ORDER_AND_TRANSMISSION_TERMS",
                    "RESOLVE_TERMINAL_SPEAKER",
                    "DETERMINE_MARFU_MAWQUF_MAQTU_OR_MURSAL",
                    "CHECK_CHAIN_CONTINUITY_AND_SOURCE_DEPENDENCE",
                    "LINK_ONLY_TO_APPROVED_HADITH_AUTHORITIES",
                    *( ["RESOLVE_COMPANION_OR_MARFU_TABII_FOR_SCRIPT"] if record["corrected_report_kind_candidate"] == "PROPHETIC_HADITH_CANDIDATE" else [] ),
                    *( ["REPORT_LEVEL_ISRAILIYYAT_CLASSIFICATION_REQUIRED"] if record["attribution_profiles"] else [] ),
                ]),
                "permissions": record["permissions"],
            }
        )

    # Exact normalized-text groups only.
    exact_groups = []
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in normalized_records:
        by_hash[record["normalized_text_sha256"]].append(record)
    for text_hash, records in sorted(by_hash.items()):
        if len(records) < 2:
            continue
        exact_groups.append(
            {
                "exact_duplicate_group_id": stable_id("adam_normalized_exact_duplicate", text_hash),
                "normalized_text_sha256": text_hash,
                "normalized_report_ids": [record["normalized_report_id"] for record in records],
                "work_source_ids": sorted({record["work_source_id"] for record in records}),
                "independent_route_status": "NOT_ASSESSED",
                "status": "EXACT_NORMALIZED_TEXT_MATCH",
            }
        )

    registry_path = output_root / "normalized-report-register-v1.jsonl"
    chain_path = output_root / "normalized-isnad-chain-candidates-v1.jsonl"
    unresolved_path = output_root / "unresolved-boundary-review-queue-v1.jsonl"
    merge_lineage_path = output_root / "merge-lineage-v1.jsonl"
    reseg_lineage_path = output_root / "resegmentation-lineage-v1.jsonl"
    exact_path = output_root / "normalized-exact-duplicate-groups-v1.json"
    review_csv_path = output_root / "normalized-report-review-queue-v1.csv"

    write_jsonl(registry_path, normalized_records)
    write_jsonl(chain_path, chain_records)
    write_jsonl(unresolved_path, unresolved_records)
    write_jsonl(merge_lineage_path, merge_lineage)
    write_jsonl(reseg_lineage_path, reseg_lineage)
    write_json(
        exact_path,
        {
            "schema_version": "siraj-adam-normalized-exact-duplicate-groups-v1",
            "episode_id": EPISODE_ID,
            "group_count": len(exact_groups),
            "groups": exact_groups,
        },
    )

    with review_csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        fields = [
            "normalized_report_id",
            "parent_report_candidate_ids",
            "lineage_action",
            "work_source_id",
            "book_id",
            "corrected_report_kind_candidate",
            "report_form_candidate",
            "chain_node_count",
            "terminal_speaker_surface_candidate",
            "normalization_warnings",
            "boundary_decision",
            "speaker_resolution",
            "chain_resolution",
            "reviewer_notes",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in normalized_records:
            writer.writerow(
                {
                    "normalized_report_id": record["normalized_report_id"],
                    "parent_report_candidate_ids": " | ".join(record["parent_report_candidate_ids"]),
                    "lineage_action": record["lineage_action"],
                    "work_source_id": record["work_source_id"],
                    "book_id": record["book_id"],
                    "corrected_report_kind_candidate": record["corrected_report_kind_candidate"],
                    "report_form_candidate": record["report_form_candidate"],
                    "chain_node_count": record["chain_node_count"],
                    "terminal_speaker_surface_candidate": record["terminal_speaker_surface_candidate"] or "",
                    "normalization_warnings": " | ".join(record["normalization_warnings"]),
                    "boundary_decision": "",
                    "speaker_resolution": "",
                    "chain_resolution": "",
                    "reviewer_notes": "",
                }
            )

    action_counts = Counter(record["lineage_action"] for record in normalized_records)
    kind_counts = Counter(record["corrected_report_kind_candidate"] for record in normalized_records)
    source_counts = Counter(record["work_source_id"] for record in normalized_records)
    warning_counts = Counter(warning for record in normalized_records for warning in record["normalization_warnings"])

    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "episode_id": EPISODE_ID,
        "status": "PASS_NORMALIZED_REPORTS_READY_FOR_BOUNDED_SEMANTIC_REVIEW",
        "created_at": now_utc(),
        "source_review_manifest": source_manifest_path.relative_to(project).as_posix(),
        "source_review_manifest_sha256": sha256_file(source_manifest_path),
        "source_report_registry": report_registry_path.relative_to(project).as_posix(),
        "source_report_registry_sha256": sha256_file(report_registry_path),
        "source_retained_candidate_count": 732,
        "source_single_candidate_count": 260,
        "source_resegmentation_candidate_count": 435,
        "source_merge_candidate_count": 37,
        "consumed_source_candidate_count": len(consumed_ids),
        "merge_component_count": len(merge_components),
        "normalized_report_count": len(normalized_records),
        "normalized_chain_candidate_count": len(chain_records),
        "unresolved_boundary_record_count": len(unresolved_records),
        "resegmentation_lineage_count": len(reseg_lineage),
        "merge_lineage_count": len(merge_lineage),
        "exact_duplicate_group_count": len(exact_groups),
        "lineage_action_counts": dict(sorted(action_counts.items())),
        "report_kind_counts": dict(sorted(kind_counts.items())),
        "source_counts": dict(sorted(source_counts.items())),
        "warning_counts": dict(sorted(warning_counts.items())),
        "outputs": {
            "normalized_report_register": {
                "project_path": registry_path.relative_to(project).as_posix(),
                "rows": len(normalized_records),
                "sha256": sha256_file(registry_path),
            },
            "normalized_isnad_chain_candidates": {
                "project_path": chain_path.relative_to(project).as_posix(),
                "rows": len(chain_records),
                "sha256": sha256_file(chain_path),
            },
            "unresolved_boundary_review_queue": {
                "project_path": unresolved_path.relative_to(project).as_posix(),
                "rows": len(unresolved_records),
                "sha256": sha256_file(unresolved_path),
            },
            "merge_lineage": {
                "project_path": merge_lineage_path.relative_to(project).as_posix(),
                "rows": len(merge_lineage),
                "sha256": sha256_file(merge_lineage_path),
            },
            "resegmentation_lineage": {
                "project_path": reseg_lineage_path.relative_to(project).as_posix(),
                "rows": len(reseg_lineage),
                "sha256": sha256_file(reseg_lineage_path),
            },
            "exact_duplicate_groups": {
                "project_path": exact_path.relative_to(project).as_posix(),
                "groups": len(exact_groups),
                "sha256": sha256_file(exact_path),
            },
            "review_queue": {
                "project_path": review_csv_path.relative_to(project).as_posix(),
                "rows": len(normalized_records),
                "sha256": sha256_file(review_csv_path),
            },
        },
        "permissions": {
            "candidate_only": True,
            "gemini_execution_enabled": False,
            "source_approval_changed": False,
            "evidence_approval_changed": False,
            "quotation_approval_changed": False,
            "hadith_grading_changed": False,
            "narrator_judgement_changed": False,
            "israiliyyat_classification_changed": False,
            "final_narrative_approval_changed": False,
        },
        "next_gate": "BOUNDED_GEMINI_SEMANTIC_ANALYSIS_DRAFT",
        "next_gate_constraints": {
            "gemini_may": [
                "propose report boundaries for unresolved records",
                "propose speaker and chain-surface interpretations",
                "compare text variants and source dependence",
                "map reports to episode events and research questions",
            ],
            "gemini_may_not": [
                "grade a hadith",
                "judge a narrator",
                "approve an isnad",
                "approve an Israiliyyat classification",
                "approve evidence or quotation",
                "write outside the supplied candidate records",
            ],
            "execution_enabled": False,
        },
    }

    manifest_path = output_root / "report-resegmentation-chain-normalization-manifest-v1.json"
    write_json(manifest_path, manifest)

    print(
        json.dumps(
            {
                "status": "PASS",
                "manifest": str(manifest_path),
                "counts": {
                    "source_retained": 732,
                    "consumed_source_candidates": len(consumed_ids),
                    "merge_components": len(merge_components),
                    "normalized_reports": len(normalized_records),
                    "chain_candidates": len(chain_records),
                    "unresolved_boundaries": len(unresolved_records),
                    "exact_duplicate_groups": len(exact_groups),
                    "lineage_actions": dict(sorted(action_counts.items())),
                    "report_kinds": dict(sorted(kind_counts.items())),
                },
                "gemini_execution_enabled": False,
                "hadith_grading_changed": False,
                "narrator_judgement_changed": False,
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
