from __future__ import annotations

import argparse
import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

from src.application.local_semantic_intelligence.critical_regression import (
    CriticalEvidenceValidationError,
    _validate_route_output,
    resolve_route_evidence,
)
from src.application.local_semantic_intelligence.foundation import (
    atomic_write_json,
    atomic_write_text,
    integrity_hash,
)
from src.application.local_semantic_intelligence.gemini_provider import (
    GeminiSemanticProvider,
    load_gemini_config,
)

SCHEMA = "siraj-semantic-critical-20-v1"
ROUTES = ("PERSON_AND_STATUS", "APPOINTMENT_AND_OFFICE", "ISNAD", "SIRA_POETRY")


def span(text: str, value: str) -> dict[str, Any]:
    start = text.index(value)
    return {"start": start, "end": start + len(value), "text": value}


def entity(text: str, surface: str, entity_id: str) -> dict[str, Any]:
    return {
        "id": entity_id,
        "surface": surface,
        "types": ["person"],
        "roles": [],
        "explicit_proper_name": True,
        "evidence": span(text, surface),
    }


def person_case(number: int, text: str, names: list[str], status: tuple[int, str, str] | None, relation: tuple[int, str, int, str] | None, legacy: bool) -> dict[str, Any]:
    entities = [entity(text, name, f"entity_{i}") for i, name in enumerate(names)]
    statuses = [] if status is None else [{"person": f"entity_{status[0]}", "status": status[1], "evidence": span(text, status[2])}]
    relations = [] if relation is None else [{"subject": f"entity_{relation[0]}", "predicate": relation[1], "object": f"entity_{relation[2]}", "evidence": span(text, relation[3])}]
    return case(number, "PERSON_AND_STATUS", text, {"route": "PERSON_AND_STATUS", "entities": entities, "statuses": statuses, "relations": relations}, legacy)


def appointment_case(number: int, text: str, names: list[str], authority_index: int | None, appointee_index: int, office: str, jurisdiction: str, evidence: str, legacy: bool, kind: str = "APPOINTMENT") -> dict[str, Any]:
    entities = [entity(text, name, f"entity_{i}") for i, name in enumerate(names)]
    return case(number, "APPOINTMENT_AND_OFFICE", text, {"route": "APPOINTMENT_AND_OFFICE", "entities": entities, "appointments": [{"kind": kind, "appointee": f"entity_{appointee_index}", "appointing_authority": "" if authority_index is None else f"entity_{authority_index}", "office": office, "jurisdiction": jurisdiction, "generic_object": "", "evidence": span(text, evidence)}]}, legacy)


def isnad_case(number: int, text: str, narrators: list[str], evidence: str, boundary: str, legacy: bool) -> dict[str, Any]:
    entities = [entity(text, name, f"entity_{i}") for i, name in enumerate(narrators)]
    return case(number, "ISNAD", text, {"route": "ISNAD", "entities": entities, "isnads": [{"narrators": [f"entity_{i}" for i in range(len(narrators))], "evidence": span(text, evidence), "matn_boundary": text.index(boundary)}]}, legacy)


def sira_case(number: int, text: str, name: str, event_type: str, evidence: str, legacy: bool) -> dict[str, Any]:
    return case(number, "SIRA_POETRY", text, {"route": "SIRA_POETRY", "entities": [entity(text, name, "entity_0")], "events": [{"type": event_type, "explicit": True, "evidence": span(text, evidence)}]}, legacy)


def case(number: int, route: str, text: str, expected: dict[str, Any], legacy: bool) -> dict[str, Any]:
    return {
        "case_id": f"critical-{number:02d}",
        "segment_id": number,
        "audit_segment_id": f"critical-20-audit-{number:02d}",
        "source_id": "siraj-critical-20",
        "locator": f"siraj://critical-20/{number:02d}",
        "book_title": "Critical-20 controlled benchmark",
        "original_text": text,
        "route": route,
        "legacy_critical_4": legacy,
        "expected_output": expected,
        "expected_hash": integrity_hash(expected),
    }


CASES = [
    person_case(1, "إسماعيل بن أبي يحيى شيخ الشافعية وصفه أحمد بالتدليس", ["إسماعيل بن أبي يحيى", "أحمد"], (0, "مدلس", "وصفه أحمد بالتدليس"), (1, "criticized", 0, "وصفه أحمد بالتدليس"), True),
    person_case(2, "قال يحيى عن خالد إنه ثقة", ["يحيى", "خالد"], (1, "ثقة", "خالد إنه ثقة"), (0, "evaluated", 1, "قال يحيى عن خالد إنه ثقة"), False),
    person_case(3, "ذكر أحمد بن سعيد وقال إنه ضعيف", ["أحمد بن سعيد"], (0, "ضعيف", "أحمد بن سعيد وقال إنه ضعيف"), None, False),
    person_case(4, "قال تعالى في كتابه ثم روى عبد الله الخبر", ["عبد الله"], None, None, False),
    person_case(5, "جرح ابن معين سليمان وقال هو متروك", ["ابن معين", "سليمان"], (1, "متروك", "سليمان وقال هو متروك"), (0, "criticized", 1, "جرح ابن معين سليمان"), False),
    appointment_case(6, "ولي محمد بن يحيى تدريس المدرسة النظامية", ["محمد بن يحيى"], None, 0, "تدريس", "المدرسة النظامية", "تدريس المدرسة النظامية", True),
    appointment_case(7, "عهد الخليفة إلى علي بقضاء بغداد", ["الخليفة", "علي"], 0, 1, "قضاء", "بغداد", "عهد الخليفة إلى علي بقضاء بغداد", False),
    appointment_case(8, "استناب الوالي عمر على ديوان الخراج", ["الوالي", "عمر"], 0, 1, "ديوان الخراج", "", "استناب الوالي عمر على ديوان الخراج", False),
    appointment_case(9, "تولى زيد إمامة الجامع الكبير", ["زيد"], None, 0, "إمامة", "الجامع الكبير", "تولى زيد إمامة الجامع الكبير", False),
    appointment_case(10, "صرف الأمير حسن عن ولاية الموصل", ["الأمير", "حسن"], 0, 1, "ولاية", "الموصل", "صرف الأمير حسن عن ولاية الموصل", False, "REMOVAL"),
    isnad_case(11, "حدثنا الأعمش عن حبيب بن أبي ثابت قال الخبر", ["الأعمش", "حبيب بن أبي ثابت"], "الأعمش عن حبيب بن أبي ثابت", "قال", True),
    isnad_case(12, "أخبرنا مالك عن نافع عن ابن عمر أن النبي قال", ["مالك", "نافع", "ابن عمر"], "مالك عن نافع عن ابن عمر", "أن النبي", False),
    isnad_case(13, "سمعت سفيان يقول حدثني منصور ثم قال المتن", ["سفيان", "منصور"], "سفيان يقول حدثني منصور", "ثم قال", False),
    isnad_case(14, "روى شعبة عن قتادة الخبر بلا زيادة", ["شعبة", "قتادة"], "شعبة عن قتادة", "الخبر", False),
    isnad_case(15, "حدثنا وكيع حدثنا الأعمش قال هذا المتن", ["وكيع", "الأعمش"], "وكيع حدثنا الأعمش", "قال هذا", False),
    sira_case(16, "هاشم قد آلت له سقاية فإنها منارة العطاء", "هاشم", "OFFICE_INHERITANCE", "آلت له سقاية", True),
    sira_case(17, "خرج خالد إلى بدر في العام الثاني", "خالد", "EXPEDITION", "خرج خالد إلى بدر", False),
    sira_case(18, "قال الشاعر يوم أحد ثبتنا مع الرسول", "الشاعر", "POETRY_CONTEXT", "قال الشاعر يوم أحد", False),
    sira_case(19, "هاجر عثمان من مكة إلى المدينة", "عثمان", "MIGRATION", "هاجر عثمان من مكة إلى المدينة", False),
    sira_case(20, "ورث العباس السقاية بعد أبيه", "العباس", "OFFICE_INHERITANCE", "ورث العباس السقاية", False),
]


class OfflineProvider:
    def __init__(self) -> None:
        self.outputs = {item["case_id"]: deepcopy(item["expected_output"]) for item in CASES}

    def extract_critical_route(self, route: str, request: dict[str, Any]) -> dict[str, Any]:
        return deepcopy(self.outputs[str(request["case_id"])])

    def unload(self) -> dict[str, Any]:
        return {"status": "UNLOADED"}


def root(output_root: str | Path) -> Path:
    return Path(output_root) / "critical-20"


def prepare(output_root: str | Path) -> dict[str, Any]:
    target = root(output_root)
    manifest = {
        "schema_version": SCHEMA,
        "sample": "critical-20",
        "status": "PREPARED",
        "case_count": 20,
        "legacy_case_count": 4,
        "new_case_count": 16,
        "route_counts": {route: sum(item["route"] == route for item in CASES) for route in ROUTES},
        "concurrency": 1,
        "cases": CASES,
    }
    atomic_write_json(target / "critical-20-manifest.json", manifest)
    atomic_write_json(target / "critical-20-expected.json", {"schema_version": SCHEMA, "cases": [{"case_id": item["case_id"], "route": item["route"], "expected_output": item["expected_output"], "expected_hash": item["expected_hash"]} for item in CASES]})
    atomic_write_json(target / "critical-20-adversarial.json", {"schema_version": SCHEMA, "mutation": "NON_VERBATIM_REQUIRED_EVIDENCE", "cases": [{"case_id": item["case_id"], "expected_rejection": "EVIDENCE_TEXT_NOT_VERBATIM"} for item in CASES]})
    atomic_write_json(target / "critical-20-adjudication.json", {"schema_version": SCHEMA, "status": "PENDING_PROVIDER_RUNS", "cases": [{"case_id": item["case_id"], "route": item["route"], "offline_status": "PENDING", "gemini_status": "PENDING", "decision": "PENDING"} for item in CASES]})
    return manifest


def run(
    output_root: str | Path,
    provider: Any,
    provider_id: str,
) -> dict[str, Any]:
    target = root(output_root)
    prepare(output_root)

    checkpoint_root = (
        target
        / f"{provider_id.lower()}-checkpoints"
    )
    checkpoint_root.mkdir(
        parents=True,
        exist_ok=True,
    )

    results = []

    def quality(
        validation: dict[str, Any],
    ) -> tuple[int, int, int]:
        rank = {
            "FAIL": 0,
            "PARTIAL": 1,
            "PASS": 2,
        }.get(
            str(
                validation.get(
                    "case_status",
                    "FAIL",
                )
            ),
            0,
        )

        return (
            rank,
            int(
                validation.get(
                    "accepted_items",
                    0,
                )
            ),
            -int(
                validation.get(
                    "rejected_items",
                    0,
                )
            ),
        )

    for item in CASES:
        checkpoint = (
            checkpoint_root
            / f"{item['case_id']}.json"
        )

        if checkpoint.is_file():
            results.append(
                json.loads(
                    checkpoint.read_text(
                        encoding="utf-8",
                    )
                )
            )
            continue

        request = {
            "source_id": item["source_id"],
            "locator": item["locator"],
            "original_text": item[
                "original_text"
            ],
            "route": item["route"],
            "case_id": item["case_id"],
            "repair": False,
        }

        first_output = (
            provider.extract_critical_route(
                item["route"],
                request,
            )
        )

        (
            first_resolved,
            first_validation,
            first_diagnostics,
        ) = resolve_route_evidence(
            item,
            first_output,
            1,
        )

        resolved = first_resolved
        validation = first_validation
        diagnostics = list(
            first_diagnostics
        )
        calls = 1

        if validation["case_status"] != "PASS":
            rejection = (
                validation.get(
                    "rejections",
                    [{}],
                )[0]
                if validation.get(
                    "rejections"
                )
                else {}
            )

            repair_request = {
                **request,
                "repair": True,
                "repair_reason": (
                    rejection.get(
                        "reason_code",
                        "ROUTE_SEMANTIC_VALIDATION_FAILURE",
                    )
                ),
                "rejected_item": {
                    "collection": (
                        rejection.get(
                            "collection",
                            "",
                        )
                    ),
                    "item_kind": (
                        rejection.get(
                            "item_kind",
                            "",
                        )
                    ),
                    "evidence_text": (
                        rejection.get(
                            "evidence_text",
                            "",
                        )
                    ),
                },
                "accepted_output": (
                    first_resolved
                ),
            }

            repair_output = (
                provider.extract_critical_route(
                    item["route"],
                    repair_request,
                )
            )

            (
                repair_resolved,
                repair_validation,
                repair_diagnostics,
            ) = resolve_route_evidence(
                item,
                repair_output,
                2,
            )

            diagnostics.extend(
                repair_diagnostics
            )
            calls = 2

            if quality(
                repair_validation
            ) > quality(
                first_validation
            ):
                resolved = repair_resolved
                validation = (
                    repair_validation
                )

        case_result = {
            "case_id": item["case_id"],
            "route": item["route"],
            "status": validation[
                "case_status"
            ],
            "calls": calls,
            "validation": validation,
            "diagnostics": diagnostics,
            "output": resolved,
        }

        atomic_write_json(
            checkpoint,
            case_result,
        )
        results.append(case_result)

    counts = {
        status: sum(
            row["status"] == status
            for row in results
        )
        for status in (
            "PASS",
            "PARTIAL",
            "FAIL",
        )
    }

    report = {
        "schema_version": SCHEMA,
        "provider_id": provider_id,
        "status": (
            "PASS"
            if counts["PASS"] == 20
            else "FAIL"
        ),
        "case_count": 20,
        "status_counts": counts,
        "cases": results,
    }

    atomic_write_json(
        target
        / f"critical-20-{provider_id.lower()}-run.json",
        report,
    )

    return report


def run_offline(output_root: str | Path) -> dict[str, Any]:
    return run(output_root, OfflineProvider(), "OFFLINE")


def run_adversarial(output_root: str | Path) -> dict[str, Any]:
    prepare(output_root)
    rows = []
    required = {"PERSON_AND_STATUS": "entities", "APPOINTMENT_AND_OFFICE": "appointments", "ISNAD": "isnads", "SIRA_POETRY": "entities"}
    for item in CASES:
        output = deepcopy(item["expected_output"])
        output[required[item["route"]]][0]["evidence"] = {"start": 0, "end": 9, "text": "غير موجود"}
        reason = "NO_REJECTION"
        try:
            _validate_route_output(item, output)
        except CriticalEvidenceValidationError as error:
            reason = str(error)
        rows.append({"case_id": item["case_id"], "status": "PASS" if "EVIDENCE_TEXT_NOT_VERBATIM" in reason else "FAIL", "reason": reason})
    report = {"schema_version": SCHEMA, "status": "PASS" if all(row["status"] == "PASS" for row in rows) else "FAIL", "case_count": 20, "cases": rows}
    atomic_write_json(root(output_root) / "critical-20-adversarial-run.json", report)
    return report


def run_gemini(output_root: str | Path, config_path: str | Path) -> dict[str, Any]:
    config = load_gemini_config(config_path)
    config = replace(config, maximum_requests_per_run=max(config.maximum_requests_per_run, 40), maximum_input_tokens_per_run=max(config.maximum_input_tokens_per_run, 100000), maximum_output_tokens_per_run=max(config.maximum_output_tokens_per_run, 40000))
    provider = GeminiSemanticProvider(config)
    try:
        return run(output_root, provider, "GEMINI")
    finally:
        provider.unload()


def adjudicate(output_root: str | Path) -> dict[str, Any]:
    target = root(output_root)
    offline = json.loads((target / "critical-20-offline-run.json").read_text(encoding="utf-8"))
    gemini_path = target / "critical-20-gemini-run.json"
    gemini = json.loads(gemini_path.read_text(encoding="utf-8")) if gemini_path.exists() else None
    off = {row["case_id"]: row for row in offline["cases"]}
    gem = {row["case_id"]: row for row in gemini["cases"]} if gemini else {}
    rows = []
    for item in CASES:
        g = gem.get(item["case_id"])
        decision = "ACCEPTED" if off[item["case_id"]]["status"] == "PASS" and g and g["status"] == "PASS" else "REVIEW_REQUIRED"
        rows.append({"case_id": item["case_id"], "route": item["route"], "offline_status": off[item["case_id"]]["status"], "gemini_status": g["status"] if g else "NOT_RUN", "decision": decision})
    status = "COMPLETED" if all(row["decision"] == "ACCEPTED" for row in rows) else "REVIEW_REQUIRED"
    report = {"schema_version": SCHEMA, "status": status, "cases": rows}
    atomic_write_json(target / "critical-20-adjudication.json", report)
    atomic_write_text(target / "critical-20-adjudication.md", f"# Critical-20 adjudication\n\nStatus: `{status}`\n")
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "offline", "adversarial", "gemini", "adjudicate"))
    parser.add_argument("--output-root", required=True)
    parser.add_argument("--config")
    args = parser.parse_args()
    if args.action == "prepare": result = prepare(args.output_root)
    elif args.action == "offline": result = run_offline(args.output_root)
    elif args.action == "adversarial": result = run_adversarial(args.output_root)
    elif args.action == "gemini":
        if not args.config: parser.error("--config is required for gemini")
        result = run_gemini(args.output_root, args.config)
    else: result = adjudicate(args.output_root)
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result.get("status") != "FAIL" else 1


if __name__ == "__main__":
    raise SystemExit(main())
