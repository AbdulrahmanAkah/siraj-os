"""Materialize Quran-source candidates for all Quran-explicit Adam events.

This module is deliberately conservative. It records verse locators, normalized
Arabic anchor text, claim scope, and deterministic checksums. It does not record
human approval, complete evidence binding, open the gate, or enable providers.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Mapping

SOURCE_SCHEMA = "siraj-quran-source-materialization-v1"
BINDING_SCHEMA = "siraj-quran-event-binding-candidate-v1"
REVIEW_SCHEMA = "siraj-quran-binding-human-review-template-v1"
STATUS = "QURAN_SOURCE_MATERIALIZED_HUMAN_REVIEW_PENDING"
GATE = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTO_APPROVAL = "FORBIDDEN"
LIVE_EXECUTION = "BLOCKED"

EXPECTED_EVENTS = (
    "EV-ADAM-004", "EV-ADAM-006", "EV-ADAM-010", "EV-ADAM-011",
    "EV-ADAM-020", "EV-ADAM-022", "EV-ADAM-030", "EV-ADAM-040",
    "EV-ADAM-041", "EV-ADAM-050", "EV-ADAM-051", "EV-ADAM-052",
    "EV-ADAM-053", "EV-ADAM-054", "EV-ADAM-055", "EV-ADAM-080",
    "EV-ADAM-081", "EV-ADAM-082", "EV-ADAM-090",
)

SOURCE_RECORDS = (
    {
        "source_record_id": "QSR-007-054",
        "surah": 7,
        "ayah_start": 54,
        "ayah_end": 54,
        "locator": "Quran 7:54",
        "source_url": "https://quran.com/7/54",
        "arabic_anchor_text": "إن ربكم الله الذي خلق السماوات والأرض في ستة أيام",
    },
    {
        "source_record_id": "QSR-015-027",
        "surah": 15,
        "ayah_start": 27,
        "ayah_end": 27,
        "locator": "Quran 15:27",
        "source_url": "https://quran.com/15/27",
        "arabic_anchor_text": "والجان خلقناه من قبل من نار السموم",
    },
    {
        "source_record_id": "QSR-002-030",
        "surah": 2,
        "ayah_start": 30,
        "ayah_end": 30,
        "locator": "Quran 2:30",
        "source_url": "https://quran.com/2/30",
        "arabic_anchor_text": "وإذ قال ربك للملائكة إني جاعل في الأرض خليفة قالوا أتجعل فيها من يفسد فيها ويسفك الدماء",
    },
    {
        "source_record_id": "QSR-003-059",
        "surah": 3,
        "ayah_start": 59,
        "ayah_end": 59,
        "locator": "Quran 3:59",
        "source_url": "https://quran.com/3/59",
        "arabic_anchor_text": "إن مثل عيسى عند الله كمثل آدم خلقه من تراب ثم قال له كن فيكون",
    },
    {
        "source_record_id": "QSR-015-029",
        "surah": 15,
        "ayah_start": 29,
        "ayah_end": 29,
        "locator": "Quran 15:29",
        "source_url": "https://quran.com/15/29",
        "arabic_anchor_text": "فإذا سويته ونفخت فيه من روحي فقعوا له ساجدين",
    },
    {
        "source_record_id": "QSR-002-031",
        "surah": 2,
        "ayah_start": 31,
        "ayah_end": 31,
        "locator": "Quran 2:31",
        "source_url": "https://quran.com/2/31",
        "arabic_anchor_text": "وعلم آدم الأسماء كلها ثم عرضهم على الملائكة فقال أنبئوني بأسماء هؤلاء إن كنتم صادقين",
    },
    {
        "source_record_id": "QSR-002-034",
        "surah": 2,
        "ayah_start": 34,
        "ayah_end": 34,
        "locator": "Quran 2:34",
        "source_url": "https://quran.com/2/34",
        "arabic_anchor_text": "وإذ قلنا للملائكة اسجدوا لآدم فسجدوا إلا إبليس أبى واستكبر وكان من الكافرين",
    },
    {
        "source_record_id": "QSR-007-012",
        "surah": 7,
        "ayah_start": 12,
        "ayah_end": 12,
        "locator": "Quran 7:12",
        "source_url": "https://quran.com/7/12",
        "arabic_anchor_text": "قال ما منعك ألا تسجد إذ أمرتك قال أنا خير منه خلقتني من نار وخلقته من طين",
    },
    {
        "source_record_id": "QSR-007-013-015",
        "surah": 7,
        "ayah_start": 13,
        "ayah_end": 15,
        "locator": "Quran 7:13-15",
        "source_url": "https://quran.com/7/13-15",
        "arabic_anchor_text": "قال فاهبط منها فما يكون لك أن تتكبر فيها فاخرج إنك من الصاغرين | قال أنظرني إلى يوم يبعثون | قال إنك من المنظرين",
    },
    {
        "source_record_id": "QSR-007-016-017",
        "surah": 7,
        "ayah_start": 16,
        "ayah_end": 17,
        "locator": "Quran 7:16-17",
        "source_url": "https://quran.com/7/16-17",
        "arabic_anchor_text": "قال فبما أغويتني لأقعدن لهم صراطك المستقيم | ثم لآتينهم من بين أيديهم ومن خلفهم وعن أيمانهم وعن شمائلهم ولا تجد أكثرهم شاكرين",
    },
    {
        "source_record_id": "QSR-002-035",
        "surah": 2,
        "ayah_start": 35,
        "ayah_end": 35,
        "locator": "Quran 2:35",
        "source_url": "https://quran.com/2/35",
        "arabic_anchor_text": "وقلنا يا آدم اسكن أنت وزوجك الجنة وكلا منها رغدا حيث شئتما ولا تقربا هذه الشجرة فتكونا من الظالمين",
    },
    {
        "source_record_id": "QSR-007-019",
        "surah": 7,
        "ayah_start": 19,
        "ayah_end": 19,
        "locator": "Quran 7:19",
        "source_url": "https://quran.com/7/19",
        "arabic_anchor_text": "ويا آدم اسكن أنت وزوجك الجنة فكلا من حيث شئتما ولا تقربا هذه الشجرة فتكونا من الظالمين",
    },
    {
        "source_record_id": "QSR-020-117",
        "surah": 20,
        "ayah_start": 117,
        "ayah_end": 117,
        "locator": "Quran 20:117",
        "source_url": "https://quran.com/20/117",
        "arabic_anchor_text": "فقلنا يا آدم إن هذا عدو لك ولزوجك فلا يخرجنكما من الجنة فتشقى",
    },
    {
        "source_record_id": "QSR-020-118-119",
        "surah": 20,
        "ayah_start": 118,
        "ayah_end": 119,
        "locator": "Quran 20:118-119",
        "source_url": "https://quran.com/20/118-119",
        "arabic_anchor_text": "إن لك ألا تجوع فيها ولا تعرى | وأنك لا تظمأ فيها ولا تضحى",
    },
)

EVENT_BINDINGS = (
    ("EV-ADAM-004", ("QSR-007-054",), "خلق الله السماوات والأرض في ستة أيام"),
    ("EV-ADAM-006", ("QSR-015-027",), "خلق الجان قبل آدم من نار السموم"),
    ("EV-ADAM-010", ("QSR-002-030",), "إعلان جعل خليفة في الأرض"),
    ("EV-ADAM-011", ("QSR-002-030",), "سؤال الملائكة عن الإفساد وسفك الدماء"),
    ("EV-ADAM-020", ("QSR-003-059",), "خلق آدم من تراب"),
    ("EV-ADAM-022", ("QSR-015-029",), "تسوية خلق آدم"),
    ("EV-ADAM-030", ("QSR-015-029",), "نفخ الروح في آدم"),
    ("EV-ADAM-040", ("QSR-002-031",), "تعليم آدم الأسماء كلها"),
    ("EV-ADAM-041", ("QSR-002-031",), "عرض المسميات على الملائكة"),
    ("EV-ADAM-050", ("QSR-002-034", "QSR-015-029"), "أمر الملائكة بالسجود لآدم"),
    ("EV-ADAM-051", ("QSR-002-034",), "سجود الملائكة لآدم"),
    ("EV-ADAM-052", ("QSR-002-034",), "امتناع إبليس واستكباره"),
    ("EV-ADAM-053", ("QSR-007-012",), "احتجاج إبليس بأنه خلق من نار وآدم من طين"),
    ("EV-ADAM-054", ("QSR-007-013-015",), "طرد إبليس وطلبه الإنظار وإخباره بأنه من المنظرين"),
    ("EV-ADAM-055", ("QSR-007-016-017",), "إعلان إبليس ترصده لبني آدم وإتيانهم من الجهات"),
    ("EV-ADAM-080", ("QSR-002-035", "QSR-007-019"), "إسكان آدم وزوجه الجنة"),
    ("EV-ADAM-081", ("QSR-020-118-119",), "عدم الجوع والعري والعطش والضحى في الجنة"),
    ("EV-ADAM-082", ("QSR-020-117",), "تحذير آدم وزوجه من عداوة إبليس"),
    ("EV-ADAM-090", ("QSR-002-035", "QSR-007-019"), "النهي عن الاقتراب من الشجرة"),
)


class QuranBindingError(ValueError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def text_sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def read_json(path: Path) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise QuranBindingError(f"Invalid JSON: {path}") from exc


def build_source_materialization() -> dict:
    records = []
    for base in SOURCE_RECORDS:
        record = dict(base)
        record.update({
            "source_type": "QURAN",
            "origin_classification": "QURAN_EXPLICIT",
            "arabic_text_form": "NORMALIZED_REFERENCE_ANCHOR",
            "arabic_anchor_sha256": text_sha256(record["arabic_anchor_text"]),
            "human_verified_against_mushaf": False,
            "automatic_approval": False,
        })
        records.append(record)
    package = {
        "schema_version": SOURCE_SCHEMA,
        "status": STATUS,
        "episode_id": "episode-001-adam",
        "source_record_count": len(records),
        "source_records": records,
        "provenance": {
            "reference_site": "Quran.com",
            "reference_domain": "quran.com",
            "locator_audit_required": True,
            "mushaf_text_human_verification_required": True,
            "translation_included": False,
            "tafsir_included": False,
        },
        "human_approval": False,
        "binding_ready": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    package["source_package_id"] = (
        "adam_quran_source_materialization_" + canonical_sha256(package)[:16]
    )
    validate_source_materialization(package)
    return package


def build_event_bindings(inventory_path: Path, source_package: Mapping[str, object]) -> dict:
    inventory = read_json(inventory_path)
    if not isinstance(inventory, Mapping):
        raise QuranBindingError("Inventory must be an object.")
    if inventory.get("schema_version") != "siraj-full-episode-adjudication-inventory-v1":
        raise QuranBindingError("Unexpected inventory schema.")
    events = inventory.get("events")
    if not isinstance(events, list):
        raise QuranBindingError("Inventory events missing.")
    quran_events = {
        str(item.get("event_id")): item
        for item in events
        if isinstance(item, Mapping)
        and item.get("verification_status") == "quran_explicit"
    }
    if tuple(sorted(quran_events, key=lambda x: int(x.rsplit("-", 1)[1]))) != EXPECTED_EVENTS:
        raise QuranBindingError("Quran-explicit event set changed.")

    source_index = {
        str(item["source_record_id"]): item
        for item in source_package["source_records"]
    }
    items = []
    for event_id, source_ids, claim_scope in EVENT_BINDINGS:
        event = quran_events[event_id]
        evidence_items = []
        for source_id in source_ids:
            source = source_index[source_id]
            evidence_items.append({
                "source_record_id": source_id,
                "locator": source["locator"],
                "source_url": source["source_url"],
                "source_materialization_sha256": canonical_sha256(source),
                "excerpt_sha256": source["arabic_anchor_sha256"],
                "excerpt_form": source["arabic_text_form"],
            })
        items.append({
            "event_id": event_id,
            "event_title": event["title"],
            "section": event["section"],
            "claim_scope": claim_scope,
            "origin_classification": "QURAN_EXPLICIT",
            "proposed_disposition": "include_assertive",
            "human_decision": False,
            "binding_status": "SOURCE_MATERIALIZED_HUMAN_REVIEW_PENDING",
            "evidence_items": evidence_items,
            "excluded_scope": [
                "tafsir beyond the explicit verse wording",
                "chronology not explicit in the cited verses",
                "visual reconstruction of unseen persons or beings",
            ],
        })

    package = {
        "schema_version": BINDING_SCHEMA,
        "status": STATUS,
        "episode_id": "episode-001-adam",
        "inventory_id": inventory["inventory_id"],
        "inventory_sha256": canonical_sha256(inventory),
        "source_package_id": source_package["source_package_id"],
        "source_package_sha256": canonical_sha256(source_package),
        "event_count": len(items),
        "event_ids": [x["event_id"] for x in items],
        "bindings": items,
        "human_approval": False,
        "full_episode_adjudication_complete": False,
        "binding_ready": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    package["binding_candidate_id"] = (
        "adam_quran_binding_candidate_" + canonical_sha256(package)[:16]
    )
    validate_event_bindings(package, source_package)
    return package


def build_human_review_template(binding_package: Mapping[str, object]) -> dict:
    template = {
        "schema_version": REVIEW_SCHEMA,
        "status": "TEMPLATE_NOT_APPROVED",
        "episode_id": "episode-001-adam",
        "binding_candidate_id": binding_package["binding_candidate_id"],
        "binding_candidate_sha256": canonical_sha256(binding_package),
        "review_scope": "ALL_19_QURAN_EXPLICIT_EVENTS",
        "approved_by": "",
        "approved_at": "",
        "human_approval": False,
        "decisions": [
            {
                "event_id": item["event_id"],
                "proposed_disposition": item["proposed_disposition"],
                "approved": False,
                "human_decision": False,
                "reviewer_notes": "",
            }
            for item in binding_package["bindings"]
        ],
        "full_episode_adjudication_complete": False,
        "opens_evidence_gate": False,
        "evidence_gate_status": GATE,
        "automatic_evidence_approval": AUTO_APPROVAL,
        "live_provider_execution": LIVE_EXECUTION,
    }
    validate_human_review_template(template)
    return template


def validate_source_materialization(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != SOURCE_SCHEMA or data.get("status") != STATUS:
        raise QuranBindingError("Invalid source materialization schema/status.")
    records = data.get("source_records")
    if not isinstance(records, list) or len(records) != 14:
        raise QuranBindingError("Expected exactly 14 Quran source records.")
    ids = [x.get("source_record_id") for x in records if isinstance(x, Mapping)]
    if len(ids) != 14 or len(set(ids)) != 14:
        raise QuranBindingError("Source record ids are invalid.")
    locator_re = re.compile(r"^Quran \d+:\d+(?:-\d+)?$")
    for item in records:
        if item.get("source_type") != "QURAN":
            raise QuranBindingError("Only Quran sources are allowed.")
        if item.get("origin_classification") != "QURAN_EXPLICIT":
            raise QuranBindingError("Quran source classification changed.")
        if not locator_re.fullmatch(str(item.get("locator", ""))):
            raise QuranBindingError("Invalid Quran locator.")
        if not str(item.get("source_url", "")).startswith("https://quran.com/"):
            raise QuranBindingError("Unexpected source domain.")
        anchor = item.get("arabic_anchor_text")
        if not isinstance(anchor, str) or not anchor.strip():
            raise QuranBindingError("Arabic anchor missing.")
        if text_sha256(anchor) != item.get("arabic_anchor_sha256"):
            raise QuranBindingError("Arabic anchor checksum mismatch.")
        if item.get("human_verified_against_mushaf") is not False:
            raise QuranBindingError("Source may not claim human verification.")
    if data.get("human_approval") is not False or data.get("binding_ready") is not False:
        raise QuranBindingError("Source materialization cannot approve or bind.")
    _validate_global_guards(data)


def validate_event_bindings(
    data: Mapping[str, object], source_package: Mapping[str, object]
) -> None:
    if data.get("schema_version") != BINDING_SCHEMA or data.get("status") != STATUS:
        raise QuranBindingError("Invalid binding schema/status.")
    if tuple(data.get("event_ids", ())) != EXPECTED_EVENTS:
        raise QuranBindingError("Binding event set changed.")
    bindings = data.get("bindings")
    if not isinstance(bindings, list) or len(bindings) != 19:
        raise QuranBindingError("Expected exactly 19 event bindings.")
    source_index = {
        item["source_record_id"]: item
        for item in source_package["source_records"]
    }
    for item in bindings:
        if item.get("origin_classification") != "QURAN_EXPLICIT":
            raise QuranBindingError("Non-Quran classification entered batch.")
        if item.get("proposed_disposition") != "include_assertive":
            raise QuranBindingError("Unexpected proposed disposition.")
        if item.get("human_decision") is not False:
            raise QuranBindingError("Human decision cannot be prefilled.")
        evidence = item.get("evidence_items")
        if not isinstance(evidence, list) or not evidence:
            raise QuranBindingError("Every event requires Quran evidence.")
        for evidence_item in evidence:
            source_id = evidence_item.get("source_record_id")
            if source_id not in source_index:
                raise QuranBindingError("Unknown source record reference.")
            source = source_index[source_id]
            if evidence_item.get("excerpt_sha256") != source["arabic_anchor_sha256"]:
                raise QuranBindingError("Excerpt checksum mismatch.")
            if evidence_item.get("source_materialization_sha256") != canonical_sha256(source):
                raise QuranBindingError("Source materialization checksum mismatch.")
    if data.get("full_episode_adjudication_complete") is not False:
        raise QuranBindingError("Quran batch cannot complete full adjudication.")
    if data.get("opens_evidence_gate") is not False:
        raise QuranBindingError("Quran batch cannot open evidence gate.")
    _validate_global_guards(data)


def validate_human_review_template(data: Mapping[str, object]) -> None:
    if data.get("schema_version") != REVIEW_SCHEMA:
        raise QuranBindingError("Unexpected review template schema.")
    if data.get("status") != "TEMPLATE_NOT_APPROVED":
        raise QuranBindingError("Review template cannot be preapproved.")
    decisions = data.get("decisions")
    if not isinstance(decisions, list) or len(decisions) != 19:
        raise QuranBindingError("Review template must contain 19 decisions.")
    for item in decisions:
        if item.get("approved") is not False or item.get("human_decision") is not False:
            raise QuranBindingError("Review decisions must be blank.")
    if data.get("approved_by") or data.get("approved_at"):
        raise QuranBindingError("Reviewer metadata must be blank.")
    if data.get("human_approval") is not False:
        raise QuranBindingError("Template cannot claim human approval.")
    _validate_global_guards(data)


def _validate_global_guards(data: Mapping[str, object]) -> None:
    if data.get("evidence_gate_status") != GATE:
        raise QuranBindingError("Evidence gate must remain withheld.")
    if data.get("automatic_evidence_approval") != AUTO_APPROVAL:
        raise QuranBindingError("Automatic approval must remain forbidden.")
    if data.get("live_provider_execution") != LIVE_EXECUTION:
        raise QuranBindingError("Provider execution must remain blocked.")


def write_json(path: Path, data: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def build_and_write(repo_root: Path, output_root: Path) -> dict[str, Path]:
    inventory_path = (
        Path(repo_root)
        / "projects/episode-001-adam/evidence/full-episode-adjudication-inventory-v1.json"
    )
    source_package = build_source_materialization()
    binding_package = build_event_bindings(inventory_path, source_package)
    review_template = build_human_review_template(binding_package)
    output_root = Path(output_root)
    outputs = {
        "source_materialization": output_root / (
            "projects/episode-001-adam/evidence/"
            "quran-source-materialization-v1.json"
        ),
        "binding_candidate": output_root / (
            "projects/episode-001-adam/evidence/"
            "quran-event-binding-candidate-v1.json"
        ),
        "human_review_template": output_root / (
            "projects/episode-001-adam/evidence/"
            "quran-binding-human-review-v1.template.json"
        ),
    }
    write_json(outputs["source_materialization"], source_package)
    write_json(outputs["binding_candidate"], binding_package)
    write_json(outputs["human_review_template"], review_template)
    return outputs
