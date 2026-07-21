from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from src.application.local_semantic_intelligence.semantic_acceptance_gate import (
    evaluate_semantic_acceptance,
)


def _read(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"JSON_ROOT_NOT_OBJECT:{path}")
    return payload


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--provider-output", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    parser.add_argument("--repaired-output", required=True, type=Path)
    args = parser.parse_args()

    source = _read(args.input)
    provider_output = _read(args.provider_output)
    report = evaluate_semantic_acceptance(
        str(source["original_text"]),
        str(source["route"]),
        provider_output,
    )
    repaired_output = report.pop("repaired_output")
    _write(args.report, report)
    _write(args.repaired_output, repaired_output)

    summary = {
        "status": report["status"],
        "production_acceptance": report["production_acceptance"],
        "repair_count": report["repair_count"],
        "rejection_count": report["rejection_count"],
        "matn_boundary_error_count": report[
            "matn_boundary_error_count"
        ],
        "isnad_completeness": report["isnad_completeness"]["status"],
        "uncovered_isnad_candidates": report[
            "isnad_completeness"
        ]["uncovered_candidate_count"],
        "report": str(args.report),
        "repaired_output": str(args.repaired_output),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
