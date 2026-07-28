"""Validate persistent creator intent and historical narration policy.

This layer records editorial direction only. It never grades, approves, or binds
evidence and it cannot open the evidence gate.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence


HISTORICAL_NARRATION_POLICY_SCHEMA = "siraj-historical-narration-policy-v1"
CREATOR_EDITORIAL_INTENT_SCHEMA = "siraj-creator-editorial-intent-v1"
ADAM_EDITORIAL_DIRECTION_SCHEMA = "siraj-adam-editorial-direction-v1"

POLICY_STATUS = "approved"
DIRECTION_STATUS = "HUMAN_EDITORIAL_DIRECTION_RECORDED"
AUTOMATIC_APPROVAL_STATUS = "FORBIDDEN"
EVIDENCE_GATE_STATUS = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
LIVE_EXECUTION_STATUS = "BLOCKED"

TARGET_EVENT_IDS = ("EV-ADAM-031", "EV-ADAM-071", "EV-ADAM-091")

UNKNOWN_TREE_FORMULA = (
    "ونهاهما الله عن شجرة في الجنة، وقد اختلف المفسرون في نوعها، "
    "ولم يثبت في القرآن ولا في السنة الصحيحة ما يعيّنها."
)


class NarrationIntentError(ValueError):
    """Raised when creator intent or narration policy is unsafe or inconsistent."""


def canonical_json_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise NarrationIntentError(f"{key} must be a nonblank string.")
    return value.strip()


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise NarrationIntentError(f"{label} must be an object.")
    return value


def _objects(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise NarrationIntentError(f"{label} must be a list of objects.")
    return list(value)


def _strings(value: object, label: str) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise NarrationIntentError(f"{label} must be a list of nonblank strings.")
    result = [item.strip() for item in value]
    if len(result) != len(set(result)):
        raise NarrationIntentError(f"{label} must not contain duplicates.")
    return result


def _assert_no_secret_like_keys(value: object, path: str = "root") -> None:
    secret_fragments = (
        "api_key",
        "apikey",
        "access_token",
        "refresh_token",
        "password",
        "secret",
        "credential",
        "cookie",
    )
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in secret_fragments):
                raise NarrationIntentError(f"Secret-like field is forbidden: {path}.{key}")
            _assert_no_secret_like_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_no_secret_like_keys(item, f"{path}[{index}]")


def validate_historical_narration_policy(payload: Mapping[str, object]) -> None:
    _assert_no_secret_like_keys(payload)
    if payload.get("schema_version") != HISTORICAL_NARRATION_POLICY_SCHEMA:
        raise NarrationIntentError("Unexpected historical narration policy schema.")
    if payload.get("status") != POLICY_STATUS:
        raise NarrationIntentError("Historical narration policy must be approved.")
    if payload.get("scope") != "global":
        raise NarrationIntentError("Historical narration policy must be global.")
    if payload.get("automatic_evidence_approval") != AUTOMATIC_APPROVAL_STATUS:
        raise NarrationIntentError("Automatic evidence approval must remain forbidden.")
    if payload.get("evidence_gate_effect") != "NONE":
        raise NarrationIntentError("Narration policy cannot affect the evidence gate.")

    firstness = _object(
        payload.get("unsupported_firstness_policy"),
        "unsupported_firstness_policy",
    )
    if firstness.get("status") != "PROHIBITED_WITHOUT_DIRECT_SOUND_EVIDENCE":
        raise NarrationIntentError("Unsupported firstness must be prohibited.")
    covered = set(_strings(firstness.get("covered_claims"), "covered_claims"))
    required_firstness = {
        "first movement",
        "first speech",
        "first word",
        "first action",
        "earliest occurrence",
        "exclusive causal sequence",
    }
    if covered != required_firstness:
        raise NarrationIntentError("Firstness policy coverage changed.")

    workflow = _object(payload.get("source_origin_workflow"), "source_origin_workflow")
    if workflow.get("required_order") != [
        "trace_origin",
        "classify_origin",
        "verify_text",
        "choose_certainty",
        "write_narration",
    ]:
        raise NarrationIntentError("Source-origin workflow order changed.")
    origin_classes = set(_strings(workflow.get("origin_classes"), "origin_classes"))
    for required in (
        "quran_explicit",
        "authentic_sunnah",
        "accepted_athar",
        "tafsir_report",
        "historical_report",
        "israiliyyat",
        "weak_report",
        "scholarly_interpretation",
        "supported_synthesis",
    ):
        if required not in origin_classes:
            raise NarrationIntentError(f"Missing origin class: {required}")

    israiliyyat = _object(payload.get("israiliyyat_policy"), "israiliyyat_policy")
    if israiliyyat.get("must_be_explicitly_labeled_in_narration") is not True:
        raise NarrationIntentError("Israiliyyat must be explicitly labeled.")
    if israiliyyat.get("assertive_language") is not False:
        raise NarrationIntentError("Israiliyyat cannot use assertive language.")
    if israiliyyat.get("may_establish_creed") is not False:
        raise NarrationIntentError("Israiliyyat cannot establish creed.")
    if israiliyyat.get("may_establish_law") is not False:
        raise NarrationIntentError("Israiliyyat cannot establish law.")
    if israiliyyat.get("contradictory_material") != "OMIT":
        raise NarrationIntentError("Contradictory Israiliyyat must be omitted.")

    synthesis = _object(
        payload.get("supported_synthesis_policy"),
        "supported_synthesis_policy",
    )
    if synthesis.get("allowed") is not True:
        raise NarrationIntentError("Supported synthesis must remain allowed.")
    if synthesis.get("minimum_independently_established_premises") != 2:
        raise NarrationIntentError("Supported synthesis must require two premises.")
    if synthesis.get("premise_trace_required") is not True:
        raise NarrationIntentError("Supported synthesis must preserve premise trace.")
    if synthesis.get("conclusion_must_not_add_unproved_detail") is not True:
        raise NarrationIntentError("Synthesis cannot add unproved detail.")

    source_mentions = _object(
        payload.get("source_mention_policy"),
        "source_mention_policy",
    )
    if source_mentions.get("default_narration") != "DO_NOT_OVERLOAD_WITH_SOURCE_NAMES":
        raise NarrationIntentError("Source-name overload policy changed.")
    triggers = set(
        _strings(
            source_mentions.get("mandatory_audience_attribution_triggers"),
            "mandatory_audience_attribution_triggers",
        )
    )
    required_triggers = {
        "doctrinal_ambiguity",
        "serious_moral_or_personal_confusion",
        "israiliyyat",
        "weak_report",
        "material_dispute",
        "sensitive_inference",
        "conflicting_reports",
    }
    if triggers != required_triggers:
        raise NarrationIntentError("Mandatory attribution triggers changed.")

    qualified = _object(
        payload.get("qualified_language_policy"),
        "qualified_language_policy",
    )
    if qualified.get("uncertain_specific_template") != UNKNOWN_TREE_FORMULA:
        raise NarrationIntentError("Unknown-specific narration formula changed.")

    visual = _object(
        payload.get("visual_correspondence_policy"),
        "visual_correspondence_policy",
    )
    if visual.get("unknown_specifics_must_remain_visually_unspecified") is not True:
        raise NarrationIntentError("Unknown specifics must remain visually unspecified.")
    if visual.get("visual_must_not_convert_qualified_claim_to_assertive_fact") is not True:
        raise NarrationIntentError("Visuals cannot turn qualified claims into facts.")

    future = _object(payload.get("future_episode_application"), "future_episode_application")
    if future.get("reuse_without_reasking_creator") is not True:
        raise NarrationIntentError("Creator should not be repeatedly re-asked.")
    if future.get("new_creator_feedback_updates_profile") is not True:
        raise NarrationIntentError("New creator feedback must update the profile.")


def validate_creator_editorial_intent(payload: Mapping[str, object]) -> None:
    _assert_no_secret_like_keys(payload)
    if payload.get("schema_version") != CREATOR_EDITORIAL_INTENT_SCHEMA:
        raise NarrationIntentError("Unexpected creator intent schema.")
    if payload.get("status") != POLICY_STATUS:
        raise NarrationIntentError("Creator intent profile must be approved.")
    if payload.get("scope") != "series_global":
        raise NarrationIntentError("Creator intent profile must be series-global.")
    if payload.get("owner") != "Abdulrahman Akah":
        raise NarrationIntentError("Creator intent owner changed.")
    if payload.get("evidence_gate_effect") != "NONE":
        raise NarrationIntentError("Creator intent cannot open evidence gate.")
    if payload.get("automatic_evidence_approval") != AUTOMATIC_APPROVAL_STATUS:
        raise NarrationIntentError("Creator intent cannot approve evidence.")

    preferences = _object(payload.get("preferences"), "preferences")
    expected = {
        "historical_accuracy": "STRICT",
        "dramatic_quality": "HIGH_WITHOUT_FACTUAL_DISTORTION",
        "unsupported_firstness": "NEVER_ASSERT",
        "nonfoundational_reports": (
            "TRACE_CLASSIFY_AND_USE_WITH_PROPER_CERTAINTY_WHEN_VALUABLE"
        ),
        "israiliyyat": "MAY_INCLUDE_WITH_EXPLICIT_LABEL_IF_NONCONTRADICTORY",
        "source_names_in_narration": "SPARING",
        "source_attribution": (
            "MANDATORY_AT_DOCTRINALLY_OR_MORALLY_SENSITIVE_OR_DISPUTED_POINTS"
        ),
        "supported_synthesis": (
            "ALLOWED_WHEN_PREMISES_ARE_ESTABLISHED_AND_NO_EXTRA_DETAIL_IS_ADDED"
        ),
        "unknown_specifics": (
            "STATE_DISAGREEMENT_AND_LACK_OF_SOUND_DETERMINATION"
        ),
        "visual_unknowns": "KEEP_GENERIC_AND_NON_IDENTIFIABLE",
        "repeat_explanations_to_creator": "AVOID",
        "early_episode_feedback": "GENERALIZE_TO_FUTURE_EPISODES",
    }
    for key, value in expected.items():
        if preferences.get(key) != value:
            raise NarrationIntentError(f"Creator preference changed: {key}")

    examples = _objects(payload.get("canonical_examples"), "canonical_examples")
    by_topic = {_required_text(item, "topic"): item for item in examples}
    if by_topic.get("unknown_tree_type", {}).get("approved_wording") != UNKNOWN_TREE_FORMULA:
        raise NarrationIntentError("Creator-approved tree wording changed.")
    if "unverified_firstness" not in by_topic or "israiliyyat" not in by_topic:
        raise NarrationIntentError("Creator examples are incomplete.")


def validate_adam_editorial_direction(
    payload: Mapping[str, object],
    *,
    event_map: Sequence[Mapping[str, object]] | None = None,
) -> None:
    _assert_no_secret_like_keys(payload)
    if payload.get("schema_version") != ADAM_EDITORIAL_DIRECTION_SCHEMA:
        raise NarrationIntentError("Unexpected Adam editorial direction schema.")
    if payload.get("status") != DIRECTION_STATUS:
        raise NarrationIntentError("Adam editorial direction status changed.")
    if payload.get("episode_id") != "episode-001-adam":
        raise NarrationIntentError("Adam direction episode id changed.")
    if payload.get("evidence_gate_status") != EVIDENCE_GATE_STATUS:
        raise NarrationIntentError("Adam direction cannot open evidence gate.")
    if payload.get("automatic_evidence_approval") != AUTOMATIC_APPROVAL_STATUS:
        raise NarrationIntentError("Adam direction cannot approve evidence.")
    if payload.get("live_provider_execution") != LIVE_EXECUTION_STATUS:
        raise NarrationIntentError("Adam direction cannot enable live providers.")

    decisions = _objects(payload.get("decisions"), "decisions")
    ids = tuple(_required_text(item, "event_id") for item in decisions)
    if ids != TARGET_EVENT_IDS:
        raise NarrationIntentError("Adam direction event order changed.")
    by_id = {item["event_id"]: item for item in decisions}

    event_031 = by_id["EV-ADAM-031"]
    if event_031.get("event_title_override_for_narration") != "عطاس آدم وحمده لله":
        raise NarrationIntentError("EV-ADAM-031 title must remove unsupported firstness.")
    prohibited_031 = " ".join(
        _strings(
            event_031.get("prohibited_without_direct_sound_evidence"),
            "EV-ADAM-031.prohibited",
        )
    )
    for required in ("أول حركة", "أول فعل", "أول كلام"):
        if required not in prohibited_031:
            raise NarrationIntentError(f"EV-ADAM-031 missing prohibition: {required}")
    if event_031.get("evidence_approval") is not False:
        raise NarrationIntentError("EV-ADAM-031 is editorial direction, not approval.")

    event_071 = by_id["EV-ADAM-071"]
    synthesis = _object(
        event_071.get("assertive_supported_synthesis_after_source_binding"),
        "EV-ADAM-071.synthesis",
    )
    premises = _strings(synthesis.get("premises"), "EV-ADAM-071.premises")
    if len(premises) != 2:
        raise NarrationIntentError("EV-ADAM-071 synthesis must have two premises.")
    if synthesis.get("conclusion") != "حواء خلقت من ضلع آدم":
        raise NarrationIntentError("EV-ADAM-071 synthesis conclusion changed.")
    loneliness = _object(event_071.get("loneliness_report"), "loneliness_report")
    if loneliness.get("status") != "SOURCE_ORIGIN_CLASSIFICATION_PENDING":
        raise NarrationIntentError("Loneliness report must remain origin-pending.")
    if loneliness.get("narration_until_classified") != "QUALIFIED_ONLY":
        raise NarrationIntentError("Loneliness report must remain qualified.")
    if loneliness.get("if_israiliyyat") != "EXPLICIT_ISRAILIYYAT_LABEL_REQUIRED":
        raise NarrationIntentError("Israiliyyat origin must be labeled.")
    excluded = set(
        _strings(
            event_071.get("details_requiring_origin_label_or_omission"),
            "EV-ADAM-071.details",
        )
    )
    required_excluded = {
        "الضلع الأيسر",
        "أقصر ضلع",
        "خلق حواء أثناء نوم آدم",
        "التئام موضع الضلع لحمًا",
        "الحوار المنقول بين آدم وحواء",
        "سؤال الملائكة عن اسمها",
        "تعليل اسم حواء بأنها خلقت من حي",
    }
    if excluded != required_excluded:
        raise NarrationIntentError("EV-ADAM-071 uncertain detail policy changed.")
    if event_071.get("evidence_approval") is not False:
        raise NarrationIntentError("EV-ADAM-071 is editorial direction, not approval.")

    event_091 = by_id["EV-ADAM-091"]
    if event_091.get("approved_narration_formula") != UNKNOWN_TREE_FORMULA:
        raise NarrationIntentError("EV-ADAM-091 approved wording changed.")
    if event_091.get("specific_type_assertion") != "PROHIBITED":
        raise NarrationIntentError("Tree type must not be asserted.")
    visual = _required_text(event_091, "visual_rule")
    for forbidden_specific in ("wheat", "grape", "fig"):
        if forbidden_specific not in visual:
            raise NarrationIntentError(
                f"Tree visual rule must exclude identifiable {forbidden_specific}."
            )
    if event_091.get("evidence_approval") is not False:
        raise NarrationIntentError("EV-ADAM-091 is editorial direction, not approval.")

    if event_map is not None:
        event_ids = [
            _required_text(item, "event_id")
            for item in event_map
        ]
        for event_id in TARGET_EVENT_IDS:
            if event_ids.count(event_id) != 1:
                raise NarrationIntentError(
                    f"Adam direction references missing/duplicate event: {event_id}"
                )


def load_and_validate_bundle(
    *,
    narration_policy_path: Path,
    creator_intent_path: Path,
    adam_direction_path: Path,
    event_map_path: Path | None = None,
) -> dict[str, object]:
    def read(path: Path) -> object:
        try:
            return json.loads(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, json.JSONDecodeError) as error:
            raise NarrationIntentError(f"Invalid JSON: {path}") from error

    narration = _object(read(narration_policy_path), "narration_policy")
    creator = _object(read(creator_intent_path), "creator_intent")
    direction = _object(read(adam_direction_path), "adam_direction")
    event_map = None
    if event_map_path is not None:
        raw_events = read(event_map_path)
        if not isinstance(raw_events, list) or any(
            not isinstance(item, Mapping) for item in raw_events
        ):
            raise NarrationIntentError("Event map must be a list of objects.")
        event_map = list(raw_events)

    validate_historical_narration_policy(narration)
    validate_creator_editorial_intent(creator)
    validate_adam_editorial_direction(direction, event_map=event_map)

    fingerprint_payload = {
        "narration_policy_sha256": canonical_json_sha256(narration),
        "creator_intent_sha256": canonical_json_sha256(creator),
        "adam_direction_sha256": canonical_json_sha256(direction),
        "event_map_sha256": (
            canonical_json_sha256(event_map) if event_map is not None else None
        ),
    }
    return {
        "schema_version": "siraj-narration-intent-validation-v1",
        "status": "PASS",
        "automatic_evidence_approval": AUTOMATIC_APPROVAL_STATUS,
        "evidence_gate_status": EVIDENCE_GATE_STATUS,
        "live_provider_execution": LIVE_EXECUTION_STATUS,
        "fingerprints": fingerprint_payload,
        "bundle_id": (
            "narration_intent_bundle_"
            + canonical_json_sha256(fingerprint_payload)[:16]
        ),
    }


def write_validation_manifest(path: Path, payload: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
