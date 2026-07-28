"""Delegated hadith research and routine event-scope adjudication."""
from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from collections import Counter
from pathlib import Path
from typing import Mapping

RESEARCH_SCHEMA = "siraj-delegated-hadith-authentication-research-v1"
EVENT_SCOPE_SCHEMA = "siraj-routine-event-scope-adjudication-v1"
DOSSIER_SCHEMA = "siraj-high-importance-evidence-review-dossier-v1"

GATE = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTO_APPROVAL = "FORBIDDEN"
LIVE_EXECUTION = "BLOCKED"

EXPECTED_SOURCE_COUNT = 11
EXPECTED_DELEGATED_SOURCE_COUNT = 8
EXPECTED_HIGH_IMPORTANCE_SOURCE_COUNT = 3
EXPECTED_EVENT_COUNT = 14
EXPECTED_ROUTINE_EVENT_COUNT = 8
EXPECTED_COMPLEX_EVENT_COUNT = 6

ROUTINE_SOURCE_IDS = (
    "SRC-BUKHARI-3191",
    "SRC-BUKHARI-3326",
    "SRC-BUKHARI-3331",
    "SRC-MUSLIM-1468A",
    "SRC-MUSLIM-2611A",
    "SRC-MUSLIM-2653B",
    "SRC-MUSLIM-2996",
    "SRC-TIRMIDHI-3076",
)

HIGH_IMPORTANCE_SOURCE_IDS = (
    "SRC-ABUDAWUD-4700",
    "SRC-MUSLIM-2841",
    "SRC-TIRMIDHI-2155",
)

COMPLEX_EVENT_IDS = (
    "EV-ADAM-003",
    "EV-ADAM-007",
    "EV-ADAM-021",
    "EV-ADAM-042",
    "EV-ADAM-061",
    "EV-ADAM-070",
)

ROUTINE_EVENT_IDS = (
    "EV-ADAM-001",
    "EV-ADAM-002",
    "EV-ADAM-005",
    "EV-ADAM-023",
    "EV-ADAM-024",
    "EV-ADAM-032",
    "EV-ADAM-033",
    "EV-ADAM-060",
)

HIGH_IMPORTANCE_TREATMENTS = {
    "chronology_interpretation_review_required",
    "scholarly_interpretation_review_required",
    "supported_synthesis_human_review_required",
    "hadith_authority_review_required",
    "theological_interpretation_review_required",
}

RESEARCH_RECORDS = {
    "SRC-BUKHARI-3191": {
        "collection": "Sahih al-Bukhari",
        "record_number": "3191",
        "source_url": "https://sunnah.com/bukhari:3191",
        "authentication_result": "SAHIH_BY_COLLECTION",
        "authentication_authority": "Sahih al-Bukhari",
        "origin_classification": "MARFU_PROPHETIC_HADITH",
        "decision": "ACCEPT_ROUTINE",
        "claim_scope": [
            "كان الله ولم يكن شيء غيره",
            "كان عرشه على الماء",
            "كتب في الذكر كل شيء",
            "خلق السماوات والأرض",
        ],
        "scope_limitations": [
            "لا يستنبط من هذا السجل وحده ترتيب جميع المخلوقات",
            "لا يحسم ترتيب العرش والقلم من هذا السجل وحده",
        ],
    },
    "SRC-BUKHARI-3326": {
        "collection": "Sahih al-Bukhari",
        "record_number": "3326",
        "source_url": "https://sunnah.com/bukhari:3326",
        "authentication_result": "SAHIH_BY_COLLECTION",
        "authentication_authority": "Sahih al-Bukhari",
        "origin_classification": "MARFU_PROPHETIC_HADITH",
        "decision": "ACCEPT_ROUTINE",
        "claim_scope": [
            "خلق آدم وطوله ستون ذراعا",
            "تعليم آدم تحية السلام",
            "رد الملائكة وزيادتهم ورحمة الله",
        ],
        "scope_limitations": [
            "لا يستخدم لإثبات تفسير عقدي لعبارة الصورة",
        ],
    },
    "SRC-BUKHARI-3331": {
        "collection": "Sahih al-Bukhari",
        "record_number": "3331",
        "source_url": "https://sunnah.com/bukhari:3331",
        "authentication_result": "SAHIH_BY_COLLECTION",
        "authentication_authority": "Sahih al-Bukhari",
        "origin_classification": "MARFU_PROPHETIC_HADITH",
        "decision": "ACCEPT_ROUTINE",
        "claim_scope": [
            "المرأة خلقت من ضلع",
            "الوصية بالنساء",
        ],
        "scope_limitations": [
            "اللفظ لا يسمي حواء",
            "ربط الحديث بزوج آدم تركيب استدلالي يحتاج قرار نطاق مستقل",
        ],
    },
    "SRC-MUSLIM-1468A": {
        "collection": "Sahih Muslim",
        "record_number": "1468a",
        "source_url": "https://sunnah.com/muslim:1468a",
        "authentication_result": "SAHIH_BY_COLLECTION",
        "authentication_authority": "Sahih Muslim",
        "origin_classification": "MARFU_PROPHETIC_HADITH",
        "decision": "ACCEPT_ROUTINE",
        "claim_scope": [
            "المرأة خلقت من ضلع",
            "الوصية بالنساء خيرا",
        ],
        "scope_limitations": [
            "اللفظ لا يسمي حواء",
            "لا يعتمد وحده لإثبات كل تفاصيل خلق زوج آدم",
        ],
    },
    "SRC-MUSLIM-2611A": {
        "collection": "Sahih Muslim",
        "record_number": "2611a",
        "source_url": "https://sunnah.com/muslim:2611a",
        "authentication_result": "SAHIH_BY_COLLECTION",
        "authentication_authority": "Sahih Muslim",
        "origin_classification": "MARFU_PROPHETIC_HADITH",
        "decision": "ACCEPT_ROUTINE",
        "claim_scope": [
            "صور الله آدم في الجنة",
            "تركه مدة شاءها",
            "طاف إبليس به ونظر إليه",
            "كان جسد آدم أجوف",
        ],
        "scope_limitations": [
            "لا تحدد مدة الترك",
            "لا تضاف تفاصيل غير موجودة عن كيفية الجسد أو زمن نفخ الروح",
        ],
    },
    "SRC-MUSLIM-2653B": {
        "collection": "Sahih Muslim",
        "record_number": "2653b",
        "source_url": "https://sunnah.com/muslim:2653b",
        "authentication_result": "SAHIH_BY_COLLECTION",
        "authentication_authority": "Sahih Muslim",
        "origin_classification": "MARFU_PROPHETIC_HADITH",
        "decision": "ACCEPT_ROUTINE",
        "claim_scope": [
            "كتبت مقادير الخلائق قبل خلق السماوات والأرض بخمسين ألف سنة",
            "كان العرش على الماء",
        ],
        "scope_limitations": [
            "لا يحسم وحده تفسير أولية القلم",
        ],
    },
    "SRC-MUSLIM-2996": {
        "collection": "Sahih Muslim",
        "record_number": "2996",
        "source_url": "https://sunnah.com/muslim:2996",
        "authentication_result": "SAHIH_BY_COLLECTION",
        "authentication_authority": "Sahih Muslim",
        "origin_classification": "MARFU_PROPHETIC_HADITH",
        "decision": "ACCEPT_ROUTINE",
        "claim_scope": [
            "خلقت الملائكة من نور",
            "خلق الجان من مارج من نار",
            "خلق آدم مما وصف في القرآن",
        ],
        "scope_limitations": [
            "لا يحدد ترتيب خلق الملائكة بالنسبة إلى العرش والقلم",
        ],
    },
    "SRC-TIRMIDHI-3076": {
        "collection": "Jami at-Tirmidhi",
        "record_number": "3076",
        "source_url": "https://sunnah.com/tirmidhi:3076",
        "authentication_result": (
            "HASAN_SAHIH_BY_AL_TIRMIDHI_AND_HASAN_BY_DARUSSALAM"
        ),
        "authentication_authority": (
            "Al-Tirmidhi; Darussalam edition grading"
        ),
        "origin_classification": "MARFU_PROPHETIC_HADITH",
        "decision": "ACCEPT_ROUTINE_WITH_GRADE_NOTE",
        "claim_scope": [
            "مسح ظهر آدم وإظهار ذريته",
            "قصة آدم وداود في العمر",
        ],
        "scope_limitations": [
            "تذكر درجة الترمذي ودرجة دار السلام عند التوثيق",
            "ربط الحديث بتفسير آية الميثاق يحتاج قرار نطاق مستقل",
        ],
    },
    "SRC-ABUDAWUD-4700": {
        "collection": "Sunan Abi Dawud",
        "record_number": "4700",
        "source_url": "https://sunnah.com/abudawud:4700",
        "authentication_result": "SAHIH_BY_AL_ALBANI",
        "authentication_authority": "Al-Albani grading on Sunan Abi Dawud",
        "origin_classification": "MARFU_PROPHETIC_HADITH",
        "decision": "RESEARCH_COMPLETE_USER_REVIEW_REQUIRED",
        "claim_scope": [
            "أول ما خلق الله القلم",
            "أمر القلم بكتابة مقادير كل شيء",
        ],
        "scope_limitations": [
            "لا يعتمد تفسير الأولية المطلقة آليا",
            "يفصل ثبوت الحديث عن الجمع بينه وبين نص العرش على الماء",
        ],
    },
    "SRC-MUSLIM-2841": {
        "collection": "Sahih Muslim",
        "record_number": "2841",
        "source_url": "https://sunnah.com/muslim:2841",
        "authentication_result": "SAHIH_BY_COLLECTION",
        "authentication_authority": "Sahih Muslim",
        "origin_classification": "MARFU_PROPHETIC_HADITH",
        "decision": "RESEARCH_COMPLETE_USER_REVIEW_REQUIRED",
        "claim_scope": [
            "طول آدم ستون ذراعا",
            "تعليم آدم تحية السلام",
            "عبارة خلق آدم على صورته",
        ],
        "scope_limitations": [
            "تفسير الضمير في على صورته مسألة عقدية خارج القرار الآلي",
            "يمكن الاستغناء عنه في الطول والسلام بصحيح البخاري 3326",
        ],
    },
    "SRC-TIRMIDHI-2155": {
        "collection": "Jami at-Tirmidhi",
        "record_number": "2155",
        "source_url": "https://sunnah.com/tirmidhi:2155",
        "authentication_result": (
            "GHARIB_FROM_THIS_ROUTE_BY_AL_TIRMIDHI_AND_SAHIH_BY_DARUSSALAM"
        ),
        "authentication_authority": (
            "Al-Tirmidhi route note; Darussalam edition grading"
        ),
        "origin_classification": "MARFU_PROPHETIC_HADITH",
        "decision": "RESEARCH_COMPLETE_USER_REVIEW_REQUIRED",
        "claim_scope": [
            "أول ما خلق الله القلم",
            "أمر القلم بكتابة القدر إلى الأبد",
        ],
        "scope_limitations": [
            "يثبت اختلاف وصف الطريق عن الحكم النهائي في الطبعات الحديثة",
            "لا يعتمد تفسير الأولية المطلقة آليا",
        ],
    },
}

COMPLEX_RECOMMENDATIONS = {
    "EV-ADAM-003": {
        "recommended_disposition": "include_qualified",
        "recommended_narration": (
            "كتب الله مقادير الخلائق قبل خلق السماوات والأرض بخمسين ألف "
            "سنة، وكان عرشه على الماء. وورد في حديث القلم أن الله أمره "
            "بكتابة المقادير؛ ولا يجزم السرد هنا بأن القلم أول المخلوقات "
            "على الإطلاق."
        ),
        "reason": "جمع آمن بين النصوص دون حسم ترتيب العرش والماء والقلم.",
        "user_question": (
            "هل تعتمد الصياغة المؤهلة التي تثبت الكتابة وتترك الأولية "
            "المطلقة بلا جزم؟"
        ),
    },
    "EV-ADAM-007": {
        "recommended_disposition": "include_qualified",
        "recommended_narration": (
            "كان إبليس من الجن، وحضر أمر السجود لآدم فامتنع واستكبر. "
            "ولا يثبت من هذه الآيات وحدها تاريخ وجود إبليس الفرد قبل بدء "
            "خلق آدم."
        ),
        "reason": "فصل النص الصريح عن التركيب الزمني غير الصريح.",
        "user_question": "هل تعتمد حذف الجزم بوجود إبليس قبل بدء خلق آدم؟",
    },
    "EV-ADAM-021": {
        "recommended_disposition": "include_qualified",
        "recommended_narration": (
            "وصف القرآن مادة خلق الإنسان بالتراب والطين اللازب والحمإ "
            "المسنون والصلصال كالفخار، من غير جزم في الحلقة بمدة كل وصف "
            "أو ترتيب زمني تفصيلي بينها."
        ),
        "reason": "الأوصاف ثابتة، أما تحويلها إلى جدول زمني فاجتهاد تفسيري.",
        "user_question": "هل تعتمد عرض الأوصاف بلا جدول زمني جازم؟",
    },
    "EV-ADAM-042": {
        "recommended_disposition": "include_assertive_with_scope_limit",
        "recommended_narration": (
            "علم الله آدم الأسماء كلها، ثم أظهر للملائكة ما خصه به من "
            "العلم، فأقروا أن لا علم لهم إلا ما علمهم الله."
        ),
        "reason": "صياغة مباشرة ضمن حدود البقرة 31-33.",
        "user_question": (
            "هل تعتمد الاقتصار على النص القرآني دون تحديد ماهية الأسماء "
            "بتفصيل غير ثابت؟"
        ),
    },
    "EV-ADAM-061": {
        "recommended_disposition": "include_qualified",
        "recommended_narration": (
            "ورد في حديث حسنه الترمذي وصححه، ودرجته دار السلام حسنا، أن "
            "الله مسح ظهر آدم فأظهر ذريته له؛ وتبقى كيفية ربطه بآية "
            "الميثاق مسألة تفسيرية مستقلة."
        ),
        "reason": "ذكر اختلاف عبارة الدرجة وفصل متن الحديث عن تفسير الآية.",
        "user_question": (
            "هل تعتمد إدراج الحديث بهذه الصياغة المؤهلة دون جعله التفسير "
            "الوحيد لآية الميثاق؟"
        ),
    },
    "EV-ADAM-070": {
        "recommended_disposition": "include_qualified",
        "recommended_narration": (
            "خلق الله زوج آدم منه، وثبت في الحديث الصحيح أن المرأة خلقت "
            "من ضلع. أما تسمية حواء وربط لفظ الضلع بها صراحة فليس واردا "
            "بهذا اللفظ في الآية أو الحديثين المستخدمين هنا."
        ),
        "reason": "تمييز النص القرآني والحديث الصحيح عن التركيب التفسيري.",
        "user_question": (
            "هل تعتمد الصياغة الجامعة مع التصريح بأن اسم حواء غير وارد "
            "في هذه الأدلة المحددة؟"
        ),
    },
}


class DelegatedAdjudicationError(ValueError):
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


def read_json(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DelegatedAdjudicationError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise DelegatedAdjudicationError(f"Expected object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def validate_inputs(
    *,
    ingestion: Mapping[str, object],
    queue: Mapping[str, object],
    external_pack: Mapping[str, object],
    decision: Mapping[str, object],
    delegation: Mapping[str, object],
) -> None:
    if ingestion.get("schema_version") != "siraj-source-review-ingestion-v1":
        raise DelegatedAdjudicationError("Unexpected ingestion schema.")
    if ingestion.get("source_count") != 22:
        raise DelegatedAdjudicationError("Expected 22 ingested sources.")
    if queue.get("schema_version") != (
        "siraj-delegated-evidence-escalation-queue-v1"
    ):
        raise DelegatedAdjudicationError("Unexpected queue schema.")
    if queue.get("hadith_source_count") != EXPECTED_SOURCE_COUNT:
        raise DelegatedAdjudicationError("Expected eleven hadith sources.")
    if queue.get("ai_delegated_source_count") != (
        EXPECTED_DELEGATED_SOURCE_COUNT
    ):
        raise DelegatedAdjudicationError(
            "Expected eight delegated hadith sources."
        )
    if queue.get("user_escalation_source_count") != (
        EXPECTED_HIGH_IMPORTANCE_SOURCE_COUNT
    ):
        raise DelegatedAdjudicationError(
            "Expected three high-importance sources."
        )
    if external_pack.get("event_count") != EXPECTED_EVENT_COUNT:
        raise DelegatedAdjudicationError("Expected fourteen events.")
    if external_pack.get("event_source_link_count") != 28:
        raise DelegatedAdjudicationError(
            "Expected twenty-eight event/source links."
        )
    if decision.get("human_approval") is not True:
        raise DelegatedAdjudicationError("Human source review is not approved.")
    scope = delegation.get("delegation_scope", {})
    if scope.get("routine_evidence") != "AI_DECISION_AUTHORIZED":
        raise DelegatedAdjudicationError(
            "Routine evidence delegation is absent."
        )
    if (
        scope.get("complex_or_high_importance_evidence")
        != "USER_REVIEW_REQUIRED"
    ):
        raise DelegatedAdjudicationError(
            "High-importance escalation guard is absent."
        )
    queue_ids = {
        item["source_candidate_id"] for item in queue["source_items"]
    }
    if queue_ids != set(RESEARCH_RECORDS):
        raise DelegatedAdjudicationError(
            "Research table does not cover the exact queue sources."
        )


def build_hadith_research(
    *,
    ingestion: Mapping[str, object],
    queue: Mapping[str, object],
) -> dict:
    records = []
    queue_index = {
        item["source_candidate_id"]: item for item in queue["source_items"]
    }
    for source_id in sorted(RESEARCH_RECORDS):
        base = dict(RESEARCH_RECORDS[source_id])
        queue_item = queue_index[source_id]
        delegated = source_id in ROUTINE_SOURCE_IDS
        record = {
            "source_candidate_id": source_id,
            **base,
            "event_ids": list(queue_item["event_ids"]),
            "source_text_locator_verified": True,
            "research_complete": True,
            "delegated_ai_decision": delegated,
            "delegated_authentication_accepted": delegated,
            "final_user_review_required": not delegated,
            "authentication_verified_by_human": False,
            "origin_classification_verified_by_human": False,
            "research_date": "2026-07-28",
        }
        records.append(record)

    artifact = {
        "schema_version": RESEARCH_SCHEMA,
        "status": "DELEGATED_HADITH_RESEARCH_COMPLETE",
        "episode_id": "episode-001-adam",
        "source_review_ingestion_id": ingestion["ingestion_id"],
        "source_count": len(records),
        "delegated_source_count": sum(
            item["delegated_ai_decision"] for item in records
        ),
        "high_importance_source_count": sum(
            item["final_user_review_required"] for item in records
        ),
        "research_complete_count": sum(
            item["research_complete"] for item in records
        ),
        "delegated_authentication_accepted_count": sum(
            item["delegated_authentication_accepted"] for item in records
        ),
        "records": records,
        "source_authentication_research_complete": True,
        "routine_source_decisions_complete": True,
        "high_importance_source_decisions_complete": False,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    artifact["research_id"] = (
        "adam_delegated_hadith_research_"
        + canonical_sha256(artifact)[:16]
    )
    return artifact


def _effective_sources(
    event: Mapping[str, object],
    research: Mapping[str, object],
) -> list[str]:
    accepted = {
        item["source_candidate_id"]
        for item in research["records"]
        if item["delegated_authentication_accepted"]
    }
    result = []
    for source_id in event["source_candidate_ids"]:
        if source_id.startswith("SRC-QURAN-") or source_id in accepted:
            result.append(source_id)
    return sorted(result)


def _claim_supported(
    layer: Mapping[str, object],
    effective_sources: set[str],
) -> bool:
    return bool(set(layer.get("support", [])) & effective_sources)


def build_event_scope_adjudication(
    *,
    ingestion: Mapping[str, object],
    external_pack: Mapping[str, object],
    research: Mapping[str, object],
) -> dict:
    rows = []
    for event in sorted(
        external_pack["events"],
        key=lambda item: item["event_id"],
    ):
        event_id = event["event_id"]
        treatments = sorted(
            {
                layer.get("treatment", "")
                for layer in event.get("claim_layers", [])
            }
        )
        effective = _effective_sources(event, research)
        effective_set = set(effective)
        claims_supported = all(
            _claim_supported(layer, effective_set)
            for layer in event.get("claim_layers", [])
            if layer.get("treatment") == "assertive_candidate"
        )
        complex_event = event_id in COMPLEX_EVENT_IDS
        if event_id not in set(COMPLEX_EVENT_IDS) | set(ROUTINE_EVENT_IDS):
            raise DelegatedAdjudicationError(
                f"Unclassified event: {event_id}"
            )
        delegated_approved = (
            not complex_event
            and claims_supported
            and bool(effective)
        )
        rows.append(
            {
                "event_id": event_id,
                "title": event["title"],
                "proposed_disposition": event["proposed_disposition"],
                "claim_treatments": treatments,
                "scope_limitations": list(event["scope_limitations"]),
                "all_source_candidate_ids": list(
                    event["source_candidate_ids"]
                ),
                "effective_source_candidate_ids": effective,
                "routine_delegation_applies": not complex_event,
                "delegated_ai_event_scope_approved": delegated_approved,
                "binding_ready_under_delegation": delegated_approved,
                "final_user_review_required": complex_event,
                "event_scope_status": (
                    "ROUTINE_EVENT_SCOPE_APPROVED"
                    if delegated_approved
                    else "HIGH_IMPORTANCE_REVIEW_REQUIRED"
                    if complex_event
                    else "ROUTINE_SUPPORT_INCOMPLETE"
                ),
            }
        )

    routine = [
        item for item in rows
        if item["delegated_ai_event_scope_approved"]
    ]
    complex_rows = [
        item for item in rows if item["final_user_review_required"]
    ]
    if len(routine) != EXPECTED_ROUTINE_EVENT_COUNT:
        raise DelegatedAdjudicationError(
            f"Expected eight routine events, got {len(routine)}."
        )
    if len(complex_rows) != EXPECTED_COMPLEX_EVENT_COUNT:
        raise DelegatedAdjudicationError(
            f"Expected six complex events, got {len(complex_rows)}."
        )

    artifact = {
        "schema_version": EVENT_SCOPE_SCHEMA,
        "status": "ROUTINE_EVENT_SCOPE_ADJUDICATION_COMPLETE",
        "episode_id": "episode-001-adam",
        "source_review_ingestion_id": ingestion["ingestion_id"],
        "hadith_research_id": research["research_id"],
        "event_count": len(rows),
        "routine_event_count": len(routine),
        "complex_event_count": len(complex_rows),
        "delegated_approved_event_count": len(routine),
        "events": rows,
        "routine_event_scope_complete": True,
        "complex_event_scope_complete": False,
        "event_binding_complete": False,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    artifact["adjudication_id"] = (
        "adam_routine_event_scope_"
        + canonical_sha256(artifact)[:16]
    )
    return artifact


def build_high_importance_dossier(
    *,
    ingestion: Mapping[str, object],
    research: Mapping[str, object],
    event_scope: Mapping[str, object],
) -> dict:
    source_index = {
        item["source_candidate_id"]: item
        for item in research["records"]
    }
    event_index = {
        item["event_id"]: item for item in event_scope["events"]
    }
    source_items = [
        {
            "source_candidate_id": source_id,
            "collection": source_index[source_id]["collection"],
            "record_number": source_index[source_id]["record_number"],
            "source_url": source_index[source_id]["source_url"],
            "authentication_result": source_index[source_id][
                "authentication_result"
            ],
            "authentication_authority": source_index[source_id][
                "authentication_authority"
            ],
            "claim_scope": source_index[source_id]["claim_scope"],
            "scope_limitations": source_index[source_id][
                "scope_limitations"
            ],
            "research_complete": True,
            "recommended_safe_action": (
                "ACCEPT_SOURCE_WITH_SCOPE_LIMITATIONS"
            ),
            "final_user_decision": "PENDING",
        }
        for source_id in HIGH_IMPORTANCE_SOURCE_IDS
    ]
    event_items = [
        {
            "event_id": event_id,
            "title": event_index[event_id]["title"],
            **COMPLEX_RECOMMENDATIONS[event_id],
            "effective_source_candidate_ids": event_index[event_id][
                "effective_source_candidate_ids"
            ],
            "final_user_decision": "PENDING",
        }
        for event_id in COMPLEX_EVENT_IDS
    ]

    dossier = {
        "schema_version": DOSSIER_SCHEMA,
        "status": "HIGH_IMPORTANCE_RESEARCH_COMPLETE_USER_DECISIONS_PENDING",
        "episode_id": "episode-001-adam",
        "source_review_ingestion_id": ingestion["ingestion_id"],
        "hadith_research_id": research["research_id"],
        "event_scope_adjudication_id": event_scope["adjudication_id"],
        "source_item_count": len(source_items),
        "event_item_count": len(event_items),
        "source_items": source_items,
        "event_items": event_items,
        "research_complete": True,
        "recommendations_complete": True,
        "final_user_decisions_complete": False,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    dossier["dossier_id"] = (
        "adam_high_importance_dossier_"
        + canonical_sha256(dossier)[:16]
    )
    return dossier


def write_outputs(
    *,
    output_root: Path,
    research: Mapping[str, object],
    event_scope: Mapping[str, object],
    dossier: Mapping[str, object],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "research": output_root / "delegated-hadith-authentication-research-v1.json",
        "event_scope": output_root / "routine-event-scope-adjudication-v1.json",
        "dossier": output_root / "high-importance-evidence-review-dossier-v1.json",
        "summary": output_root / "delegated-adjudication-summary.csv",
        "readme": output_root / "README.md",
    }
    write_json(outputs["research"], research)
    write_json(outputs["event_scope"], event_scope)
    write_json(outputs["dossier"], dossier)

    with outputs["summary"].open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        fields = [
            "record_type",
            "record_id",
            "status",
            "user_review_required",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in research["records"]:
            writer.writerow(
                {
                    "record_type": "source",
                    "record_id": record["source_candidate_id"],
                    "status": record["decision"],
                    "user_review_required": record[
                        "final_user_review_required"
                    ],
                }
            )
        for event in event_scope["events"]:
            writer.writerow(
                {
                    "record_type": "event",
                    "record_id": event["event_id"],
                    "status": event["event_scope_status"],
                    "user_review_required": event[
                        "final_user_review_required"
                    ],
                }
            )

    outputs["readme"].write_text(
        "# Adam delegated evidence adjudication v1\n\n"
        "Research is complete for eleven hadith records. Eight routine "
        "records are accepted under the active user delegation; three "
        "high-importance records retain final user review. Eight routine "
        "events have delegated scope approval. Six complex events are "
        "reduced to a focused dossier with safe recommendations. No full "
        "episode adjudication, approved evidence package, gate opening, "
        "or provider execution is produced by this stage.\n",
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
