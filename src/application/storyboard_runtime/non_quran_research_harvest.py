"""Harvest local research candidates for Adam's unresolved non-Quran events.

The harvest is a research workbench, not an evidence approval system. It scans
local project text artifacts, records file/excerpt checksums, deduplicates
candidate snippets, produces event review files and research prompts, and keeps
all human approval and evidence gates closed.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping

HARVEST_SCHEMA = "siraj-non-quran-research-harvest-v1"
BACKLOG_SCHEMA = "siraj-non-quran-research-backlog-v1"
PROMPT_SCHEMA = "siraj-non-quran-research-prompt-pack-v1"
EDITORIAL_SCHEMA = "siraj-editorial-event-review-template-v1"
STATUS = "LOCAL_CANDIDATE_HARVEST_READY_HUMAN_RESEARCH_PENDING"
GATE = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTO_APPROVAL = "FORBIDDEN"
LIVE_EXECUTION = "BLOCKED"

FACTUAL_EVENTS = (
    "EV-ADAM-001", "EV-ADAM-002", "EV-ADAM-003", "EV-ADAM-005",
    "EV-ADAM-007", "EV-ADAM-021", "EV-ADAM-023", "EV-ADAM-024",
    "EV-ADAM-032", "EV-ADAM-033", "EV-ADAM-042", "EV-ADAM-060",
    "EV-ADAM-061", "EV-ADAM-070",
)
EDITORIAL_EVENTS = ("EV-ADAM-099",)
TARGET_EVENTS = FACTUAL_EVENTS + EDITORIAL_EVENTS

TEXT_EXTENSIONS = {".json", ".jsonl", ".md", ".txt", ".yaml", ".yml", ".csv"}
EXCLUDED_BASENAMES = {
    "event-map.json",
    "full-episode-adjudication-inventory-v1.json",
    "non-quran-research-harvest-v1.json",
    "non-quran-research-backlog-v1.json",
}
TOKEN_RE = re.compile(r"\b(?:EV-ADAM-\d{3}|RQ-ADAM-\d{3})\b")


class NonQuranHarvestError(ValueError):
    pass


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise NonQuranHarvestError(f"Invalid JSON: {path}") from exc


def load_target_events(inventory_path: Path) -> list[dict]:
    inventory = read_json(inventory_path)
    if not isinstance(inventory, Mapping):
        raise NonQuranHarvestError("Inventory must be an object.")
    if inventory.get("schema_version") != "siraj-full-episode-adjudication-inventory-v1":
        raise NonQuranHarvestError("Unexpected inventory schema.")
    events = inventory.get("events")
    if not isinstance(events, list):
        raise NonQuranHarvestError("Inventory events missing.")
    by_id = {
        str(item.get("event_id")): dict(item)
        for item in events
        if isinstance(item, Mapping)
    }
    if any(event_id not in by_id for event_id in TARGET_EVENTS):
        raise NonQuranHarvestError("Target event set is incomplete.")
    selected = [by_id[event_id] for event_id in TARGET_EVENTS]
    factual = selected[: len(FACTUAL_EVENTS)]
    if any(item.get("verification_status") == "quran_explicit" for item in selected):
        raise NonQuranHarvestError("Quran-explicit event entered non-Quran harvest.")
    if any(item.get("human_gap_decision_recorded") for item in selected):
        raise NonQuranHarvestError("Human-approved gap event entered research harvest.")
    if any(item.get("event_id") == "EV-ADAM-099" and
           item.get("verification_status") != "editorial" for item in selected):
        raise NonQuranHarvestError("Editorial event classification changed.")
    if len(factual) != 14 or len(selected) != 15:
        raise NonQuranHarvestError("Expected 14 factual events and one editorial event.")
    return selected


def _normalise_excerpt(text: str) -> str:
    return " ".join(text.split())


def _artifact_role(relative: str) -> str:
    lowered = "/" + relative.lower()
    if "/evidence/" in lowered:
        return "EVIDENCE_ARTIFACT"
    if "/research/" in lowered:
        return "RESEARCH_ARTIFACT"
    if "/editorial/" in lowered:
        return "EDITORIAL_ARTIFACT"
    if "/contracts/" in lowered:
        return "CONTRACT_ARTIFACT"
    return "PROJECT_ARTIFACT"


def _source_hints(text: str) -> list[str]:
    lowered = text.lower()
    hints = []
    groups = (
        ("QURAN_CONTEXT", ("quran", "قرآن", "سورة", "آية")),
        ("HADITH_CANDIDATE", (
            "حديث", "البخاري", "مسلم", "الترمذي", "أبو داود",
            "النسائي", "ابن ماجه", "مسند",
        )),
        ("TAFSIR_OR_ATHAR_CANDIDATE", (
            "تفسير", "الطبري", "ابن كثير", "ابن أبي حاتم",
            "البيهقي", "السدي", "أثر",
        )),
        ("ISRAILIYYAT_CANDIDATE", (
            "الإسرائيليات", "اسرائيليات", "أهل الكتاب", "التوراة",
        )),
    )
    for label, terms in groups:
        if any(term.lower() in lowered for term in terms):
            hints.append(label)
    return hints or ["INTERNAL_REFERENCE"]


def _rank_candidate(
    *, role: str, matched_tokens: list[str], source_hints: list[str],
    excerpt: str
) -> int:
    score = {
        "EVIDENCE_ARTIFACT": 45,
        "RESEARCH_ARTIFACT": 35,
        "EDITORIAL_ARTIFACT": 18,
        "CONTRACT_ARTIFACT": 12,
        "PROJECT_ARTIFACT": 8,
    }[role]
    score += 20 if any(token.startswith("EV-") for token in matched_tokens) else 0
    score += 10 if any(token.startswith("RQ-") for token in matched_tokens) else 0
    score += 15 if source_hints != ["INTERNAL_REFERENCE"] else 0
    score += min(len(excerpt) // 250, 10)
    return score


def scan_local_candidates(
    *, project_root: Path, target_events: Iterable[Mapping[str, object]],
    context_lines: int = 4, max_snippets_per_event: int = 120,
    max_file_bytes: int = 25_000_000,
) -> tuple[dict[str, list[dict]], dict]:
    project_root = Path(project_root)
    events = list(target_events)
    tokens_by_event = {
        str(item["event_id"]): {
            str(item["event_id"]),
            *[str(value) for value in item.get("question_ids", [])],
        }
        for item in events
    }
    collected: dict[str, list[dict]] = defaultdict(list)
    seen: dict[str, set[str]] = defaultdict(set)
    scanned_files = 0
    skipped_large = 0
    skipped_excluded = 0
    file_manifest = []

    for path in sorted(project_root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in TEXT_EXTENSIONS:
            continue
        if path.name in EXCLUDED_BASENAMES or "non-quran-research" in path.name:
            skipped_excluded += 1
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > max_file_bytes:
            skipped_large += 1
            continue
        try:
            raw = path.read_bytes()
            text = raw.decode("utf-8-sig", errors="replace")
        except OSError:
            continue
        relative = path.relative_to(project_root).as_posix()
        scanned_files += 1
        file_manifest.append({
            "path": relative,
            "size_bytes": size,
            "file_sha256": hashlib.sha256(raw).hexdigest(),
            "artifact_role": _artifact_role(relative),
        })
        lines = text.splitlines()
        for index, line in enumerate(lines):
            line_tokens = set(TOKEN_RE.findall(line))
            if not line_tokens:
                continue
            for event_id, event_tokens in tokens_by_event.items():
                matched = sorted(line_tokens & event_tokens)
                if not matched or len(collected[event_id]) >= max_snippets_per_event:
                    continue
                start = max(0, index - context_lines)
                end = min(len(lines), index + context_lines + 1)
                excerpt = "\n".join(lines[start:end]).strip()
                normalised = _normalise_excerpt(excerpt)
                if not normalised:
                    continue
                dedupe_hash = text_sha256(normalised)
                if dedupe_hash in seen[event_id]:
                    continue
                seen[event_id].add(dedupe_hash)
                role = _artifact_role(relative)
                hints = _source_hints(excerpt)
                candidate = {
                    "candidate_id": (
                        event_id.lower().replace("-", "_") + "_" + dedupe_hash[:16]
                    ),
                    "event_id": event_id,
                    "path": relative,
                    "line_start": start + 1,
                    "line_end": end,
                    "matched_tokens": matched,
                    "artifact_role": role,
                    "source_hints": hints,
                    "automatic_source_classification": False,
                    "file_sha256": hashlib.sha256(raw).hexdigest(),
                    "excerpt_sha256": text_sha256(excerpt),
                    "normalised_excerpt_sha256": dedupe_hash,
                    "excerpt": excerpt,
                }
                candidate["research_priority_score"] = _rank_candidate(
                    role=role,
                    matched_tokens=matched,
                    source_hints=hints,
                    excerpt=excerpt,
                )
                collected[event_id].append(candidate)

    for event_id in collected:
        collected[event_id].sort(
            key=lambda item: (
                -item["research_priority_score"],
                item["path"],
                item["line_start"],
            )
        )
    return dict(collected), {
        "files_scanned": scanned_files,
        "files_skipped_large": skipped_large,
        "files_skipped_excluded": skipped_excluded,
        "source_file_manifest": file_manifest,
        "raw_excerpts_retained_locally": True,
        "automatic_source_classification": False,
    }


def build_backlog(target_events: Iterable[Mapping[str, object]]) -> dict:
    items = []
    for event in target_events:
        event_id = str(event["event_id"])
        editorial = event_id in EDITORIAL_EVENTS
        items.append({
            "event_id": event_id,
            "title": event["title"],
            "section": event["section"],
            "question_ids": list(event.get("question_ids", [])),
            "event_kind": "EDITORIAL_TRANSITION" if editorial else "FACTUAL_RESEARCH",
            "recommended_disposition": "editorial_only" if editorial else None,
            "research_required": not editorial,
            "human_decision_required": True,
            "status": (
                "EDITORIAL_ONLY_HUMAN_DECISION_PENDING"
                if editorial
                else "SOURCE_EXTRACTION_AND_VERIFICATION_PENDING"
            ),
        })
    backlog = {
        "schema_version": BACKLOG_SCHEMA,
        "status": "RESEARCH_BACKLOG_READY",
        "episode_id": "episode-001-adam",
        "factual_event_count": 14,
        "editorial_event_count": 1,
        "event_count": len(items),
        "event_ids": [item["event_id"] for item in items],
        "items": items,
        "human_approval": False,
        "full_episode_adjudication_complete": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    backlog["backlog_id"] = (
        "adam_non_quran_backlog_" + canonical_sha256(backlog)[:16]
    )
    validate_backlog(backlog)
    return backlog


def build_prompt_pack(target_events: Iterable[Mapping[str, object]]) -> dict:
    events = list(target_events)
    groups = (
        (
            "NQ-BATCH-01-PRE-CREATION",
            ("EV-ADAM-001", "EV-ADAM-002", "EV-ADAM-003",
             "EV-ADAM-005", "EV-ADAM-007"),
            "حال الكون والمخلوقات قبل خلق آدم",
        ),
        (
            "NQ-BATCH-02-CREATION-LIFE-KNOWLEDGE",
            ("EV-ADAM-021", "EV-ADAM-023", "EV-ADAM-024",
             "EV-ADAM-032", "EV-ADAM-033", "EV-ADAM-042"),
            "تفاصيل خلق آدم وبداية حياته وفضل العلم",
        ),
        (
            "NQ-BATCH-03-COVENANT-SPOUSE-EDITORIAL",
            ("EV-ADAM-060", "EV-ADAM-061", "EV-ADAM-070",
             "EV-ADAM-099"),
            "الميثاق وخلق الزوج والانتقال التحريري",
        ),
    )
    by_id = {str(item["event_id"]): item for item in events}
    batches = []
    for batch_id, event_ids, objective in groups:
        batch_events = []
        for event_id in event_ids:
            event = by_id[event_id]
            batch_events.append({
                "event_id": event_id,
                "title": event["title"],
                "question_ids": list(event.get("question_ids", [])),
                "event_kind": (
                    "EDITORIAL_TRANSITION"
                    if event_id in EDITORIAL_EVENTS
                    else "FACTUAL_RESEARCH"
                ),
            })
        prompt = (
            "اعمل على الأحداث المحددة فقط. استخرج من المصادر الأصلية المصرح بها "
            "النص الدقيق، واسم المصدر، والجزء/الصفحة أو رقم الحديث/الأثر، والسياق "
            "الكافي قبل النص وبعده. افصل بين النص الصريح، والتفسير، والاستنباط، "
            "والرواية الإسرائيلية. لا تحكم آليًا بصحة الحديث، ولا تدمج الروايات "
            "المتعارضة، ولا تكتب نص الحلقة النهائي. أعد نتيجة مستقلة لكل event_id "
            "تتضمن source_locator وexact_excerpt وorigin_candidate وclassification_notes "
            "وuncertainties وrecommended_next_check. بالنسبة للحدث التحريري "
            "EV-ADAM-099 لا تبحث عن دليل يثبت الانتقال الفني؛ اقترح وظيفة انتقالية "
            "فقط بلا إضافة واقعة تاريخية."
        )
        batches.append({
            "batch_id": batch_id,
            "objective": objective,
            "event_ids": list(event_ids),
            "events": batch_events,
            "chatgpt_prompt": prompt,
            "notebooklm_prompt": prompt,
            "automatic_adjudication": False,
        })
    pack = {
        "schema_version": PROMPT_SCHEMA,
        "status": "PROMPT_PACK_READY",
        "episode_id": "episode-001-adam",
        "batch_count": len(batches),
        "batches": batches,
        "human_approval": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    pack["prompt_pack_id"] = (
        "adam_non_quran_prompt_pack_" + canonical_sha256(pack)[:16]
    )
    validate_prompt_pack(pack)
    return pack


def build_editorial_review_template(target_events: Iterable[Mapping[str, object]]) -> dict:
    by_id = {str(item["event_id"]): item for item in target_events}
    event = by_id["EV-ADAM-099"]
    template = {
        "schema_version": EDITORIAL_SCHEMA,
        "status": "TEMPLATE_NOT_APPROVED",
        "episode_id": "episode-001-adam",
        "event_id": "EV-ADAM-099",
        "title": event["title"],
        "event_kind": "EDITORIAL_TRANSITION",
        "proposed_disposition": "editorial_only",
        "research_required": False,
        "proposed_function": (
            "تهيئة المشاهد للانتقال إلى بدء الوسوسة دون تقرير واقعة جديدة "
            "أو استباق تفاصيل الحلقة التالية."
        ),
        "prohibited_claims": [
            "تعيين كيفية بدء الوسوسة قبل بحث الحلقة التالية",
            "إضافة حوار غير ثابت",
            "إضافة زمن أو مكان غير ثابت",
            "عرض غيبيات أو ذوات مقدسة بصريًا",
        ],
        "approved": False,
        "human_decision": False,
        "approved_by": "",
        "approved_at": "",
        "reviewer_notes": "",
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    validate_editorial_review_template(template)
    return template


def build_harvest(
    *, inventory_path: Path, project_root: Path, include_snippets: bool = True
) -> tuple[dict, dict, dict, dict]:
    events = load_target_events(inventory_path)
    backlog = build_backlog(events)
    prompt_pack = build_prompt_pack(events)
    editorial = build_editorial_review_template(events)
    candidates, scan = scan_local_candidates(
        project_root=project_root, target_events=events
    ) if include_snippets else ({}, {
        "files_scanned": 0,
        "files_skipped_large": 0,
        "files_skipped_excluded": 0,
        "source_file_manifest": [],
        "raw_excerpts_retained_locally": False,
        "automatic_source_classification": False,
    })
    event_items = []
    for event in events:
        event_id = str(event["event_id"])
        event_candidates = candidates.get(event_id, [])
        hint_counts = Counter(
            hint
            for candidate in event_candidates
            for hint in candidate["source_hints"]
        )
        event_items.append({
            "event_id": event_id,
            "title": event["title"],
            "section": event["section"],
            "question_ids": list(event.get("question_ids", [])),
            "event_kind": (
                "EDITORIAL_TRANSITION"
                if event_id in EDITORIAL_EVENTS
                else "FACTUAL_RESEARCH"
            ),
            "candidate_count": len(event_candidates),
            "source_hint_counts": dict(sorted(hint_counts.items())),
            "candidates": event_candidates,
            "research_status": (
                "EDITORIAL_REVIEW_PENDING"
                if event_id in EDITORIAL_EVENTS
                else (
                    "LOCAL_CANDIDATES_READY_FOR_VERIFICATION"
                    if event_candidates
                    else "SOURCE_DISCOVERY_REQUIRED"
                )
            ),
        })
    harvest = {
        "schema_version": HARVEST_SCHEMA,
        "status": STATUS,
        "episode_id": "episode-001-adam",
        "backlog_id": backlog["backlog_id"],
        "prompt_pack_id": prompt_pack["prompt_pack_id"],
        "factual_event_count": 14,
        "editorial_event_count": 1,
        "event_count": 15,
        "events_with_candidates": sum(
            item["candidate_count"] > 0 for item in event_items
        ),
        "candidate_count": sum(item["candidate_count"] for item in event_items),
        "events": event_items,
        "scan_summary": {
            key: value for key, value in scan.items()
            if key != "source_file_manifest"
        },
        "human_approval": False,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    harvest["harvest_id"] = (
        "adam_non_quran_harvest_" + canonical_sha256(harvest)[:16]
    )
    validate_harvest(harvest)
    manifest = {
        "schema_version": "siraj-local-source-file-manifest-v1",
        "harvest_id": harvest["harvest_id"],
        "file_count": len(scan["source_file_manifest"]),
        "files": scan["source_file_manifest"],
        "raw_file_content_retained": False,
    }
    return harvest, backlog, prompt_pack, editorial, manifest


def validate_backlog(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != BACKLOG_SCHEMA:
        raise NonQuranHarvestError("Unexpected backlog schema.")
    if tuple(data.get("event_ids", ())) != TARGET_EVENTS:
        raise NonQuranHarvestError("Backlog target set changed.")
    if data.get("factual_event_count") != 14 or data.get("editorial_event_count") != 1:
        raise NonQuranHarvestError("Backlog counts changed.")
    item_099 = next(
        item for item in data["items"] if item["event_id"] == "EV-ADAM-099"
    )
    if item_099["recommended_disposition"] != "editorial_only":
        raise NonQuranHarvestError("Editorial disposition changed.")
    if item_099["research_required"] is not False:
        raise NonQuranHarvestError("Editorial transition cannot require factual research.")
    _validate_guards(data)


def validate_prompt_pack(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != PROMPT_SCHEMA or data.get("batch_count") != 3:
        raise NonQuranHarvestError("Prompt pack structure changed.")
    covered = [
        event_id
        for batch in data["batches"]
        for event_id in batch["event_ids"]
    ]
    if tuple(covered) != TARGET_EVENTS:
        raise NonQuranHarvestError("Prompt pack event coverage changed.")
    if any(batch.get("automatic_adjudication") is not False for batch in data["batches"]):
        raise NonQuranHarvestError("Prompts cannot authorize adjudication.")
    _validate_guards(data)


def validate_editorial_review_template(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != EDITORIAL_SCHEMA:
        raise NonQuranHarvestError("Unexpected editorial review schema.")
    if data.get("status") != "TEMPLATE_NOT_APPROVED":
        raise NonQuranHarvestError("Editorial review cannot be preapproved.")
    if data.get("event_id") != "EV-ADAM-099":
        raise NonQuranHarvestError("Unexpected editorial event.")
    if data.get("proposed_disposition") != "editorial_only":
        raise NonQuranHarvestError("Editorial event must remain editorial_only.")
    if data.get("research_required") is not False:
        raise NonQuranHarvestError("Editorial event cannot require source binding.")
    if data.get("approved") is not False or data.get("human_decision") is not False:
        raise NonQuranHarvestError("Editorial review must remain blank.")
    _validate_guards(data)


def validate_harvest(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != HARVEST_SCHEMA or data.get("status") != STATUS:
        raise NonQuranHarvestError("Unexpected harvest schema/status.")
    events = data.get("events")
    if not isinstance(events, list) or len(events) != 15:
        raise NonQuranHarvestError("Harvest must contain 15 events.")
    ids = tuple(item["event_id"] for item in events)
    if ids != TARGET_EVENTS:
        raise NonQuranHarvestError("Harvest target event set changed.")
    if data.get("factual_event_count") != 14 or data.get("editorial_event_count") != 1:
        raise NonQuranHarvestError("Harvest counts changed.")
    if data.get("full_episode_adjudication_complete") is not False:
        raise NonQuranHarvestError("Harvest cannot complete adjudication.")
    if data.get("approved_evidence_package_complete") is not False:
        raise NonQuranHarvestError("Harvest cannot complete evidence package.")
    for event in events:
        for candidate in event["candidates"]:
            if candidate.get("automatic_source_classification") is not False:
                raise NonQuranHarvestError("Candidate cannot be auto-classified.")
            if text_sha256(candidate["excerpt"]) != candidate["excerpt_sha256"]:
                raise NonQuranHarvestError("Candidate excerpt checksum mismatch.")
    _validate_guards(data)


def _validate_guards(data: Mapping[str, object]) -> None:
    if data.get("evidence_gate_status") != GATE:
        raise NonQuranHarvestError("Evidence gate must remain withheld.")
    if data.get("automatic_evidence_approval") != AUTO_APPROVAL:
        raise NonQuranHarvestError("Automatic approval must remain forbidden.")
    if data.get("live_provider_execution") != LIVE_EXECUTION:
        raise NonQuranHarvestError("Provider execution must remain blocked.")
    if data.get("human_approval") not in (None, False):
        raise NonQuranHarvestError("Research harvest cannot claim human approval.")


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def write_local_outputs(
    *, output_root: Path, harvest: Mapping[str, object],
    backlog: Mapping[str, object], prompt_pack: Mapping[str, object],
    editorial: Mapping[str, object], manifest: Mapping[str, object],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "harvest": output_root / "non-quran-research-harvest-v1.json",
        "backlog": output_root / "non-quran-research-backlog-v1.json",
        "prompt_pack": output_root / "non-quran-research-prompt-pack-v1.json",
        "editorial_review": output_root / "editorial-event-099-review-v1.template.json",
        "source_manifest": output_root / "source-file-manifest-v1.json",
        "coverage_csv": output_root / "event-candidate-coverage.csv",
        "summary": output_root / "README.md",
    }
    write_json(outputs["harvest"], harvest)
    write_json(outputs["backlog"], backlog)
    write_json(outputs["prompt_pack"], prompt_pack)
    write_json(outputs["editorial_review"], editorial)
    write_json(outputs["source_manifest"], manifest)

    with outputs["coverage_csv"].open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=(
            "event_id", "title", "section", "event_kind",
            "candidate_count", "research_status",
        ))
        writer.writeheader()
        for event in harvest["events"]:
            writer.writerow({
                key: event[key] for key in writer.fieldnames
            })

    event_dir = output_root / "event-review"
    event_dir.mkdir(parents=True, exist_ok=True)
    for event in harvest["events"]:
        path = event_dir / f"{event['event_id']}.md"
        lines = [
            f"# {event['event_id']} — {event['title']}",
            "",
            f"- Section: {event['section']}",
            f"- Kind: {event['event_kind']}",
            f"- Candidate count: {event['candidate_count']}",
            f"- Status: {event['research_status']}",
            "",
        ]
        for index, candidate in enumerate(event["candidates"], 1):
            lines.extend([
                f"## Candidate {index}",
                "",
                f"- Path: `{candidate['path']}`",
                f"- Lines: {candidate['line_start']}-{candidate['line_end']}",
                f"- Priority score: {candidate['research_priority_score']}",
                f"- Source hints: {', '.join(candidate['source_hints'])}",
                f"- File SHA-256: `{candidate['file_sha256']}`",
                f"- Excerpt SHA-256: `{candidate['excerpt_sha256']}`",
                "",
                "```text",
                candidate["excerpt"],
                "```",
                "",
            ])
        path.write_text("\n".join(lines), encoding="utf-8", newline="\n")

    prompt_dir = output_root / "research-prompts"
    prompt_dir.mkdir(parents=True, exist_ok=True)
    for index, batch in enumerate(prompt_pack["batches"], 1):
        path = prompt_dir / f"{index:02d}-{batch['batch_id'].lower()}.md"
        path.write_text(
            f"# {batch['batch_id']}\n\n"
            f"## Objective\n\n{batch['objective']}\n\n"
            f"## Events\n\n" +
            "\n".join(
                f"- {event['event_id']}: {event['title']}"
                for event in batch["events"]
            ) +
            f"\n\n## ChatGPT Prompt\n\n{batch['chatgpt_prompt']}\n\n"
            f"## NotebookLM Prompt\n\n{batch['notebooklm_prompt']}\n",
            encoding="utf-8",
            newline="\n",
        )

    outputs["summary"].write_text(
        "# Adam Non-Quran Research Harvest v1\n\n"
        f"- Factual unresolved events: {harvest['factual_event_count']}\n"
        f"- Editorial events: {harvest['editorial_event_count']}\n"
        f"- Events with local candidates: {harvest['events_with_candidates']}\n"
        f"- Deduplicated candidates: {harvest['candidate_count']}\n"
        f"- Files scanned: {harvest['scan_summary']['files_scanned']}\n"
        "- Candidate source hints are heuristic and are not source classifications.\n"
        "- No evidence was approved and the evidence gate remains withheld.\n",
        encoding="utf-8",
        newline="\n",
    )

    archive = output_root.with_suffix(".zip")
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(output_root.rglob("*")):
            if path.is_file():
                bundle.write(path, path.relative_to(output_root).as_posix())
    outputs["archive"] = archive
    return outputs
