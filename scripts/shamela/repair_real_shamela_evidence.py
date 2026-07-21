from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import unicodedata
from typing import Any


SCHEMA_VERSION = "siraj-deterministic-evidence-alignment-v1"

OUTPUT_ROOT = Path(
    r"C:\SIRAJ\Workspace\first-project\working"
    r"\gold-20-fast-track\real-shamela-gemini-3-v2"
)

TARGET_SEGMENT = "4445-6244"

ROUTE_COLLECTIONS = {
    "PERSON_AND_STATUS": (
        "entities",
        "statuses",
        "relations",
    ),
    "APPOINTMENT_AND_OFFICE": (
        "entities",
        "appointments",
    ),
    "ISNAD": (
        "entities",
        "isnads",
    ),
    "SIRA_POETRY": (
        "entities",
        "events",
    ),
}


def sha256_text(text: str) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(
        path.read_text(encoding="utf-8")
    )

    if not isinstance(payload, dict):
        raise RuntimeError(
            f"JSON_ROOT_NOT_OBJECT:{path}"
        )

    return payload


def canonicalize_with_mapping(
    text: str,
) -> tuple[str, list[int], list[int]]:
    """
    Remove Arabic combining marks and tatweel only for alignment.

    The returned mappings preserve the corresponding original source
    boundaries so that accepted evidence always becomes an exact source
    slice, never normalized text.
    """

    normalized: list[str] = []
    starts: list[int] = []
    ends: list[int] = []

    for index, character in enumerate(text):
        category = unicodedata.category(character)

        if (
            character == "\u0640"
            or category in {"Mn", "Me"}
        ):
            if ends:
                ends[-1] = index + 1
            continue

        emitted = (
            " "
            if character.isspace()
            else character
        )

        if (
            emitted == " "
            and normalized
            and normalized[-1] == " "
        ):
            ends[-1] = index + 1
            continue

        normalized.append(emitted)
        starts.append(index)
        ends.append(index + 1)

    return "".join(normalized), starts, ends


def canonicalize_quote(text: str) -> str:
    normalized, _, _ = canonicalize_with_mapping(
        text
    )

    return normalized.strip()


def all_occurrences(
    source: str,
    target: str,
) -> list[int]:
    positions: list[int] = []

    start = source.find(target)

    while start >= 0:
        positions.append(start)
        start = source.find(target, start + 1)

    return positions


def align_unique_quote(
    source_text: str,
    provider_quote: str,
) -> dict[str, Any]:
    if not provider_quote.strip():
        return {
            "status": "REJECTED",
            "reason_code": "EVIDENCE_TEXT_EMPTY",
        }

    if provider_quote in source_text:
        start = source_text.index(provider_quote)

        return {
            "status": "EXACT_LITERAL",
            "reason_code": "",
            "provider_quote": provider_quote,
            "source_quote": provider_quote,
            "start": start,
            "end": start + len(provider_quote),
            "normalized_occurrences": 1,
        }

    normalized_source, starts, ends = (
        canonicalize_with_mapping(source_text)
    )

    normalized_quote = canonicalize_quote(
        provider_quote
    )

    if not normalized_quote:
        return {
            "status": "REJECTED",
            "reason_code": (
                "NORMALIZED_EVIDENCE_EMPTY"
            ),
        }

    positions = all_occurrences(
        normalized_source,
        normalized_quote,
    )

    if not positions:
        return {
            "status": "REJECTED",
            "reason_code": (
                "NORMALIZED_EVIDENCE_NOT_FOUND"
            ),
            "provider_quote": provider_quote,
            "normalized_quote": normalized_quote,
            "normalized_occurrences": 0,
        }

    if len(positions) != 1:
        return {
            "status": "REJECTED",
            "reason_code": (
                "NORMALIZED_EVIDENCE_AMBIGUOUS"
            ),
            "provider_quote": provider_quote,
            "normalized_quote": normalized_quote,
            "normalized_occurrences": len(
                positions
            ),
        }

    normalized_start = positions[0]
    normalized_end = (
        normalized_start + len(normalized_quote)
    )

    source_start = starts[normalized_start]
    source_end = ends[normalized_end - 1]

    source_quote = source_text[
        source_start:source_end
    ]

    if (
        canonicalize_quote(source_quote)
        != normalized_quote
    ):
        return {
            "status": "REJECTED",
            "reason_code": (
                "SOURCE_SLICE_ALIGNMENT_MISMATCH"
            ),
            "provider_quote": provider_quote,
            "source_quote": source_quote,
        }

    return {
        "status": (
            "ALIGNED_TO_UNIQUE_SOURCE_SLICE"
        ),
        "reason_code": (
            "DIACRITIC_INSENSITIVE_UNIQUE_MATCH"
        ),
        "provider_quote": provider_quote,
        "source_quote": source_quote,
        "start": source_start,
        "end": source_end,
        "normalized_occurrences": 1,
    }


def validate_output(
    *,
    route: str,
    output: dict[str, Any],
    source_text: str,
) -> dict[str, Any]:
    semantic_item_count = 0
    evidence_quote_count = 0
    items_without_evidence = 0
    invalid_evidence: list[dict[str, Any]] = []

    for collection_name in ROUTE_COLLECTIONS[
        route
    ]:
        collection = output.get(
            collection_name,
            [],
        )

        if not isinstance(collection, list):
            invalid_evidence.append({
                "collection": collection_name,
                "reason": "COLLECTION_NOT_LIST",
            })
            continue

        for item_index, item in enumerate(collection):
            semantic_item_count += 1

            if not isinstance(item, dict):
                items_without_evidence += 1
                invalid_evidence.append({
                    "collection": collection_name,
                    "item_index": item_index,
                    "reason": "ITEM_NOT_OBJECT",
                })
                continue

            evidence = item.get("evidence")

            if not isinstance(evidence, dict):
                items_without_evidence += 1
                invalid_evidence.append({
                    "collection": collection_name,
                    "item_index": item_index,
                    "reason": (
                        "EVIDENCE_OBJECT_MISSING"
                    ),
                })
                continue

            quote = evidence.get("text")

            if (
                not isinstance(quote, str)
                or not quote.strip()
            ):
                items_without_evidence += 1
                invalid_evidence.append({
                    "collection": collection_name,
                    "item_index": item_index,
                    "reason": (
                        "EVIDENCE_TEXT_EMPTY"
                    ),
                })
                continue

            evidence_quote_count += 1

            if quote not in source_text:
                invalid_evidence.append({
                    "collection": collection_name,
                    "item_index": item_index,
                    "reason": (
                        "QUOTE_NOT_FOUND_IN_SOURCE"
                    ),
                    "text": quote,
                })

    return {
        "semantic_item_count": semantic_item_count,
        "evidence_quote_count": (
            evidence_quote_count
        ),
        "items_without_evidence": (
            items_without_evidence
        ),
        "invalid_evidence_count": len(
            invalid_evidence
        ),
        "invalid_evidence": invalid_evidence,
    }


def main() -> int:
    case_root = OUTPUT_ROOT / TARGET_SEGMENT

    input_path = case_root / "input.json"
    parsed_path = case_root / "parsed-output.json"
    validation_path = (
        case_root / "validation.json"
    )
    manifest_path = OUTPUT_ROOT / "run-manifest.json"

    for required in (
        input_path,
        parsed_path,
        validation_path,
        manifest_path,
    ):
        if not required.exists():
            raise RuntimeError(
                f"REQUIRED_ARTIFACT_MISSING:{required}"
            )

    input_payload = read_json(input_path)
    original_output = read_json(parsed_path)
    original_validation = read_json(
        validation_path
    )
    original_manifest = read_json(
        manifest_path
    )

    source_text = str(
        input_payload["original_text"]
    )

    expected_hash = str(
        input_payload["source_text_hash"]
    )

    actual_hash = sha256_text(source_text)

    if actual_hash != expected_hash:
        raise RuntimeError(
            "SOURCE_HASH_MISMATCH"
        )

    route = str(input_payload["route"])

    if route not in ROUTE_COLLECTIONS:
        raise RuntimeError(
            f"ROUTE_NOT_SUPPORTED:{route}"
        )

    repaired_output = deepcopy(original_output)
    repair_entries: list[dict[str, Any]] = []
    rejection_entries: list[dict[str, Any]] = []

    for collection_name in ROUTE_COLLECTIONS[
        route
    ]:
        collection = repaired_output.get(
            collection_name,
            [],
        )

        if not isinstance(collection, list):
            rejection_entries.append({
                "collection": collection_name,
                "reason": "COLLECTION_NOT_LIST",
            })
            continue

        for item_index, item in enumerate(collection):
            if not isinstance(item, dict):
                rejection_entries.append({
                    "collection": collection_name,
                    "item_index": item_index,
                    "reason": "ITEM_NOT_OBJECT",
                })
                continue

            evidence = item.get("evidence")

            if not isinstance(evidence, dict):
                rejection_entries.append({
                    "collection": collection_name,
                    "item_index": item_index,
                    "reason": (
                        "EVIDENCE_OBJECT_MISSING"
                    ),
                })
                continue

            quote = evidence.get("text")

            if not isinstance(quote, str):
                rejection_entries.append({
                    "collection": collection_name,
                    "item_index": item_index,
                    "reason": (
                        "EVIDENCE_TEXT_NOT_STRING"
                    ),
                })
                continue

            resolution = align_unique_quote(
                source_text,
                quote,
            )

            resolution_record = {
                "collection": collection_name,
                "item_index": item_index,
                **resolution,
            }

            if resolution["status"] == "REJECTED":
                rejection_entries.append(
                    resolution_record
                )
                continue

            if (
                resolution["status"]
                == "ALIGNED_TO_UNIQUE_SOURCE_SLICE"
            ):
                evidence["text"] = resolution[
                    "source_quote"
                ]

                repair_entries.append(
                    resolution_record
                )

    repair_report = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "PASS"
            if not rejection_entries
            else "FAIL"
        ),
        "segment_id": TARGET_SEGMENT,
        "route": route,
        "source_hash_match": True,
        "original_provider_output_preserved": True,
        "original_parsed_output_hash": (
            sha256_text(
                json.dumps(
                    original_output,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
            )
        ),
        "repair_method": (
            "DIACRITIC_INSENSITIVE_UNIQUE_ALIGNMENT"
        ),
        "repair_count": len(repair_entries),
        "repairs": repair_entries,
        "rejection_count": len(
            rejection_entries
        ),
        "rejections": rejection_entries,
    }

    write_json(
        case_root / "evidence-repair-report.json",
        repair_report,
    )

    if rejection_entries:
        print(
            json.dumps(
                repair_report,
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    original_backup = (
        case_root / "parsed-output.original.json"
    )

    if not original_backup.exists():
        shutil.copy2(
            parsed_path,
            original_backup,
        )

    repaired_path = (
        case_root / "parsed-output.repaired.json"
    )

    write_json(
        repaired_path,
        repaired_output,
    )

    repaired_validation_core = validate_output(
        route=route,
        output=repaired_output,
        source_text=source_text,
    )

    repaired_status = (
        "PASS"
        if (
            repaired_output.get("route") == route
            and repaired_validation_core[
                "semantic_item_count"
            ] > 0
            and repaired_validation_core[
                "items_without_evidence"
            ] == 0
            and repaired_validation_core[
                "invalid_evidence_count"
            ] == 0
        )
        else "FAIL"
    )

    repaired_validation = {
        **original_validation,
        **repaired_validation_core,
        "schema_version": SCHEMA_VERSION,
        "status": repaired_status,
        "source_hash_match": True,
        "evidence_repair_applied": True,
        "evidence_repair_count": len(
            repair_entries
        ),
        "evidence_repair_method": (
            "DIACRITIC_INSENSITIVE_UNIQUE_ALIGNMENT"
        ),
        "original_automatic_status": (
            original_validation.get("status")
        ),
        "parsed_output_artifact": (
            f"{TARGET_SEGMENT}"
            "/parsed-output.repaired.json"
        ),
        "repair_report_artifact": (
            f"{TARGET_SEGMENT}"
            "/evidence-repair-report.json"
        ),
        "human_review_status": "PENDING",
    }

    write_json(
        case_root / "validation.repaired.json",
        repaired_validation,
    )

    final_manifest = deepcopy(
        original_manifest
    )

    final_cases: list[dict[str, Any]] = []

    for case in final_manifest.get("cases", []):
        if (
            isinstance(case, dict)
            and case.get("segment_id")
            == TARGET_SEGMENT
        ):
            final_cases.append(
                repaired_validation
            )
        else:
            final_cases.append(case)

    pass_count = sum(
        isinstance(case, dict)
        and case.get("status") == "PASS"
        for case in final_cases
    )

    fail_count = len(final_cases) - pass_count

    final_manifest.update({
        "schema_version": (
            "siraj-real-shamela-gemini-validation-final-v1"
        ),
        "status": (
            "PASS"
            if fail_count == 0
            else "FAIL"
        ),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "cases": final_cases,
        "provider_request_count": (
            original_manifest.get(
                "provider_request_count",
                0,
            )
        ),
        "provider_requests_reused": True,
        "additional_provider_requests": 0,
        "deterministic_evidence_repairs": len(
            repair_entries
        ),
        "source_manifest": "run-manifest.json",
        "human_review_status": "PENDING",
    })

    write_json(
        OUTPUT_ROOT / "run-manifest-final.json",
        final_manifest,
    )

    queue_path = (
        OUTPUT_ROOT / "human-review-queue.json"
    )

    if queue_path.exists():
        review_queue = read_json(queue_path)

        for case in review_queue.get(
            "cases",
            [],
        ):
            if (
                isinstance(case, dict)
                and case.get("segment_id")
                == TARGET_SEGMENT
            ):
                case["parsed_output_artifact"] = (
                    f"{TARGET_SEGMENT}"
                    "/parsed-output.repaired.json"
                )
                case["validation_artifact"] = (
                    f"{TARGET_SEGMENT}"
                    "/validation.repaired.json"
                )
                case["repair_report_artifact"] = (
                    f"{TARGET_SEGMENT}"
                    "/evidence-repair-report.json"
                )
                case[
                    "deterministic_evidence_repair"
                ] = "APPLIED"

        write_json(
            OUTPUT_ROOT
            / "human-review-queue-final.json",
            review_queue,
        )

    summary = {
        "status": final_manifest["status"],
        "case_count": len(final_cases),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "provider_request_count": (
            final_manifest.get(
                "provider_request_count"
            )
        ),
        "additional_provider_requests": 0,
        "repaired_segment": TARGET_SEGMENT,
        "evidence_repair_count": len(
            repair_entries
        ),
        "invalid_evidence_count": (
            repaired_validation[
                "invalid_evidence_count"
            ]
        ),
        "items_without_evidence": (
            repaired_validation[
                "items_without_evidence"
            ]
        ),
        "human_review_status": "PENDING",
        "final_manifest": str(
            OUTPUT_ROOT
            / "run-manifest-final.json"
        ),
    }

    print(
        json.dumps(
            summary,
            ensure_ascii=False,
            indent=2,
        )
    )

    return (
        0
        if final_manifest["status"] == "PASS"
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())