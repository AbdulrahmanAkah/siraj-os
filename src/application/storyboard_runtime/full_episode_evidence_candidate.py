"""Build a complete 37-event Adam evidence-package approval candidate."""
from __future__ import annotations

import csv
import hashlib
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path
from typing import Mapping

from .evidence_binding import ApprovedEvidenceItem, EventEvidenceDecision

INTEGRATION_SCHEMA = "siraj-full-episode-evidence-integration-v1"
SOURCE_CANDIDATE_SCHEMA = "siraj-approved-source-package-candidate-v1"
EVIDENCE_CANDIDATE_SCHEMA = "siraj-approved-evidence-package-candidate-v1"
ADJUDICATION_CANDIDATE_SCHEMA = (
    "siraj-event-evidence-adjudication-candidate-v1"
)
APPROVAL_REQUEST_SCHEMA = "siraj-final-evidence-human-approval-request-v1"
EDITORIAL_DECISION_SCHEMA = "siraj-editorial-event-delegated-decision-v1"

TARGET_EVIDENCE_SCHEMA = "siraj-approved-evidence-package-v1"
TARGET_ADJUDICATION_SCHEMA = "siraj-event-evidence-adjudication-v1"

GATE = "WITHHELD_PENDING_FINAL_EVIDENCE_PACKAGE_APPROVAL"
AUTO_APPROVAL = "FORBIDDEN"
LIVE_EXECUTION = "BLOCKED"

EXPECTED_EVENT_COUNT = 37
EXPECTED_QURAN_EVENT_COUNT = 19
EXPECTED_EXTERNAL_EVENT_COUNT = 14
EXPECTED_GAP_EVENT_COUNT = 3
EXPECTED_EDITORIAL_EVENT_COUNT = 1

GAP_EVENT_IDS = ("EV-ADAM-031", "EV-ADAM-071", "EV-ADAM-091")
EDITORIAL_EVENT_ID = "EV-ADAM-099"

GAP_SOURCE_IDS = {
    "EV-ADAM-031": (
        "SRCREC-ADAM-SNEEZE-TIRMIDHI-3368",
    ),
    "EV-ADAM-071": (
        "SRCREC-HAWA-NAME-BUKHARI-3330-MUSLIM-1470",
        "SRCREC-WOMAN-RIB-BUKHARI-3331-MUSLIM-1468",
        "SRCREC-TABARI-8406-SUDDI-LONELINESS",
        "SRCREC-IBN-ABI-HATIM-8276-SUDDI-LONELINESS",
        "SRCREC-BAYHAQI-820-SUDDI-LONELINESS",
        "SRCREC-TABARI-8407-IBN-ISHAQ-AHL-AL-KITAB",
    ),
    "EV-ADAM-091": (
        "SRCREC-TABARI-TREE-NONDETERMINATION",
        "SRCREC-IBN-KATHIR-TREE-NONDETERMINATION",
    ),
}

GAP_CLAIMS = {
    "SRCREC-ADAM-SNEEZE-TIRMIDHI-3368": (
        "عطس آدم بعد نفخ الروح وحمد الله وثبت خطاب الله له في الحديث."
    ),
    "SRCREC-HAWA-NAME-BUKHARI-3330-MUSLIM-1470": (
        "يثبت أن زوج آدم هي حواء، ولا يثبت بهذا السجل سبب التسمية."
    ),
    "SRCREC-WOMAN-RIB-BUKHARI-3331-MUSLIM-1468": (
        "يثبت أن المرأة خلقت من ضلع دون تعيين اليسار أو النوم."
    ),
    "SRCREC-TABARI-8406-SUDDI-LONELINESS": (
        "خبر تفسيري عن وحدة آدم والحوار واسم حواء، منسوب بلا جزم."
    ),
    "SRCREC-IBN-ABI-HATIM-8276-SUDDI-LONELINESS": (
        "خبر تفسيري عن وحدة آدم قبل خلق زوجه، منسوب بلا جزم."
    ),
    "SRCREC-BAYHAQI-820-SUDDI-LONELINESS": (
        "نسخة تفسيرية مركبة في خبر وحدة آدم، لا تروى بصيغة الجزم."
    ),
    "SRCREC-TABARI-8407-IBN-ISHAQ-AHL-AL-KITAB": (
        "تفاصيل الضلع الأيسر والنوم والتئام الموضع من أخبار أهل الكتاب."
    ),
    "SRCREC-TABARI-TREE-NONDETERMINATION": (
        "نقل اختلاف المفسرين في نوع الشجرة وعدم وجود تعيين قطعي."
    ),
    "SRCREC-IBN-KATHIR-TREE-NONDETERMINATION": (
        "نقل أقوال نوع الشجرة مع عدم ثبوت تعيينها في النص الصحيح."
    ),
}

QUALIFICATION_LABELS = {
    "EV-ADAM-007": "ذكر تفسيري منسوب بلا جزم",
    "EV-ADAM-021": "ترتيب الأوصاف غير مجزوم به",
    "EV-ADAM-042": "أقوال تفسيرية منسوبة بلا حصر للمراد",
    "EV-ADAM-061": "حديث مذكور بدرجته وليس التفسير الوحيد للآية",
    "EV-ADAM-070": "تفاصيل تفسيرية وإسرائيليات موسومة بلا جزم",
    "EV-ADAM-071": "تفاصيل تفسيرية وإسرائيليات موسومة بلا جزم",
    "EV-ADAM-091": "اختلف المفسرون ولم يثبت تعيين نوع الشجرة",
}

APPROVAL_PHRASE = (
    "أعتمد بشريًا حزمة أدلة حلقة آدم النهائية وتحكيم أحداثها الـ37 "
    "وفق البصمات المحددة فقط، وأجيز فتح بوابة الأدلة دون السماح بأي "
    "تشغيل مدفوع أو مباشر"
)

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class FullEpisodeCandidateError(ValueError):
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


def read_json(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FullEpisodeCandidateError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise FullEpisodeCandidateError(f"Expected object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _event_map_items(event_map: object) -> list[dict]:
    if not isinstance(event_map, list):
        raise FullEpisodeCandidateError("Event map must be a list.")
    if not all(isinstance(item, dict) for item in event_map):
        raise FullEpisodeCandidateError("Event map entries must be objects.")
    return [dict(item) for item in event_map]


def validate_inputs(
    *,
    inventory: Mapping[str, object],
    event_map: object,
    quran_candidate: Mapping[str, object],
    external_scope: Mapping[str, object],
    external_pack: Mapping[str, object],
    gap_approval: Mapping[str, object],
    origin_classification: Mapping[str, object],
    delegation: Mapping[str, object],
    episode_definition: Mapping[str, object],
) -> None:
    if inventory.get("event_count") != EXPECTED_EVENT_COUNT:
        raise FullEpisodeCandidateError("Inventory must contain 37 events.")
    inventory_events = inventory.get("events")
    if not isinstance(inventory_events, list) or len(inventory_events) != 37:
        raise FullEpisodeCandidateError("Inventory event coverage is incomplete.")

    map_items = _event_map_items(event_map)
    if len(map_items) != 37:
        raise FullEpisodeCandidateError("Event map must contain 37 events.")
    map_ids = [item.get("event_id") for item in map_items]
    inventory_ids = [item.get("event_id") for item in inventory_events]
    if map_ids != inventory_ids:
        raise FullEpisodeCandidateError(
            "Inventory and event-map order must match exactly."
        )

    historical = episode_definition.get("historical_scope")
    if not isinstance(historical, Mapping):
        raise FullEpisodeCandidateError("Historical scope is missing.")
    if historical.get("required_event_ids") != map_ids:
        raise FullEpisodeCandidateError(
            "Episode required-event order differs from event map."
        )

    if quran_candidate.get("schema_version") != (
        "siraj-quran-event-binding-candidate-v1"
    ):
        raise FullEpisodeCandidateError("Unexpected Quran candidate schema.")
    if quran_candidate.get("event_count") != EXPECTED_QURAN_EVENT_COUNT:
        raise FullEpisodeCandidateError("Expected 19 Quran events.")

    if external_scope.get("schema_version") != (
        "siraj-external-event-scope-final-adjudication-v1"
    ):
        raise FullEpisodeCandidateError("Unexpected external scope schema.")
    if external_scope.get("event_count") != EXPECTED_EXTERNAL_EVENT_COUNT:
        raise FullEpisodeCandidateError("Expected 14 external events.")
    if external_scope.get("external_event_scope_complete") is not True:
        raise FullEpisodeCandidateError(
            "External event-scope adjudication is incomplete."
        )

    if external_pack.get("schema_version") != (
        "siraj-external-event-source-candidate-pack-v1"
    ):
        raise FullEpisodeCandidateError("Unexpected external pack schema.")
    if external_pack.get("event_count") != EXPECTED_EXTERNAL_EVENT_COUNT:
        raise FullEpisodeCandidateError(
            "External pack must contain fourteen events."
        )

    if gap_approval.get("human_approval") is not True:
        raise FullEpisodeCandidateError("Gap human approval is absent.")
    gap_ids = {
        item["event_id"] for item in gap_approval.get("decisions", [])
    }
    if gap_ids != set(GAP_EVENT_IDS):
        raise FullEpisodeCandidateError(
            "Gap approval must cover exactly 031, 071, and 091."
        )

    source_records = origin_classification.get("source_records")
    if not isinstance(source_records, list):
        raise FullEpisodeCandidateError(
            "Source-origin records are missing."
        )
    source_record_ids = {
        item.get("source_record_id") for item in source_records
    }
    required_gap_sources = {
        source_id
        for source_ids in GAP_SOURCE_IDS.values()
        for source_id in source_ids
    }
    missing = required_gap_sources - source_record_ids
    if missing:
        raise FullEpisodeCandidateError(
            f"Missing gap source records: {sorted(missing)}"
        )

    scope = delegation.get("delegation_scope")
    if not isinstance(scope, Mapping):
        raise FullEpisodeCandidateError("Delegation scope is absent.")
    if scope.get("routine_evidence") != "AI_DECISION_AUTHORIZED":
        raise FullEpisodeCandidateError(
            "Routine evidence delegation is not active."
        )


def build_editorial_decision() -> dict:
    artifact = {
        "schema_version": EDITORIAL_DECISION_SCHEMA,
        "status": "DELEGATED_EDITORIAL_DECISION_COMPLETE",
        "episode_id": "episode-001-adam",
        "event_id": EDITORIAL_EVENT_ID,
        "event_kind": "EDITORIAL_TRANSITION",
        "disposition": "editorial_only",
        "function": (
            "تهيئة المشاهد للانتقال إلى بدء الوسوسة دون تقرير واقعة "
            "جديدة أو استباق تفاصيل الحلقة التالية."
        ),
        "prohibited_claims": [
            "تعيين كيفية بدء الوسوسة قبل بحث الحلقة التالية",
            "إضافة حوار غير ثابت",
            "إضافة زمن أو مكان غير ثابت",
            "عرض غيبيات أو ذوات مقدسة بصريًا",
        ],
        "research_required": False,
        "delegated_ai_decision": True,
        "human_decision": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    artifact["decision_id"] = (
        "adam_editorial_099_"
        + canonical_sha256(artifact)[:16]
    )
    return artifact


def _normalize_disposition(event_id: str, raw: str) -> str:
    if raw == "include_assertive":
        return "include_assertive"
    if raw == "include_qualified":
        return "include_qualified"
    if raw == "include_assertive_with_scope_limit":
        return "include_assertive"
    if raw in {
        "include_assertive_with_qualified_tafsir_supplement",
        "include_assertive_with_qualified_details",
    }:
        return "include_qualified"
    if raw == "omit_unverified":
        return raw
    if raw == "editorial_only":
        return raw
    raise FullEpisodeCandidateError(
        f"Unsupported disposition for {event_id}: {raw}"
    )


def build_integration(
    *,
    inventory: Mapping[str, object],
    quran_candidate: Mapping[str, object],
    external_scope: Mapping[str, object],
    gap_approval: Mapping[str, object],
    editorial_decision: Mapping[str, object],
) -> dict:
    quran_index = {
        item["event_id"]: item for item in quran_candidate["bindings"]
    }
    external_index = {
        item["event_id"]: item for item in external_scope["events"]
    }
    gap_index = {
        item["event_id"]: item for item in gap_approval["decisions"]
    }

    rows = []
    route_counts: dict[str, int] = defaultdict(int)
    for inventory_event in inventory["events"]:
        event_id = inventory_event["event_id"]
        if event_id in quran_index:
            route = "QURAN_ROUTINE_DELEGATION"
            source = quran_index[event_id]
            disposition = "include_assertive"
            approval_origin = "ACTIVE_USER_DELEGATION"
        elif event_id in external_index:
            route = "EXTERNAL_SOURCE_FINAL_SCOPE"
            source = external_index[event_id]
            disposition = _normalize_disposition(
                event_id, source["disposition"]
            )
            approval_origin = source["decision_origin"]
        elif event_id in gap_index:
            route = "PRIOR_GAP_HUMAN_APPROVAL"
            source = gap_index[event_id]
            disposition = source["disposition"]
            approval_origin = "EXPLICIT_HUMAN_DECISION"
        elif event_id == EDITORIAL_EVENT_ID:
            route = "DELEGATED_EDITORIAL_TRANSITION"
            source = editorial_decision
            disposition = "editorial_only"
            approval_origin = "ACTIVE_USER_DELEGATION"
        else:
            raise FullEpisodeCandidateError(
                f"Unresolved episode event: {event_id}"
            )
        route_counts[route] += 1
        rows.append(
            {
                "event_id": event_id,
                "order": inventory_event["order"],
                "title": inventory_event["title"],
                "section": inventory_event["section"],
                "verification_status": inventory_event[
                    "verification_status"
                ],
                "route": route,
                "approval_origin": approval_origin,
                "disposition": disposition,
                "scope_resolved": True,
            }
        )

    if len(rows) != EXPECTED_EVENT_COUNT:
        raise FullEpisodeCandidateError(
            "Full integration must contain 37 events."
        )
    expected_counts = {
        "QURAN_ROUTINE_DELEGATION": 19,
        "EXTERNAL_SOURCE_FINAL_SCOPE": 14,
        "PRIOR_GAP_HUMAN_APPROVAL": 3,
        "DELEGATED_EDITORIAL_TRANSITION": 1,
    }
    if dict(route_counts) != expected_counts:
        raise FullEpisodeCandidateError(
            f"Unexpected integration route counts: {dict(route_counts)}"
        )

    artifact = {
        "schema_version": INTEGRATION_SCHEMA,
        "status": "FULL_EPISODE_SCOPE_INTEGRATED_CANDIDATE_READY",
        "episode_id": "episode-001-adam",
        "event_count": len(rows),
        "quran_event_count": expected_counts["QURAN_ROUTINE_DELEGATION"],
        "external_event_count": expected_counts[
            "EXTERNAL_SOURCE_FINAL_SCOPE"
        ],
        "gap_human_event_count": expected_counts[
            "PRIOR_GAP_HUMAN_APPROVAL"
        ],
        "editorial_event_count": expected_counts[
            "DELEGATED_EDITORIAL_TRANSITION"
        ],
        "events": rows,
        "event_scope_complete": True,
        "evidence_items_complete": False,
        "final_human_package_approval": False,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    artifact["integration_id"] = (
        "adam_full_episode_integration_"
        + canonical_sha256(artifact)[:16]
    )
    return artifact


def _source_type_from_classification(classification: str) -> str:
    if classification == "quran_explicit":
        return "QURAN"
    if classification == "authentic_sunnah":
        return "HADITH"
    if classification == "accepted_athar":
        return "ATHAR"
    if classification in {
        "scholarly_interpretation",
        "disputed_view",
    }:
        return "TAFSIR"
    if classification == "israiliyyat":
        return "ISRAILIYYAT"
    if classification == "weak_report":
        return "WEAK_REPORT"
    raise FullEpisodeCandidateError(
        f"Unknown classification: {classification}"
    )


def _origin_to_claim_classification(origin: str) -> str:
    mapping = {
        "AUTHENTIC_SUNNAH": "authentic_sunnah",
        "TAFSIR_REPORT_COMPOSITE_CHAIN_NOT_MARFU":
            "scholarly_interpretation",
        "ISRAILIYYAT_EXPLICIT_ORIGIN": "israiliyyat",
        "DISPUTED_TAFSIR_VIEW": "disputed_view",
        "SUPPORTED_SYNTHESIS": "scholarly_interpretation",
    }
    if origin not in mapping:
        raise FullEpisodeCandidateError(
            f"Unsupported origin classification: {origin}"
        )
    return mapping[origin]


def _evidence_id(event_id: str, source_id: str) -> str:
    return (
        "EVID-"
        + event_id.replace("EV-", "")
        + "-"
        + hashlib.sha256(source_id.encode("utf-8")).hexdigest()[:12]
    )


def _source_link_index(
    external_pack: Mapping[str, object],
) -> dict[str, dict[str, dict]]:
    result: dict[str, dict[str, dict]] = {}
    for event in external_pack["events"]:
        result[event["event_id"]] = {
            link["source_candidate_id"]: link
            for link in event["source_links"]
        }
    return result


def _claim_summary_for_external(
    event: Mapping[str, object],
    source_id: str,
) -> str:
    claims = [
        layer["claim"]
        for layer in event.get("claim_layers", [])
        if source_id in layer.get("support", [])
    ]
    if not claims:
        return event["title"]
    return "؛ ".join(dict.fromkeys(claims))


def _gap_locator(record: Mapping[str, object]) -> str:
    references = record.get("references")
    if isinstance(references, list) and references:
        return "؛ ".join(str(item) for item in references)
    work = str(record.get("work", "")).strip()
    number = str(record.get("record", "")).strip()
    locator = "؛ ".join(item for item in (work, number) if item)
    return locator or str(record["source_record_id"])


def build_candidates(
    *,
    integration: Mapping[str, object],
    quran_candidate: Mapping[str, object],
    external_scope: Mapping[str, object],
    external_pack: Mapping[str, object],
    gap_approval: Mapping[str, object],
    origin_classification: Mapping[str, object],
    editorial_decision: Mapping[str, object],
) -> tuple[dict, dict, dict]:
    source_items: dict[str, dict] = {}
    source_supports: dict[str, set[str]] = defaultdict(set)
    evidence_items: list[dict] = []
    decisions: list[dict] = []

    def register_source(
        *,
        source_id: str,
        title: str,
        source_type: str,
        checksum: str,
        event_id: str,
        locator: str,
        quotation_allowed: bool,
    ) -> None:
        if not _SHA256_RE.fullmatch(checksum):
            raise FullEpisodeCandidateError(
                f"Invalid source checksum: {source_id}"
            )
        source_supports[source_id].add(event_id)
        item = {
            "source_id": source_id,
            "title": title,
            "source_type": source_type,
            "access_status": "VERIFIED",
            "allowed_for_extraction": True,
            "allowed_for_quotation": quotation_allowed,
            "checksum": checksum,
            "locator": locator,
            "notes": {
                "supports_event_ids": [],
            },
        }
        if source_id in source_items:
            existing = source_items[source_id]
            for key in (
                "source_type",
                "checksum",
                "allowed_for_quotation",
            ):
                if existing[key] != item[key]:
                    raise FullEpisodeCandidateError(
                        f"Conflicting source record: {source_id}"
                    )
        else:
            source_items[source_id] = item

    def append_evidence(
        *,
        event_id: str,
        source_id: str,
        classification: str,
        claim_summary: str,
        locator: str,
        source_checksum: str,
        excerpt_sha256: str,
        quotation_allowed: bool,
        restrictions: list[str],
    ) -> str:
        evidence_id = _evidence_id(event_id, source_id)
        item = {
            "evidence_id": evidence_id,
            "event_id": event_id,
            "source_id": source_id,
            "claim_classification": classification,
            "claim_summary": claim_summary,
            "locator": locator,
            "source_checksum_sha256": source_checksum,
            "excerpt_sha256": excerpt_sha256,
            "quotation_allowed": quotation_allowed,
            "visual_reconstruction_allowed": False,
            "usage_restrictions": list(dict.fromkeys(restrictions)),
        }
        ApprovedEvidenceItem.from_mapping(item)
        evidence_items.append(item)
        return evidence_id

    quran_index = {
        item["event_id"]: item for item in quran_candidate["bindings"]
    }
    external_scope_index = {
        item["event_id"]: item for item in external_scope["events"]
    }
    external_pack_index = {
        item["event_id"]: item for item in external_pack["events"]
    }
    external_links = _source_link_index(external_pack)
    gap_index = {
        item["event_id"]: item for item in gap_approval["decisions"]
    }
    origin_index = {
        item["source_record_id"]: item
        for item in origin_classification["source_records"]
    }

    for integrated in integration["events"]:
        event_id = integrated["event_id"]
        disposition = integrated["disposition"]
        evidence_ids: list[str] = []
        rationale = ""
        qualification = None

        if event_id in quran_index:
            binding = quran_index[event_id]
            for raw in binding["evidence_items"]:
                source_id = raw["source_record_id"]
                checksum = raw["source_materialization_sha256"]
                register_source(
                    source_id=source_id,
                    title=raw["locator"],
                    source_type="QURAN",
                    checksum=checksum,
                    event_id=event_id,
                    locator=raw["locator"],
                    quotation_allowed=True,
                )
                evidence_ids.append(
                    append_evidence(
                        event_id=event_id,
                        source_id=source_id,
                        classification="quran_explicit",
                        claim_summary=binding["claim_scope"],
                        locator=raw["locator"],
                        source_checksum=checksum,
                        excerpt_sha256=raw["excerpt_sha256"],
                        quotation_allowed=True,
                        restrictions=list(binding["excluded_scope"]),
                    )
                )
            rationale = (
                "نص قرآني صريح بمصدر وموضع وبصمات مادية مكتملة، "
                "مع اعتماد روتيني مفوض."
            )

        elif event_id in external_scope_index:
            scope_event = external_scope_index[event_id]
            pack_event = external_pack_index[event_id]
            if scope_event["human_decision"]:
                selected_ids = list(
                    scope_event["source_candidate_ids"]
                )
            else:
                selected_ids = list(
                    scope_event["effective_source_candidate_ids"]
                )
            if not selected_ids:
                raise FullEpisodeCandidateError(
                    f"No external sources selected for {event_id}."
                )
            for source_id in selected_ids:
                link = external_links[event_id].get(source_id)
                if link is None:
                    raise FullEpisodeCandidateError(
                        f"Missing external source link: {event_id}/{source_id}"
                    )
                is_quran = source_id.startswith("SRC-QURAN-")
                classification = (
                    "quran_explicit"
                    if is_quran
                    else "authentic_sunnah"
                )
                source_type = (
                    "QURAN" if is_quran else "HADITH"
                )
                checksum = link["source_candidate_sha256"]
                register_source(
                    source_id=source_id,
                    title=link["locator"],
                    source_type=source_type,
                    checksum=checksum,
                    event_id=event_id,
                    locator=link["locator"],
                    quotation_allowed=True,
                )
                evidence_ids.append(
                    append_evidence(
                        event_id=event_id,
                        source_id=source_id,
                        classification=classification,
                        claim_summary=_claim_summary_for_external(
                            pack_event, source_id
                        ),
                        locator=link["locator"],
                        source_checksum=checksum,
                        excerpt_sha256=link[
                            "arabic_anchor_sha256"
                        ],
                        quotation_allowed=True,
                        restrictions=[
                            *pack_event["scope_limitations"],
                            "لا تتجاوز دلالة النص المعتمد",
                            "لا تجسيد لذوات غيبية أو مقدسة",
                        ],
                    )
                )
            rationale = (
                "قرار نطاق نهائي يجمع المصادر المتحققة والقرار البشري "
                "أو التفويض الروتيني المسجل."
            )
            if disposition == "include_qualified":
                qualification = QUALIFICATION_LABELS.get(
                    event_id,
                    "ذكر مؤهل ضمن قيود النطاق المعتمدة",
                )

        elif event_id in gap_index:
            for source_id in GAP_SOURCE_IDS[event_id]:
                record = origin_index[source_id]
                classification = _origin_to_claim_classification(
                    record["origin_classification"]
                )
                source_type = _source_type_from_classification(
                    classification
                )
                checksum = canonical_sha256(record)
                locator = _gap_locator(record)
                quotation_allowed = classification in {
                    "authentic_sunnah",
                    "accepted_athar",
                }
                register_source(
                    source_id=source_id,
                    title=str(record.get("work", source_id)),
                    source_type=source_type,
                    checksum=checksum,
                    event_id=event_id,
                    locator=locator,
                    quotation_allowed=quotation_allowed,
                )
                claim = GAP_CLAIMS[source_id]
                evidence_ids.append(
                    append_evidence(
                        event_id=event_id,
                        source_id=source_id,
                        classification=classification,
                        claim_summary=claim,
                        locator=locator,
                        source_checksum=checksum,
                        excerpt_sha256=text_sha256(claim),
                        quotation_allowed=quotation_allowed,
                        restrictions=[
                            "يلتزم قرار الفجوة البشري السابق",
                            "التفسير والإسرائيليات منسوبة بلا جزم",
                            "لا تجسيد غيبي أو نبوي",
                        ],
                    )
                )
            rationale = (
                "قرار بشري سابق محدود النطاق مع تصنيف أصل كل سجل."
            )
            if disposition == "include_qualified":
                qualification = QUALIFICATION_LABELS[event_id]

        elif event_id == EDITORIAL_EVENT_ID:
            if editorial_decision["disposition"] != "editorial_only":
                raise FullEpisodeCandidateError(
                    "Editorial event 099 disposition changed."
                )
            rationale = editorial_decision["function"]

        else:
            raise FullEpisodeCandidateError(
                f"No candidate builder route for {event_id}"
            )

        decision = {
            "event_id": event_id,
            "disposition": disposition,
            "evidence_ids": evidence_ids,
            "qualification_label": qualification,
            "rationale": rationale,
        }
        EventEvidenceDecision.from_mapping(decision)
        decisions.append(decision)

    for source_id, item in source_items.items():
        item["notes"]["supports_event_ids"] = sorted(
            source_supports[source_id]
        )

    source_list = sorted(
        source_items.values(),
        key=lambda item: item["source_id"],
    )
    source_candidate = {
        "schema_version": SOURCE_CANDIDATE_SCHEMA,
        "target_schema_version": "siraj-approved-source-package-v1",
        "status": "FINAL_HUMAN_APPROVAL_PENDING",
        "package_status": "CANDIDATE_NOT_APPROVED",
        "episode_id": "episode-001-adam",
        "source_count": len(source_list),
        "source_items": source_list,
        "human_approval": False,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "live_provider_execution": LIVE_EXECUTION,
    }
    source_candidate["input_fingerprint"] = canonical_sha256(
        source_candidate
    )
    source_candidate["candidate_id"] = (
        "adam_source_package_candidate_"
        + source_candidate["input_fingerprint"][:16]
    )

    evidence_candidate = {
        "schema_version": EVIDENCE_CANDIDATE_SCHEMA,
        "target_schema_version": TARGET_EVIDENCE_SCHEMA,
        "status": "FINAL_HUMAN_APPROVAL_PENDING",
        "package_id": (
            "adam_approved_evidence_candidate_"
            + canonical_sha256(evidence_items)[:16]
        ),
        "episode_id": "episode-001-adam",
        "source_package_fingerprint": source_candidate[
            "input_fingerprint"
        ],
        "approval": {
            "approval_id": "",
            "approved_by": "",
            "approved_at": "",
            "approval_status": "PENDING",
            "human_approval": False,
            "notes": "",
        },
        "evidence_item_count": len(evidence_items),
        "evidence_items": evidence_items,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "live_provider_execution": LIVE_EXECUTION,
    }
    evidence_candidate["candidate_fingerprint"] = canonical_sha256(
        evidence_candidate
    )

    adjudication_candidate = {
        "schema_version": ADJUDICATION_CANDIDATE_SCHEMA,
        "target_schema_version": TARGET_ADJUDICATION_SCHEMA,
        "status": "FINAL_HUMAN_APPROVAL_PENDING",
        "adjudication_id": (
            "adam_event_adjudication_candidate_"
            + canonical_sha256(decisions)[:16]
        ),
        "episode_id": "episode-001-adam",
        "evidence_package_id": evidence_candidate["package_id"],
        "approval": {
            "approval_id": "",
            "approved_by": "",
            "approved_at": "",
            "approval_status": "PENDING",
            "human_approval": False,
            "notes": "",
        },
        "decision_count": len(decisions),
        "decisions": decisions,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "live_provider_execution": LIVE_EXECUTION,
    }
    adjudication_candidate["candidate_fingerprint"] = (
        canonical_sha256(adjudication_candidate)
    )

    validate_candidates(
        source_candidate=source_candidate,
        evidence_candidate=evidence_candidate,
        adjudication_candidate=adjudication_candidate,
    )
    return (
        source_candidate,
        evidence_candidate,
        adjudication_candidate,
    )


def validate_candidates(
    *,
    source_candidate: Mapping[str, object],
    evidence_candidate: Mapping[str, object],
    adjudication_candidate: Mapping[str, object],
) -> None:
    sources = source_candidate.get("source_items")
    evidence = evidence_candidate.get("evidence_items")
    decisions = adjudication_candidate.get("decisions")
    if not isinstance(sources, list):
        raise FullEpisodeCandidateError("Source candidate items missing.")
    if not isinstance(evidence, list):
        raise FullEpisodeCandidateError("Evidence candidate items missing.")
    if not isinstance(decisions, list):
        raise FullEpisodeCandidateError(
            "Adjudication candidate decisions missing."
        )
    if len(decisions) != EXPECTED_EVENT_COUNT:
        raise FullEpisodeCandidateError(
            "Candidate adjudication must resolve all 37 events."
        )

    source_index = {item["source_id"]: item for item in sources}
    if len(source_index) != len(sources):
        raise FullEpisodeCandidateError("Candidate source ids duplicate.")

    evidence_index = {}
    for item in evidence:
        parsed = ApprovedEvidenceItem.from_mapping(item)
        if parsed.evidence_id in evidence_index:
            raise FullEpisodeCandidateError(
                "Candidate evidence ids duplicate."
            )
        evidence_index[parsed.evidence_id] = item
        source = source_index.get(parsed.source_id)
        if source is None:
            raise FullEpisodeCandidateError(
                f"Evidence source missing: {parsed.source_id}"
            )
        if source["checksum"] != parsed.source_checksum_sha256:
            raise FullEpisodeCandidateError(
                f"Evidence/source checksum mismatch: {parsed.evidence_id}"
            )
        if parsed.event_id not in source["notes"]["supports_event_ids"]:
            raise FullEpisodeCandidateError(
                f"Source event support missing: {parsed.evidence_id}"
            )

    referenced: list[str] = []
    event_ids: list[str] = []
    for item in decisions:
        parsed = EventEvidenceDecision.from_mapping(item)
        event_ids.append(parsed.event_id)
        referenced.extend(parsed.evidence_ids)
    if len(set(event_ids)) != EXPECTED_EVENT_COUNT:
        raise FullEpisodeCandidateError(
            "Candidate adjudication event ids duplicate."
        )
    if len(referenced) != len(set(referenced)):
        raise FullEpisodeCandidateError(
            "Candidate evidence item reused by multiple events."
        )
    if set(referenced) != set(evidence_index):
        raise FullEpisodeCandidateError(
            "Candidate evidence contains orphans or missing references."
        )
    editorial = [
        item for item in decisions
        if item["disposition"] == "editorial_only"
    ]
    if len(editorial) != 1 or editorial[0]["event_id"] != EDITORIAL_EVENT_ID:
        raise FullEpisodeCandidateError(
            "Exactly event 099 must be editorial-only."
        )


def build_approval_request(
    *,
    integration: Mapping[str, object],
    source_candidate: Mapping[str, object],
    evidence_candidate: Mapping[str, object],
    adjudication_candidate: Mapping[str, object],
) -> dict:
    request = {
        "schema_version": APPROVAL_REQUEST_SCHEMA,
        "status": "FINAL_HUMAN_APPROVAL_REQUIRED",
        "episode_id": "episode-001-adam",
        "integration_id": integration["integration_id"],
        "event_count": EXPECTED_EVENT_COUNT,
        "source_count": source_candidate["source_count"],
        "evidence_item_count": evidence_candidate[
            "evidence_item_count"
        ],
        "decision_count": adjudication_candidate["decision_count"],
        "source_package_input_fingerprint": source_candidate[
            "input_fingerprint"
        ],
        "evidence_candidate_fingerprint": evidence_candidate[
            "candidate_fingerprint"
        ],
        "adjudication_candidate_fingerprint": adjudication_candidate[
            "candidate_fingerprint"
        ],
        "exact_approval_phrase": APPROVAL_PHRASE,
        "exact_approval_phrase_sha256": text_sha256(
            APPROVAL_PHRASE
        ),
        "approval_effect": [
            "تحويل المرشحات إلى حزمة مصدر وأدلة وتحكيم معتمدة بشريًا",
            "تحديث مراجع الحلقة وبصماتها",
            "فتح بوابة الأدلة بالربط غير المتصل فقط",
            "إبقاء تشغيل Runware وأي مزود مدفوع أو مباشر محظورًا",
        ],
        "human_approval": False,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "live_provider_execution": LIVE_EXECUTION,
    }
    request["request_id"] = (
        "adam_final_evidence_approval_request_"
        + canonical_sha256(request)[:16]
    )
    return request


def write_outputs(
    *,
    output_root: Path,
    editorial_decision: Mapping[str, object],
    integration: Mapping[str, object],
    source_candidate: Mapping[str, object],
    evidence_candidate: Mapping[str, object],
    adjudication_candidate: Mapping[str, object],
    approval_request: Mapping[str, object],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "editorial": output_root
        / "editorial-event-099-delegated-decision-v1.json",
        "integration": output_root
        / "full-episode-evidence-integration-v1.json",
        "source_candidate": output_root
        / "source-package-v1.approval-candidate.json",
        "evidence_candidate": output_root
        / "approved-evidence-package-v1.candidate.json",
        "adjudication_candidate": output_root
        / "event-evidence-adjudication-v1.candidate.json",
        "approval_request": output_root
        / "final-evidence-human-approval-request-v1.json",
        "summary": output_root
        / "full-episode-evidence-candidate-summary.csv",
        "readme": output_root / "README.md",
    }
    write_json(outputs["editorial"], editorial_decision)
    write_json(outputs["integration"], integration)
    write_json(outputs["source_candidate"], source_candidate)
    write_json(outputs["evidence_candidate"], evidence_candidate)
    write_json(
        outputs["adjudication_candidate"],
        adjudication_candidate,
    )
    write_json(outputs["approval_request"], approval_request)

    with outputs["summary"].open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        fields = [
            "event_id",
            "order",
            "title",
            "route",
            "disposition",
            "approval_origin",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in integration["events"]:
            writer.writerow({field: item[field] for field in fields})

    outputs["readme"].write_text(
        "# Adam full-episode evidence candidate v1\n\n"
        "All thirty-seven required episode events are resolved into a "
        "single ordered candidate: nineteen Quran-explicit events, fourteen "
        "external-source events, three previously human-approved gap events, "
        "and one delegated editorial transition. Source, evidence and event-"
        "adjudication candidates are structurally compatible with the strict "
        "binder, but their approval records remain empty. The final request "
        "contains exact candidate fingerprints and one exact Arabic approval "
        "phrase. Until that phrase is explicitly provided, no approved package "
        "is created and the evidence gate remains withheld. Provider execution "
        "remains blocked even after a later offline evidence binding.\n",
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
