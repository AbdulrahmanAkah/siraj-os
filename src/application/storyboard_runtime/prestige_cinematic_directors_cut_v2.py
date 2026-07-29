"""Build the evidence-bound prestige cinematic script and storyboard."""
from __future__ import annotations

import copy
import csv
import hashlib
import json
import zipfile
from pathlib import Path
from typing import Mapping, Sequence

SCRIPT_BLUEPRINT_SCHEMA = "siraj-prestige-cinematic-directors-cut-blueprint-v2"
SCRIPT_SCHEMA = "siraj-prestige-cinematic-script-v2"
STORYBOARD_SCHEMA = "siraj-detailed-cinematic-storyboard-v2"
TRACE_SCHEMA = "siraj-script-storyboard-evidence-trace-v2"
APPROVAL_REQUEST_SCHEMA = "siraj-script-storyboard-human-approval-request-v2"
PRODUCTION_BRIEF_SCHEMA = "siraj-prestige-production-brief-v2"

TIMEZONE = "Asia/Baghdad"
EVIDENCE_GATE_OPEN = "OPEN_APPROVED_EVIDENCE_PACKAGE_BOUND"
LIVE_EXECUTION = "BLOCKED"
PAID_EXECUTION = "BLOCKED"
FORMAT_IDENTITY = "PRESTIGE_HISTORICAL_CINEMATIC_SERIES"
PRODUCTION_PROFILE = "WORLD_CLASS_PRESTIGE_HISTORICAL_CINEMA_V1"

EXPECTED_FRAME_COUNT = 14
EXPECTED_EVENT_COUNT = 37
EXPECTED_EVIDENCE_ITEM_COUNT = 57
EXPECTED_TOTAL_SECONDS = 1320
EXPECTED_SHOT_COUNT = 70
EXPECTED_QUALIFIED_EVENTS = {
    "EV-ADAM-007",
    "EV-ADAM-021",
    "EV-ADAM-042",
    "EV-ADAM-061",
    "EV-ADAM-070",
    "EV-ADAM-071",
    "EV-ADAM-091",
}
EDITORIAL_EVENT_ID = "EV-ADAM-099"

APPROVAL_PHRASE = (
    "أعتمد بشريًا النسخة الإخراجية الثانية للنص السينمائي "
    "والستوريبورد التفصيلي لحلقة آدم وفق بصمتيهما المحددتين، "
    "وأجيز الانتقال إلى تصميم الهوية البصرية الرئيسية والأنيماتيك "
    "غير المدفوع دون السماح بأي تشغيل مدفوع أو مباشر"
)

SUPERSEDED_SCRIPT_ID = "adam_prestige_cinematic_script_c187aabf5ee4b245"
SUPERSEDED_SCRIPT_FINGERPRINT = (
    "c187aabf5ee4b245439b3404715e6174fd391c77f4c93a80de8fafe0f4b7ae85"
)
SUPERSEDED_STORYBOARD_ID = (
    "adam_detailed_cinematic_storyboard_92caa3306cff1ecb"
)
SUPERSEDED_STORYBOARD_FINGERPRINT = (
    "92caa3306cff1ecb63f5c76b062fb39f5f76c1d94060feab1c906675452ce8b2"
)

FORBIDDEN_RESEARCH_META_PHRASES = (
    "نحن لا نبحث",
    "نذكر الحديث",
    "ورد في الحديث",
    "في الحديث الصحيح",
    "ما المراد بالأسماء",
    "ذكر المفسرون",
    "اختلف المفسرون",
    "لا نصور الروح",
    "لا نملأ الغيب",
    "بدرجته المسجلة",
    "إذا احتاجها السياق",
    "لم يثبت نص صحيح يعين",
)

MATERIAL_TREATMENTS = {
    "cinematic_matte_painting",
    "environment_vfx_plan",
    "practical_macro_reference",
}
MINIMUM_MATERIAL_SHOT_COUNT = 60

FORBIDDEN_VISUAL_PHRASES = (
    "وجه الله",
    "جسد الله",
    "هيئة الله",
    "وجه آدم ظاهر",
    "جسد آدم كامل",
    "ملامح آدم",
    "وجه حواء ظاهر",
    "ملامح حواء",
    "هيئة ملاك",
    "أجساد الملائكة",
    "وجه إبليس",
    "جسد إبليس",
)


class DirectorsCutError(ValueError):
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
        raise DirectorsCutError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise DirectorsCutError(f"Expected object: {path}")
    return value


def read_json_list(path: Path) -> list[dict]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise DirectorsCutError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, list) or not all(
        isinstance(item, dict) for item in value
    ):
        raise DirectorsCutError(f"Expected object list: {path}")
    return [dict(item) for item in value]


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def validate_superseded_artifacts(
    *,
    script_v1: Mapping[str, object],
    storyboard_v1: Mapping[str, object],
) -> None:
    if script_v1.get("script_id") != SUPERSEDED_SCRIPT_ID:
        raise DirectorsCutError("Unexpected superseded script id.")
    if script_v1.get("script_fingerprint") != (
        SUPERSEDED_SCRIPT_FINGERPRINT
    ):
        raise DirectorsCutError("Unexpected superseded script fingerprint.")
    if storyboard_v1.get("storyboard_id") != (
        SUPERSEDED_STORYBOARD_ID
    ):
        raise DirectorsCutError("Unexpected superseded storyboard id.")
    if storyboard_v1.get("storyboard_fingerprint") != (
        SUPERSEDED_STORYBOARD_FINGERPRINT
    ):
        raise DirectorsCutError(
            "Unexpected superseded storyboard fingerprint."
        )


def _frame_indices(
    bound_blueprint: Mapping[str, object],
) -> tuple[dict[str, dict], dict[str, dict]]:
    storyboard = bound_blueprint.get("storyboard")
    compilation = bound_blueprint.get("cinematic_compilation")
    if not isinstance(storyboard, Mapping) or not isinstance(
        compilation, Mapping
    ):
        raise DirectorsCutError(
            "Bound blueprint lacks storyboard or compilation."
        )
    bound_frames = storyboard.get("frames")
    directives = compilation.get("frames")
    if not isinstance(bound_frames, list) or not isinstance(
        directives, list
    ):
        raise DirectorsCutError("Blueprint frames are missing.")
    return (
        {item["frame_id"]: dict(item) for item in bound_frames},
        {item["frame_id"]: dict(item) for item in directives},
    )


def _word_count(text: str) -> int:
    return len([token for token in text.split() if token.strip()])


def validate_inputs(
    *,
    creative_blueprint: Mapping[str, object],
    bound_blueprint: Mapping[str, object],
    direction: Mapping[str, object],
    event_map: Sequence[Mapping[str, object]],
    evidence_package: Mapping[str, object],
    adjudication: Mapping[str, object],
    episode_definition: Mapping[str, object],
) -> None:
    if creative_blueprint.get("schema_version") != SCRIPT_BLUEPRINT_SCHEMA:
        raise DirectorsCutError(
            "Unexpected creative blueprint schema."
        )
    if creative_blueprint.get("sequence_count") != EXPECTED_FRAME_COUNT:
        raise DirectorsCutError("Expected fourteen sequences.")
    if creative_blueprint.get("shot_count") != EXPECTED_SHOT_COUNT:
        raise DirectorsCutError("Expected seventy shots.")
    if creative_blueprint.get("target_duration_seconds") != (
        EXPECTED_TOTAL_SECONDS
    ):
        raise DirectorsCutError("Expected 1320 seconds.")
    if creative_blueprint.get("timezone") != TIMEZONE:
        raise DirectorsCutError(
            "Creative blueprint must use Asia/Baghdad."
        )
    if creative_blueprint.get("adaptation_policy") != (
        "MEANING_PRESERVED_WORDING_CINEMATICALLY_ADAPTED"
    ):
        raise DirectorsCutError(
            "Director's Cut must preserve meaning while adapting wording."
        )
    if creative_blueprint.get("source_wording_policy") != (
        "SOURCE_LANGUAGE_NOT_REQUIRED_EXCEPT_WHEN_DRAMATICALLY_OR_DOCTRINALLY_USEFUL"
    ):
        raise DirectorsCutError(
            "Unexpected source-wording policy."
        )
    payload = copy.deepcopy(dict(creative_blueprint))
    stored_fingerprint = payload.pop("creative_blueprint_fingerprint", None)
    if stored_fingerprint != canonical_sha256(payload):
        raise DirectorsCutError(
            "Creative blueprint fingerprint mismatch."
        )

    if bound_blueprint.get("evidence_gate_status") != EVIDENCE_GATE_OPEN:
        raise DirectorsCutError("Evidence gate is not open.")
    if bound_blueprint.get("live_execution_status") != LIVE_EXECUTION:
        raise DirectorsCutError("Live execution must be blocked.")
    runware = bound_blueprint.get("runware_execution_status")
    if not isinstance(runware, str) or not runware.startswith("BLOCKED"):
        raise DirectorsCutError("Runware must remain blocked.")
    if direction.get("format_identity") != FORMAT_IDENTITY:
        raise DirectorsCutError(
            "Prestige historical direction is not active."
        )
    if direction.get("production_profile") != PRODUCTION_PROFILE:
        raise DirectorsCutError(
            "World-class production profile is absent."
        )
    if direction.get("timezone") != TIMEZONE:
        raise DirectorsCutError(
            "Canonical creator timezone must be Asia/Baghdad."
        )
    if direction.get("live_provider_execution") != LIVE_EXECUTION:
        raise DirectorsCutError(
            "Direction contract must block live execution."
        )
    if len(event_map) != EXPECTED_EVENT_COUNT:
        raise DirectorsCutError("Expected 37 event-map entries.")
    if len(evidence_package.get("evidence_items", [])) != (
        EXPECTED_EVIDENCE_ITEM_COUNT
    ):
        raise DirectorsCutError("Expected 57 evidence items.")
    if len(adjudication.get("decisions", [])) != EXPECTED_EVENT_COUNT:
        raise DirectorsCutError(
            "Expected 37 event decisions."
        )
    if episode_definition.get("evidence_gate_status") != EVIDENCE_GATE_OPEN:
        raise DirectorsCutError(
            "Episode definition does not record the open evidence gate."
        )

    frame_index, directive_index = _frame_indices(bound_blueprint)
    if len(frame_index) != EXPECTED_FRAME_COUNT or len(
        directive_index
    ) != EXPECTED_FRAME_COUNT:
        raise DirectorsCutError("Expected fourteen frames.")
    creative_ids = [
        item["frame_id"] for item in creative_blueprint["sequences"]
    ]
    expected_ids = [
        item["frame_id"]
        for item in bound_blueprint["storyboard"]["frames"]
    ]
    if creative_ids != expected_ids:
        raise DirectorsCutError(
            "Creative sequence order differs from the bound storyboard."
        )


def build_script_and_storyboard(
    *,
    creative_blueprint: Mapping[str, object],
    bound_blueprint: Mapping[str, object],
    direction: Mapping[str, object],
    event_map: Sequence[Mapping[str, object]],
    evidence_package: Mapping[str, object],
    adjudication: Mapping[str, object],
) -> tuple[dict, dict, dict, dict, dict]:
    frame_index, directive_index = _frame_indices(bound_blueprint)
    event_index = {item["event_id"]: dict(item) for item in event_map}
    decision_index = {
        item["event_id"]: dict(item)
        for item in adjudication["decisions"]
    }
    evidence_index = {
        item["evidence_id"]: dict(item)
        for item in evidence_package["evidence_items"]
    }

    sequences = []
    all_shots = []
    traced_events: list[str] = []
    traced_evidence: list[str] = []
    for creative in creative_blueprint["sequences"]:
        frame_id = creative["frame_id"]
        frame = frame_index[frame_id]
        directive = directive_index[frame_id]
        trace = frame["trace_metadata"]
        event_ids = list(trace["event_ids"])
        evidence_ids = list(frame["referenced_evidence_ids"])
        qualification_labels = list(trace["qualification_labels"])

        for event_id in event_ids:
            if event_id not in event_index:
                raise DirectorsCutError(
                    f"Unknown event in bound frame: {event_id}"
                )
            if event_id != EDITORIAL_EVENT_ID and event_id not in (
                bound_blueprint["event_resolution"]["included_event_ids"]
            ):
                raise DirectorsCutError(
                    f"Non-included event in script: {event_id}"
                )
            if event_id in decision_index:
                decision = decision_index[event_id]
                if (
                    decision["disposition"] == "include_qualified"
                    and not decision["qualification_label"]
                ):
                    raise DirectorsCutError(
                        f"Qualified event lacks label: {event_id}"
                    )
        for evidence_id in evidence_ids:
            if evidence_id not in evidence_index:
                raise DirectorsCutError(
                    f"Unknown evidence in bound frame: {evidence_id}"
                )

        shots = copy.deepcopy(creative["shots"])
        if sum(item["duration_seconds"] for item in shots) != (
            directive["planned_seconds"]
        ):
            raise DirectorsCutError(
                f"Shot duration mismatch for {frame_id}"
            )
        for shot in shots:
            shot["sequence_id"] = (
                f"ADAM-SEQUENCE-{creative['sequence_number']:02d}"
            )
            shot["frame_id"] = frame_id
            shot["scene_id"] = frame["scene_id"]
            shot["event_ids"] = event_ids
            shot["evidence_ids"] = evidence_ids

        sequence = {
            **copy.deepcopy(creative),
            "sequence_id": (
                f"ADAM-SEQUENCE-{creative['sequence_number']:02d}"
            ),
            "scene_id": frame["scene_id"],
            "duration_seconds": directive["planned_seconds"],
            "narrative_function": directive["narrative_function"],
            "spectacle_level": directive["spectacle_level"],
            "evidence_mode": directive["evidence_mode"],
            "narration_word_count": _word_count(creative["narration"]),
            "event_ids": event_ids,
            "event_titles": [
                event_index[event_id]["title"] for event_id in event_ids
            ],
            "evidence_ids": evidence_ids,
            "qualification_labels": qualification_labels,
            "shot_count": len(shots),
            "shots": shots,
            "live_provider_execution": LIVE_EXECUTION,
            "paid_execution": PAID_EXECUTION,
        }
        sequences.append(sequence)
        all_shots.extend(shots)
        traced_events.extend(event_ids)
        traced_evidence.extend(evidence_ids)

    script = {
        "schema_version": SCRIPT_SCHEMA,
        "status": "HUMAN_REVIEW_REQUIRED",
        "episode_id": "episode-001-adam",
        "series_title": creative_blueprint["series_title"],
        "episode_title": creative_blueprint["episode_title"],
        "language": "ar",
        "timezone": TIMEZONE,
        "created_date_baghdad": creative_blueprint[
            "created_date_baghdad"
        ],
        "format_identity": FORMAT_IDENTITY,
        "production_profile": PRODUCTION_PROFILE,
        "director_cut_version": 2,
        "adaptation_policy": creative_blueprint["adaptation_policy"],
        "source_wording_policy": creative_blueprint[
            "source_wording_policy"
        ],
        "narrative_policy": copy.deepcopy(
            creative_blueprint["narrative_policy"]
        ),
        "supersedes": {
            "script_id": SUPERSEDED_SCRIPT_ID,
            "script_fingerprint": SUPERSEDED_SCRIPT_FINGERPRINT,
        },
        "creative_blueprint_fingerprint": creative_blueprint[
            "creative_blueprint_fingerprint"
        ],
        "target_duration_seconds": EXPECTED_TOTAL_SECONDS,
        "sequence_count": len(sequences),
        "narration_word_count": sum(
            item["narration_word_count"] for item in sequences
        ),
        "dramatic_arc": copy.deepcopy(
            direction["dramatic_engine"]["episode_arc"]
        ),
        "creative_statement": (
            "المعلومة تتحول إلى فعل درامي وصورة وصوت وإيقاع، "
            "مع حفظ معناها ودرجة الجزم بها؛ لا سياق مصدري حرفي "
            "ولا محاضرة ولا وثائقي تلقيني."
        ),
        "sequences": sequences,
        "human_script_approval": False,
        "religious_safety_approval": False,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
    }
    script["script_fingerprint"] = canonical_sha256(script)
    script["script_id"] = (
        "adam_prestige_cinematic_script_v2_"
        + script["script_fingerprint"][:16]
    )

    storyboard = {
        "schema_version": STORYBOARD_SCHEMA,
        "status": "HUMAN_REVIEW_REQUIRED",
        "episode_id": "episode-001-adam",
        "script_id": script["script_id"],
        "script_fingerprint": script["script_fingerprint"],
        "timezone": TIMEZONE,
        "format_identity": FORMAT_IDENTITY,
        "director_cut_version": 2,
        "meaning_preservation": "REQUIRED",
        "adaptation_policy": (
            "MEANING_PRESERVED_WORDING_CINEMATICALLY_ADAPTED"
        ),
        "supersedes": {
            "storyboard_id": SUPERSEDED_STORYBOARD_ID,
            "storyboard_fingerprint":
                SUPERSEDED_STORYBOARD_FINGERPRINT,
        },
        "target_duration_seconds": EXPECTED_TOTAL_SECONDS,
        "sequence_count": len(sequences),
        "shot_count": len(all_shots),
        "shots": all_shots,
        "master_visual_rules": {
            "literal_unseen_depiction": "FORBIDDEN",
            "allah_depiction": "FORBIDDEN",
            "angel_body_depiction": "FORBIDDEN",
            "prophet_face_or_body_depiction": "FORBIDDEN",
            "iblis_body_depiction": "FORBIDDEN",
            "invented_historical_dialogue": "FORBIDDEN",
            "symbolic_environmental_visuals": (
                "ALLOWED_NON_ASSERTIVELY"
            ),
            "generated_or_paid_execution": PAID_EXECUTION,
        },
        "human_storyboard_approval": False,
        "master_visual_approval": False,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
    }
    storyboard["storyboard_fingerprint"] = canonical_sha256(storyboard)
    storyboard["storyboard_id"] = (
        "adam_detailed_cinematic_storyboard_v2_"
        + storyboard["storyboard_fingerprint"][:16]
    )

    event_set = set(traced_events)
    evidence_set = set(traced_evidence)
    expected_event_set = {
        item["event_id"] for item in event_map
    }
    expected_evidence_set = {
        item["evidence_id"]
        for item in evidence_package["evidence_items"]
    }
    trace = {
        "schema_version": TRACE_SCHEMA,
        "status": "PASS_COMPLETE_TRACE",
        "episode_id": "episode-001-adam",
        "director_cut_version": 2,
        "meaning_preservation": "REQUIRED",
        "script_id": script["script_id"],
        "storyboard_id": storyboard["storyboard_id"],
        "event_count": len(event_set),
        "evidence_item_count": len(evidence_set),
        "qualified_event_ids": sorted(EXPECTED_QUALIFIED_EVENTS),
        "editorial_event_id": EDITORIAL_EVENT_ID,
        "missing_event_ids": sorted(expected_event_set - event_set),
        "unexpected_event_ids": sorted(event_set - expected_event_set),
        "missing_evidence_ids": sorted(expected_evidence_set - evidence_set),
        "unexpected_evidence_ids": sorted(
            evidence_set - expected_evidence_set
        ),
        "event_coverage_complete": event_set == expected_event_set,
        "evidence_coverage_complete": evidence_set == expected_evidence_set,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
    }
    trace["trace_id"] = (
        "adam_script_storyboard_trace_v2_"
        + canonical_sha256(trace)[:16]
    )

    approval_request = {
        "schema_version": APPROVAL_REQUEST_SCHEMA,
        "status": "SCRIPT_STORYBOARD_HUMAN_APPROVAL_REQUIRED",
        "episode_id": "episode-001-adam",
        "director_cut_version": 2,
        "adaptation_policy":
            "MEANING_PRESERVED_WORDING_CINEMATICALLY_ADAPTED",
        "script_id": script["script_id"],
        "script_fingerprint": script["script_fingerprint"],
        "storyboard_id": storyboard["storyboard_id"],
        "storyboard_fingerprint": storyboard[
            "storyboard_fingerprint"
        ],
        "trace_id": trace["trace_id"],
        "exact_approval_phrase": APPROVAL_PHRASE,
        "exact_approval_phrase_sha256": hashlib.sha256(
            APPROVAL_PHRASE.encode("utf-8")
        ).hexdigest(),
        "approval_effect": [
            "اعتماد النسخة الإخراجية الثانية للنص السينمائي",
            "اعتماد حفظ المعنى مع التحرر من السياق المصدري الحرفي",
            "اعتماد السلامة الدينية للنص",
            "اعتماد الستوريبورد التفصيلي الثاني",
            "السماح ببناء الهوية البصرية الرئيسية والأنيماتيك غير المدفوع",
            "عدم السماح بأي تشغيل مدفوع أو مباشر",
        ],
        "human_approval": False,
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
    }
    approval_request["request_id"] = (
        "adam_script_storyboard_approval_request_v2_"
        + canonical_sha256(approval_request)[:16]
    )

    production_brief = {
        "schema_version": PRODUCTION_BRIEF_SCHEMA,
        "status": "PLANNING_ONLY_PROVIDER_EXECUTION_BLOCKED",
        "episode_id": "episode-001-adam",
        "director_cut_version": 2,
        "adaptation_policy":
            "MEANING_PRESERVED_WORDING_CINEMATICALLY_ADAPTED",
        "script_id": script["script_id"],
        "storyboard_id": storyboard["storyboard_id"],
        "creative_target": (
            "World-class prestige historical cinema: epic scale, intimate "
            "emotional progression, authored visual language, and "
            "evidence-bound religious safety."
        ),
        "sequence_count": len(sequences),
        "shot_count": len(all_shots),
        "target_duration_seconds": EXPECTED_TOTAL_SECONDS,
        "generated_video_planned_seconds": 0,
        "provider_selection": "DEFERRED",
        "budget_allocation": "DEFERRED",
        "animatic_status": (
            "PENDING_HUMAN_SCRIPT_STORYBOARD_APPROVAL"
        ),
        "live_provider_execution": LIVE_EXECUTION,
        "paid_execution": PAID_EXECUTION,
    }
    production_brief["brief_id"] = (
        "adam_prestige_production_brief_v2_"
        + canonical_sha256(production_brief)[:16]
    )

    validate_outputs(
        script=script,
        storyboard=storyboard,
        trace=trace,
        approval_request=approval_request,
        production_brief=production_brief,
        bound_blueprint=bound_blueprint,
    )
    return (
        script,
        storyboard,
        trace,
        approval_request,
        production_brief,
    )


def validate_outputs(
    *,
    script: Mapping[str, object],
    storyboard: Mapping[str, object],
    trace: Mapping[str, object],
    approval_request: Mapping[str, object],
    production_brief: Mapping[str, object],
    bound_blueprint: Mapping[str, object],
) -> None:
    sequences = script.get("sequences")
    shots = storyboard.get("shots")
    if not isinstance(sequences, list) or len(sequences) != (
        EXPECTED_FRAME_COUNT
    ):
        raise DirectorsCutError("Script must have 14 sequences.")
    if not isinstance(shots, list) or len(shots) != EXPECTED_SHOT_COUNT:
        raise DirectorsCutError("Storyboard must have 70 shots.")
    if sum(item["duration_seconds"] for item in sequences) != (
        EXPECTED_TOTAL_SECONDS
    ):
        raise DirectorsCutError("Script duration must be 1320s.")
    if sum(item["duration_seconds"] for item in shots) != (
        EXPECTED_TOTAL_SECONDS
    ):
        raise DirectorsCutError(
            "Storyboard shot duration must be 1320s."
        )
    if len({item["shot_id"] for item in shots}) != len(shots):
        raise DirectorsCutError("Shot ids must be unique.")
    if not 1200 <= script["narration_word_count"] <= 3500:
        raise DirectorsCutError(
            "Narration density is outside the cinematic range."
        )
    frame_ids = [item["frame_id"] for item in sequences]
    expected_frame_ids = [
        item["frame_id"]
        for item in bound_blueprint["storyboard"]["frames"]
    ]
    if frame_ids != expected_frame_ids:
        raise DirectorsCutError(
            "Script sequence order differs from bound storyboard."
        )
    qualified = {
        event_id
        for item in sequences
        for event_id in item["event_ids"]
        if event_id in EXPECTED_QUALIFIED_EVENTS
    }
    if qualified != EXPECTED_QUALIFIED_EVENTS:
        raise DirectorsCutError(
            "Qualified event coverage is incomplete."
        )
    for item in sequences:
        visual_text = (
            item["visual_thesis"]
            + " "
            + " ".join(
                " ".join(str(value) for value in shot.values())
                for shot in item["shots"]
            )
        )
        for phrase in FORBIDDEN_VISUAL_PHRASES:
            if phrase in visual_text:
                raise DirectorsCutError(
                    f"Forbidden visual phrase in {item['sequence_id']}"
                )
        if not item["dialogue_policy"].startswith("NO_INVENTED"):
            raise DirectorsCutError(
                "Dialogue policy must forbid invented dialogue."
            )
        for phrase in FORBIDDEN_RESEARCH_META_PHRASES:
            if phrase in item["narration"]:
                raise DirectorsCutError(
                    f"Research meta-language remains in {item['sequence_id']}: "
                    f"{phrase}"
                )
    material_shot_count = sum(
        1 for shot in shots
        if shot["treatment"] in MATERIAL_TREATMENTS
    )
    if material_shot_count < MINIMUM_MATERIAL_SHOT_COUNT:
        raise DirectorsCutError(
            "Director's Cut remains too abstract."
        )
    if script.get("adaptation_policy") != (
        "MEANING_PRESERVED_WORDING_CINEMATICALLY_ADAPTED"
    ):
        raise DirectorsCutError(
            "Meaning-preserving adaptation policy is missing."
        )
    if trace["event_coverage_complete"] is not True:
        raise DirectorsCutError(
            f"Missing events: {trace['missing_event_ids']}"
        )
    if trace["evidence_coverage_complete"] is not True:
        raise DirectorsCutError(
            f"Missing evidence: {trace['missing_evidence_ids']}"
        )
    if approval_request["human_approval"] is not False:
        raise DirectorsCutError(
            "Script/storyboard approval cannot be automatic."
        )
    for artifact in (
        script,
        storyboard,
        trace,
        approval_request,
        production_brief,
    ):
        if artifact["live_provider_execution"] != LIVE_EXECUTION:
            raise DirectorsCutError(
                "Live provider execution must remain blocked."
            )
        if artifact["paid_execution"] != PAID_EXECUTION:
            raise DirectorsCutError(
                "Paid execution must remain blocked."
            )


def update_episode_definition(
    *,
    episode_definition: Mapping[str, object],
    script: Mapping[str, object],
    storyboard: Mapping[str, object],
    trace: Mapping[str, object],
    approval_request: Mapping[str, object],
    production_brief: Mapping[str, object],
) -> dict:
    definition = copy.deepcopy(dict(episode_definition))
    existing_revision = definition.get("director_cut_revision")
    existing_superseded = definition.get(
        "superseded_script_storyboard_v1"
    )
    already_v2 = (
        isinstance(existing_revision, Mapping)
        and str(existing_revision.get("version")) in {"2", "2.1"}
    )

    if already_v2:
        if not isinstance(existing_superseded, Mapping):
            raise DirectorsCutError(
                "Existing Director's Cut v2 definition lacks the "
                "superseded v1 audit record."
            )
        superseded_v1 = copy.deepcopy(dict(existing_superseded))
        if (
            superseded_v1.get("script_fingerprint")
            != SUPERSEDED_SCRIPT_FINGERPRINT
            or superseded_v1.get("storyboard_fingerprint")
            != SUPERSEDED_STORYBOARD_FINGERPRINT
        ):
            raise DirectorsCutError(
                "Existing superseded v1 fingerprints changed."
            )
    else:
        previous_script = copy.deepcopy(
            definition.get("cinematic_script")
        )
        previous_storyboard = copy.deepcopy(
            definition.get("detailed_storyboard")
        )
        superseded_v1 = {
            "status": "SUPERSEDED_BY_DIRECTORS_CUT_V2",
            "cinematic_script": previous_script,
            "detailed_storyboard": previous_storyboard,
            "script_id": SUPERSEDED_SCRIPT_ID,
            "script_fingerprint": SUPERSEDED_SCRIPT_FINGERPRINT,
            "storyboard_id": SUPERSEDED_STORYBOARD_ID,
            "storyboard_fingerprint":
                SUPERSEDED_STORYBOARD_FINGERPRINT,
        }

    definition["superseded_script_storyboard_v1"] = superseded_v1
    definition["cinematic_script"] = {
        "status": "HUMAN_REVIEW_REQUIRED",
        "path": "editorial/prestige-cinematic-script-v2.json",
        "markdown_path": "editorial/prestige-cinematic-script-v2.md",
        "script_id": script["script_id"],
        "input_fingerprint": script["script_fingerprint"],
        "human_approval": False,
        "director_cut_version": 2,
    }
    definition["detailed_storyboard"] = {
        "status": "HUMAN_REVIEW_REQUIRED",
        "path": "cinematic/detailed-storyboard-v2.json",
        "storyboard_id": storyboard["storyboard_id"],
        "input_fingerprint": storyboard["storyboard_fingerprint"],
        "human_approval": False,
        "director_cut_version": 2,
    }
    definition["script_storyboard_trace"] = {
        "status": "PASS_COMPLETE_TRACE",
        "path": "evidence/script-storyboard-evidence-trace-v2.json",
        "trace_id": trace["trace_id"],
    }
    definition["script_storyboard_approval_request"] = {
        "status": "HUMAN_APPROVAL_REQUIRED",
        "path": (
            "evidence/script-storyboard-human-approval-request-v2.json"
        ),
        "request_id": approval_request["request_id"],
    }
    definition["production_brief"] = {
        "status": "PLANNING_ONLY_PROVIDER_EXECUTION_BLOCKED",
        "path": "cinematic/prestige-production-brief-v2.json",
        "brief_id": production_brief["brief_id"],
    }
    definition["director_cut_revision"] = {
        "version": 2,
        "status": "HUMAN_REVIEW_REQUIRED",
        "adaptation_policy":
            "MEANING_PRESERVED_WORDING_CINEMATICALLY_ADAPTED",
        "source_context_literalism": "REMOVED",
        "meaning_change": "FORBIDDEN",
        "supersedes_script_fingerprint":
            SUPERSEDED_SCRIPT_FINGERPRINT,
        "supersedes_storyboard_fingerprint":
            SUPERSEDED_STORYBOARD_FINGERPRINT,
        "script_fingerprint": script["script_fingerprint"],
        "storyboard_fingerprint":
            storyboard["storyboard_fingerprint"],
    }
    definition["next_stage"] = (
        "HUMAN_REVIEW_OF_PRESTIGE_CINEMATIC_DIRECTORS_CUT_V2"
    )
    definition["live_execution_status"] = LIVE_EXECUTION
    definition["paid_execution"] = PAID_EXECUTION
    definition["timezone_policy"]["canonical_local_timezone"] = TIMEZONE
    return definition


def render_script_markdown(script: Mapping[str, object]) -> str:
    lines = [
        "# سراج: التاريخ الإسلامي",
        "",
        "## الحلقة الأولى: آدم — التكريم والاختبار — Director’s Cut v2",
        "",
        f"**المدة المستهدفة:** {script['target_duration_seconds'] // 60} دقيقة",
        f"**عدد التسلسلات:** {script['sequence_count']}",
        f"**عدد كلمات التعليق:** {script['narration_word_count']}",
        "",
        "> المعنى محفوظ، لكن المعلومة لا تُلقى بصيغة المصدر؛ "
        "تتحول إلى دراما وصورة وصوت وإيقاع.",
        "",
    ]
    for sequence in script["sequences"]:
        lines.extend(
            [
                f"## {sequence['sequence_number']:02d}. "
                f"{sequence['sequence_title']}",
                "",
                f"**المدة:** {sequence['duration_seconds']} ثانية",
                f"**الوظيفة الدرامية:** {sequence['narrative_function']}",
                f"**الهدف:** {sequence['dramatic_objective']}",
                f"**الضغط:** {sequence['pressure']}",
                f"**التحول:** {sequence['turn']}",
                "",
                "### التعليق الصوتي",
                "",
                sequence["narration"],
                "",
                "### المعالجة",
                "",
                f"- الأطروحة البصرية: {sequence['visual_thesis']}",
                f"- نظام الصورة: {sequence['image_system']}",
                f"- تصميم الصوت: {sequence['sound_design']}",
                f"- الموسيقى: {sequence['music_direction']}",
                f"- الانتقال: {sequence['transition']}",
                f"- الأحداث: {', '.join(sequence['event_ids']) or 'تحريري'}",
                f"- القيود: {', '.join(sequence['qualification_labels']) or 'لا يوجد'}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(
    *,
    output_root: Path,
    script: Mapping[str, object],
    storyboard: Mapping[str, object],
    trace: Mapping[str, object],
    approval_request: Mapping[str, object],
    production_brief: Mapping[str, object],
    episode_definition: Mapping[str, object],
) -> dict[str, Path]:
    output_root = Path(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = {
        "script_json": output_root / "prestige-cinematic-script-v2.json",
        "script_markdown": output_root / "prestige-cinematic-script-v2.md",
        "storyboard_json": output_root / "detailed-storyboard-v2.json",
        "storyboard_csv": output_root / "detailed-storyboard-v2.csv",
        "trace": output_root / "script-storyboard-evidence-trace-v2.json",
        "approval_request": output_root
        / "script-storyboard-human-approval-request-v2.json",
        "production_brief": output_root
        / "prestige-production-brief-v2.json",
        "episode_definition": output_root / "episode-definition-v1.json",
        "readme": output_root / "README.md",
    }
    write_json(outputs["script_json"], script)
    outputs["script_markdown"].write_text(
        render_script_markdown(script),
        encoding="utf-8",
        newline="\n",
    )
    write_json(outputs["storyboard_json"], storyboard)
    write_json(outputs["trace"], trace)
    write_json(outputs["approval_request"], approval_request)
    write_json(outputs["production_brief"], production_brief)
    write_json(outputs["episode_definition"], episode_definition)

    with outputs["storyboard_csv"].open(
        "w",
        encoding="utf-8-sig",
        newline="",
    ) as stream:
        fields = [
            "shot_id",
            "sequence_id",
            "frame_id",
            "scene_id",
            "duration_seconds",
            "treatment",
            "composition",
            "camera",
            "screen_action",
            "lighting_and_colour",
            "sound_detail",
            "transition_role",
            "religious_visual_safety",
            "event_ids",
            "evidence_ids",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for shot in storyboard["shots"]:
            row = {key: shot[key] for key in fields}
            row["event_ids"] = "|".join(shot["event_ids"])
            row["evidence_ids"] = "|".join(shot["evidence_ids"])
            writer.writerow(row)

    outputs["readme"].write_text(
        "# Adam prestige cinematic Director’s Cut v2\n\n"
        "Director's Cut v2 converts evidence meaning into cinematic action, "
        "image, sound, rhythm, and dramatic progression without changing the "
        "supported meaning or qualification level. It contains fourteen "
        "evidence-bound sequences, seventy timed shots, a complete 37-event "
        "and 57-evidence trace, and one exact human approval request. The v1 "
        "candidate remains preserved as a superseded audit artifact. No paid, "
        "live, direct, or Runware execution is authorised.\n",
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
