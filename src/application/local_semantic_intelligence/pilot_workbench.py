"""Offline RTL workbench for independent Pilot-12 human adjudication."""

from __future__ import annotations

from collections import Counter
from copy import deepcopy
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.application.operations_common import integrity_hash

from .orchestrator import atomic_write_json
from .pilot_evaluation import (
    ADJUDICATION_CATEGORIES,
    ERROR_TAXONOMY,
    PILOT_EVALUATION_SCHEMA_VERSION,
    PilotEvaluationError,
    evaluate_pilot_12,
    pilot_root,
)
from .pilot_view_models import (
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    build_presentation_view,
)


_IMMUTABLE_FIELDS = {
    "annotation_id",
    "audit_segment_id",
    "segment_id",
    "source_id",
    "locator",
    "book_id",
    "book_title",
    "original_text",
    "immutable_input_hash",
    "prior_diagnostic_reviewer_notes",
}
_EDITABLE_FIELDS = {
    "structural_type_gold",
    "gold_entities",
    "gold_events",
    "gold_relations",
    "gold_temporal_mentions",
    "gold_isnad",
    "gold_claims_attribution",
    "explicitly_absent",
    "category_review",
    "adjudication_status",
    "model_output_judgments",
    "baseline_output_judgments",
    "reviewer_notes",
    "expert_review_resolution",
}
_GOLD_FIELDS = {
    "entities": "gold_entities",
    "events": "gold_events",
    "relations": "gold_relations",
    "temporal_mentions": "gold_temporal_mentions",
    "isnad": "gold_isnad",
    "claims_attribution": "gold_claims_attribution",
}
_ALLOWED_STATUS = {
    "PENDING",
    "IN_PROGRESS",
    "COMPLETED",
    "NEEDS_EXPERT_REVIEW",
}
_MAX_REQUEST_BYTES = 4_000_000


class PilotAdjudicationError(PilotEvaluationError):
    """Human adjudication data violates an immutable or completion rule."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"FILE_NOT_FOUND:{path.name}")
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise PilotAdjudicationError(
            f"INVALID_JSON:{path.name}:{error.lineno}:{error.colno}"
        ) from error
    if not isinstance(value, dict):
        raise PilotAdjudicationError("JSON_ROOT_MUST_BE_OBJECT")
    return value


def _validate_span(span: dict[str, Any], text: str) -> None:
    try:
        start, end = int(span["start"]), int(span["end"])
    except (KeyError, TypeError, ValueError) as error:
        raise PilotAdjudicationError("INVALID_SPAN_OFFSETS") from error
    if start < 0 or end <= start or end > len(text):
        raise PilotAdjudicationError("SPAN_OUT_OF_RANGE")
    expected = str(
        span.get("text")
        or span.get("exact_surface")
        or text[start:end]
    )
    if expected != text[start:end]:
        raise PilotAdjudicationError("SPAN_TEXT_MISMATCH")


def _validate_spans(value: Any, text: str) -> None:
    if isinstance(value, list):
        for item in value:
            _validate_spans(item, text)
        return
    if not isinstance(value, dict):
        return
    if "start" in value or "end" in value:
        _validate_span(value, text)
    for key, item in value.items():
        if key in {
            "evidence",
            "span",
            "trigger",
            "exact_chain_range",
            "matn_range",
        } and isinstance(item, dict):
            _validate_span(item, text)
        else:
            _validate_spans(item, text)


def _judgments_valid(items: Any) -> bool:
    if not isinstance(items, list):
        return False
    return all(
        isinstance(item, dict)
        and isinstance(item.get("error_codes", []), list)
        and set(map(str, item.get("error_codes", []))).issubset(
            ERROR_TAXONOMY
        )
        for item in items
    )


class PilotAdjudicationStore:
    """Atomic local store with immutable source identity and strict completion."""

    def __init__(self, semantic_root: str | Path):
        self.semantic_root = Path(semantic_root).resolve()
        self.root = pilot_root(self.semantic_root)
        self.path = self.root / "pilot-12-human-adjudication.json"
        self.backup_root = self.root / "adjudication-backups"
        self.undo_root = self.root / "adjudication-undo"
        self.undo_marker = self.root / "adjudication-undo-state.json"

    def load(self) -> dict[str, Any]:
        payload = _read_json(self.path)
        if payload.get("schema_version") != PILOT_EVALUATION_SCHEMA_VERSION:
            raise PilotAdjudicationError(
                "UNSUPPORTED_ADJUDICATION_SCHEMA"
            )
        for annotation in payload.get("annotations", []):
            self._validate_annotation(annotation)
        return payload

    def _validate_annotation(self, annotation: dict[str, Any]) -> None:
        missing = _IMMUTABLE_FIELDS - set(annotation)
        if missing:
            raise PilotAdjudicationError(
                "MISSING_IMMUTABLE_FIELDS:" + ",".join(sorted(missing))
            )
        status = str(annotation.get("adjudication_status", ""))
        if status not in _ALLOWED_STATUS:
            raise PilotAdjudicationError("INVALID_ADJUDICATION_STATUS")
        if not isinstance(annotation.get("reviewer_notes"), str):
            raise PilotAdjudicationError("REVIEWER_NOTES_MUST_BE_TEXT")
        text = str(annotation["original_text"])
        for field in _GOLD_FIELDS.values():
            if not isinstance(annotation.get(field), list):
                raise PilotAdjudicationError(
                    f"GOLD_FIELD_MUST_BE_LIST:{field}"
                )
            _validate_spans(annotation[field], text)
        absent = annotation.get("explicitly_absent")
        review = annotation.get("category_review")
        if not isinstance(absent, dict) or not isinstance(review, dict):
            raise PilotAdjudicationError(
                "CATEGORY_DECISIONS_MUST_BE_OBJECTS"
            )
        if set(review) != set(ADJUDICATION_CATEGORIES):
            raise PilotAdjudicationError(
                "CATEGORY_REVIEW_KEYS_INCOMPLETE"
            )
        if set(absent) != set(ADJUDICATION_CATEGORIES) - {"structure"}:
            raise PilotAdjudicationError(
                "EXPLICITLY_ABSENT_KEYS_INCOMPLETE"
            )
        if not _judgments_valid(
            annotation.get("model_output_judgments")
        ) or not _judgments_valid(
            annotation.get("baseline_output_judgments")
        ):
            raise PilotAdjudicationError("INVALID_OUTPUT_JUDGMENTS")
        if status == "COMPLETED":
            self._validate_completion(annotation)
        if status == "NEEDS_EXPERT_REVIEW":
            resolution = annotation.get("expert_review_resolution", {})
            if resolution.get("status") not in {
                "UNRESOLVED",
                "RESOLVED_INCLUDED",
                "EXCLUDED_WITH_REASON",
            }:
                raise PilotAdjudicationError(
                    "INVALID_EXPERT_REVIEW_RESOLUTION"
                )

    @staticmethod
    def _validate_completion(annotation: dict[str, Any]) -> None:
        review = annotation["category_review"]
        if any(
            review.get(category) != "REVIEWED"
            for category in ADJUDICATION_CATEGORIES
        ):
            raise PilotAdjudicationError(
                "COMPLETION_REQUIRES_ALL_CATEGORIES_REVIEWED"
            )
        if not str(annotation.get("structural_type_gold", "")).strip():
            raise PilotAdjudicationError(
                "COMPLETION_REQUIRES_STRUCTURAL_TYPE"
            )
        for category, field in _GOLD_FIELDS.items():
            if (
                not annotation[field]
                and not annotation["explicitly_absent"].get(category)
            ):
                raise PilotAdjudicationError(
                    f"EMPTY_CATEGORY_NOT_EXPLICITLY_ABSENT:{category}"
                )

    def _backup_path(self) -> Path:
        self.backup_root.mkdir(parents=True, exist_ok=True)
        pattern = re.compile(
            r"pilot-12-human-adjudication\.backup-(\d{6})\.json$"
        )
        versions = [
            int(match.group(1))
            for item in self.backup_root.glob("*.json")
            if (match := pattern.match(item.name))
        ]
        return self.backup_root / (
            "pilot-12-human-adjudication.backup-"
            f"{max(versions, default=0) + 1:06d}.json"
        )

    def _save(self, payload: dict[str, Any]) -> dict[str, Any]:
        for annotation in payload.get("annotations", []):
            self._validate_annotation(annotation)
        backup = self._backup_path()
        atomic_write_json(backup, self.load())
        atomic_write_json(self.path, payload)
        atomic_write_json(
            self.undo_marker,
            {"last_applied_backup": "", "current_hash": integrity_hash(payload)},
        )
        return {
            "status": "SAVED",
            "backup_file": backup.name,
            "adjudication_hash": integrity_hash(payload),
        }

    @staticmethod
    def _annotation(
        payload: dict[str, Any],
        annotation_id: str,
    ) -> dict[str, Any]:
        for annotation in payload.get("annotations", []):
            if annotation["annotation_id"] == annotation_id:
                return annotation
        raise KeyError("ANNOTATION_NOT_FOUND")

    def update(
        self,
        annotation_id: str,
        patch: dict[str, Any],
    ) -> dict[str, Any]:
        invalid = set(patch) - _EDITABLE_FIELDS
        if invalid or set(patch) & _IMMUTABLE_FIELDS:
            raise PilotAdjudicationError("IMMUTABLE_FIELD_UPDATE_DENIED")
        payload = self.load()
        annotation = self._annotation(payload, annotation_id)
        candidate = {**annotation, **deepcopy(patch)}
        self._validate_annotation(candidate)
        annotation.clear()
        annotation.update(candidate)
        payload["status"] = "IN_PROGRESS"
        return self._save(payload)

    def undo_last(self) -> dict[str, Any]:
        backups = sorted(self.backup_root.glob("*.json"))
        if not backups:
            raise PilotAdjudicationError("NO_ADJUDICATION_EDIT_TO_UNDO")
        latest = backups[-1]
        marker = (
            _read_json(self.undo_marker)
            if self.undo_marker.exists()
            else {}
        )
        if marker.get("last_applied_backup") == latest.name:
            raise PilotAdjudicationError("LAST_EDIT_ALREADY_UNDONE")
        previous = _read_json(latest)
        for annotation in previous.get("annotations", []):
            self._validate_annotation(annotation)
        self.undo_root.mkdir(parents=True, exist_ok=True)
        atomic_write_json(
            self.undo_root / f"before-{latest.stem}.json",
            self.load(),
        )
        atomic_write_json(self.path, previous)
        atomic_write_json(
            self.undo_marker,
            {
                "last_applied_backup": latest.name,
                "restored_hash": integrity_hash(previous),
            },
        )
        return {
            "status": "UNDONE",
            "restored_backup": latest.name,
        }

    def progress(self) -> dict[str, Any]:
        payload = self.load()
        annotations = list(payload.get("annotations", []))
        statuses = Counter(
            item["adjudication_status"] for item in annotations
        )
        category_progress = {
            category: sum(
                item["category_review"].get(category) == "REVIEWED"
                for item in annotations
            )
            for category in ADJUDICATION_CATEGORIES
        }
        by_book: dict[str, dict[str, int]] = {}
        for item in annotations:
            key = item["book_title"]
            value = by_book.setdefault(
                key,
                {"total": 0, "completed": 0, "needs_expert_review": 0},
            )
            value["total"] += 1
            value["completed"] += (
                item["adjudication_status"] == "COMPLETED"
            )
            value["needs_expert_review"] += (
                item["adjudication_status"]
                == "NEEDS_EXPERT_REVIEW"
            )
        eligible = all(
            item["adjudication_status"] == "COMPLETED"
            or (
                item["adjudication_status"] == "NEEDS_EXPERT_REVIEW"
                and item["expert_review_resolution"]["status"]
                in {"RESOLVED_INCLUDED", "EXCLUDED_WITH_REASON"}
                and item["expert_review_resolution"]["reason"].strip()
            )
            for item in annotations
        )
        return {
            "total": len(annotations),
            "pending": statuses["PENDING"],
            "in_progress": statuses["IN_PROGRESS"],
            "completed": statuses["COMPLETED"],
            "needs_expert_review": statuses["NEEDS_EXPERT_REVIEW"],
            "completion_percentage": round(
                statuses["COMPLETED"] / len(annotations) * 100,
                2,
            )
            if annotations
            else 0.0,
            "category_reviewed": category_progress,
            "by_book": dict(sorted(by_book.items())),
            "evaluation_eligible": bool(annotations) and eligible,
        }

    def state(self) -> dict[str, Any]:
        payload = self.load()
        comparisons = {}
        for item in payload.get("annotations", []):
            root = self.root / "segments" / item["audit_segment_id"]
            comparisons[item["audit_segment_id"]] = {
                "baseline": _read_json(
                    root / "baseline-rule-extraction.json"
                )
                if (root / "baseline-rule-extraction.json").exists()
                else {},
                "model_raw": _read_json(
                    root / "parsed-semantic-v2.json"
                )
                if (root / "parsed-semantic-v2.json").exists()
                else {},
                "reconciliation": _read_json(
                    root / "reconciliation-output.json"
                )
                if (root / "reconciliation-output.json").exists()
                else {},
                "validation": _read_json(
                    root / "deterministic-validation.json"
                )
                if (root / "deterministic-validation.json").exists()
                else {},
                "rejected_elements": _read_json(
                    root / "rejected-elements.json"
                )
                if (root / "rejected-elements.json").exists()
                else {"items": []},
                "warnings": _read_json(root / "warnings.json")
                if (root / "warnings.json").exists()
                else {"items": []},
            }
        presentation = {
            item["audit_segment_id"]: build_presentation_view(
                item,
                comparisons[item["audit_segment_id"]],
            )
            for item in payload.get("annotations", [])
        }
        return {
            **payload,
            "progress": self.progress(),
            "comparisons": comparisons,
            "presentation": presentation,
            "presentation_contract": {
                "default_tab": "reconciled",
                "categories": [
                    {"key": key, "label": CATEGORY_LABELS[key]}
                    for key in CATEGORY_ORDER
                ],
            },
            "error_taxonomy": list(ERROR_TAXONOMY),
            "ai_calls_allowed": False,
            "external_network_allowed": False,
        }

    def search(self, query: str) -> list[dict[str, Any]]:
        needle = query.casefold().strip()
        return [
            {
                "annotation_id": item["annotation_id"],
                "audit_segment_id": item["audit_segment_id"],
                "book_title": item["book_title"],
                "segment_id": item["segment_id"],
                "status": item["adjudication_status"],
            }
            for item in self.load().get("annotations", [])
            if not needle
            or needle
            in "\n".join(
                (
                    item["book_title"],
                    item["locator"],
                    item["original_text"],
                    item["reviewer_notes"],
                )
            ).casefold()
        ]

    def evaluate(self) -> dict[str, Any]:
        if not self.progress()["evaluation_eligible"]:
            raise PilotAdjudicationError(
                "PILOT_EVALUATION_REQUIRES_COMPLETED_ADJUDICATION"
            )
        return evaluate_pilot_12(self.semantic_root)


def _legacy_ui_html() -> str:
    return r"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>Siraj Pilot-12 Adjudication</title>
<style>
body{font-family:Segoe UI,Tahoma,sans-serif;margin:0;background:#f1eee7;color:#17232b}
header{position:sticky;top:0;background:#123447;color:#fff;padding:10px 18px;z-index:5}
.layout{display:grid;grid-template-columns:260px 1fr;gap:12px;padding:12px}
.panel{background:#fff;border-radius:8px;padding:12px;box-shadow:0 1px 5px #0002}
.compare{display:grid;grid-template-columns:repeat(3,1fr);gap:8px}.source{white-space:pre-wrap;line-height:2;border-right:4px solid #b88b3d;background:#fffaf0;padding:12px}
textarea{width:100%;min-height:120px;direction:ltr}button,input,select{font:inherit;padding:6px;margin:3px}
pre{white-space:pre-wrap;max-height:300px;overflow:auto;font-size:12px}.ok{color:#176b38}.warn{color:#9a4d00}
</style></head><body>
<header><b>Siraj Pilot-12</b> <span id="progress"></span>
<button onclick="save()">حفظ Ctrl+S</button><button onclick="undo()">تراجع Ctrl+Z</button>
<button onclick="prev()">السابق ←</button><button onclick="next()">التالي →</button></header>
<div class="layout"><aside class="panel">
<input id="search" placeholder="بحث أو رقم مقطع"><button onclick="find()">بحث</button><div id="results"></div>
<hr><div id="meta"></div><label>الحالة</label><select id="status">
<option>PENDING</option><option>IN_PROGRESS</option><option>COMPLETED</option><option>NEEDS_EXPERT_REVIEW</option></select>
<label>النوع البنيوي</label><input id="structure"><label>ملاحظات</label><textarea id="notes"></textarea>
</aside><main><section class="panel source" id="source"></section>
<section class="panel compare"><div><h3>Baseline</h3><pre id="baseline"></pre></div>
<div><h3>Raw model</h3><pre id="model"></pre></div><div><h3>Validation/Reconciliation</h3><pre id="reconciled"></pre></div></section>
<section class="panel"><h3>Gold adjudication</h3><div id="categories"></div>
<h4>Model-output judgments</h4><textarea id="modelJudgments"></textarea>
<h4>Baseline-output judgments</h4><textarea id="baselineJudgments"></textarea>
</section></main></div>
<script>
let state,index=0;const cats=['entities','events','relations','temporal_mentions','isnad','claims_attribution'];
const field={entities:'gold_entities',events:'gold_events',relations:'gold_relations',temporal_mentions:'gold_temporal_mentions',isnad:'gold_isnad',claims_attribution:'gold_claims_attribution'};
const esc=x=>String(x).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function api(p,o={}){let r=await fetch(p,{headers:{'Content-Type':'application/json'},...o});let j=await r.json();if(!r.ok)throw Error(j.error);return j}
function a(){return state.annotations[index]}function comp(){return state.comparisons[a().audit_segment_id]||{}}
async function load(){state=await api('/api/state');render()}
function render(){let x=a(),c=comp();document.getElementById('progress').textContent=`${state.progress.completed}/${state.progress.total}`;
document.getElementById('meta').innerHTML=`<b>${esc(x.book_title)}</b><br>${esc(x.audit_segment_id)}<br><small>${esc(x.locator)}</small><br><b>Reviewer notes القديمة:</b><br>${esc(x.prior_diagnostic_reviewer_notes)}`;
document.getElementById('source').textContent=x.original_text;document.getElementById('status').value=x.adjudication_status;document.getElementById('structure').value=x.structural_type_gold;document.getElementById('notes').value=x.reviewer_notes;
document.getElementById('baseline').textContent=JSON.stringify(c.baseline||{},null,2);document.getElementById('model').textContent=JSON.stringify(c.model_raw||{},null,2);document.getElementById('reconciled').textContent=JSON.stringify({validation:c.validation,reconciliation:c.reconciliation},null,2);
document.getElementById('modelJudgments').value=JSON.stringify(x.model_output_judgments||[],null,2);document.getElementById('baselineJudgments').value=JSON.stringify(x.baseline_output_judgments||[],null,2);
document.getElementById('categories').innerHTML=cats.map(k=>`<h4>${k} <label><input id="review-${k}" type=checkbox ${x.category_review[k]==='REVIEWED'?'checked':''}> تمت المراجعة</label> <label><input id="absent-${k}" type=checkbox ${x.explicitly_absent[k]?'checked':''}> لا يوجد</label> <button onclick="copyFrom('model','${k}')">اقبل من النموذج</button> <button onclick="copyFrom('baseline','${k}')">اقبل من baseline</button></h4><textarea id="${k}">${esc(JSON.stringify(x[field[k]],null,2))}</textarea>`).join('')}
function next(){index=(index+1)%state.annotations.length;render()}function prev(){index=(index+state.annotations.length-1)%state.annotations.length;render()}
function candidate(source,k){let c=comp(),v=source==='baseline'?(c.baseline||{}):(c.model_raw||{});let aliases={entities:['entities','entity_mentions'],events:['events'],relations:['relations'],temporal_mentions:['temporal_mentions','temporals'],isnad:['isnad','isnad_chains'],claims_attribution:['claims_attribution','claims']};for(const key of aliases[k]){if(Array.isArray(v[key]))return v[key]}for(const group of ['mentions','events_relations','claims_attribution']){let g=v[group];if(g)for(const key of aliases[k])if(Array.isArray(g[key]))return g[key]}return []}
function copyFrom(source,k){document.getElementById(k).value=JSON.stringify(candidate(source,k),null,2);document.getElementById('review-'+k).checked=true;document.getElementById('absent-'+k).checked=false}
async function save(){let x=a(),patch={structural_type_gold:document.getElementById('structure').value,reviewer_notes:document.getElementById('notes').value,adjudication_status:document.getElementById('status').value,model_output_judgments:JSON.parse(document.getElementById('modelJudgments').value||'[]'),baseline_output_judgments:JSON.parse(document.getElementById('baselineJudgments').value||'[]'),category_review:{...x.category_review,structure:document.getElementById('structure').value?'REVIEWED':x.category_review.structure},explicitly_absent:{...x.explicitly_absent}};
for(const k of cats){patch[field[k]]=JSON.parse(document.getElementById(k).value);patch.category_review[k]=document.getElementById('review-'+k).checked?'REVIEWED':'PENDING';patch.explicitly_absent[k]=document.getElementById('absent-'+k).checked}
await api('/api/annotation/'+x.annotation_id,{method:'POST',body:JSON.stringify(patch)});await load()}
async function undo(){await api('/api/undo',{method:'POST',body:'{}'});await load()}
async function find(){let q=document.getElementById('search').value,r=await api('/api/search?q='+encodeURIComponent(q));document.getElementById('results').innerHTML=r.map(v=>`<button onclick="jump('${v.annotation_id}')">${esc(v.book_title)} / ${v.segment_id}</button>`).join('')}
function jump(id){index=state.annotations.findIndex(x=>x.annotation_id===id);if(index>=0)render()}
document.addEventListener('keydown',e=>{if(e.ctrlKey&&e.key==='s'){e.preventDefault();save()}if(e.ctrlKey&&e.key==='z'){e.preventDefault();undo()}if(e.altKey&&e.key==='ArrowLeft')next();if(e.altKey&&e.key==='ArrowRight')prev()});load()
</script></body></html>"""


def _quick_ui_html() -> str:
    """Compact one-screen review UI with no technical payloads."""

    return r"""<!doctype html><html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>Siraj Pilot-12 Quick Review</title><style>
:root{--ink:#17232b;--paper:#fff;--ground:#f4f1ea;--accent:#123447;--line:#d9d3c8;--good:#166534;--warn:#9a5b00;--bad:#9b1c1c}*{box-sizing:border-box}body{margin:0;background:var(--ground);color:var(--ink);font:18px/1.8 "Segoe UI",Tahoma,Arial,sans-serif;overflow-x:hidden}header{position:sticky;top:0;z-index:4;background:var(--accent);color:#fff;padding:10px 18px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}header b{margin-left:auto}.layout{display:grid;grid-template-columns:250px minmax(0,1fr);gap:14px;max-width:1350px;margin:auto;padding:14px}.panel,.card{background:var(--paper);border:1px solid var(--line);border-radius:11px;padding:14px;box-shadow:0 1px 4px #0001}.sticky{position:sticky;top:70px;height:max-content}.source{white-space:pre-wrap;background:#fffdf7;border-right:5px solid #b88b3d;font-size:20px;line-height:2.1}.group{border:1px solid var(--line);border-radius:9px;margin:10px 0;padding:10px}.group h3{margin:0 0 6px}.cards{display:grid;gap:8px}.card{box-shadow:none;border-right:5px solid #64748b}.card.good{border-right-color:var(--good)}.card.warn{border-right-color:var(--warn)}.card.bad{border-right-color:var(--bad)}.evidence{background:#fff7df;border-radius:6px;padding:5px 9px;margin-top:6px}.muted{color:#5b6470;font-size:14px}.judgments{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.judgment{font-size:20px;padding:12px;background:#e9e3d8}.judgment.selected{outline:3px solid var(--accent)}.errors{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:4px}.errors label{font-weight:400}.actions{display:flex;gap:7px;flex-wrap:wrap;margin-top:10px}button,input,textarea{font:inherit}button{border:0;border-radius:7px;padding:8px 12px;cursor:pointer;background:#e6e0d5;color:var(--ink)}button.primary{background:var(--accent);color:#fff}textarea,input{width:100%;padding:8px;border:1px solid #b9b3aa;border-radius:6px;background:#fff}textarea{min-height:100px}@media(max-width:800px){.layout{grid-template-columns:1fr}.sticky{position:static}.judgments{grid-template-columns:repeat(2,1fr)}.errors{grid-template-columns:1fr}}
</style></head><body><header><b>Quick Review — Pilot-12</b><span id="progress"></span><button onclick="saveNext()">احفظ وانتقل للتالي</button><button onclick="prev()">السابق</button><button onclick="next()">التالي</button></header><div class="layout"><aside class="panel sticky"><label>بحث</label><input id="search" placeholder="عنوان الكتاب"><button onclick="find()">بحث</button><div id="results"></div><hr><div id="book"></div><p class="muted">هذا الوضع مستقل عن التحكيم التفصيلي، ولا يغيّر حالته.</p><button onclick="alert('للتحكيم التفصيلي شغّل الواجهة مع --mode detailed')">فتح التحكيم التفصيلي</button></aside><main><section class="panel source"><h2>النص الأصلي</h2><div id="source"></div></section><section class="panel"><h2>النتيجة بعد التحقق والمصالحة</h2><div id="groups"></div></section><section class="panel"><h2>الحكم السريع</h2><div class="judgments" id="judgments"></div><h3>تصنيف الأخطاء — اختياري</h3><div class="errors" id="errors"></div><label>اكتب باختصار أهم الأخطاء أو العناصر المفقودة</label><textarea id="notes"></textarea><div class="actions"><button class="primary" onclick="saveNext()">احفظ وانتقل للتالي</button><button onclick="saveOnly()">حفظ</button></div></section></main></div><script>
let state,index=0;const judgments=[['GOOD','النتيجة جيدة'],['PARTIAL','صحيحة جزئياً'],['BAD','النتيجة سيئة'],['NEEDS_CONTEXT','يحتاج سياقاً إضافياً']];const errors=[['MISSING_IMPORTANT_ELEMENTS','عناصر مهمة مفقودة'],['ELEMENT_NOT_IN_TEXT','عناصر غير موجودة في النص'],['WRONG_BOUNDARY','حدود اسم أو عبارة خاطئة'],['WRONG_ENTITY_TYPE','نوع الكيان خاطئ'],['WRONG_OR_MISSING_EVENT','حدث خاطئ أو مفقود'],['WRONG_OR_MISSING_RELATION','علاقة خاطئة أو مفقودة'],['WRONG_PARTICIPANT_OR_PLACE_ROLE','أدوار المشاركين أو الأماكن خاطئة'],['WRONG_OR_MISSING_TIME','زمن خاطئ أو مفقود'],['WRONG_ISNAD','سند خاطئ'],['HALLUCINATION_OR_EXTERNAL_KNOWLEDGE','هلوسة أو معرفة خارج النص'],['TEXT_NOT_UNDERSTOOD','النص لم يُفهم'],['OTHER','مشكلة أخرى']];const esc=x=>String(x??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));async function api(path,options={}){const response=await fetch(path,{headers:{'Content-Type':'application/json'},...options});const body=await response.json();if(!response.ok)throw Error(body.error||'REQUEST_FAILED');return body}function record(){return state.records[index]}function view(){return state.presentation[record().audit_segment_id].tabs.reconciled.categories}function currentJudgment(){return record().judgment}async function load(){state=await api('/api/state');render()}function render(){const r=record();document.getElementById('progress').textContent=`${state.progress.completed}/${state.progress.total} مكتمل`;document.getElementById('book').innerHTML=`<b>${esc(r.book_title)}</b><br><span class="muted">Quick Review مستقل</span>`;document.getElementById('source').textContent=r.original_text;document.getElementById('notes').value=r.notes||'';renderGroups();renderJudgments();renderErrors()}function renderGroups(){const wanted=['entities','events','relations','temporal_mentions','isnad','claims_attribution'];const groups=view().filter(g=>wanted.includes(g.key));document.getElementById('groups').innerHTML=groups.map(g=>`<section class="group"><h3>${esc(g.label)}</h3>${g.items.length?`<div class="cards">${g.items.map(card=>quickCard(g.key,g)).join('')}</div>`:`<div class="muted">لا توجد عناصر مستخرجة في هذه الفئة</div>`}</section>`).join('')}function quickCard(key,g){return g.items.map((item,i)=>{let title='';if(item.kind==='entity')title=`<b>${esc(item.surface)}</b><div class="muted">النوع: ${esc((item.types||[]).join('، ')||'غير محدد')} — الدور: ${esc((item.roles||[]).join('، ')||'غير محدد')}</div>`;else if(item.kind==='event')title=`<b>${esc(item.event_type)}</b>${list('المشاركون',item.participants,x=>x.name+' — '+x.role)}${list('الأماكن',item.places,x=>x.name+' — '+x.role)}`;else if(item.kind==='relation')title=`<b>${esc(item.sentence)}</b><div class="muted">${esc(item.explicitness)}</div>`;else if(item.kind==='temporal')title=`<b>${esc(item.expression)}</b><div class="muted">${esc(item.precision)}</div>`;else if(item.kind==='isnad')title=`<b>${esc((item.narrators||[]).join(' ← ')||'سند غير مكتمل')}</b>`;else title=`<b>${esc(item.proposition)}</b><div class="muted">${esc(item.modality||item.quote_type||'')}</div>`;return `<article class="card ${item.status.code==='ACCEPTED_HIGH_CONFIDENCE'?'good':item.status.code==='REJECTED_UNSUPPORTED'?'bad':'warn'}">${title}${item.evidence?`<div class="evidence">الدليل: «${esc(item.evidence)}»</div>`:''}<div class="muted">${esc(item.status.label)}</div></article>`}).join('')}function list(title,items,format){return items&&items.length?`<div class="muted"><b>${title}:</b> ${items.map(x=>esc(format(x))).join('، ')}</div>`:''}function renderJudgments(){document.getElementById('judgments').innerHTML=judgments.map(([code,label],i)=>`<button class="judgment ${currentJudgment()===code?'selected':''}" onclick="choose('${code}')">${i+1} — ${label}</button>`).join('')}function renderErrors(){const selected=record().error_categories||[];document.getElementById('errors').innerHTML=errors.map(([code,label])=>`<label><input type="checkbox" value="${code}" ${selected.includes(code)?'checked':''}> ${label}</label>`).join('')}function choose(code){record().judgment=code;renderJudgments()}function selectedErrors(){return Array.from(document.querySelectorAll('#errors input:checked')).map(x=>x.value)}async function saveOnly(){if(!record().judgment){alert('اختر حكماً أولاً');return}await api('/api/record/'+record().annotation_id,{method:'POST',body:JSON.stringify({judgment:record().judgment,error_categories:selectedErrors(),notes:document.getElementById('notes').value})});await load()}async function saveNext(){await saveOnly();if(index<state.records.length-1){index++;render()}}function next(){index=(index+1)%state.records.length;render()}function prev(){index=(index+state.records.length-1)%state.records.length;render()}async function find(){const results=await api('/api/search?q='+encodeURIComponent(document.getElementById('search').value));document.getElementById('results').innerHTML=results.map(x=>`<button onclick="jump('${x.annotation_id}')">${esc(x.book_title)}</button>`).join('')||'<span class="muted">لا توجد نتائج</span>'}function jump(id){const found=state.records.findIndex(x=>x.annotation_id===id);if(found>=0){index=found;render()}}document.addEventListener('keydown',e=>{if(e.key>='1'&&e.key<='4')choose(judgments[Number(e.key)-1][0]);if(e.ctrlKey&&e.key==='Enter'){e.preventDefault();saveNext()}if(e.key==='ArrowLeft')next();if(e.key==='ArrowRight')prev()});load();</script></body></html>"""


def _ui_html(mode: str = "detailed") -> str:
    if mode == "quick":
        return _quick_ui_html()
    return r"""<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8">
<title>Siraj Pilot-12 Adjudication</title>
<style>
:root{--ink:#17232b;--paper:#fff;--ground:#f4f1ea;--accent:#123447;--line:#d9d3c8;--good:#166534;--warn:#9a5b00;--bad:#9b1c1c;--muted:#5b6470}*{box-sizing:border-box}body{font-family:"Segoe UI",Tahoma,Arial,sans-serif;margin:0;background:var(--ground);color:var(--ink);font-size:17px;line-height:1.75;overflow-x:hidden}header{position:sticky;top:0;z-index:10;background:var(--accent);color:#fff;padding:10px 18px;display:flex;gap:8px;align-items:center;flex-wrap:wrap}header b{margin-left:auto}.layout{display:grid;grid-template-columns:minmax(235px,290px) minmax(0,1fr);gap:14px;padding:14px;max-width:1540px;margin:auto}.panel,.card{background:var(--paper);border:1px solid var(--line);border-radius:11px;padding:14px;box-shadow:0 1px 4px #00000012}.sticky{position:sticky;top:66px;height:max-content}.source{white-space:pre-wrap;line-height:2.1;font-size:19px;border-right:5px solid #b88b3d;background:#fffdf7}.metadata{color:var(--muted);font-size:14px}.tabs,.actions{display:flex;gap:7px;flex-wrap:wrap;margin:12px 0}.tab{background:#e9e3d8;color:var(--ink);border:1px solid var(--line)}.tab.active,.primary{background:var(--accent);color:#fff}.sections,.cards{display:grid;gap:10px}.section{background:#fff;border:1px solid var(--line);border-radius:10px}.section summary{padding:11px 14px;font-weight:700;cursor:pointer}.section-body{padding:0 14px 14px}.empty{color:var(--muted);padding:8px 0}.card{box-shadow:none;border-right:5px solid #64748b}.status-ACCEPTED_HIGH_CONFIDENCE{border-right-color:var(--good)}.status-ACCEPTED_WITH_WARNING,.status-HUMAN_REVIEW_REQUIRED{border-right-color:var(--warn)}.status-REJECTED_UNSUPPORTED{border-right-color:var(--bad)}.status{font-weight:700}.status-ACCEPTED_HIGH_CONFIDENCE .status{color:var(--good)}.status-ACCEPTED_WITH_WARNING .status,.status-HUMAN_REVIEW_REQUIRED .status{color:var(--warn)}.status-REJECTED_UNSUPPORTED .status{color:var(--bad)}.evidence{background:#fff7df;border-radius:6px;padding:7px 10px;margin:8px 0}.facts{margin:6px 0;padding:0 18px}.technical{margin-top:10px;color:var(--muted);font-size:14px}.technical summary{cursor:pointer}.technical pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:320px;overflow:auto;direction:ltr;text-align:left;background:#f6f7f8;padding:10px}label{display:block;font-weight:600;margin-top:7px}textarea,input,select,button{font:inherit}textarea,input,select{width:100%;padding:7px;border:1px solid #b9b3aa;border-radius:6px;background:#fff}textarea{min-height:92px;direction:rtl}button{cursor:pointer;border:0;border-radius:6px;padding:7px 11px;background:#e6e0d5;color:var(--ink)}button.danger{background:#f9e1e1;color:#7b1515}.results button{display:block;width:100%;text-align:right;margin:5px 0}.hidden{display:none}dialog{border:1px solid var(--line);border-radius:12px;width:min(760px,94vw);max-height:90vh;overflow:auto;padding:18px}dialog::backdrop{background:#0006}.form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px}.full{grid-column:1/-1}@media(max-width:850px){.layout{grid-template-columns:1fr}.sticky{position:static}.form-grid{grid-template-columns:1fr}.source{font-size:17px}}
</style></head><body>
<header><b>Siraj Pilot-12 — التحكيم الدلالي المحلي</b><span id="progress"></span><button onclick="save()">حفظ</button><button onclick="undo()">تراجع</button><button onclick="prev()">السابق</button><button onclick="next()">التالي</button></header>
<div class="layout"><aside class="panel sticky"><label>بحث أو انتقال إلى مقطع</label><input id="search" placeholder="عنوان الكتاب أو رقم المقطع"><button onclick="find()">بحث</button><div class="results" id="results"></div><hr><div id="meta"></div><label>حالة المراجعة</label><select id="status"><option>PENDING</option><option>IN_PROGRESS</option><option>COMPLETED</option><option>NEEDS_EXPERT_REVIEW</option></select><label>التصنيف البنيوي</label><input id="structure" placeholder="مثال: سرد تاريخي"><label>ملاحظات المراجع</label><textarea id="notes" placeholder="ملاحظة بشرية اختيارية"></textarea><p class="metadata">لا يكتمل المقطع قبل مراجعة الفئات أو تعليمها صراحة بأنها غير موجودة.</p></aside>
<main><section class="panel source"><h2>النص الأصلي</h2><div id="source"></div></section><section class="panel"><div class="tabs" id="tabs"></div><div id="view"></div></section><section class="panel"><h2>الإجابة البشرية</h2><p class="metadata">يمكن قبول بطاقة أو تعديلها أو حذفها أو إضافة عنصر مفقود من دون محرر JSON.</p><div id="humanEditor"></div></section></main></div>
<dialog id="editor"><form method="dialog"><h2 id="editorTitle">تعديل عنصر</h2><div class="form-grid" id="editorFields"></div><div class="actions"><button class="primary" type="button" onclick="applyEditor()">حفظ العنصر</button><button type="button" onclick="closeEditor()">إلغاء</button></div></form></dialog>
<script>
let state,index=0,activeTab='reconciled',draft={},editing=null;const editable=['entities','events','relations','temporal_mentions','isnad','claims_attribution'];const field={entities:'gold_entities',events:'gold_events',relations:'gold_relations',temporal_mentions:'gold_temporal_mentions',isnad:'gold_isnad',claims_attribution:'gold_claims_attribution'};const tabLabels={baseline:'المستخرج القاعدي',model:'مخرج النموذج الخام',reconciled:'النتيجة بعد التحقق والمصالحة',human:'الإجابة البشرية'};const esc=x=>String(x??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));const clone=x=>JSON.parse(JSON.stringify(x));
async function api(path,options={}){const response=await fetch(path,{headers:{'Content-Type':'application/json'},...options});const body=await response.json();if(!response.ok)throw Error(body.error||'REQUEST_FAILED');return body}function annotation(){return state.annotations[index]}function presentation(){return state.presentation[annotation().audit_segment_id]}function currentDraft(){return draft[annotation().annotation_id]}function initializeDraft(){const a=annotation();if(!draft[a.annotation_id])draft[a.annotation_id]={entities:clone(a.gold_entities),events:clone(a.gold_events),relations:clone(a.gold_relations),temporal_mentions:clone(a.gold_temporal_mentions),isnad:clone(a.gold_isnad),claims_attribution:clone(a.gold_claims_attribution)}}
async function load(){state=await api('/api/state');initializeDraft();render()}function render(){const a=annotation();initializeDraft();document.getElementById('progress').textContent=`${state.progress.completed}/${state.progress.total} مكتمل`;document.getElementById('meta').innerHTML=`<b>${esc(a.book_title)}</b><br><span class="metadata">مقطع ${esc(a.segment_id)}</span><br><b>ملاحظة تشخيصية سابقة:</b><br>${esc(a.prior_diagnostic_reviewer_notes||'لا توجد')}`;document.getElementById('source').textContent=a.original_text;document.getElementById('status').value=a.adjudication_status;document.getElementById('structure').value=a.structural_type_gold||'';document.getElementById('notes').value=a.reviewer_notes||'';renderTabs();renderHumanEditor()}
function renderTabs(){const p=presentation();document.getElementById('tabs').innerHTML=Object.keys(tabLabels).map(key=>`<button class="tab ${key===activeTab?'active':''}" onclick="activateTab('${key}')">${tabLabels[key]}</button>`).join('');renderView(p.tabs[activeTab],activeTab,p.technical)}function activateTab(key){activeTab=key;renderTabs()}function listHtml(title,items,format){if(!items||!items.length)return '';return `<div><b>${esc(title)}:</b><ul class="facts">${items.map(item=>`<li>${esc(format(item))}</li>`).join('')}</ul></div>`}function evidenceHtml(text){return text?`<div class="evidence"><b>الدليل النصي:</b> «${esc(text)}»</div>`:''}function statusHtml(status){return `<div class="status">${esc(status.label)}</div>${(status.reasons||[]).map(reason=>`<div class="metadata">${esc(reason)}</div>`).join('')}`}
function actionsHtml(source,category,index){if(!editable.includes(category))return '';if(source==='human')return `<div class="actions"><button onclick="editCard('human','${category}',${index})">تعديل</button><button class="danger" onclick="deleteCard('${category}',${index})">حذف</button></div>`;return `<div class="actions"><button class="primary" onclick="acceptCard('${source}','${category}',${index})">قبول في الإجابة البشرية</button><button onclick="editCard('${source}','${category}',${index})">تعديل قبل الإضافة</button></div>`}
function cardHtml(card,source,category,index){let content='';if(card.kind==='entity')content=`<b>${esc(card.surface)}</b><ul class="facts"><li>النوع: ${esc((card.types||[]).join('، ')||'غير محدد')}</li><li>الدور: ${esc((card.roles||[]).join('، ')||'غير محدد')}</li></ul>`;else if(card.kind==='event')content=`<b>نوع الحدث: ${esc(card.event_type)}</b>${listHtml('المشاركون',card.participants,x=>`${x.name} — ${x.role}`)}${listHtml('الأماكن',card.places,x=>`${x.name} — ${x.role}`)}${listHtml('المؤسسات أو المناصب',card.institutions,x=>x)}${listHtml('الزمن',card.temporal,x=>x)}`;else if(card.kind==='relation')content=`<b>${esc(card.sentence)}</b><div>العلاقة: ${esc(card.explicitness)}</div>`;else if(card.kind==='temporal')content=`<b>${esc(card.expression)}</b><ul class="facts"><li>النوع: ${esc(card.precision)}</li>${card.relative_reference?`<li>المرجع النسبي: ${esc(card.relative_reference)}</li>`:''}${card.calendar?`<li>التقويم: ${esc(card.calendar)}</li>`:''}</ul>`;else if(card.kind==='isnad')content=`<b>${esc((card.narrators||[]).join(' ← ')||'سند غير مكتمل')}</b>${card.chain_text?`<div>نص السند: ${esc(card.chain_text)}</div>`:''}${card.matn_boundary?`<div>بداية المتن: ${esc(card.matn_boundary)}</div>`:''}${listHtml('مواضع الغموض',card.ambiguities||[],x=>x)}`;else if(card.kind==='claim')content=`<b>${esc(card.proposition)}</b>${card.attribution?`<div>القائل أو المصدر: ${esc(card.attribution)}</div>`:''}${card.quote_type?`<div>الصيغة: ${esc(card.quote_type)}</div>`:''}${card.modality?`<div>الحكم: ${esc(card.modality)}</div>`:''}`;else content=`<b>${esc(card.message)}</b>`;return `<article class="card status-${esc(card.status.code)}">${content}${evidenceHtml(card.evidence)}${statusHtml(card.status)}${actionsHtml(source,category,index)}<details class="technical"><summary>عرض التفاصيل التقنية</summary><pre>${esc(JSON.stringify(card.technical,null,2))}</pre></details></article>`}
function renderView(tab,source,technical){document.getElementById('view').innerHTML=`<div class="sections">${tab.categories.map((category,i)=>`<details class="section" name="semantic-section" ${i===0?'open':''}><summary>${esc(category.label)} (${category.items.length})</summary><div class="section-body">${category.items.length?`<div class="cards">${category.items.map((card,j)=>cardHtml(card,source,category.key,j)).join('')}</div>`:`<div class="empty">${esc(category.empty_message)}</div>`}${editable.includes(category.key)?`<div class="actions"><button onclick="addMissing('${category.key}')">إضافة عنصر مفقود</button><label><input id="review-${category.key}" type="checkbox" ${annotation().category_review[category.key]==='REVIEWED'?'checked':''}> تمت مراجعة الفئة</label><label><input id="absent-${category.key}" type="checkbox" ${annotation().explicitly_absent[category.key]?'checked':''}> لا توجد عناصر في هذه الفئة</label></div>`:''}</div></details>`).join('')}</div><details class="technical"><summary>عرض التفاصيل التقنية</summary><pre>${esc(JSON.stringify(technical,null,2))}</pre></details>`}
function renderHumanEditor(){document.getElementById('humanEditor').innerHTML=`<div class="sections">${editable.map(key=>`<details class="section"><summary>${esc(state.presentation_contract.categories.find(x=>x.key===key).label)} البشرية (${currentDraft()[key].length})</summary><div class="section-body"><div class="cards">${humanCards(key)}</div><div class="actions"><button onclick="addMissing('${key}')">إضافة عنصر مفقود</button></div></div></details>`).join('')}</div>`}function humanCards(category){const sourceCategory=presentation().tabs.human.categories.find(x=>x.key===category),cards=sourceCategory?sourceCategory.items:[];return cards.length?cards.map((card,i)=>cardHtml(card,'human',category,i)).join(''):'<div class="empty">لا توجد عناصر مستخرجة في هذه الفئة</div>'}
function next(){index=(index+1)%state.annotations.length;activeTab='reconciled';initializeDraft();render()}function prev(){index=(index+state.annotations.length-1)%state.annotations.length;activeTab='reconciled';initializeDraft();render()}function sourceCard(source,category,index){return presentation().tabs[source].categories.find(x=>x.key===category).items[index]}function cardToDraft(card,category){const raw=clone(card.technical||{});if(category==='entities'&&!raw.exact_surface)raw.exact_surface=card.surface;if(category==='events'&&!raw.event_type)raw.event_type=card.event_type;if(category==='relations'&&!raw.predicate)raw.predicate=card.sentence;if(category==='temporal_mentions'&&!raw.exact_expression)raw.exact_expression=card.expression;if(category==='claims_attribution'&&!raw.proposition)raw.proposition=card.proposition;return raw}function acceptCard(source,category,index){currentDraft()[category].push(cardToDraft(sourceCard(source,category,index),category));activeTab='human';render()}function deleteCard(category,index){currentDraft()[category].splice(index,1);renderHumanEditor()}
function formSpec(category,item){const evidence=(item.evidence||item.original_text_span||item.evidence_span||{}),common=[['surface','النص المستخرج',item.exact_surface||item.surface||item.exact_expression||item.proposition||''],['start','بداية الموضع',item.start??evidence.start??''],['end','نهاية الموضع',item.end??evidence.end??''],['evidence','الدليل النصي',evidence.text||item.text||'']];if(category==='entities')return [...common,['type','النوع',Array.isArray(item.entity_types)?item.entity_types[0]:(Array.isArray(item.entity_type_candidate)?item.entity_type_candidate[0]:item.type||'')],['role','الدور السياقي',Array.isArray(item.contextual_roles)?item.contextual_roles[0]:item.contextual_role||'']];if(category==='events')return [['event_type','نوع الحدث',item.event_type||item.type||''],...common,['participants','المشاركون: اسم | دور، سطر لكل مشارك',(item.participants||[]).map(x=>`${x.exact_surface||x.name||x.mention_reference||''} | ${x.role||''}`).join('\n')],['places','الأماكن: اسم | دور، سطر لكل مكان',(item.places||[]).map(x=>`${x.exact_surface||x.name||x.mention_reference||''} | ${x.role||''}`).join('\n')],['institution','المؤسسة أو المنصب',(item.institutions||item.offices||[]).map(x=>typeof x==='string'?x:(x.name||x.exact_surface||'')).join('، ')]];if(category==='relations')return [['subject','الطرف الأول',item.subject||item.subject_mention||''],['predicate','نوع العلاقة',item.predicate||item.relation_type||''],['object','الطرف الثاني',item.object||item.object_mention||''],...common,['explicitness','هل العلاقة صريحة أم مستنتجة',item.explicit_or_inferred||'EXPLICIT']];if(category==='temporal_mentions')return [['expression','العبارة الزمنية',item.exact_expression||item.expression||item.temporal_expression||''],...common,['precision','نوع الزمن أو درجة الدقة',item.precision||item.temporal_precision||''],['relative_reference','المرجع النسبي',item.relative_reference||''],['calendar','التقويم الصريح',item.calendar||'']];if(category==='isnad')return [['narrators','الرواة بالترتيب، مفصولون بفاصلة',(item.ordered_narrators||item.narrators||[]).map(x=>typeof x==='string'?x:(x.exact_surface||x.name||'')).join('، ')],...common,['matn_boundary','بداية المتن',item.matn_boundary||''],['ambiguities','مواضع الغموض',Array.isArray(item.ambiguous_transitions)?item.ambiguous_transitions.join('، '):'']];return [['proposition','مضمون الادعاء',item.proposition||item.normalized_claim||item.original_text||''],...common,['attribution','القائل أو المصدر',item.speaker_or_source||item.attribution||''],['quote_type','قول منقول أم كلام المؤلف',item.quoted_or_authorial||''],['modality','إثبات أو نفي أو احتمال',item.modality||item.claim_modality||'']]}
function editCard(source,category,index){const item=source==='human'?currentDraft()[category][index]:cardToDraft(sourceCard(source,category,index),category);openEditor(category,item,source==='human'?index:null)}function addMissing(category){openEditor(category,{},null)}function openEditor(category,item,indexToReplace){editing={category,index:indexToReplace};document.getElementById('editorTitle').textContent=indexToReplace===null?'إضافة عنصر مفقود':'تعديل عنصر';document.getElementById('editorFields').innerHTML=formSpec(category,item).map(([key,label,value])=>`<label class="${['evidence','participants','places','ambiguities','proposition'].includes(key)?'full':''}">${esc(label)}<textarea data-field="${key}">${esc(value)}</textarea></label>`).join('');document.getElementById('editor').showModal()}function values(){const result={};document.querySelectorAll('#editorFields [data-field]').forEach(node=>result[node.dataset.field]=node.value.trim());return result}function parseLines(value){return value.split('\n').map(line=>line.trim()).filter(Boolean).map(line=>{const [name,role='']=line.split('|').map(x=>x.trim());return {exact_surface:name,role}})}
function applyEditor(){const v=values(),category=editing.category,span={start:Number(v.start||0),end:Number(v.end||0),text:v.evidence||v.surface||v.expression||v.proposition||''};let item={};if(category==='entities')item={exact_surface:v.surface,start:span.start,end:span.end,text:span.text,type:v.type,contextual_role:v.role,evidence:span};else if(category==='events')item={event_type:v.event_type,trigger:span,evidence:span,participants:parseLines(v.participants||''),places:parseLines(v.places||''),institutions:v.institution?[v.institution]:[]};else if(category==='relations')item={subject:v.subject,predicate:v.predicate,object:v.object,evidence:span,explicit_or_inferred:v.explicitness};else if(category==='temporal_mentions')item={exact_expression:v.expression,start:span.start,end:span.end,text:span.text,evidence:span,precision:v.precision,relative_reference:v.relative_reference,calendar:v.calendar};else if(category==='isnad')item={narrators:(v.narrators||'').split('،').map(x=>x.trim()).filter(Boolean),exact_chain_range:span,matn_boundary:v.matn_boundary,ambiguous_transitions:(v.ambiguities||'').split('،').map(x=>x.trim()).filter(Boolean)};else item={proposition:v.proposition,evidence:span,speaker_or_source:v.attribution,quoted_or_authorial:v.quote_type,modality:v.modality};if(editing.index===null)currentDraft()[category].push(item);else currentDraft()[category][editing.index]=item;closeEditor();renderHumanEditor()}function closeEditor(){document.getElementById('editor').close();editing=null}
async function save(){const a=annotation(),d=currentDraft(),patch={structural_type_gold:document.getElementById('structure').value.trim(),reviewer_notes:document.getElementById('notes').value,adjudication_status:document.getElementById('status').value,model_output_judgments:a.model_output_judgments,baseline_output_judgments:a.baseline_output_judgments,category_review:{...a.category_review,structure:document.getElementById('structure').value.trim()?'REVIEWED':a.category_review.structure},explicitly_absent:{...a.explicitly_absent}};for(const key of editable){patch[field[key]]=d[key];const review=document.getElementById('review-'+key),absent=document.getElementById('absent-'+key);if(review)patch.category_review[key]=review.checked?'REVIEWED':'PENDING';if(absent)patch.explicitly_absent[key]=absent.checked}await api('/api/annotation/'+a.annotation_id,{method:'POST',body:JSON.stringify(patch)});draft={};await load()}async function undo(){await api('/api/undo',{method:'POST',body:'{}'});draft={};await load()}async function find(){const results=await api('/api/search?q='+encodeURIComponent(document.getElementById('search').value));document.getElementById('results').innerHTML=results.map(item=>`<button onclick="jump('${item.annotation_id}')">${esc(item.book_title)} — ${esc(item.segment_id)}</button>`).join('')||'<div class="metadata">لا توجد نتائج</div>'}function jump(id){const nextIndex=state.annotations.findIndex(item=>item.annotation_id===id);if(nextIndex>=0){index=nextIndex;activeTab='reconciled';initializeDraft();render()}}document.addEventListener('keydown',event=>{if(event.ctrlKey&&event.key==='s'){event.preventDefault();save()}if(event.ctrlKey&&event.key==='z'){event.preventDefault();undo()}if(event.altKey&&event.key==='ArrowLeft')next();if(event.altKey&&event.key==='ArrowRight')prev()});load()
</script></body></html>"""


class PilotWorkbenchServer(ThreadingHTTPServer):
    def __init__(
        self,
        address: tuple[str, int],
        store: Any,
        *,
        mode: str = "detailed",
    ):
        self.store = store
        self.mode = mode
        super().__init__(address, PilotWorkbenchHandler)


class PilotWorkbenchHandler(BaseHTTPRequestHandler):
    server: PilotWorkbenchServer

    def log_message(self, _format: str, *_args: object) -> None:
        """Do not expose source text, locators, or request paths."""

    def _json(self, status: HTTPStatus, payload: Any) -> None:
        body = (
            json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        self.send_response(status)
        self.send_header(
            "Content-Type",
            "application/json; charset=utf-8",
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 <= length <= _MAX_REQUEST_BYTES:
            raise PilotAdjudicationError("REQUEST_SIZE_INVALID")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PilotAdjudicationError("INVALID_REQUEST_JSON") from error
        if not isinstance(value, dict):
            raise PilotAdjudicationError("REQUEST_MUST_BE_OBJECT")
        return value

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                body = _ui_html(self.server.mode).encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header(
                    "Content-Type",
                    "text/html; charset=utf-8",
                )
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/api/state":
                self._json(HTTPStatus.OK, self.server.store.state())
                return
            if parsed.path == "/api/status":
                self._json(
                    HTTPStatus.OK,
                    self.server.store.progress(),
                )
                return
            if parsed.path == "/api/search":
                query = parse_qs(parsed.query).get("q", [""])[0]
                self._json(
                    HTTPStatus.OK,
                    self.server.store.search(query),
                )
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
        except (PilotEvaluationError, PilotAdjudicationError, FileNotFoundError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = self.path.rstrip("/")
            if path == "/api/undo":
                self._body()
                self._json(
                    HTTPStatus.OK,
                    self.server.store.undo_last(),
                )
                return
            if path == "/api/evaluate":
                self._body()
                self._json(
                    HTTPStatus.OK,
                    self.server.store.evaluate(),
                )
                return
            quick_prefix = "/api/record/"
            if path.startswith(quick_prefix):
                record_id = path[len(quick_prefix) :]
                self._json(
                    HTTPStatus.OK,
                    self.server.store.update(record_id, self._body()),
                )
                return
            prefix = "/api/annotation/"
            if path.startswith(prefix):
                annotation_id = path[len(prefix) :]
                self._json(
                    HTTPStatus.OK,
                    self.server.store.update(
                        annotation_id,
                        self._body(),
                    ),
                )
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
        except KeyError as error:
            self._json(HTTPStatus.NOT_FOUND, {"error": str(error)})
        except (PilotEvaluationError, PilotAdjudicationError, FileNotFoundError) as error:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})


def build_pilot_workbench_server(
    semantic_root: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8775,
    mode: str = "detailed",
) -> PilotWorkbenchServer:
    if host != "127.0.0.1":
        raise PilotAdjudicationError("LOCALHOST_ONLY")
    if not 0 <= int(port) <= 65535:
        raise PilotAdjudicationError("INVALID_PORT")
    if mode not in {"quick", "detailed"}:
        raise PilotAdjudicationError("INVALID_MODE")
    if mode == "quick":
        from .pilot_quick_review import PilotQuickReviewStore, prepare_quick_review

        prepare_quick_review(semantic_root)
        store: Any = PilotQuickReviewStore(semantic_root)
    else:
        store = PilotAdjudicationStore(semantic_root)
    return PilotWorkbenchServer(
        (host, int(port)),
        store,
        mode=mode,
    )


__all__ = [
    "PilotAdjudicationError",
    "PilotAdjudicationStore",
    "PilotWorkbenchServer",
    "build_pilot_workbench_server",
]
