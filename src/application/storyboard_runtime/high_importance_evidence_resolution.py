"""Resolve Adam high-importance evidence from explicit user decisions."""
from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Mapping

APPROVAL_SCHEMA = "siraj-high-importance-evidence-human-approval-v1"
FINAL_SCOPE_SCHEMA = "siraj-external-event-scope-final-adjudication-v1"
PROGRESS_SCHEMA = "siraj-episode-evidence-adjudication-progress-v1"

GATE = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTO_APPROVAL = "FORBIDDEN"
LIVE_EXECUTION = "BLOCKED"

EXPECTED_ROUTINE_EVENT_COUNT = 8
EXPECTED_HIGH_IMPORTANCE_EVENT_COUNT = 6
EXPECTED_FINAL_EVENT_COUNT = 14
EXPECTED_HIGH_IMPORTANCE_SOURCE_COUNT = 3

HIGH_IMPORTANCE_SOURCE_IDS = (
    "SRC-ABUDAWUD-4700",
    "SRC-MUSLIM-2841",
    "SRC-TIRMIDHI-2155",
)

HIGH_IMPORTANCE_EVENT_IDS = (
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

USER_DECISION_TEXT = """القلم هو اول مخلوق بنص الحديث فالدليل فيه واضح ولا يحتاج الى ابهام

النقطة الثانية اعتمد الذكر بلا جزم

الثالثة تم

الرابعة اذا ذكر المفسرون او الاسرائيليات فيها شيئا فاذكره بدون الجزم فيه

الخامسة تم

السادسة الاسم وربط الضلع بها واردان في ادلة اخرى اظننا ناقشناها في وقت سابق"""

SOURCE_DECISIONS = {
    "SRC-ABUDAWUD-4700": {
        "decision": "ACCEPT_ASSERTIVE_WITH_SCOPE",
        "accepted_claims": [
            "القلم أول مخلوق بنص الحديث",
            "أمر الله القلم بكتابة مقادير كل شيء",
        ],
        "scope_limitations": [
            "لا يُضعف وضوح لفظ الأولية في السرد",
            "يمكن ذكر نص الحديث مباشرة",
        ],
        "human_decision": True,
    },
    "SRC-TIRMIDHI-2155": {
        "decision": "ACCEPT_CORROBORATIVE_WITH_GRADE_NOTE",
        "accepted_claims": [
            "القلم أول مخلوق بنص الحديث",
            "أمر الله القلم بكتابة القدر إلى الأبد",
        ],
        "scope_limitations": [
            "يُذكر عند التوثيق أن الترمذي وصف الطريق بالغريب من هذا الوجه",
            "تُسجل درجة دار السلام: صحيح",
        ],
        "human_decision": True,
    },
    "SRC-MUSLIM-2841": {
        "decision": "ACCEPT_WITH_THEOLOGICAL_PHRASE_EXCLUDED",
        "accepted_claims": [
            "طول آدم ستون ذراعا",
            "تعليم آدم تحية السلام",
        ],
        "scope_limitations": [
            "لا تُفسر عبارة على صورته في السرد ضمن هذه الحزمة",
            "الأحداث الروتينية تعتمد البخاري 3326 استقلالا",
        ],
        "human_decision": True,
    },
}

EVENT_DECISIONS = {
    "EV-ADAM-003": {
        "disposition": "include_assertive",
        "approved_narration": (
            "إن أول ما خلق الله القلم، فقال له: اكتب، فكتب مقادير كل شيء "
            "إلى قيام الساعة. وكتب الله مقادير الخلائق قبل خلق السماوات "
            "والأرض بخمسين ألف سنة، وكان عرشه على الماء."
        ),
        "decision_basis": (
            "اعتماد المستخدم صراحة أولية القلم لورودها بنص الحديث."
        ),
        "firstness_claim": "ASSERTIVE_BY_EXPLICIT_HADITH_TEXT",
        "qualified_supplement_policy": "NOT_REQUIRED_FOR_FIRSTNESS",
        "human_decision": True,
    },
    "EV-ADAM-007": {
        "disposition": "include_qualified",
        "approved_narration": (
            "كان إبليس من الجن، وحضر أمر السجود لآدم فامتنع واستكبر. "
            "ويجوز ذكر أنه كان موجودا قبل بدء خلق آدم إذا ورد في بعض "
            "روايات التفسير، لكن بصيغة منسوبة وغير جازمة."
        ),
        "decision_basis": "اعتماد الذكر بلا جزم في التركيب الزمني.",
        "assertive_core": [
            "إبليس من الجن",
            "إبليس حضر أمر السجود وامتنع",
        ],
        "qualified_supplements": [
            "وجود إبليس الفرد قبل بدء خلق آدم",
        ],
        "human_decision": True,
    },
    "EV-ADAM-021": {
        "disposition": "include_qualified",
        "approved_narration": (
            "وصف القرآن مادة خلق آدم بالتراب والطين اللازب والحمإ "
            "المسنون والصلصال كالفخار. تُذكر الأوصاف بثبوتها، من دون "
            "تحويلها إلى مدد أو جدول زمني جازم إلا بنقل تفسيري منسوب."
        ),
        "decision_basis": "اعتماد المستخدم للتوصية الثالثة.",
        "human_decision": True,
    },
    "EV-ADAM-042": {
        "disposition": "include_assertive_with_qualified_tafsir_supplement",
        "approved_narration": (
            "علّم الله آدم الأسماء كلها، ثم أظهر للملائكة ما خصه به من "
            "العلم، فأقروا أن لا علم لهم إلا ما علّمهم الله. ويجوز بعد "
            "ذلك ذكر أقوال المفسرين في المراد بالأسماء—كأسماء الأشياء "
            "كلها، أو الملائكة، أو الذرية—منسوبةً إلى قائليها من دون "
            "الجزم بأن أحدها هو المراد الوحيد."
        ),
        "decision_basis": (
            "اعتماد النص القرآني جازما، والسماح بأقوال التفسير أو "
            "الإسرائيليات بلا جزم."
        ),
        "tafsir_supplement_rules": [
            "ATTRIBUTION_REQUIRED",
            "NO_EXCLUSIVE_INTERPRETATION_ASSERTION",
            "ISRAILIYYAT_EXPLICIT_LABEL_REQUIRED",
            "SOURCE_RECORD_REQUIRED",
        ],
        "documented_tafsir_views": [
            "أسماء جميع الأشياء",
            "أسماء الملائكة",
            "أسماء ذرية آدم",
            "أسماء الأجناس والمخلوقات",
        ],
        "human_decision": True,
    },
    "EV-ADAM-061": {
        "disposition": "include_qualified",
        "approved_narration": (
            "ورد في الحديث أن الله مسح ظهر آدم فأظهر ذريته له. يُذكر "
            "الحديث بدرجته المسجلة، ولا يُجعل التفسير الوحيد لآية "
            "الميثاق."
        ),
        "decision_basis": "اعتماد المستخدم للتوصية الخامسة.",
        "human_decision": True,
    },
    "EV-ADAM-070": {
        "disposition": "include_assertive_with_qualified_details",
        "approved_narration": (
            "زوج آدم هي حواء، وقد خُلقت من ضلع آدم؛ فاسم حواء ثابت في "
            "الحديث الصحيح، وثبت أن المرأة خُلقت من ضلع، ويُعتمد الربط "
            "بين المقدمتين كما سبق اعتماده في مراجعة الحلقة. أما الضلع "
            "الأيسر، ونوم آدم، والتئام موضع الضلع، والحوار المنقول، "
            "وسؤال الملائكة عن اسمها، وتعليل اسم حواء، فتُذكر فقط إذا "
            "كانت لها قيمة تحريرية، مع نسبتها إلى بعض المفسرين أو "
            "الإسرائيليات وترك الجزم بها."
        ),
        "decision_basis": (
            "استعادة الاعتماد السابق لـ EV-ADAM-071 وربطه بهذا الحدث."
        ),
        "authentic_sunnah_premises": [
            "اسم زوج آدم: حواء — البخاري 3330 ومسلم 1470",
            "المرأة خلقت من ضلع — البخاري 3331 ومسلم 1468",
        ],
        "supported_synthesis": "حواء خلقت من ضلع آدم",
        "prior_human_approval_event_id": "EV-ADAM-071",
        "secondary_detail_policy": [
            "QUALIFIED_TAFSIR_ATTRIBUTION",
            "EXPLICIT_ISRAILIYYAT_LABEL",
            "NO_ASSERTIVE_VISUALIZATION",
        ],
        "human_decision": True,
    },
}


class HighImportanceResolutionError(ValueError):
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
        raise HighImportanceResolutionError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise HighImportanceResolutionError(f"Expected object: {path}")
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
    dossier: Mapping[str, object],
    event_scope: Mapping[str, object],
    research: Mapping[str, object],
    prior_gap_approval: Mapping[str, object],
    origin_classification: Mapping[str, object],
) -> None:
    if dossier.get("schema_version") != (
        "siraj-high-importance-evidence-review-dossier-v1"
    ):
        raise HighImportanceResolutionError("Unexpected dossier schema.")
    if dossier.get("source_item_count") != (
        EXPECTED_HIGH_IMPORTANCE_SOURCE_COUNT
    ):
        raise HighImportanceResolutionError(
            "Expected three high-importance sources."
        )
    if dossier.get("event_item_count") != (
        EXPECTED_HIGH_IMPORTANCE_EVENT_COUNT
    ):
        raise HighImportanceResolutionError(
            "Expected six high-importance events."
        )
    if event_scope.get("schema_version") != (
        "siraj-routine-event-scope-adjudication-v1"
    ):
        raise HighImportanceResolutionError(
            "Unexpected routine event-scope schema."
        )
    if event_scope.get("routine_event_count") != (
        EXPECTED_ROUTINE_EVENT_COUNT
    ):
        raise HighImportanceResolutionError(
            "Expected eight routine events."
        )
    if research.get("schema_version") != (
        "siraj-delegated-hadith-authentication-research-v1"
    ):
        raise HighImportanceResolutionError(
            "Unexpected hadith research schema."
        )
    if prior_gap_approval.get("human_approval") is not True:
        raise HighImportanceResolutionError(
            "Prior gap human approval is absent."
        )
    prior_ids = {
        item["event_id"] for item in prior_gap_approval["decisions"]
    }
    if "EV-ADAM-071" not in prior_ids:
        raise HighImportanceResolutionError(
            "Prior Hawwa approval EV-ADAM-071 is missing."
        )
    origin_events = {
        item["event_id"] for item in origin_classification["events"]
    }
    if "EV-ADAM-071" not in origin_events:
        raise HighImportanceResolutionError(
            "Hawwa origin classification is missing."
        )
    dossier_source_ids = {
        item["source_candidate_id"] for item in dossier["source_items"]
    }
    if dossier_source_ids != set(HIGH_IMPORTANCE_SOURCE_IDS):
        raise HighImportanceResolutionError(
            "High-importance source set differs."
        )
    dossier_event_ids = {
        item["event_id"] for item in dossier["event_items"]
    }
    if dossier_event_ids != set(HIGH_IMPORTANCE_EVENT_IDS):
        raise HighImportanceResolutionError(
            "High-importance event set differs."
        )


def build_human_approval(
    *,
    dossier: Mapping[str, object],
    prior_gap_approval: Mapping[str, object],
    origin_classification: Mapping[str, object],
) -> dict:
    source_rows = [
        {
            "source_candidate_id": source_id,
            **SOURCE_DECISIONS[source_id],
        }
        for source_id in HIGH_IMPORTANCE_SOURCE_IDS
    ]
    event_rows = [
        {
            "event_id": event_id,
            **EVENT_DECISIONS[event_id],
        }
        for event_id in HIGH_IMPORTANCE_EVENT_IDS
    ]
    approval = {
        "schema_version": APPROVAL_SCHEMA,
        "status": "HUMAN_APPROVED_HIGH_IMPORTANCE_SCOPE",
        "episode_id": "episode-001-adam",
        "dossier_id": dossier["dossier_id"],
        "prior_gap_approval_id": prior_gap_approval["approval_id"],
        "origin_classification_id": origin_classification[
            "classification_id"
        ],
        "approved_by": "Abdulrahman Akah",
        "approved_at": "2026-07-28",
        "user_decision_text": USER_DECISION_TEXT,
        "user_decision_text_sha256": text_sha256(USER_DECISION_TEXT),
        "source_decision_count": len(source_rows),
        "event_decision_count": len(event_rows),
        "source_decisions": source_rows,
        "event_decisions": event_rows,
        "human_approval": True,
        "final_user_high_importance_decisions_complete": True,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    approval["approval_id"] = (
        "adam_high_importance_human_approval_"
        + canonical_sha256(approval)[:16]
    )
    return approval


def build_final_external_scope(
    *,
    event_scope: Mapping[str, object],
    approval: Mapping[str, object],
) -> dict:
    complex_index = {
        item["event_id"]: item for item in approval["event_decisions"]
    }
    rows = []
    for event in sorted(
        event_scope["events"],
        key=lambda item: item["event_id"],
    ):
        event_id = event["event_id"]
        if event_id in complex_index:
            decision = complex_index[event_id]
            rows.append(
                {
                    "event_id": event_id,
                    "title": event["title"],
                    "decision_origin": "EXPLICIT_HUMAN_DECISION",
                    "disposition": decision["disposition"],
                    "approved_narration": decision[
                        "approved_narration"
                    ],
                    "source_candidate_ids": event[
                        "all_source_candidate_ids"
                    ],
                    "effective_source_candidate_ids": event[
                        "effective_source_candidate_ids"
                    ],
                    "event_scope_approved": True,
                    "human_decision": True,
                    "delegated_ai_decision": False,
                    "scope_constraints": {
                        key: value
                        for key, value in decision.items()
                        if key not in {
                            "event_id",
                            "disposition",
                            "approved_narration",
                            "decision_basis",
                            "human_decision",
                        }
                    },
                }
            )
        else:
            if event_id not in ROUTINE_EVENT_IDS:
                raise HighImportanceResolutionError(
                    f"Unexpected event id: {event_id}"
                )
            if not event["delegated_ai_event_scope_approved"]:
                raise HighImportanceResolutionError(
                    f"Routine event is not delegated-approved: {event_id}"
                )
            rows.append(
                {
                    "event_id": event_id,
                    "title": event["title"],
                    "decision_origin": "ACTIVE_USER_DELEGATION",
                    "disposition": event["proposed_disposition"],
                    "approved_narration": "",
                    "source_candidate_ids": event[
                        "all_source_candidate_ids"
                    ],
                    "effective_source_candidate_ids": event[
                        "effective_source_candidate_ids"
                    ],
                    "event_scope_approved": True,
                    "human_decision": False,
                    "delegated_ai_decision": True,
                    "scope_constraints": {
                        "scope_limitations": event[
                            "scope_limitations"
                        ],
                    },
                }
            )

    if len(rows) != EXPECTED_FINAL_EVENT_COUNT:
        raise HighImportanceResolutionError(
            "Expected fourteen final event-scope decisions."
        )
    if not all(item["event_scope_approved"] for item in rows):
        raise HighImportanceResolutionError(
            "Every external event scope must be approved."
        )

    artifact = {
        "schema_version": FINAL_SCOPE_SCHEMA,
        "status": "EXTERNAL_EVENT_SCOPE_ADJUDICATION_COMPLETE",
        "episode_id": "episode-001-adam",
        "high_importance_approval_id": approval["approval_id"],
        "event_count": len(rows),
        "routine_delegated_event_count": sum(
            item["delegated_ai_decision"] for item in rows
        ),
        "explicit_human_event_count": sum(
            item["human_decision"] for item in rows
        ),
        "events": rows,
        "external_event_scope_complete": True,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    artifact["adjudication_id"] = (
        "adam_external_event_scope_final_"
        + canonical_sha256(artifact)[:16]
    )
    return artifact


def build_progress(
    *,
    approval: Mapping[str, object],
    final_scope: Mapping[str, object],
) -> dict:
    artifact = {
        "schema_version": PROGRESS_SCHEMA,
        "status": "HIGH_IMPORTANCE_SCOPE_RESOLVED",
        "episode_id": "episode-001-adam",
        "high_importance_approval_id": approval["approval_id"],
        "external_event_scope_adjudication_id": final_scope[
            "adjudication_id"
        ],
        "human_source_text_locator_review_complete": True,
        "delegated_hadith_research_complete": True,
        "routine_source_decisions_complete": True,
        "high_importance_source_decisions_complete": True,
        "routine_event_scope_complete": True,
        "high_importance_event_scope_complete": True,
        "external_event_scope_complete": True,
        "external_event_count": EXPECTED_FINAL_EVENT_COUNT,
        "known_episode_event_count": 37,
        "remaining_episode_event_integration_required": True,
        "full_episode_adjudication_complete": False,
        "approved_evidence_package_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
        "next_stage": (
            "INTEGRATE_EXTERNAL_SCOPE_WITH_QURAN_EXPLICIT_AND_GAP_APPROVALS"
        ),
    }
    artifact["progress_id"] = (
        "adam_evidence_adjudication_progress_"
        + canonical_sha256(artifact)[:16]
    )
    return artifact


def write_outputs(
    *,
    output_root: Path,
    approval: Mapping[str, object],
    final_scope: Mapping[str, object],
    progress: Mapping[str, object],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "approval": output_root
        / "high-importance-evidence-human-approval-v1.json",
        "final_scope": output_root
        / "external-event-scope-final-adjudication-v1.json",
        "progress": output_root
        / "episode-evidence-adjudication-progress-v1.json",
        "summary": output_root
        / "high-importance-resolution-summary.csv",
        "readme": output_root / "README.md",
    }
    write_json(outputs["approval"], approval)
    write_json(outputs["final_scope"], final_scope)
    write_json(outputs["progress"], progress)

    with outputs["summary"].open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        fields = [
            "record_type",
            "record_id",
            "decision",
            "human_decision",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for item in approval["source_decisions"]:
            writer.writerow(
                {
                    "record_type": "source",
                    "record_id": item["source_candidate_id"],
                    "decision": item["decision"],
                    "human_decision": True,
                }
            )
        for item in final_scope["events"]:
            writer.writerow(
                {
                    "record_type": "event",
                    "record_id": item["event_id"],
                    "decision": item["disposition"],
                    "human_decision": item["human_decision"],
                }
            )

    outputs["readme"].write_text(
        "# Adam high-importance evidence resolution v1\n\n"
        "This package records the creator's explicit decisions for three "
        "high-importance sources and six complex events. It also combines "
        "them with eight routine delegated decisions, completing scope "
        "adjudication for the fourteen external-source events. The Hawwa "
        "decision restores the earlier approved synthesis based on authentic "
        "name and rib premises, while secondary tafsir and Israiliyyat details "
        "remain qualified. The broader 37-event episode integration and final "
        "approved evidence package remain pending; the gate and providers stay "
        "blocked.\n",
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
