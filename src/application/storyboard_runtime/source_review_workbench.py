"""Offline human-review workbench for the twenty-two Adam sources."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import unicodedata
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Mapping

WORKBENCH_SCHEMA = "siraj-source-review-workbench-v1"
MANIFEST_SCHEMA = "siraj-source-review-workbench-manifest-v1"
DECISION_SCHEMA = "siraj-source-review-human-decision-v1"
TEMPLATE_SCHEMA = "siraj-source-review-human-decision-template-v1"
VALIDATION_SCHEMA = "siraj-source-review-validation-report-v1"
POLICY_SCHEMA = "siraj-source-review-workbench-policy-v1"
JSON_SCHEMA_ID = "siraj-source-review-human-decision-json-schema-v1"
STATUS = "SOURCE_REVIEW_WORKBENCH_READY"
GATE = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTO_APPROVAL = "FORBIDDEN"
LIVE_EXECUTION = "BLOCKED"

EXPECTED_SOURCE_COUNT = 22
EXPECTED_EVENT_COUNT = 14
EXPECTED_LINK_COUNT = 28
EXPECTED_DOCKET_SCHEMA = "siraj-source-review-docket-v1"
EXPECTED_RESOLUTION_SCHEMA = "siraj-partial-source-resolution-v1"
EXPECTED_EVENT_SCHEMA = "siraj-event-source-review-readiness-v1"
EXPECTED_MATERIALIZATION_SCHEMA = "siraj-remote-source-materialization-v1"

ALLOWED_DECISIONS = (
    "confirm_exact_source_text",
    "confirm_with_correction",
    "reject_locator",
    "defer_authentication",
)
CONFIRMING_DECISIONS = (
    "confirm_exact_source_text",
    "confirm_with_correction",
    "defer_authentication",
)
FINAL_APPROVAL_PHRASE = (
    "أعتمد بشريًا قرارات مقارنة النصوص والمواضع للمصادر الـ22 "
    "ضمن النطاق المحدد فقط"
)

DIACRITICS_RE = re.compile(
    r"[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]"
)


class SourceReviewWorkbenchError(ValueError):
    pass


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SourceReviewWorkbenchError(f"Invalid JSON: {path}") from exc


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def normalize_arabic(value: str) -> str:
    value = unicodedata.normalize("NFKC", value)
    value = DIACRITICS_RE.sub("", value).replace("\u0640", "")
    for source, target in {
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٱ": "ا",
        "ى": "ي",
        "ؤ": "و",
        "ئ": "ي",
        "ة": "ه",
    }.items():
        value = value.replace(source, target)
    value = re.sub(r"[^\u0600-\u06ff0-9A-Za-z]+", " ", value)
    return " ".join(value.split()).strip()


def _load_checked(path: Path, schema: str) -> dict:
    data = read_json(path)
    if not isinstance(data, Mapping):
        raise SourceReviewWorkbenchError(f"Expected object: {path}")
    if data.get("schema_version") != schema:
        raise SourceReviewWorkbenchError(f"Unexpected schema: {path}")
    return dict(data)


def load_docket(path: Path) -> dict:
    data = _load_checked(path, EXPECTED_DOCKET_SCHEMA)
    if data.get("source_count") != EXPECTED_SOURCE_COUNT:
        raise SourceReviewWorkbenchError("Expected 22 docket sources.")
    if data.get("remaining_resolution_source_ids") != []:
        raise SourceReviewWorkbenchError("Unresolved sources remain.")
    expected = {
        "READY_FOR_HUMAN_CONFIRMATION": 17,
        "REFINED_READY_FOR_HUMAN_CONFIRMATION": 5,
    }
    if data.get("refined_readiness_counts") != expected:
        raise SourceReviewWorkbenchError("Unexpected readiness counts.")
    if data.get("human_comparison_complete") is not False:
        raise SourceReviewWorkbenchError("Docket already claims completion.")
    return data


def load_resolution(path: Path) -> dict:
    data = _load_checked(path, EXPECTED_RESOLUTION_SCHEMA)
    if data.get("source_count") != EXPECTED_SOURCE_COUNT:
        raise SourceReviewWorkbenchError("Expected 22 resolution records.")
    if data.get("remaining_resolution_source_count") != 0:
        raise SourceReviewWorkbenchError("Resolution is incomplete.")
    if len(data.get("records", [])) != EXPECTED_SOURCE_COUNT:
        raise SourceReviewWorkbenchError("Resolution coverage is incomplete.")
    return data


def load_events(path: Path) -> dict:
    data = _load_checked(path, EXPECTED_EVENT_SCHEMA)
    if data.get("event_count") != EXPECTED_EVENT_COUNT:
        raise SourceReviewWorkbenchError("Expected 14 events.")
    if data.get("event_source_link_count") != EXPECTED_LINK_COUNT:
        raise SourceReviewWorkbenchError("Expected 28 event/source links.")
    return data


def load_materialization(path: Path) -> dict:
    data = _load_checked(path, EXPECTED_MATERIALIZATION_SCHEMA)
    if data.get("source_count") != EXPECTED_SOURCE_COUNT:
        raise SourceReviewWorkbenchError("Expected 22 materialized sources.")
    return data


def build_policy() -> dict:
    policy = {
        "schema_version": POLICY_SCHEMA,
        "status": "SOURCE_REVIEW_WORKBENCH_POLICY_ACTIVE",
        "episode_id": "episode-001-adam",
        "allowed_decisions": list(ALLOWED_DECISIONS),
        "final_approval_phrase": FINAL_APPROVAL_PHRASE,
        "fixed_false_fields": [
            "authentication_verified",
            "origin_classification_verified",
            "approved_for_event_binding",
        ],
        "prohibitions": [
            "defaulting or auto-selecting a human decision",
            "automatic source verification",
            "automatic hadith grading",
            "automatic source authentication",
            "automatic source-origin classification",
            "automatic event-binding approval",
            "automatic evidence approval",
            "opening the evidence gate",
            "provider execution",
        ],
        "human_approval": False,
        "source_verification_complete": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    policy["policy_id"] = (
        "adam_source_review_workbench_policy_"
        + canonical_sha256(policy)[:16]
    )
    validate_policy(policy)
    return policy


def build_manifest(
    *,
    docket: Mapping[str, object],
    resolution: Mapping[str, object],
    events: Mapping[str, object],
    materialization: Mapping[str, object],
    policy: Mapping[str, object],
) -> dict:
    resolution_index = {
        item["source_candidate_id"]: item
        for item in resolution["records"]
    }
    materialization_index = {
        item["source_candidate_id"]: item
        for item in materialization["sources"]
    }
    event_links: dict[str, list[str]] = defaultdict(list)
    for event in events["events"]:
        for source_id in event["source_candidate_ids"]:
            event_links[source_id].append(event["event_id"])

    sources = []
    for docket_source in docket["sources"]:
        source_id = docket_source["source_candidate_id"]
        record = resolution_index[source_id]
        materialized = materialization_index[source_id]
        archive_paths = [
            str(item.get("raw_archive_path", ""))
            for item in materialized.get("retrievals", [])
            if item.get("raw_archive_path")
        ]
        metrics = record["enhanced_metrics"]
        sources.append(
            {
                "source_candidate_id": source_id,
                "locator": docket_source["locator"],
                "source_kind": docket_source["source_kind"],
                "refined_readiness": docket_source["refined_readiness"],
                "resolution_record_id": docket_source[
                    "resolution_record_id"
                ],
                "source_url": materialized.get("source_url", ""),
                "raw_archive_paths": archive_paths,
                "event_ids": sorted(event_links[source_id]),
                "research_anchor_text": record["research_anchor_text"],
                "machine_extracted_text": record[
                    "machine_extracted_text"
                ],
                "suggested_exact_excerpt": metrics["candidate_text"],
                "suggested_exact_excerpt_sha256": metrics[
                    "candidate_text_sha256"
                ],
                "missing_anchor_tokens": metrics[
                    "missing_anchor_tokens"
                ],
                "extra_candidate_tokens": metrics[
                    "extra_candidate_tokens"
                ],
                "weighted_resolution_score": metrics[
                    "weighted_resolution_score"
                ],
                "human_decision": False,
                "source_verified": False,
            }
        )

    manifest = {
        "schema_version": MANIFEST_SCHEMA,
        "status": STATUS,
        "episode_id": "episode-001-adam",
        "docket_id": docket["docket_id"],
        "docket_sha256": canonical_sha256(docket),
        "resolution_id": resolution["resolution_id"],
        "resolution_sha256": canonical_sha256(resolution),
        "policy_id": policy["policy_id"],
        "policy_sha256": canonical_sha256(policy),
        "source_count": len(sources),
        "event_count": events["event_count"],
        "event_source_link_count": events["event_source_link_count"],
        "sources": sources,
        "human_decisions_recorded": 0,
        "human_comparison_complete": False,
        "source_verification_complete": False,
        "human_approval": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    manifest["workbench_manifest_id"] = (
        "adam_source_review_workbench_"
        + canonical_sha256(manifest)[:16]
    )
    validate_manifest(manifest)
    return manifest


def build_decision_template(
    *, docket: Mapping[str, object], policy: Mapping[str, object]
) -> dict:
    decisions = []
    for source in docket["sources"]:
        decisions.append(
            {
                "source_candidate_id": source["source_candidate_id"],
                "locator": source["locator"],
                "source_kind": source["source_kind"],
                "refined_readiness": source["refined_readiness"],
                "resolution_record_id": source[
                    "resolution_record_id"
                ],
                "suggested_exact_excerpt_sha256": source[
                    "suggested_exact_excerpt_sha256"
                ],
                "decision": "",
                "approved_locator": "",
                "approved_exact_excerpt": "",
                "approved_exact_excerpt_sha256": "",
                "approved_context_before_after": "",
                "human_compared_to_source": False,
                "source_verified": False,
                "authentication_result": "",
                "authentication_authority": "",
                "authentication_verified": False,
                "origin_classification": "",
                "origin_classification_basis": "",
                "origin_classification_verified": False,
                "approved_for_event_binding": False,
                "human_decision": False,
                "verified_by": "",
                "verified_at": "",
                "reviewer_notes": "",
            }
        )
    template = {
        "schema_version": TEMPLATE_SCHEMA,
        "status": "EDITABLE_DRAFT_NOT_APPROVED",
        "episode_id": "episode-001-adam",
        "docket_id": docket["docket_id"],
        "docket_sha256": canonical_sha256(docket),
        "policy_id": policy["policy_id"],
        "policy_sha256": canonical_sha256(policy),
        "source_count": len(decisions),
        "decisions": decisions,
        "approved_by": "",
        "approved_at": "",
        "approval_phrase": "",
        "human_comparison_complete": False,
        "source_verification_complete": False,
        "human_approval": False,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    validate_decision_template(template)
    return template


def build_json_schema() -> dict:
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "$id": JSON_SCHEMA_ID,
        "title": "SIRAJ source-review human decision",
        "type": "object",
        "required": [
            "schema_version",
            "episode_id",
            "docket_id",
            "docket_sha256",
            "policy_id",
            "policy_sha256",
            "source_count",
            "decisions",
            "approved_by",
            "approved_at",
            "approval_phrase",
            "human_comparison_complete",
            "source_verification_complete",
            "human_approval",
            "full_episode_adjudication_complete",
            "approved_evidence_package_complete",
            "opens_evidence_gate",
            "evidence_gate_status",
            "automatic_evidence_approval",
            "live_provider_execution",
        ],
        "properties": {
            "schema_version": {"const": DECISION_SCHEMA},
            "episode_id": {"const": "episode-001-adam"},
            "source_count": {"const": EXPECTED_SOURCE_COUNT},
            "decisions": {
                "type": "array",
                "minItems": EXPECTED_SOURCE_COUNT,
                "maxItems": EXPECTED_SOURCE_COUNT,
            },
            "full_episode_adjudication_complete": {"const": False},
            "approved_evidence_package_complete": {"const": False},
            "opens_evidence_gate": {"const": False},
            "evidence_gate_status": {"const": GATE},
            "automatic_evidence_approval": {"const": AUTO_APPROVAL},
            "live_provider_execution": {"const": LIVE_EXECUTION},
        },
    }


def _decision_errors(
    item: Mapping[str, object], expected: Mapping[str, object]
) -> list[str]:
    errors = []
    source_id = expected["source_candidate_id"]
    if item.get("source_candidate_id") != source_id:
        errors.append("source_candidate_id mismatch")
    for field in (
        "locator",
        "source_kind",
        "refined_readiness",
        "resolution_record_id",
        "suggested_exact_excerpt_sha256",
    ):
        if item.get(field) != expected.get(field):
            errors.append(f"{field} mismatch")

    decision = item.get("decision")
    if decision not in ALLOWED_DECISIONS:
        errors.append("decision is not allowed")
        return errors

    if item.get("human_compared_to_source") is not True:
        errors.append("human_compared_to_source must be true")
    if item.get("human_decision") is not True:
        errors.append("human_decision must be true")
    if not str(item.get("verified_by", "")).strip():
        errors.append("verified_by is required")
    if not str(item.get("verified_at", "")).strip():
        errors.append("verified_at is required")
    if item.get("authentication_verified") is not False:
        errors.append("authentication_verified must remain false")
    if item.get("origin_classification_verified") is not False:
        errors.append(
            "origin_classification_verified must remain false"
        )
    if item.get("approved_for_event_binding") is not False:
        errors.append("approved_for_event_binding must remain false")

    excerpt = str(item.get("approved_exact_excerpt", "")).strip()
    excerpt_sha = str(
        item.get("approved_exact_excerpt_sha256", "")
    ).strip()
    locator = str(item.get("approved_locator", "")).strip()
    context = str(
        item.get("approved_context_before_after", "")
    ).strip()
    notes = str(item.get("reviewer_notes", "")).strip()

    if decision in CONFIRMING_DECISIONS:
        if item.get("source_verified") is not True:
            errors.append("source_verified must be true")
        if not locator:
            errors.append("approved_locator is required")
        if not excerpt:
            errors.append("approved_exact_excerpt is required")
        if not context:
            errors.append("approved_context_before_after is required")
        if not re.fullmatch(r"[0-9a-f]{64}", excerpt_sha):
            errors.append(
                "approved_exact_excerpt_sha256 must be SHA-256"
            )
        elif text_sha256(excerpt) != excerpt_sha:
            errors.append("excerpt SHA-256 mismatch")
        if decision == "confirm_exact_source_text":
            suggested = str(
                expected.get("suggested_exact_excerpt", "")
            )
            if normalize_arabic(excerpt) != normalize_arabic(suggested):
                errors.append(
                    "exact confirmation differs; use correction decision"
                )
        if decision == "confirm_with_correction" and not notes:
            errors.append("correction notes are required")
    else:
        if item.get("source_verified") is not False:
            errors.append("rejected locator cannot be verified")
        if not notes:
            errors.append("rejection notes are required")
    return errors


def validate_human_decision(
    data: Mapping[str, object],
    *,
    docket: Mapping[str, object],
    policy: Mapping[str, object],
    require_final: bool,
) -> dict:
    errors: list[str] = []
    warnings: list[str] = []

    if data.get("schema_version") != DECISION_SCHEMA:
        errors.append("unexpected decision schema")
    if data.get("episode_id") != "episode-001-adam":
        errors.append("unexpected episode_id")
    if data.get("docket_id") != docket["docket_id"]:
        errors.append("docket_id mismatch")
    if data.get("docket_sha256") != canonical_sha256(docket):
        errors.append("docket_sha256 mismatch")
    if data.get("policy_id") != policy["policy_id"]:
        errors.append("policy_id mismatch")
    if data.get("policy_sha256") != canonical_sha256(policy):
        errors.append("policy_sha256 mismatch")
    if data.get("source_count") != EXPECTED_SOURCE_COUNT:
        errors.append("source_count must equal 22")

    decisions = data.get("decisions")
    if not isinstance(decisions, list):
        decisions = []
        errors.append("decisions must be an array")
    if len(decisions) != EXPECTED_SOURCE_COUNT:
        errors.append("decisions must contain exactly 22 items")

    expected_index = {
        item["source_candidate_id"]: item for item in docket["sources"]
    }
    seen = set()
    per_source = []
    for item in decisions:
        if not isinstance(item, Mapping):
            errors.append("decision item must be an object")
            continue
        source_id = str(item.get("source_candidate_id", ""))
        if source_id in seen:
            errors.append(f"duplicate source decision: {source_id}")
            continue
        seen.add(source_id)
        expected = expected_index.get(source_id)
        if expected is None:
            errors.append(f"unknown source decision: {source_id}")
            continue
        item_errors = _decision_errors(item, expected)
        per_source.append(
            {
                "source_candidate_id": source_id,
                "decision": item.get("decision", ""),
                "valid": not item_errors,
                "errors": item_errors,
            }
        )
        errors.extend(
            f"{source_id}: {message}" for message in item_errors
        )
    missing = sorted(set(expected_index) - seen)
    if missing:
        errors.append("missing source decisions: " + ", ".join(missing))

    decision_counts = dict(
        sorted(
            Counter(
                str(item.get("decision", ""))
                for item in decisions
                if isinstance(item, Mapping)
            ).items()
        )
    )
    verified_count = sum(
        item.get("source_verified") is True
        for item in decisions
        if isinstance(item, Mapping)
    )
    rejected_count = decision_counts.get("reject_locator", 0)
    human_complete = (
        len(per_source) == EXPECTED_SOURCE_COUNT
        and all(item["valid"] for item in per_source)
    )
    source_complete = (
        human_complete
        and verified_count == EXPECTED_SOURCE_COUNT
        and rejected_count == 0
    )

    fixed = {
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    for field, expected in fixed.items():
        if data.get(field) != expected:
            errors.append(f"{field} must remain {expected}")

    if require_final:
        if data.get("human_comparison_complete") is not True:
            errors.append("human_comparison_complete must be true")
        if data.get("human_approval") is not True:
            errors.append("human_approval must be true")
        if not str(data.get("approved_by", "")).strip():
            errors.append("approved_by is required")
        if not str(data.get("approved_at", "")).strip():
            errors.append("approved_at is required")
        if data.get("approval_phrase") != FINAL_APPROVAL_PHRASE:
            errors.append("approval phrase mismatch")
        if data.get("source_verification_complete") is not source_complete:
            errors.append("source_verification_complete mismatch")
    elif data.get("human_approval") is True:
        warnings.append(
            "draft claims human approval; final validation is required"
        )

    report = {
        "schema_version": VALIDATION_SCHEMA,
        "status": (
            "PASS_FINAL_HUMAN_SOURCE_REVIEW"
            if require_final and not errors
            else "PASS_DRAFT_SOURCE_REVIEW"
            if not require_final and not errors
            else "FAIL_SOURCE_REVIEW_VALIDATION"
        ),
        "episode_id": "episode-001-adam",
        "docket_id": docket["docket_id"],
        "input_sha256": canonical_sha256(data),
        "validation_mode": "FINAL" if require_final else "DRAFT",
        "source_count": len(decisions),
        "valid_source_decision_count": sum(
            item["valid"] for item in per_source
        ),
        "invalid_source_decision_count": sum(
            not item["valid"] for item in per_source
        ),
        "decision_counts": decision_counts,
        "source_verified_count": verified_count,
        "rejected_locator_count": rejected_count,
        "computed_human_comparison_complete": human_complete,
        "computed_source_verification_complete": source_complete,
        "errors": errors,
        "warnings": warnings,
        "per_source": per_source,
        "human_approval": bool(require_final and not errors),
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    return report


HTML_SHELL = r"""<!doctype html>
<html lang="ar" dir="rtl">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>SIRAJ — مراجعة مصادر حلقة آدم</title>
<style>
:root{color-scheme:dark;--bg:#0d1117;--p:#161b22;--b:#30363d;--t:#e6edf3;--m:#8b949e;--a:#58a6ff;--ok:#3fb950;--bad:#f85149}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--t);font-family:Tahoma,Arial,sans-serif}
header{position:sticky;top:0;z-index:5;background:#0d1117f2;border-bottom:1px solid var(--b);padding:12px}
h1{font-size:20px;margin:0 0 8px}.toolbar{display:flex;gap:7px;flex-wrap:wrap;align-items:center}
button,input,select,textarea{font:inherit}button{background:#21262d;color:var(--t);border:1px solid var(--b);border-radius:6px;padding:7px 10px;cursor:pointer}
button.primary{background:#1f6feb}button:disabled{opacity:.45}.layout{display:grid;grid-template-columns:290px 1fr}
aside{position:sticky;top:87px;max-height:calc(100vh - 87px);overflow:auto;border-left:1px solid var(--b);padding:8px}
.nav{width:100%;text-align:right;margin-bottom:5px}.nav.active{border-color:var(--a)}.nav.done{box-shadow:inset -4px 0 var(--ok)}.nav.bad{box-shadow:inset -4px 0 var(--bad)}
main{padding:16px;max-width:1200px;width:100%;margin:auto}.card{background:var(--p);border:1px solid var(--b);border-radius:9px;padding:14px;margin-bottom:12px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}label{display:block;font-weight:bold;margin:4px 0}
input[type=text],input[type=datetime-local],select,textarea{width:100%;background:var(--bg);color:var(--t);border:1px solid var(--b);border-radius:6px;padding:8px}
textarea{min-height:90px}.ref{white-space:pre-wrap;background:#090d12;border:1px solid var(--b);border-radius:6px;padding:9px;max-height:240px;overflow:auto;line-height:1.65}
.meta{color:var(--m);font-size:13px;display:flex;gap:12px;flex-wrap:wrap}.checks{display:flex;gap:16px;flex-wrap:wrap;padding:8px 0}
.err{color:#ff7b72;white-space:pre-wrap}.ok{color:var(--ok)}a{color:var(--a)}.small{color:var(--m);font-size:12px}
@media(max-width:850px){.layout{grid-template-columns:1fr}aside{position:static;max-height:none;border-left:0;border-bottom:1px solid var(--b)}.grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<header><h1>SIRAJ — مراجعة مصادر حلقة آدم</h1>
<div class="toolbar">
<button id="prev">السابق</button><button id="next">التالي</button>
<button id="copyLoc">نسخ الموضع المقترح</button><button id="copyText">نسخ النص المقترح</button>
<button id="draft">تصدير مسودة</button><button id="importBtn">استيراد JSON</button>
<input id="importFile" type="file" accept=".json" hidden>
<button id="check">فحص القرارات</button><button id="final" class="primary" disabled>تصدير الاعتماد النهائي</button>
<span id="progress" class="small"></span>
</div></header>
<div class="layout"><aside id="nav"></aside><main>
<div class="card"><div id="meta" class="meta"></div><h2 id="title"></h2><div id="links"></div></div>
<div class="card"><h3>المادة المرجعية</h3><div class="grid">
<div><label>مرساة البحث</label><div id="anchor" class="ref"></div></div>
<div><label>النص المستخرج آليًا</label><div id="extracted" class="ref"></div></div>
<div><label>النص المقترح</label><div id="suggested" class="ref"></div></div>
<div><label>الفروقات</label><div id="diff" class="ref"></div></div>
</div></div>
<div class="card"><h3>القرار البشري</h3><div class="grid">
<div><label>القرار</label><select id="decision">
<option value="">— اختر بعد المراجعة —</option>
<option value="confirm_exact_source_text">تأكيد النص والموضع كما هما</option>
<option value="confirm_with_correction">تأكيد مع تصحيح</option>
<option value="reject_locator">رفض الموضع أو النص</option>
<option value="defer_authentication">تأكيد النص وتأجيل التصحيح/الأصل</option>
</select></div>
<div><label>الموضع المعتمد</label><input id="locator" type="text"></div>
<div><label>النص الحرفي المعتمد</label><textarea id="excerpt"></textarea></div>
<div><label>السياق السابق واللاحق</label><textarea id="context"></textarea></div>
<div><label>اسم المراجع</label><input id="by" type="text"></div>
<div><label>وقت المراجعة</label><input id="at" type="datetime-local"></div>
<div style="grid-column:1/-1"><label>ملاحظات المراجع</label><textarea id="notes"></textarea></div>
</div><div class="checks">
<label><input id="compared" type="checkbox"> قارنت المصدر بنفسي</label>
<label><input id="verified" type="checkbox"> النص والموضع متحققان</label>
<label><input id="human" type="checkbox"> هذا قرار بشري نهائي</label>
</div><p class="small">تبقى المصادقة، تصنيف الأصل، وربط الحدث خارج هذه المرحلة.</p><div id="oneErr" class="err"></div></div>
<div class="card"><h3>الاعتماد المحدود</h3><div class="grid">
<div><label>اسم المعتمد</label><input id="approvedBy" type="text"></div>
<div><label>وقت الاعتماد</label><input id="approvedAt" type="datetime-local"></div>
<div style="grid-column:1/-1"><label>عبارة الاعتماد الحرفية</label><textarea id="phrase"></textarea></div>
</div><div id="allErr" class="err"></div><div id="allOk" class="ok"></div></div>
</main></div>
<script type="application/json" id="manifest">__MANIFEST__</script>
<script type="application/json" id="template">__TEMPLATE__</script>
<script type="application/json" id="policy">__POLICY__</script>
<script>
"use strict";
const M=JSON.parse(document.getElementById("manifest").textContent);
const T=JSON.parse(document.getElementById("template").textContent);
const P=JSON.parse(document.getElementById("policy").textContent);
const $=x=>document.getElementById(x),clone=x=>JSON.parse(JSON.stringify(x));
const key="siraj-source-review-"+M.docket_id;
let i=0;
function validState(x){return !!(x&&x.docket_id===T.docket_id&&Array.isArray(x.decisions)&&x.decisions.length===22)}
function showFatal(error){const box=$("allErr");if(box){box.textContent="تعذر تشغيل منضدة المراجعة: "+String(error&&error.message?error.message:error)}}
window.addEventListener("error",event=>showFatal(event.error||event.message));
function load(){try{const raw=localStorage.getItem(key);if(!raw)return clone(T);const x=JSON.parse(raw);if(validState(x))return x}catch(e){}return clone(T)}
let D=load();
function save(){localStorage.setItem(key,JSON.stringify(D))}
function s(){return M.sources[i]}function d(){return D.decisions[i]}
function norm(x){return String(x||"").normalize("NFKC").replace(/[\u0610-\u061a\u064b-\u065f\u0670\u06d6-\u06ed]/g,"").replace(/ـ/g,"").replace(/[أإآٱ]/g,"ا").replace(/ى/g,"ي").replace(/ؤ/g,"و").replace(/ئ/g,"ي").replace(/ة/g,"ه").replace(/[^\u0600-\u06ff0-9A-Za-z]+/g," ").trim().replace(/\s+/g," ")}
async function hash(x){let b=new TextEncoder().encode(x),h=await crypto.subtle.digest("SHA-256",b);return [...new Uint8Array(h)].map(v=>v.toString(16).padStart(2,"0")).join("")}
function sync(){let x=d();x.decision=$("decision").value;x.approved_locator=$("locator").value.trim();x.approved_exact_excerpt=$("excerpt").value.trim();x.approved_context_before_after=$("context").value.trim();x.human_compared_to_source=$("compared").checked;x.source_verified=$("verified").checked;x.human_decision=$("human").checked;x.verified_by=$("by").value.trim();x.verified_at=$("at").value.trim();x.reviewer_notes=$("notes").value.trim();x.authentication_verified=false;x.origin_classification_verified=false;x.approved_for_event_binding=false;D.approved_by=$("approvedBy").value.trim();D.approved_at=$("approvedAt").value.trim();D.approval_phrase=$("phrase").value;save()}
async function syncHash(){let x=d();x.approved_exact_excerpt_sha256=x.approved_exact_excerpt?await hash(x.approved_exact_excerpt):"";save()}
function errors(x,y){let e=[];if(!P.allowed_decisions.includes(x.decision))e.push("اختر قرارًا.");if(!x.human_compared_to_source)e.push("أكد المقارنة البشرية.");if(!x.human_decision)e.push("ثبت القرار البشري.");if(!x.verified_by)e.push("اسم المراجع مطلوب.");if(!x.verified_at)e.push("وقت المراجعة مطلوب.");if(["confirm_exact_source_text","confirm_with_correction","defer_authentication"].includes(x.decision)){if(!x.source_verified)e.push("ثبت تحقق النص والموضع.");if(!x.approved_locator)e.push("الموضع مطلوب.");if(!x.approved_exact_excerpt)e.push("النص الحرفي مطلوب.");if(!x.approved_context_before_after)e.push("السياق مطلوب.");if(x.decision==="confirm_exact_source_text"&&norm(x.approved_exact_excerpt)!==norm(y.suggested_exact_excerpt))e.push("النص مختلف؛ استخدم تأكيد مع تصحيح.");if(x.decision==="confirm_with_correction"&&!x.reviewer_notes)e.push("اشرح التصحيح.")}else if(x.decision==="reject_locator"){if(x.source_verified)e.push("لا يمكن رفض موضع متحقق.");if(!x.reviewer_notes)e.push("سبب الرفض مطلوب.")}return e}
function status(n){let x=D.decisions[n];if(!x.decision)return "";return errors(x,M.sources[n]).length?"bad":"done"}
function nav(){let n=$("nav");n.innerHTML="";M.sources.forEach((x,k)=>{let b=document.createElement("button");b.className="nav "+(k===i?"active ":"")+status(k);b.textContent=`${k+1}. ${x.source_candidate_id} — ${x.locator}`;b.onclick=async()=>{sync();await syncHash();i=k;render()};n.appendChild(b)})}
function fileHref(p){return "file:///"+encodeURI(("C:/SIRAJ/Reports/adam-remote-source-materialization-v1/"+p).replaceAll("\\","/"))}
function render(){let x=s(),v=d();$("title").textContent=`${x.source_candidate_id} — ${x.locator}`;$("meta").textContent=`${x.refined_readiness} | ${x.source_kind} | الأحداث: ${x.event_ids.join(", ")} | الدرجة: ${x.weighted_resolution_score}`;let links=[];if(x.source_url)links.push(`<a href="${x.source_url}" target="_blank">المصدر الخارجي</a>`);x.raw_archive_paths.forEach((p,k)=>links.push(`<a href="${fileHref(p)}" target="_blank">الأرشيف المحلي ${k+1}</a>`));$("links").innerHTML=links.join(" | ");$("anchor").textContent=x.research_anchor_text;$("extracted").textContent=x.machine_extracted_text;$("suggested").textContent=x.suggested_exact_excerpt;$("diff").textContent="المفقود: "+(x.missing_anchor_tokens.join("، ")||"لا شيء")+"\nالزائد: "+(x.extra_candidate_tokens.join("، ")||"لا شيء");$("decision").value=v.decision;$("locator").value=v.approved_locator;$("excerpt").value=v.approved_exact_excerpt;$("context").value=v.approved_context_before_after;$("compared").checked=v.human_compared_to_source;$("verified").checked=v.source_verified;$("human").checked=v.human_decision;$("by").value=v.verified_by;$("at").value=v.verified_at;$("notes").value=v.reviewer_notes;$("approvedBy").value=D.approved_by;$("approvedAt").value=D.approved_at;$("phrase").value=D.approval_phrase;$("oneErr").textContent=v.decision?errors(v,x).join("\n"):"";let done=D.decisions.filter((q,k)=>errors(q,M.sources[k]).length===0).length;$("progress").textContent=`المكتمل ${done}/22 — المصدر ${i+1}/22`;nav()}
function prep(finalMode){sync();D.schema_version="siraj-source-review-human-decision-v1";D.status=finalMode?"HUMAN_SOURCE_REVIEW_APPROVED":"HUMAN_SOURCE_REVIEW_DRAFT";let all=D.decisions.every((x,k)=>errors(x,M.sources[k]).length===0),verified=D.decisions.filter(x=>x.source_verified).length,rejected=D.decisions.filter(x=>x.decision==="reject_locator").length;D.human_comparison_complete=all;D.source_verification_complete=all&&verified===22&&rejected===0;D.human_approval=finalMode&&all&&D.approval_phrase===P.final_approval_phrase&&!!D.approved_by&&!!D.approved_at;D.full_episode_adjudication_complete=false;D.approved_evidence_package_complete=false;D.opens_evidence_gate=false;D.evidence_gate_status="WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE";D.automatic_evidence_approval="FORBIDDEN";D.live_provider_execution="BLOCKED";return all}
function download(name,obj){let b=new Blob([JSON.stringify(obj,null,2)+"\n"],{type:"application/json"}),u=URL.createObjectURL(b),a=document.createElement("a");a.href=u;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}
async function check(){sync();await syncHash();let all=prep(false),list=[];D.decisions.forEach((x,k)=>errors(x,M.sources[k]).forEach(m=>list.push(`${M.sources[k].source_candidate_id}: ${m}`)));$("allErr").textContent=list.join("\n");$("allOk").textContent=list.length?"":"جميع القرارات صالحة بنيويًا.";$("final").disabled=!(all&&D.approval_phrase===P.final_approval_phrase&&D.approved_by&&D.approved_at);render();return !$("final").disabled}
$("prev").onclick=async()=>{sync();await syncHash();i=(i+21)%22;render()};$("next").onclick=async()=>{sync();await syncHash();i=(i+1)%22;render()};$("copyLoc").onclick=()=>{$("locator").value=s().locator;sync();render()};$("copyText").onclick=async()=>{$("excerpt").value=s().suggested_exact_excerpt;sync();await syncHash();render()};$("draft").onclick=async()=>{sync();await syncHash();prep(false);download("adam-source-review-decisions-draft.json",D)};$("check").onclick=check;$("final").onclick=async()=>{if(!await check())return;prep(true);if(D.human_approval)download("adam-source-review-human-decision-v1.json",D)};$("importBtn").onclick=()=>$("importFile").click();$("importFile").onchange=async e=>{try{let x=JSON.parse(await e.target.files[0].text());if(x.docket_id!==T.docket_id||x.decisions.length!==22)throw Error("ملف غير مطابق.");D=x;save();i=0;render();await check()}catch(z){$("allErr").textContent=z.message}e.target.value=""};["decision","locator","excerpt","context","compared","verified","human","by","at","notes","approvedBy","approvedAt","phrase"].forEach(id=>{$(id).addEventListener("input",()=>{sync();nav()});$(id).addEventListener("change",()=>{sync();render()})});try{render()}catch(error){showFatal(error)}
</script></body></html>
"""


def render_workbench_html(
    *,
    manifest: Mapping[str, object],
    template: Mapping[str, object],
    policy: Mapping[str, object],
) -> str:
    def embed(value: object) -> str:
        return json.dumps(
            value, ensure_ascii=False, separators=(",", ":")
        ).replace("</", "<\\/")
    return (
        HTML_SHELL.replace("__MANIFEST__", embed(manifest))
        .replace("__TEMPLATE__", embed(template))
        .replace("__POLICY__", embed(policy))
    )


def validate_policy(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != POLICY_SCHEMA:
        raise SourceReviewWorkbenchError("Unexpected policy schema.")
    if tuple(data.get("allowed_decisions", ())) != ALLOWED_DECISIONS:
        raise SourceReviewWorkbenchError("Allowed decisions changed.")
    if data.get("final_approval_phrase") != FINAL_APPROVAL_PHRASE:
        raise SourceReviewWorkbenchError("Approval phrase changed.")
    if "defaulting or auto-selecting a human decision" not in data.get(
        "prohibitions", []
    ):
        raise SourceReviewWorkbenchError(
            "Automatic-decision prohibition missing."
        )
    _validate_guards(data)


def validate_manifest(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != MANIFEST_SCHEMA:
        raise SourceReviewWorkbenchError("Unexpected manifest schema.")
    if data.get("status") != STATUS:
        raise SourceReviewWorkbenchError("Unexpected manifest status.")
    sources = data.get("sources")
    if not isinstance(sources, list) or len(sources) != 22:
        raise SourceReviewWorkbenchError("Manifest must cover 22 sources.")
    if len({item["source_candidate_id"] for item in sources}) != 22:
        raise SourceReviewWorkbenchError("Duplicate source ids.")
    if data.get("human_decisions_recorded") != 0:
        raise SourceReviewWorkbenchError("Manifest cannot record decisions.")
    for item in sources:
        if item.get("human_decision") is not False:
            raise SourceReviewWorkbenchError("Human decision was prefilled.")
        if item.get("source_verified") is not False:
            raise SourceReviewWorkbenchError("Source was preverified.")
    _validate_guards(data)


def validate_decision_template(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != TEMPLATE_SCHEMA:
        raise SourceReviewWorkbenchError("Unexpected template schema.")
    if data.get("status") != "EDITABLE_DRAFT_NOT_APPROVED":
        raise SourceReviewWorkbenchError("Template cannot be approved.")
    if len(data.get("decisions", [])) != 22:
        raise SourceReviewWorkbenchError("Template must cover 22 sources.")
    for item in data["decisions"]:
        if item.get("decision"):
            raise SourceReviewWorkbenchError("Decision was preselected.")
        for field in (
            "human_compared_to_source",
            "source_verified",
            "authentication_verified",
            "origin_classification_verified",
            "approved_for_event_binding",
            "human_decision",
        ):
            if item.get(field) is not False:
                raise SourceReviewWorkbenchError(
                    f"Template field prefilled: {field}"
                )
    if data.get("approval_phrase"):
        raise SourceReviewWorkbenchError("Approval phrase was prefilled.")
    _validate_guards(data)


def _validate_guards(data: Mapping[str, object]) -> None:
    if data.get("human_approval") not in (None, False):
        raise SourceReviewWorkbenchError("Human approval cannot be prefilled.")
    if data.get("evidence_gate_status") != GATE:
        raise SourceReviewWorkbenchError("Gate must remain withheld.")
    if data.get("automatic_evidence_approval") != AUTO_APPROVAL:
        raise SourceReviewWorkbenchError(
            "Automatic approval must remain forbidden."
        )
    if data.get("live_provider_execution") != LIVE_EXECUTION:
        raise SourceReviewWorkbenchError(
            "Provider execution must remain blocked."
        )


def write_local_outputs(
    *,
    output_root: Path,
    manifest: Mapping[str, object],
    template: Mapping[str, object],
    policy: Mapping[str, object],
    json_schema: Mapping[str, object],
    html_text: str,
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "html": output_root / "source-review-workbench-v1.html",
        "manifest": output_root / "source-review-workbench-manifest-v1.json",
        "template": output_root / "source-review-human-decision-v1.template.json",
        "policy": output_root / "source-review-workbench-policy-v1.json",
        "schema": output_root / "source-review-human-decision-json-schema-v1.json",
        "register": output_root / "source-review-workbench-register.csv",
        "readme": output_root / "README.md",
    }
    outputs["html"].write_text(
        html_text, encoding="utf-8", newline="\n"
    )
    write_json(outputs["manifest"], manifest)
    write_json(outputs["template"], template)
    write_json(outputs["policy"], policy)
    write_json(outputs["schema"], json_schema)

    with outputs["register"].open(
        "w", encoding="utf-8-sig", newline=""
    ) as stream:
        fields = (
            "source_candidate_id",
            "locator",
            "source_kind",
            "refined_readiness",
            "event_ids",
            "suggested_exact_excerpt_sha256",
            "human_decision",
            "source_verified",
        )
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in manifest["sources"]:
            writer.writerow(
                {
                    "source_candidate_id": item["source_candidate_id"],
                    "locator": item["locator"],
                    "source_kind": item["source_kind"],
                    "refined_readiness": item["refined_readiness"],
                    "event_ids": ";".join(item["event_ids"]),
                    "suggested_exact_excerpt_sha256": item[
                        "suggested_exact_excerpt_sha256"
                    ],
                    "human_decision": False,
                    "source_verified": False,
                }
            )

    outputs["readme"].write_text(
        "# Adam Source Review Workbench v1\n\n"
        "Open `source-review-workbench-v1.html` in a modern browser. "
        "Review every source personally, save drafts when needed, and "
        "export the final JSON only after all twenty-two records pass. "
        "The final file still does not grade hadith, authenticate reports, "
        "classify source origin, approve event binding, open the evidence "
        "gate, or enable providers.\n\n"
        f"Required approval phrase:\n\n`{FINAL_APPROVAL_PHRASE}`\n",
        encoding="utf-8",
        newline="\n",
    )

    archive = output_root.with_suffix(".zip")
    with zipfile.ZipFile(
        archive, "w", zipfile.ZIP_DEFLATED
    ) as bundle:
        for path in sorted(output_root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(output_root).as_posix())
    outputs["archive"] = archive
    return outputs
