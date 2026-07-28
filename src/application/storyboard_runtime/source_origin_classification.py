"""Validate source-origin classification and proposed Adam gap adjudication.

This layer records research conclusions and safe narration rules. It never performs
automatic evidence approval, never opens the evidence gate, and never calls a live
provider.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence


SOURCE_ORIGIN_CLASSIFICATION_SCHEMA = "siraj-source-origin-classification-v1"
PROPOSED_GAP_ADJUDICATION_SCHEMA = "siraj-proposed-gap-adjudication-v1"

CLASSIFICATION_STATUS = "SOURCE_ORIGIN_CLASSIFIED_REVIEW_PENDING"
PROPOSAL_STATUS = "HUMAN_EVIDENCE_APPROVAL_PENDING"
EVIDENCE_GATE_STATUS = "WITHHELD_PENDING_APPROVED_EVIDENCE_PACKAGE"
AUTOMATIC_APPROVAL_STATUS = "FORBIDDEN"
LIVE_EXECUTION_STATUS = "BLOCKED"

TARGET_EVENT_IDS = ("EV-ADAM-031", "EV-ADAM-071", "EV-ADAM-091")
UNKNOWN_TREE_FORMULA = (
    "ونهاهما الله عن شجرة في الجنة، وقد اختلف المفسرون في نوعها، "
    "ولم يثبت في القرآن ولا في السنة الصحيحة ما يعيّنها."
)

ALLOWED_SOURCE_ORIGINS = {
    "AUTHENTIC_SUNNAH",
    "QURAN_EXPLICIT",
    "SUPPORTED_SYNTHESIS",
    "TAFSIR_REPORT_COMPOSITE_CHAIN_NOT_MARFU",
    "ISRAILIYYAT_EXPLICIT_ORIGIN",
    "DISPUTED_TAFSIR_VIEW",
    "UNSUPPORTED_FIRSTNESS",
}

ALLOWED_PROPOSED_DISPOSITIONS = {
    "include_assertive",
    "include_qualified",
    "omit_unverified",
}

_SECRET_FRAGMENTS = (
    "api_key",
    "apikey",
    "access_token",
    "refresh_token",
    "password",
    "secret",
    "credential",
    "cookie",
)
_RAW_TEXT_FRAGMENTS = (
    "raw_text",
    "full_text",
    "page_text",
    "quoted_text",
    "verbatim_source",
)


class SourceOriginClassificationError(ValueError):
    """Raised when a source-origin record could alter evidence unsafely."""


def canonical_json_sha256(payload: object) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _object(value: object, label: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise SourceOriginClassificationError(f"{label} must be an object.")
    return value


def _objects(value: object, label: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list) or any(not isinstance(item, Mapping) for item in value):
        raise SourceOriginClassificationError(f"{label} must be a list of objects.")
    return list(value)


def _strings(value: object, label: str, *, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise SourceOriginClassificationError(
            f"{label} must be a list of nonblank strings."
        )
    result = [item.strip() for item in value]
    if not allow_empty and not result:
        raise SourceOriginClassificationError(f"{label} must not be empty.")
    if len(set(result)) != len(result):
        raise SourceOriginClassificationError(f"{label} must not contain duplicates.")
    return result


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SourceOriginClassificationError(f"{key} must be a nonblank string.")
    return value.strip()


def _assert_safe_keys(value: object, path: str = "root") -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            lowered = str(key).lower()
            if any(fragment in lowered for fragment in _SECRET_FRAGMENTS):
                raise SourceOriginClassificationError(
                    f"Secret-like field is forbidden: {path}.{key}"
                )
            if any(fragment in lowered for fragment in _RAW_TEXT_FRAGMENTS):
                raise SourceOriginClassificationError(
                    f"Raw source text field is forbidden: {path}.{key}"
                )
            _assert_safe_keys(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_safe_keys(item, f"{path}[{index}]")


def _validate_global_safety(payload: Mapping[str, object], expected_status: str) -> None:
    if payload.get("status") != expected_status:
        raise SourceOriginClassificationError(
            f"Unexpected status; expected {expected_status}."
        )
    if payload.get("evidence_gate_status") != EVIDENCE_GATE_STATUS:
        raise SourceOriginClassificationError("Evidence gate must remain withheld.")
    if payload.get("automatic_evidence_approval") != AUTOMATIC_APPROVAL_STATUS:
        raise SourceOriginClassificationError(
            "Automatic evidence approval must remain forbidden."
        )
    if payload.get("live_provider_execution") != LIVE_EXECUTION_STATUS:
        raise SourceOriginClassificationError("Live provider execution must stay blocked.")


def validate_source_origin_classification(payload: Mapping[str, object]) -> None:
    _assert_safe_keys(payload)
    if payload.get("schema_version") != SOURCE_ORIGIN_CLASSIFICATION_SCHEMA:
        raise SourceOriginClassificationError(
            "Unexpected source-origin classification schema."
        )
    _validate_global_safety(payload, CLASSIFICATION_STATUS)
    if payload.get("episode_id") != "episode-001-adam":
        raise SourceOriginClassificationError("Unexpected episode id.")
    if payload.get("evidence_approval") is not False:
        raise SourceOriginClassificationError(
            "Source-origin classification cannot approve evidence."
        )
    if payload.get("human_evidence_approval") is not False:
        raise SourceOriginClassificationError(
            "Human evidence approval must still be false."
        )

    events = _objects(payload.get("events"), "events")
    ids = [_required_text(item, "event_id") for item in events]
    if tuple(ids) != TARGET_EVENT_IDS:
        raise SourceOriginClassificationError(
            f"Source-origin events must equal {TARGET_EVENT_IDS}."
        )

    by_id = {item["event_id"]: item for item in events}

    event_031 = by_id["EV-ADAM-031"]
    if event_031.get("firstness_claim") != "PROHIBITED_UNLESS_DIRECTLY_PROVEN":
        raise SourceOriginClassificationError("Adam firstness protection changed.")
    origins_031 = {
        _required_text(item, "origin_classification")
        for item in _objects(event_031.get("claims"), "EV-ADAM-031.claims")
    }
    if "AUTHENTIC_SUNNAH" not in origins_031:
        raise SourceOriginClassificationError(
            "Adam sneeze and praise must retain authentic-Sunnah classification."
        )
    if "UNSUPPORTED_FIRSTNESS" not in origins_031:
        raise SourceOriginClassificationError(
            "Unsupported firstness must remain explicitly classified."
        )

    event_071 = by_id["EV-ADAM-071"]
    loneliness = _object(event_071.get("loneliness_report"), "loneliness_report")
    if loneliness.get("origin_classification") != (
        "TAFSIR_REPORT_COMPOSITE_CHAIN_NOT_MARFU"
    ):
        raise SourceOriginClassificationError(
            "The loneliness report must remain a non-marfu tafsir report."
        )
    if loneliness.get("definite_israiliyyat_label") is not False:
        raise SourceOriginClassificationError(
            "The composite al-Suddi report cannot be called definite Israiliyyat."
        )
    if loneliness.get("assertive_narration_allowed") is not False:
        raise SourceOriginClassificationError(
            "The loneliness report cannot be narrated assertively."
        )
    if loneliness.get("narration_mode") != "QUALIFIED_TAFSIR_ATTRIBUTION":
        raise SourceOriginClassificationError(
            "The loneliness report requires qualified tafsir attribution."
        )

    synthesis = _object(
        event_071.get("supported_synthesis"),
        "EV-ADAM-071.supported_synthesis",
    )
    premises = _strings(synthesis.get("premises"), "supported_synthesis.premises")
    if premises != ["زوج آدم هي حواء", "المرأة خلقت من ضلع"]:
        raise SourceOriginClassificationError(
            "The Hawa-from-Adam-rib synthesis premises changed."
        )
    if synthesis.get("conclusion") != "حواء خلقت من ضلع آدم":
        raise SourceOriginClassificationError(
            "The supported synthesis conclusion changed."
        )
    if synthesis.get("adds_unproved_detail") is not False:
        raise SourceOriginClassificationError(
            "Supported synthesis cannot add an unproved detail."
        )

    details = _objects(
        event_071.get("secondary_details"),
        "EV-ADAM-071.secondary_details",
    )
    detail_by_id = {_required_text(item, "detail_id"): item for item in details}
    required_details = {
        "left_rib",
        "sleep_during_creation",
        "place_filled_with_flesh",
        "adam_hawa_dialogue",
        "angels_name_question",
        "name_reason_created_from_living",
    }
    if set(detail_by_id) != required_details:
        raise SourceOriginClassificationError("Hawa detail classifications changed.")
    for detail_id in ("left_rib", "sleep_during_creation", "place_filled_with_flesh"):
        item = detail_by_id[detail_id]
        if item.get("origin_classification") != "ISRAILIYYAT_EXPLICIT_ORIGIN":
            raise SourceOriginClassificationError(
                f"{detail_id} must remain explicitly classified as Israiliyyat."
            )
        if item.get("default_narration") != "OMIT":
            raise SourceOriginClassificationError(
                f"{detail_id} must be omitted by default."
            )

    event_091 = by_id["EV-ADAM-091"]
    if event_091.get("approved_narration_formula") != UNKNOWN_TREE_FORMULA:
        raise SourceOriginClassificationError("Unknown-tree narration formula changed.")
    if event_091.get("specific_tree_type_assertion") != "PROHIBITED":
        raise SourceOriginClassificationError(
            "Specific tree type assertion must stay prohibited."
        )
    if event_091.get("visual_type_identification") != "PROHIBITED":
        raise SourceOriginClassificationError(
            "The tree must remain visually unidentified."
        )

    source_records = _objects(payload.get("source_records"), "source_records")
    if not source_records:
        raise SourceOriginClassificationError("Source records must not be empty.")
    source_ids: list[str] = []
    for item in source_records:
        source_ids.append(_required_text(item, "source_record_id"))
        origin = _required_text(item, "origin_classification")
        if origin not in ALLOWED_SOURCE_ORIGINS:
            raise SourceOriginClassificationError(
                f"Unsupported source origin classification: {origin}"
            )
        if item.get("automatic_grade") is not False:
            raise SourceOriginClassificationError(
                "Source records cannot contain an automatic grade."
            )
        references = _strings(item.get("references"), "source_record.references")
        if not references:
            raise SourceOriginClassificationError(
                "Every source record needs a traceable reference."
            )
    if len(source_ids) != len(set(source_ids)):
        raise SourceOriginClassificationError("Source record ids must be unique.")


def validate_proposed_gap_adjudication(payload: Mapping[str, object]) -> None:
    _assert_safe_keys(payload)
    if payload.get("schema_version") != PROPOSED_GAP_ADJUDICATION_SCHEMA:
        raise SourceOriginClassificationError(
            "Unexpected proposed adjudication schema."
        )
    _validate_global_safety(payload, PROPOSAL_STATUS)
    if payload.get("episode_id") != "episode-001-adam":
        raise SourceOriginClassificationError("Unexpected proposal episode id.")
    if payload.get("human_approval") is not False:
        raise SourceOriginClassificationError(
            "Proposed adjudication cannot contain human approval."
        )
    if payload.get("binding") is not False:
        raise SourceOriginClassificationError("Proposed adjudication cannot be binding.")
    if payload.get("opens_evidence_gate") is not False:
        raise SourceOriginClassificationError(
            "Proposed adjudication cannot open evidence gate."
        )

    decisions = _objects(payload.get("decisions"), "decisions")
    ids = [_required_text(item, "event_id") for item in decisions]
    if tuple(ids) != TARGET_EVENT_IDS:
        raise SourceOriginClassificationError(
            f"Proposed decisions must equal {TARGET_EVENT_IDS}."
        )
    by_id = {item["event_id"]: item for item in decisions}
    for item in decisions:
        disposition = _required_text(item, "proposed_disposition")
        if disposition not in ALLOWED_PROPOSED_DISPOSITIONS:
            raise SourceOriginClassificationError(
                f"Unsupported proposed disposition: {disposition}"
            )
        if item.get("human_decision") is not False:
            raise SourceOriginClassificationError(
                "Every proposed decision must remain non-human and non-binding."
            )
        if item.get("evidence_ids") != []:
            raise SourceOriginClassificationError(
                "Proposed decisions cannot bind evidence ids."
            )

    if by_id["EV-ADAM-031"].get("proposed_disposition") != "include_assertive":
        raise SourceOriginClassificationError(
            "EV-ADAM-031 must retain the narrowed assertive proposal."
        )
    if by_id["EV-ADAM-071"].get("proposed_disposition") != "include_qualified":
        raise SourceOriginClassificationError(
            "EV-ADAM-071 must retain mixed assertive/qualified treatment."
        )
    if by_id["EV-ADAM-091"].get("proposed_disposition") != "include_qualified":
        raise SourceOriginClassificationError(
            "EV-ADAM-091 must narrate the uncertainty rather than silently vanish."
        )
    if (
        by_id["EV-ADAM-091"].get("proposed_narration")
        != UNKNOWN_TREE_FORMULA
    ):
        raise SourceOriginClassificationError(
            "EV-ADAM-091 proposed narration formula changed."
        )


def load_and_validate_bundle(repo_root: Path) -> dict[str, object]:
    repo_root = Path(repo_root)
    classification_path = (
        repo_root
        / "projects/episode-001-adam/evidence/source-origin-classification-v1.json"
    )
    proposal_path = (
        repo_root
        / "projects/episode-001-adam/evidence/proposed-gap-adjudication-v1.json"
    )
    try:
        classification = json.loads(
            classification_path.read_text(encoding="utf-8-sig")
        )
        proposal = json.loads(proposal_path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SourceOriginClassificationError(
            "Could not load source-origin classification bundle."
        ) from error
    classification = _object(classification, "classification")
    proposal = _object(proposal, "proposal")
    validate_source_origin_classification(classification)
    validate_proposed_gap_adjudication(proposal)
    if proposal.get("classification_id") != classification.get("classification_id"):
        raise SourceOriginClassificationError(
            "Proposed adjudication must reference the classification id."
        )
    if proposal.get("classification_sha256") != canonical_json_sha256(classification):
        raise SourceOriginClassificationError(
            "Proposed adjudication classification hash is stale."
        )
    return {
        "classification": classification,
        "proposal": proposal,
    }


def write_validation_manifest(repo_root: Path, output: Path) -> dict[str, object]:
    bundle = load_and_validate_bundle(repo_root)
    classification = _object(bundle["classification"], "classification")
    proposal = _object(bundle["proposal"], "proposal")
    manifest = {
        "schema_version": "siraj-source-origin-validation-v1",
        "status": "PASS",
        "classification_id": classification["classification_id"],
        "classification_sha256": canonical_json_sha256(classification),
        "proposal_sha256": canonical_json_sha256(proposal),
        "event_ids": list(TARGET_EVENT_IDS),
        "loneliness_origin": (
            "TAFSIR_REPORT_COMPOSITE_CHAIN_NOT_MARFU"
        ),
        "explicit_israiliyyat_details": [
            "left_rib",
            "sleep_during_creation",
            "place_filled_with_flesh",
        ],
        "unsupported_firstness": "PROHIBITED",
        "tree_type_assertion": "PROHIBITED",
        "evidence_gate_status": EVIDENCE_GATE_STATUS,
        "automatic_evidence_approval": AUTOMATIC_APPROVAL_STATUS,
        "human_approval": False,
        "live_provider_execution": LIVE_EXECUTION_STATUS,
    }
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return manifest
