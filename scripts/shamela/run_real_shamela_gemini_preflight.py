from __future__ import annotations

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


INPUT_FILE = Path(r"C:\SIRAJ\4445-segments.jsonl")

OUTPUT_ROOT = Path(
    r"C:\SIRAJ\Workspace\first-project\working"
    r"\gold-20-fast-track\real-shamela-gemini-preflight"
)

TARGET_SEGMENT = "4445-6243"
TARGET_ROUTE = "PERSON_AND_STATUS"


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            value,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def sha256_text(text: str) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def load_segment() -> dict[str, Any]:
    with INPUT_FILE.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip():
                continue

            record = json.loads(line)

            if record.get("segment_id") == TARGET_SEGMENT:
                return record

    raise RuntimeError(
        f"SEGMENT_NOT_FOUND:{TARGET_SEGMENT}"
    )


def collect_evidence(
    value: Any,
    path: str = "$",
) -> list[dict[str, str]]:
    found: list[dict[str, str]] = []

    if isinstance(value, dict):
        evidence = value.get("evidence")

        if isinstance(evidence, dict):
            text = evidence.get("text")

            if isinstance(text, str):
                found.append({
                    "path": f"{path}.evidence.text",
                    "text": text,
                })

        for key, item in value.items():
            if key not in {
                "raw_provider_response",
                "provider_metadata",
            }:
                found.extend(
                    collect_evidence(
                        item,
                        f"{path}.{key}",
                    )
                )

    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(
                collect_evidence(
                    item,
                    f"{path}[{index}]",
                )
            )

    return found


def main() -> int:
    record = load_segment()
    original_text = record["original_text"]

    expected_hash = record["source_text_hash"]
    actual_hash = sha256_text(original_text)

    if actual_hash != expected_hash:
        raise RuntimeError("SOURCE_HASH_MISMATCH")

    if OUTPUT_ROOT.exists():
        shutil.rmtree(OUTPUT_ROOT)

    OUTPUT_ROOT.mkdir(parents=True)

    request = {
        "source_id": record["source_id"],
        "segment_id": record["segment_id"],
        "locator": record["locator"],
        "original_text": original_text,
        "route": TARGET_ROUTE,
    }

    write_json(
        OUTPUT_ROOT / "input.json",
        {
            **request,
            "source_text_hash": expected_hash,
            "book_id": record["book_id"],
            "source_page_id": record[
                "source_page_id"
            ],
        },
    )

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
        maximum_requests_per_run=1,
        maximum_input_tokens_per_run=20_000,
        maximum_output_tokens_per_run=8192,
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

    provider = GeminiSemanticProvider(config)

    try:
        output = provider.extract_critical_route(
            TARGET_ROUTE,
            request,
        )

    except SemanticProviderError as error:
        failure = {
            "status": "FAIL",
            "segment_id": TARGET_SEGMENT,
            "route": TARGET_ROUTE,
            "model": config.model_reference,
            "error_code": error.code,
            "details": redact_sensitive(
                error.details
            ),
            "request_count": provider.request_count,
            "input_tokens": provider.input_tokens,
            "output_tokens": provider.output_tokens,
        }

        write_json(
            OUTPUT_ROOT / "failure.json",
            failure,
        )

        print(
            json.dumps(
                failure,
                ensure_ascii=False,
                indent=2,
                default=str,
            )
        )

        return 1

    except BaseException as error:
        failure = {
            "status": "FAIL",
            "error_code": "UNEXPECTED_FAILURE",
            "exception_class": type(error).__name__,
            "message": str(error),
            "traceback": traceback.format_exc(),
        }

        write_json(
            OUTPUT_ROOT / "failure.json",
            failure,
        )

        print(
            json.dumps(
                failure,
                ensure_ascii=False,
                indent=2,
            )
        )

        return 1

    raw_response = output.get(
        "raw_provider_response",
        {},
    )

    parsed = dict(output)
    parsed.pop("raw_provider_response", None)

    write_json(
        OUTPUT_ROOT / "raw-provider-response.json",
        raw_response,
    )

    write_json(
        OUTPUT_ROOT / "parsed-output.json",
        parsed,
    )

    evidence = collect_evidence(parsed)

    invalid_evidence = [
        {
            **item,
            "reason": (
                "EMPTY_EVIDENCE"
                if not item["text"].strip()
                else "QUOTE_NOT_FOUND_IN_SOURCE"
            ),
        }
        for item in evidence
        if (
            not item["text"].strip()
            or item["text"] not in original_text
        )
    ]

    semantic_item_count = sum(
        len(parsed.get(key, []))
        for key in (
            "entities",
            "statuses",
            "relations",
        )
        if isinstance(parsed.get(key, []), list)
    )

    metadata = parsed.get(
        "provider_metadata",
        {},
    )

    status = (
        "PASS"
        if (
            parsed.get("route") == TARGET_ROUTE
            and semantic_item_count > 0
            and evidence
            and not invalid_evidence
        )
        else "FAIL"
    )

    validation = {
        "status": status,
        "segment_id": TARGET_SEGMENT,
        "route": TARGET_ROUTE,
        "model": config.model_reference,
        "source_hash_match": True,
        "response_route": parsed.get("route"),
        "semantic_item_count": semantic_item_count,
        "evidence_quote_count": len(evidence),
        "invalid_evidence_count": len(
            invalid_evidence
        ),
        "invalid_evidence": invalid_evidence,
        "finish_reason": metadata.get(
            "finish_reason"
        ),
        "usage": metadata.get("usage", {}),
        "request_count": provider.request_count,
        "input_tokens": provider.input_tokens,
        "output_tokens": provider.output_tokens,
    }

    write_json(
        OUTPUT_ROOT / "validation.json",
        validation,
    )

    print(
        json.dumps(
            validation,
            ensure_ascii=False,
            indent=2,
        )
    )

    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())