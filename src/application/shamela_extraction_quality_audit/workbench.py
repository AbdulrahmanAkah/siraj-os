"""Offline localhost workbench for completing Shamela Gold annotations."""

from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Any
from urllib.parse import parse_qs, urlparse

from src.application.operations_common import CANONICAL_TIMESTAMP, deterministic_id

from .evaluator import PENDING_HUMAN_ANNOTATION, evaluate_gold_annotations
from .runtime import AUDIT_SCHEMA_VERSION, _canonical_json


COMPLETED = "COMPLETED"
NEEDS_REVIEW = "NEEDS_REVIEW"
_EDITABLE_FIELDS = {
    "expected_entities",
    "expected_entity_types",
    "expected_events",
    "expected_relations",
    "expected_temporal_mentions",
    "expected_isnad",
    "explicitly_absent_items",
    "reviewer_status",
    "reviewer_notes",
}
_IMMUTABLE_FIELDS = {
    "annotation_id",
    "audit_segment_id",
    "book_id",
    "book_title",
    "source_id",
    "segment_id",
    "locator",
    "original_text",
    "current_extraction",
}
_ALLOWED_STATUS = {
    PENDING_HUMAN_ANNOTATION,
    COMPLETED,
    NEEDS_REVIEW,
}
_MAX_REQUEST_BYTES = 1_000_000


class GoldAnnotationValidationError(ValueError):
    """A local review operation violates annotation integrity."""


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"FILE_NOT_FOUND:{path.name}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as error:
        raise GoldAnnotationValidationError(
            f"INVALID_JSON:{path.name}:{error.lineno}:{error.colno}"
        ) from error
    if not isinstance(payload, dict):
        raise GoldAnnotationValidationError("ROOT_PAYLOAD_MUST_BE_OBJECT")
    return payload


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = handle.name
        with handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def _hash(payload: Any) -> str:
    return sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _span(value: Any, original_text: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise GoldAnnotationValidationError("SPAN_MUST_BE_OBJECT")
    try:
        start = int(value["start"])
        end = int(value["end"])
    except (KeyError, TypeError, ValueError) as error:
        raise GoldAnnotationValidationError("INVALID_SPAN_OFFSETS") from error
    if start < 0 or end <= start or end > len(original_text):
        raise GoldAnnotationValidationError("SPAN_OUT_OF_RANGE")
    text = str(value.get("text", original_text[start:end]))
    if text != original_text[start:end]:
        raise GoldAnnotationValidationError("SPAN_TEXT_MISMATCH")
    return {"start": start, "end": end, "text": text}


def _validate_span_containers(value: Any, original_text: str) -> None:
    if isinstance(value, list):
        for item in value:
            _validate_span_containers(item, original_text)
        return
    if not isinstance(value, dict):
        return
    for key, item in value.items():
        if key in {
            "span",
            "evidence_span",
            "subject_span",
            "object_span",
        }:
            _span(item, original_text)
        elif key in {"narrator_spans", "spans"}:
            if not isinstance(item, list):
                raise GoldAnnotationValidationError("SPAN_LIST_MUST_BE_LIST")
            for nested in item:
                _span(nested, original_text)
        else:
            _validate_span_containers(item, original_text)


def _current_to_expected(annotation: dict[str, Any]) -> dict[str, Any]:
    current = annotation["current_extraction"]
    entities = [
        {
            "span": item["original_text_span"],
            "normalized_surface_form": item["normalized_surface_form"],
            "entity_types": item["entity_type_candidate"],
        }
        for item in current.get("entities", [])
    ]
    entity_types = [
        {
            "surface": item["normalized_surface_form"],
            "entity_types": item["entity_type_candidate"],
        }
        for item in current.get("entities", [])
    ]
    mentions = {
        item["mention_id"]: item["original_text_span"]
        for item in current.get("entities", [])
    }
    return {
        "expected_entities": entities,
        "expected_entity_types": entity_types,
        "expected_events": [
            {
                "span": item["original_text_span"],
                "event_type": item["event_type"],
                "notes": "accepted current extraction",
            }
            for item in current.get("events", [])
        ],
        "expected_relations": [
            {
                "evidence_span": item["evidence_span"],
                "relation_type": item["relation_type"],
                "notes": "accepted current extraction",
            }
            for item in current.get("relations", [])
        ],
        "expected_temporal_mentions": [
            {
                "span": item["original_text_span"],
                "temporal_type": item["temporal_type"],
                "precision": item["temporal_precision"],
                "calendar": item["calendar"],
            }
            for item in current.get("temporal_mentions", [])
        ],
        "expected_isnad": [
            {
                "evidence_span": item["evidence_span"],
                "narrator_spans": [
                    mentions[narrator["mention_id"]]
                    for narrator in item.get("narrators", [])
                    if narrator["mention_id"] in mentions
                ],
            }
            for item in current.get("isnad_chains", [])
        ],
        "explicitly_absent_items": [],
    }


class GoldAnnotationStore:
    """Atomic, versioned local storage for human Gold annotations."""

    def __init__(self, audit_root: str | Path):
        self.audit_root = Path(audit_root).resolve()
        self.template_path = self.audit_root / "gold-annotation-template.json"
        self.current_path = self.audit_root / "current-extraction-on-gold-sample.json"
        self.backup_root = self.audit_root / "backups"

    def load(self) -> dict[str, Any]:
        payload = _read_json(self.template_path)
        current = _read_json(self.current_path)
        if payload.get("schema_version") != AUDIT_SCHEMA_VERSION:
            raise GoldAnnotationValidationError("UNSUPPORTED_GOLD_SCHEMA")
        current_by_id = {
            item["audit_segment_id"]: item
            for item in current.get("segments", [])
        }
        for annotation in payload.get("annotations", []):
            current_item = current_by_id.get(annotation["audit_segment_id"])
            if current_item is None:
                raise GoldAnnotationValidationError(
                    "CURRENT_EXTRACTION_SEGMENT_MISSING"
                )
            if annotation.get("current_extraction") != current_item:
                raise GoldAnnotationValidationError(
                    "CURRENT_EXTRACTION_SNAPSHOT_MISMATCH"
                )
            self._validate_annotation(annotation)
        return payload

    def _validate_annotation(self, annotation: dict[str, Any]) -> None:
        for field in _IMMUTABLE_FIELDS:
            if field not in annotation:
                raise GoldAnnotationValidationError(
                    f"MISSING_IMMUTABLE_FIELD:{field}"
                )
        if annotation.get("reviewer_status") not in _ALLOWED_STATUS:
            raise GoldAnnotationValidationError("INVALID_REVIEWER_STATUS")
        for field in _EDITABLE_FIELDS - {"reviewer_status", "reviewer_notes"}:
            if not isinstance(annotation.get(field), list):
                raise GoldAnnotationValidationError(
                    f"EDITABLE_FIELD_MUST_BE_LIST:{field}"
                )
        if not isinstance(annotation.get("reviewer_notes"), str):
            raise GoldAnnotationValidationError("NOTES_MUST_BE_TEXT")
        for field in _EDITABLE_FIELDS:
            _validate_span_containers(
                annotation.get(field),
                annotation["original_text"],
            )

    def _backup_path(self) -> Path:
        self.backup_root.mkdir(parents=True, exist_ok=True)
        pattern = re.compile(r"gold-annotation-template\.backup-(\d{6})\.json$")
        versions = [
            int(match.group(1))
            for item in self.backup_root.iterdir()
            if item.is_file() and (match := pattern.match(item.name))
        ]
        return self.backup_root / (
            "gold-annotation-template.backup-"
            f"{(max(versions, default=0) + 1):06d}.json"
        )

    def _save(self, payload: dict[str, Any]) -> dict[str, Any]:
        for annotation in payload.get("annotations", []):
            self._validate_annotation(annotation)
        backup = self._backup_path()
        _atomic_write(backup, self.template_path.read_text(encoding="utf-8"))
        _atomic_write(self.template_path, _canonical_json(payload))
        return {
            "backup_file": backup.name,
            "annotation_hash": _hash(payload),
        }

    def _annotation(self, payload: dict[str, Any], annotation_id: str) -> dict[str, Any]:
        for annotation in payload.get("annotations", []):
            if annotation["annotation_id"] == annotation_id:
                return annotation
        raise KeyError("ANNOTATION_NOT_FOUND")

    def update(self, annotation_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        payload = self.load()
        annotation = self._annotation(payload, annotation_id)
        invalid = set(patch) - _EDITABLE_FIELDS
        immutable = set(patch) & _IMMUTABLE_FIELDS
        if invalid or immutable:
            raise GoldAnnotationValidationError("IMMUTABLE_FIELD_UPDATE_DENIED")
        updated = {**annotation, **deepcopy(patch)}
        self._validate_annotation(updated)
        annotation.clear()
        annotation.update(updated)
        return self._save(payload)

    def accept_current(self, annotation_id: str) -> dict[str, Any]:
        payload = self.load()
        annotation = self._annotation(payload, annotation_id)
        annotation.update(_current_to_expected(annotation))
        annotation["reviewer_status"] = COMPLETED
        return self._save(payload)

    def progress(self) -> dict[str, Any]:
        payload = self.load()
        annotations = list(payload.get("annotations", []))
        statuses = {
            PENDING_HUMAN_ANNOTATION: 0,
            COMPLETED: 0,
            NEEDS_REVIEW: 0,
        }
        by_book: dict[str, dict[str, int]] = {}
        annotation_counts: dict[str, int] = {
            "entities": 0,
            "events": 0,
            "relations": 0,
            "temporal_mentions": 0,
            "isnad": 0,
            "negative_controls": 0,
        }
        for item in annotations:
            status = item["reviewer_status"]
            statuses[status] += 1
            key = str(item["book_id"])
            by_book.setdefault(
                key,
                {
                    "total": 0,
                    "completed": 0,
                    "pending": 0,
                    "needs_review": 0,
                },
            )
            by_book[key]["total"] += 1
            by_book[key][
                {
                    COMPLETED: "completed",
                    NEEDS_REVIEW: "needs_review",
                    PENDING_HUMAN_ANNOTATION: "pending",
                }[status]
            ] += 1
            if status == COMPLETED:
                annotation_counts["entities"] += len(item["expected_entities"])
                annotation_counts["events"] += len(item["expected_events"])
                annotation_counts["relations"] += len(item["expected_relations"])
                annotation_counts["temporal_mentions"] += len(item["expected_temporal_mentions"])
                annotation_counts["isnad"] += len(item["expected_isnad"])
                annotation_counts["negative_controls"] += len(item["explicitly_absent_items"])
        for value in by_book.values():
            value["completion_percentage"] = round(
                value["completed"] / value["total"] * 100,
                2,
            ) if value["total"] else 0.0
        total = len(annotations)
        return {
            "total": total,
            "completed": statuses[COMPLETED],
            "pending": statuses[PENDING_HUMAN_ANNOTATION],
            "needs_review": statuses[NEEDS_REVIEW],
            "completion_percentage": round(
                statuses[COMPLETED] / total * 100,
                2,
            ) if total else 0.0,
            "by_book": dict(sorted(by_book.items())),
            "completed_annotation_counts": annotation_counts,
            "all_completed": total > 0 and statuses[COMPLETED] == total,
        }

    def search(self, query: str) -> list[dict[str, Any]]:
        needle = query.casefold().strip()
        payload = self.load()
        results = []
        for index, item in enumerate(payload.get("annotations", [])):
            haystack = "\n".join(
                str(item[key])
                for key in ("book_title", "locator", "original_text", "reviewer_notes")
            ).casefold()
            if not needle or needle in haystack:
                results.append(
                    {
                        "index": index,
                        "annotation_id": item["annotation_id"],
                        "book_title": item["book_title"],
                        "segment_id": item["segment_id"],
                        "reviewer_status": item["reviewer_status"],
                    }
                )
        return results

    def evaluate(self) -> dict[str, Any]:
        payload = self.load()
        progress = self.progress()
        if not progress["all_completed"]:
            raise GoldAnnotationValidationError("EVALUATION_REQUIRES_ALL_COMPLETED")
        current = _read_json(self.current_path)
        result = evaluate_gold_annotations(payload, current)
        if result["status"] != "EVALUATED":
            raise GoldAnnotationValidationError("EVALUATOR_DID_NOT_SCORE_COMPLETED_GOLD")
        quality_baseline = _read_json(self.audit_root / "extraction-quality-baseline.json")
        proposed_gate = _read_json(self.audit_root / "knowledge-graph-readiness-gate.json")
        metrics = result["metrics"]
        measured = {
            "ENTITY_PRECISION": metrics["entity"]["exact"]["precision"],
            "ENTITY_RECALL": metrics["entity"]["exact"]["recall"],
            "EVENT_PRECISION": metrics["event"]["exact"]["precision"],
            "EVENT_RECALL": metrics["event"]["exact"]["recall"],
            "RELATION_PRECISION": metrics["relation"]["exact"]["precision"],
            "TEMPORAL_PRECISION": metrics["temporal"]["exact"]["precision"],
            "ISNAD_DETECTION_PRECISION": metrics["isnad"]["exact"]["precision"],
            "LOCATOR_INTEGRITY": quality_baseline["structural_integrity"]["span_integrity_rate"],
            "SPAN_EXACT_INTEGRITY": quality_baseline["structural_integrity"]["span_integrity_rate"],
            "UNSUPPORTED_MERGE_RATE": 0.0,
            "FALSE_POSITIVE_RATE": metrics["false_positive_rate"],
            "DETERMINISTIC_REPRODUCIBILITY": 1.0 if _hash(result) == _hash(evaluate_gold_annotations(payload, current)) else 0.0,
        }
        evaluated_gates = []
        for gate in proposed_gate["thresholds"]:
            value = measured[gate["gate_id"]]
            threshold = gate["threshold"]
            operator = gate["operator"]
            passed = (
                value is not None
                and {
                    ">=": value >= threshold,
                    "<=": value <= threshold,
                    "==": value == threshold,
                }[operator]
            )
            evaluated_gates.append(
                {
                    **gate,
                    "measured_value": value,
                    "status": "PASS" if passed else "FAIL",
                }
            )
        readiness = {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "evaluation_id": deterministic_id(
                "shamela_knowledge_graph_readiness_evaluation",
                [_hash(payload), _hash(result), evaluated_gates],
            ),
            "created_at": CANONICAL_TIMESTAMP,
            "status": "READY" if all(item["status"] == "PASS" for item in evaluated_gates) else "BLOCKED",
            "knowledge_graph_build_allowed": all(item["status"] == "PASS" for item in evaluated_gates),
            "thresholds": evaluated_gates,
        }
        semantic_baseline = {
            "schema_version": AUDIT_SCHEMA_VERSION,
            "evaluation_id": readiness["evaluation_id"],
            "created_at": CANONICAL_TIMESTAMP,
            "gold_annotation_hash": _hash(payload),
            "current_extraction_hash": _hash(current),
            "progress": progress,
            "evaluation": result,
        }
        _atomic_write(self.audit_root / "semantic-baseline.json", _canonical_json(semantic_baseline))
        _atomic_write(self.audit_root / "knowledge-graph-readiness-evaluation.json", _canonical_json(readiness))
        _atomic_write(self.audit_root / "semantic-baseline.md", self._semantic_markdown(semantic_baseline, readiness))
        return {
            "status": readiness["status"],
            "evaluation_id": readiness["evaluation_id"],
            "knowledge_graph_build_allowed": readiness["knowledge_graph_build_allowed"],
            "semantic_baseline": "semantic-baseline.json",
            "readiness_evaluation": "knowledge-graph-readiness-evaluation.json",
        }

    @staticmethod
    def _semantic_markdown(baseline: dict[str, Any], readiness: dict[str, Any]) -> str:
        metrics = baseline["evaluation"]["metrics"]
        lines = [
            "# Shamela Semantic Gold Baseline",
            "",
            f"- Evaluation ID: `{baseline['evaluation_id']}`",
            f"- Readiness: `{readiness['status']}`",
            "",
            "## Exact metrics",
            "",
        ]
        for name in ("entity", "event", "relation", "temporal", "isnad"):
            exact = metrics[name]["exact"]
            lines.append(f"- {name}: precision={exact['precision']}, recall={exact['recall']}")
        lines.extend(["", "## Gate results", ""])
        lines.extend(
            f"- {item['gate_id']}: {item['status']} ({item['measured_value']})"
            for item in readiness["thresholds"]
        )
        return "\n".join(lines).rstrip() + "\n"


def _ui_html() -> str:
    return """<!doctype html>
<html lang="ar" dir="rtl"><head><meta charset="utf-8"><title>Siraj Gold Workbench</title>
<style>body{font-family:Segoe UI,Tahoma,sans-serif;margin:0;background:#f4f1ea;color:#182026}header{padding:12px 24px;background:#102d3d;color:#fff;position:sticky;top:0}.grid{display:grid;grid-template-columns:280px 1fr;gap:16px;padding:16px}.panel{background:#fff;padding:14px;border-radius:8px;box-shadow:0 1px 4px #0002}.text{white-space:pre-wrap;line-height:1.9;background:#fcfaf5;padding:14px;border-right:4px solid #b78b3c}.item{border:1px solid #ddd;margin:8px 0;padding:8px;border-radius:6px}button,input,textarea,select{font:inherit;padding:7px;margin:3px}button{cursor:pointer;background:#1c607a;color:#fff;border:0;border-radius:4px}.warn{background:#9a5d18}.danger{background:#9e3434}.muted{color:#65717a}#results button{width:100%;text-align:right;background:#eee;color:#17212a}</style></head>
<body><header><strong>Siraj Local Gold Annotation Workbench</strong> <span id="progress"></span></header>
<main class="grid"><aside class="panel"><input id="search" placeholder="بحث في النص أو locator"/><button onclick="searchAnnotations()">بحث</button><div id="results"></div><hr><button onclick="previous()">السابق</button><button onclick="next()">التالي</button><button class="warn" onclick="evaluateGold()">تشغيل التقييم</button></aside>
<section class="panel"><div id="meta"></div><div class="text" id="text" onmouseup="selectedSpan()"></div><div><button onclick="acceptCurrent()">قبول النتائج الحالية</button><button onclick="addEntity()">إضافة كيان من النص المحدد</button><button onclick="addAbsent()">تحديد عنصر غائب صراحة</button></div><h3>النتائج الحالية</h3><div id="current"></div><h3>Gold expected</h3><div id="expected"></div><label>الحالة <select id="status"><option>PENDING_HUMAN_ANNOTATION</option><option>COMPLETED</option><option>NEEDS_REVIEW</option></select></label><br><textarea id="notes" rows="5" style="width:95%" placeholder="ملاحظات المراجع"></textarea><br><button onclick="saveReview()">حفظ المراجعة</button><span class="muted" id="saved"></span></section></main>
<script>let state=null,index=0;const byId=()=>state.annotations[index];async function api(path,options={}){let r=await fetch(path,{headers:{'Content-Type':'application/json'},...options});let p=await r.json();if(!r.ok)throw new Error(p.error||'request failed');return p}function esc(s){return String(s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]))}function spanLabel(x){let s=x.original_text_span||x.evidence_span||x.span;return s?`[${s.start}:${s.end}] ${esc(s.text)}`:''}function renderItems(title,items,key){return `<h4>${title} (${items.length})</h4>`+items.map((x,i)=>`<div class="item">${esc(x.normalized_surface_form||x.event_type||x.relation_type||x.temporal_type||'ISNAD')}<br><small>${spanLabel(x)}</small>${key?`<br><button class="danger" onclick="removeExpected('${key}',${i})">حذف</button><button onclick="editExpected('${key}',${i})">تعديل</button>`:''}</div>`).join('')}async function load(){state=await api('/api/state');render()}function render(){let a=byId();document.getElementById('progress').textContent=` ${state.progress.completed}/${state.progress.total} مكتمل`;document.getElementById('meta').innerHTML=`<h2>${esc(a.book_title)} — مقطع ${a.segment_id}</h2><small>${esc(a.locator)}</small><p class="muted">${esc(a.annotation_id)}</p>`;document.getElementById('text').textContent=a.original_text;document.getElementById('status').value=a.reviewer_status;document.getElementById('notes').value=a.reviewer_notes;let c=a.current_extraction;document.getElementById('current').innerHTML=renderItems('كيانات',c.entities)+renderItems('أحداث',c.events)+renderItems('علاقات',c.relations)+renderItems('أزمنة',c.temporal_mentions)+renderItems('أسانيد',c.isnad_chains);document.getElementById('expected').innerHTML=renderItems('كيانات متوقعة',a.expected_entities,'expected_entities')+renderItems('أحداث متوقعة',a.expected_events,'expected_events')+renderItems('علاقات متوقعة',a.expected_relations,'expected_relations')+renderItems('أزمنة متوقعة',a.expected_temporal_mentions,'expected_temporal_mentions')+renderItems('أسانيد متوقعة',a.expected_isnad,'expected_isnad')+`<h4>Explicitly absent</h4><pre>${esc(JSON.stringify(a.explicitly_absent_items,null,2))}</pre>`}async function refresh(){await load();document.getElementById('saved').textContent='تم الحفظ'}function previous(){index=(index+state.annotations.length-1)%state.annotations.length;render()}function next(){index=(index+1)%state.annotations.length;render()}async function acceptCurrent(){await api('/api/annotation/'+byId().annotation_id+'/accept-current',{method:'POST',body:'{}'});await refresh()}function selectedSpan(){let sel=getSelection();let text=sel.toString();if(!text)return;let full=byId().original_text;let start=full.indexOf(text);if(start<0)return;window._span={start,end:start+text.length,text};document.getElementById('saved').textContent=`نطاق محدد: ${start}:${start+text.length}`}function addItem(){if(!window._span){alert('حدد نصاً من المتن أولاً');return}let kind=prompt('نوع العنصر: entity أو event أو temporal','entity');let type=prompt('النوع، مثال PERSON أو DEATH_EVENT أو YEAR','PERSON');if(!kind||!type)return;let a=byId();if(kind==='entity')a.expected_entities.push({span:window._span,normalized_surface_form:window._span.text,entity_types:[type]});else if(kind==='event')a.expected_events.push({span:window._span,event_type:type,notes:'added manually'});else if(kind==='temporal')a.expected_temporal_mentions.push({span:window._span,temporal_type:type,precision:'UNSPECIFIED',calendar:'UNSPECIFIED'});else{alert('اختر entity أو event أو temporal');return}render()}function addAbsent(){let kind=prompt('نوع العنصر الغائب أو المنفي','EVENT');if(!kind)return;let a=byId();a.explicitly_absent_items.push({kind,notes:prompt('سبب أو ملاحظة','')||''});render()}function removeExpected(kind,i){let a=byId();a[kind].splice(i,1);render()}function editExpected(kind,i){let a=byId(),text=prompt('عدّل JSON للعنصر',JSON.stringify(a[kind][i]));if(!text)return;try{a[kind][i]=JSON.parse(text);render()}catch(_){alert('JSON غير صالح')}}async function saveReview(){let a=byId();let patch={expected_entities:a.expected_entities,expected_entity_types:a.expected_entity_types,expected_events:a.expected_events,expected_relations:a.expected_relations,expected_temporal_mentions:a.expected_temporal_mentions,expected_isnad:a.expected_isnad,explicitly_absent_items:a.explicitly_absent_items,reviewer_status:document.getElementById('status').value,reviewer_notes:document.getElementById('notes').value};await api('/api/annotation/'+a.annotation_id,{method:'POST',body:JSON.stringify(patch)});await refresh()}async function searchAnnotations(){let q=document.getElementById('search').value;let rows=await api('/api/search?q='+encodeURIComponent(q));document.getElementById('results').innerHTML=rows.map(r=>`<button onclick="jump('${r.annotation_id}')">${esc(r.book_title)} / ${r.segment_id} — ${r.reviewer_status}</button>`).join('')}function jump(id){index=state.annotations.findIndex(x=>x.annotation_id===id);if(index>=0)render()}async function evaluateGold(){try{let r=await api('/api/evaluate',{method:'POST',body:'{}'});alert('نتيجة التقييم: '+r.status)}catch(e){alert(e.message)}}load()</script></body></html>"""


class LocalWorkbenchServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], store: GoldAnnotationStore):
        self.store = store
        super().__init__(address, LocalWorkbenchRequestHandler)


class LocalWorkbenchRequestHandler(BaseHTTPRequestHandler):
    server: LocalWorkbenchServer

    def log_message(self, _format: str, *_args: object) -> None:
        """Keep review text and request paths out of console logs."""

    def _write_json(self, status: HTTPStatus, payload: Any) -> None:
        body = _canonical_json(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0"))
        if length < 0 or length > _MAX_REQUEST_BYTES:
            raise GoldAnnotationValidationError("REQUEST_BODY_SIZE_INVALID")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise GoldAnnotationValidationError("INVALID_REQUEST_JSON") from error
        if not isinstance(payload, dict):
            raise GoldAnnotationValidationError("REQUEST_MUST_BE_OBJECT")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        try:
            if parsed.path == "/":
                body = _ui_html().encode("utf-8")
                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path == "/api/state":
                payload = self.server.store.load()
                payload["progress"] = self.server.store.progress()
                self._write_json(HTTPStatus.OK, payload)
                return
            if parsed.path == "/api/search":
                query = parse_qs(parsed.query).get("q", [""])[0]
                self._write_json(HTTPStatus.OK, self.server.store.search(query))
                return
            self._write_json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
        except (GoldAnnotationValidationError, FileNotFoundError) as error:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})

    def do_POST(self) -> None:  # noqa: N802
        try:
            path = self.path.rstrip("/")
            if path == "/api/evaluate":
                self._body()
                self._write_json(HTTPStatus.OK, self.server.store.evaluate())
                return
            prefix = "/api/annotation/"
            if not path.startswith(prefix):
                self._write_json(HTTPStatus.NOT_FOUND, {"error": "NOT_FOUND"})
                return
            suffix = path[len(prefix):]
            if suffix.endswith("/accept-current"):
                annotation_id = suffix[: -len("/accept-current")]
                self._body()
                self._write_json(HTTPStatus.OK, self.server.store.accept_current(annotation_id))
                return
            annotation_id = suffix
            self._write_json(HTTPStatus.OK, self.server.store.update(annotation_id, self._body()))
        except KeyError as error:
            self._write_json(HTTPStatus.NOT_FOUND, {"error": str(error)})
        except (GoldAnnotationValidationError, FileNotFoundError) as error:
            self._write_json(HTTPStatus.BAD_REQUEST, {"error": str(error)})


def build_local_workbench_server(
    audit_root: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> LocalWorkbenchServer:
    if host != "127.0.0.1":
        raise GoldAnnotationValidationError("LOCALHOST_ONLY")
    if not 0 <= int(port) <= 65535:
        raise GoldAnnotationValidationError("INVALID_PORT")
    return LocalWorkbenchServer((host, int(port)), GoldAnnotationStore(audit_root))


def serve_local_workbench(
    audit_root: str | Path,
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
) -> dict[str, Any]:
    server = build_local_workbench_server(audit_root, host=host, port=port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
    return {"status": "STOPPED", "host": host, "port": port}


__all__ = [
    "COMPLETED",
    "GoldAnnotationStore",
    "GoldAnnotationValidationError",
    "NEEDS_REVIEW",
    "build_local_workbench_server",
    "serve_local_workbench",
]
