from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import traceback
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


from src.application.local_semantic_intelligence.gemini_provider import (
    GeminiSemanticConfig,
    GeminiSemanticProvider,
    redact_sensitive,
)
from src.application.local_semantic_intelligence.models import (
    SemanticHardwareProfile,
    SemanticProviderError,
)


SCHEMA_VERSION = "siraj-real-shamela-gemini-validation-v2"

INPUT_FILE = Path(r"C:\SIRAJ\4445-segments.jsonl")

OUTPUT_ROOT = Path(
    r"C:\SIRAJ\Workspace\first-project\working"
    r"\gold-20-fast-track\real-shamela-gemini-3-v2"
)

CASES = (
    {
        "segment_id": "4445-6243",
        "route": "PERSON_AND_STATUS",
    },
    {
        "segment_id": "4445-6244",
        "route": "ISNAD",
    },
    {
        "segment_id": "4445-6245",
        "route": "ISNAD",
    },
)

ROUTE_ITEM_KEYS = {
    "PERSON_AND_STATUS": (
        "entities",
        "statuses",
        "relations",
    ),
    "ISNAD": (
        "entities",
        "isnads",
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


def load_segments() -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}

    with INPUT_FILE.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise RuntimeError(
                    f"INVALID_JSONL_LINE:{line_number}"
                ) from error

            segment_id = str(
                record.get("segment_id", "")
            ).strip()

            if not segment_id:
                raise RuntimeError(
                    f"SEGMENT_ID_MISSING:{line_number}"
                )

            if segment_id in records:
                raise RuntimeError(
                    f"DUPLICATE_SEGMENT_ID:{segment_id}"
                )

            records[segment_id] = record

    return records


def validate_semantic_items(
    *,
    route: str,
    output: dict[str, Any],
    original_text: str,
) -> dict[str, Any]:
    item_count = 0
    evidence_quote_count = 0
    items_without_evidence = 0
    invalid_evidence: list[dict[str, Any]] = []
    evidence_quotes: list[dict[str, Any]] = []

    for collection_name in ROUTE_ITEM_KEYS[route]:
        collection = output.get(collection_name)

        if not isinstance(collection, list):
            invalid_evidence.append({
                "collection": collection_name,
                "reason": "COLLECTION_NOT_LIST",
            })
            continue

        for item_index, item in enumerate(collection):
            item_count += 1

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
                    "reason": "EVIDENCE_OBJECT_MISSING",
                })
                continue

            quote = evidence.get("text")

            if not isinstance(quote, str) or not quote.strip():
                items_without_evidence += 1
                invalid_evidence.append({
                    "collection": collection_name,
                    "item_index": item_index,
                    "reason": "EVIDENCE_TEXT_EMPTY",
                })
                continue

            evidence_quote_count += 1

            evidence_quotes.append({
                "collection": collection_name,
                "item_index": item_index,
                "text": quote,
            })

            if quote not in original_text:
                invalid_evidence.append({
                    "collection": collection_name,
                    "item_index": item_index,
                    "reason": "QUOTE_NOT_FOUND_IN_SOURCE",
                    "text": quote,
                })

    return {
        "semantic_item_count": item_count,
        "evidence_quote_count": evidence_quote_count,
        "items_without_evidence": items_without_evidence,
        "invalid_evidence_count": len(invalid_evidence),
        "invalid_evidence": invalid_evidence,
        "evidence_quotes": evidence_quotes,
    }


def build_provider() -> GeminiSemanticProvider:
    config = GeminiSemanticConfig(
        model_reference="gemini-3.5-flash",
        fallback_models=(),
        timeout_seconds=120.0,
        retries=0,
        temperature=0.0,
        maximum_output_tokens=8192,
        thinking_level="low",
        structured_output_enabled=True,
        external_network_allowed=True,
        batch_mode=False,
        data_policy_acknowledged=True,
        maximum_requests_per_run=3,
        maximum_input_tokens_per_run=30_000,
        maximum_output_tokens_per_run=24_576,
        abort_on_budget_exceeded=True,
        hardware=SemanticHardwareProfile(
            concurrency=1,
            context_tokens=16_384,
            maximum_output_tokens=8192,
            stage_timeout_seconds=120.0,
            keep_alive="0",
            checkpoint_after_each_stage=True,
        ),
    )

    return GeminiSemanticProvider(config)


def main() -> int:
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        raise RuntimeError("GEMINI_API_KEY_NOT_SET")

    records = load_segments()

    missing_segments = [
        case["segment_id"]
        for case in CASES
        if case["segment_id"] not in records
    ]

    if missing_segments:
        raise RuntimeError(
            "REQUIRED_SEGMENTS_MISSING:"
            + ",".join(missing_segments)
        )

    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    provider = build_provider()
    results: list[dict[str, Any]] = []

    for case in CASES:
        segment_id = case["segment_id"]
        route = case["route"]
        record = records[segment_id]
        case_root = OUTPUT_ROOT / segment_id

        original_text = str(
            record.get("original_text", "")
        )

        expected_hash = str(
            record.get("source_text_hash", "")
        )

        actual_hash = sha256_text(original_text)
        hash_match = actual_hash == expected_hash

        input_payload = {
            "schema_version": SCHEMA_VERSION,
            "source_id": record["source_id"],
            "book_id": record["book_id"],
            "book_title": record["book_title"],
            "segment_id": segment_id,
            "source_page_id": record["source_page_id"],
            "locator": record["locator"],
            "source_text_hash": expected_hash,
            "original_text": original_text,
            "route": route,
        }

        write_json(
            case_root / "input.json",
            input_payload,
        )

        if not hash_match:
            failure = {
                "schema_version": SCHEMA_VERSION,
                "status": "FAIL",
                "segment_id": segment_id,
                "route": route,
                "error_code": "SOURCE_HASH_MISMATCH",
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
            }

            write_json(
                case_root / "failure.json",
                failure,
            )

            results.append(failure)
            continue

        try:
            output = provider.extract_critical_route(
                route,
                {
                    "source_id": record["source_id"],
                    "segment_id": segment_id,
                    "locator": record["locator"],
                    "original_text": original_text,
                    "route": route,
                },
            )

            raw_response = output.get(
                "raw_provider_response",
                {},
            )

            parsed_output = dict(output)
            parsed_output.pop(
                "raw_provider_response",
                None,
            )

            write_json(
                case_root / "raw-provider-response.json",
                raw_response,
            )

            write_json(
                case_root / "parsed-output.json",
                parsed_output,
            )

            evidence_validation = (
                validate_semantic_items(
                    route=route,
                    output=parsed_output,
                    original_text=original_text,
                )
            )

            provider_metadata = parsed_output.get(
                "provider_metadata",
                {},
            )

            route_match = (
                parsed_output.get("route") == route
            )

            case_status = (
                "PASS"
                if (
                    hash_match
                    and route_match
                    and evidence_validation[
                        "semantic_item_count"
                    ] > 0
                    and evidence_validation[
                        "items_without_evidence"
                    ] == 0
                    and evidence_validation[
                        "invalid_evidence_count"
                    ] == 0
                )
                else "FAIL"
            )

            validation = {
                "schema_version": SCHEMA_VERSION,
                "status": case_status,
                "segment_id": segment_id,
                "route": route,
                "response_route": parsed_output.get(
                    "route"
                ),
                "response_route_match": route_match,
                "source_hash_match": hash_match,
                "source_text_hash": expected_hash,
                **evidence_validation,
                "finish_reason": provider_metadata.get(
                    "finish_reason"
                ),
                "usage": provider_metadata.get(
                    "usage",
                    {},
                ),
                "model": provider_metadata.get(
                    "model",
                    provider.config.model_reference,
                ),
            }

            write_json(
                case_root / "validation.json",
                validation,
            )

            results.append(validation)

        except SemanticProviderError as error:
            failure = {
                "schema_version": SCHEMA_VERSION,
                "status": "FAIL",
                "segment_id": segment_id,
                "route": route,
                "error_code": error.code,
                "details": redact_sensitive(
                    error.details
                ),
                "request_count": provider.request_count,
                "input_tokens": provider.input_tokens,
                "output_tokens": provider.output_tokens,
            }

            write_json(
                case_root / "failure.json",
                failure,
            )

            results.append(failure)

        except BaseException as error:
            failure = {
                "schema_version": SCHEMA_VERSION,
                "status": "FAIL",
                "segment_id": segment_id,
                "route": route,
                "error_code": "UNEXPECTED_FAILURE",
                "exception_class": type(error).__name__,
                "message": str(error),
                "traceback": traceback.format_exc(),
            }

            write_json(
                case_root / "failure.json",
                failure,
            )

            results.append(failure)

    pass_count = sum(
        result.get("status") == "PASS"
        for result in results
    )

    fail_count = len(results) - pass_count

    manifest = {
        "schema_version": SCHEMA_VERSION,
        "status": (
            "PASS"
            if pass_count == len(CASES)
            else "FAIL"
        ),
        "created_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "input_file": str(INPUT_FILE),
        "output_root": str(OUTPUT_ROOT),
        "provider_id": provider.identity.provider_id,
        "model": provider.config.model_reference,
        "fallback_models": [],
        "retries": 0,
        "case_count": len(CASES),
        "pass_count": pass_count,
        "fail_count": fail_count,
        "provider_request_count": provider.request_count,
        "provider_input_tokens": provider.input_tokens,
        "provider_output_tokens": provider.output_tokens,
        "human_review_status": "PENDING",
        "cases": results,
    }

    write_json(
        OUTPUT_ROOT / "run-manifest.json",
        manifest,
    )

    review_queue = {
        "schema_version": (
            "siraj-real-shamela-human-review-v1"
        ),
        "status": "PENDING_HUMAN_REVIEW",
        "instructions": [
            "راجع دقة أسماء الأشخاص وحدودها.",
            "راجع اكتمال سلسلة الإسناد وترتيب الرواة.",
            "راجع أن كل اقتباس يثبت العنصر المنسوب إليه.",
            "لا تعتمد أي استنتاج تاريخي قبل إكمال المراجعة.",
        ],
        "cases": [
            {
                "segment_id": result["segment_id"],
                "route": result["route"],
                "automatic_validation_status": (
                    result["status"]
                ),
                "input_artifact": (
                    f"{result['segment_id']}/input.json"
                ),
                "parsed_output_artifact": (
                    f"{result['segment_id']}"
                    "/parsed-output.json"
                ),
                "validation_artifact": (
                    f"{result['segment_id']}"
                    "/validation.json"
                ),
                "human_decision": "PENDING",
                "human_notes": "",
            }
            for result in results
        ],
    }

    write_json(
        OUTPUT_ROOT / "human-review-queue.json",
        review_queue,
    )

    print(
        json.dumps(
            {
                "status": manifest["status"],
                "case_count": manifest["case_count"],
                "pass_count": pass_count,
                "fail_count": fail_count,
                "provider_request_count": (
                    provider.request_count
                ),
                "provider_input_tokens": (
                    provider.input_tokens
                ),
                "provider_output_tokens": (
                    provider.output_tokens
                ),
                "human_review_status": (
                    manifest["human_review_status"]
                ),
                "output_root": str(OUTPUT_ROOT),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0 if manifest["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())