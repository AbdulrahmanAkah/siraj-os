from __future__ import annotations

from copy import deepcopy
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


SCHEMA_VERSION = "siraj-real-shamela-gemini-validation-v1"

INPUT_FILE = Path(r"C:\SIRAJ\4445-segments.jsonl")

OUTPUT_ROOT = Path(
    r"C:\SIRAJ\Workspace\first-project\working"
    r"\gold-20-fast-track\real-shamela-gemini-3"
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

SEMANTIC_KEYS = {
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
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


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


def load_records(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}

    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise RuntimeError(
                    f"INVALID_JSONL_LINE:{line_number}"
                ) from error

            segment_id = str(record.get("segment_id", "")).strip()

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


def collect_evidence_quotes(
    value: Any,
    path: str = "$",
) -> list[dict[str, str]]:
    results: list[dict[str, str]] = []

    if isinstance(value, dict):
        evidence = value.get("evidence")

        if isinstance(evidence, dict):
            text = evidence.get("text")

            if isinstance(text, str):
                results.append(
                    {
                        "path": f"{path}.evidence.text",
                        "text": text,
                    }
                )

        for key, item in value.items():
            if key in {
                "raw_provider_response",
                "provider_metadata",
            }:
                continue

            results.extend(
                collect_evidence_quotes(
                    item,
                    f"{path}.{key}",
                )
            )

    elif isinstance(value, list):
        for index, item in enumerate(value):
            results.extend(
                collect_evidence_quotes(
                    item,
                    f"{path}[{index}]",
                )
            )

    return results


def semantic_item_count(
    route: str,
    output: dict[str, Any],
) -> int:
    total = 0

    for key in SEMANTIC_KEYS[route]:
        value = output.get(key, [])

        if not isinstance(value, list):
            raise RuntimeError(
                f"SEMANTIC_FIELD_NOT_LIST:{route}:{key}"
            )

        total += len(value)

    return total


def build_provider() -> GeminiSemanticProvider:
    if not os.environ.get("GEMINI_API_KEY", "").strip():
        raise RuntimeError("GEMINI_API_KEY_NOT_SET")

    config = GeminiSemanticConfig(
        model_reference=os.environ.get(
            "SIRAJ_GEMINI_MODEL",
            "gemini-3.5-flash",
        ),
        fallback_models=(
            "gemini-3.1-flash-lite",
            "gemini-3-flash",
            "gemini-2.5-flash",
            "gemini-2.5-flash-lite",
        ),
        timeout_seconds=90.0,
        retries=1,
        temperature=0.0,
        maximum_output_tokens=1024,
        thinking_level="low",
        structured_output_enabled=True,
        external_network_allowed=True,
        batch_mode=False,
        data_policy_acknowledged=True,
        maximum_requests_per_run=8,
        maximum_input_tokens_per_run=20_000,
        maximum_output_tokens_per_run=4_096,
        abort_on_budget_exceeded=True,
        hardware=SemanticHardwareProfile(
            concurrency=1,
            context_tokens=8_192,
            maximum_output_tokens=1_024,
            stage_timeout_seconds=90.0,
            keep_alive="0",
            checkpoint_after_each_stage=True,
        ),
    )

    return GeminiSemanticProvider(config)


def main() -> int:
    records = load_records(INPUT_FILE)

    missing = [
        case["segment_id"]
        for case in CASES
        if case["segment_id"] not in records
    ]

    if missing:
        raise RuntimeError(
            "REQUIRED_SEGMENTS_MISSING:"
            + ",".join(missing)
        )

    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

    provider = build_provider()
    case_results: list[dict[str, Any]] = []

    for case in CASES:
        segment_id = case["segment_id"]
        route = case["route"]
        record = records[segment_id]

        case_root = OUTPUT_ROOT / segment_id
        case_root.mkdir(parents=True, exist_ok=True)

        original_text = str(
            record.get("original_text", "")
        )

        expected_hash = str(
            record.get("source_text_hash", "")
        )

        actual_hash = sha256_text(original_text)
        hash_match = actual_hash == expected_hash

        request_payload = {
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
            request_payload,
        )

        if not hash_match:
            validation = {
                "schema_version": SCHEMA_VERSION,
                "status": "FAIL",
                "segment_id": segment_id,
                "route": route,
                "source_hash_match": False,
                "expected_hash": expected_hash,
                "actual_hash": actual_hash,
                "error_code": "SOURCE_HASH_MISMATCH",
            }

            write_json(
                case_root / "validation.json",
                validation,
            )

            case_results.append(validation)
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

            parsed_output = deepcopy(output)
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

            evidence_quotes = collect_evidence_quotes(
                parsed_output
            )

            invalid_evidence: list[dict[str, str]] = []

            for evidence in evidence_quotes:
                quote = evidence["text"]

                if not quote.strip():
                    invalid_evidence.append(
                        {
                            **evidence,
                            "reason": "EMPTY_EVIDENCE",
                        }
                    )
                elif quote not in original_text:
                    invalid_evidence.append(
                        {
                            **evidence,
                            "reason": (
                                "QUOTE_NOT_FOUND_IN_SOURCE"
                            ),
                        }
                    )

            item_count = semantic_item_count(
                route,
                parsed_output,
            )

            items_without_evidence = max(
                0,
                item_count - len(evidence_quotes),
            )

            route_match = (
                parsed_output.get("route") == route
            )

            status = (
                "PASS"
                if (
                    hash_match
                    and route_match
                    and item_count > 0
                    and not invalid_evidence
                    and items_without_evidence == 0
                )
                else "FAIL"
            )

            validation = {
                "schema_version": SCHEMA_VERSION,
                "status": status,
                "segment_id": segment_id,
                "route": route,
                "response_route": parsed_output.get(
                    "route"
                ),
                "response_route_match": route_match,
                "source_hash_match": hash_match,
                "source_text_hash": expected_hash,
                "semantic_item_count": item_count,
                "evidence_quote_count": len(
                    evidence_quotes
                ),
                "invalid_evidence_count": len(
                    invalid_evidence
                ),
                "items_without_evidence": (
                    items_without_evidence
                ),
                "evidence_quotes": evidence_quotes,
                "invalid_evidence": invalid_evidence,
                "provider_metadata": parsed_output.get(
                    "provider_metadata",
                    {},
                ),
            }

            write_json(
                case_root / "validation.json",
                validation,
            )

            case_results.append(validation)

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
                "exception_class": (
                    type(error).__name__
                ),
            }

            write_json(
                case_root / "failure.json",
                failure,
            )

            case_results.append(failure)

        except BaseException as error:
            failure = {
                "schema_version": SCHEMA_VERSION,
                "status": "FAIL",
                "segment_id": segment_id,
                "route": route,
                "error_code": (
                    "UNEXPECTED_VALIDATION_FAILURE"
                ),
                "exception_class": (
                    type(error).__name__
                ),
                "message": str(error),
                "traceback": traceback.format_exc(),
            }

            write_json(
                case_root / "failure.json",
                failure,
            )

            case_results.append(failure)

    pass_count = sum(
        item["status"] == "PASS"
        for item in case_results
    )

    fail_count = len(case_results) - pass_count

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
        "primary_model": (
            provider.config.model_reference
        ),
        "model_chain": [
            provider.config.model_reference,
            *provider.config.fallback_models,
        ],
        "case_count": len(CASES),
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
        "cases": case_results,
    }

    write_json(
        OUTPUT_ROOT / "run-manifest.json",
        manifest,
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
                "output_root": str(OUTPUT_ROOT),
            },
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0 if manifest["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())