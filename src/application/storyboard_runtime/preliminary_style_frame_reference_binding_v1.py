"""Bind Adam's human-approved preliminary visual reference set and motion gate.

This stage records eight generated stills as a preliminary art-direction reference
set only. It does not claim final storyboard-shot binding or final master-visual
approval. It opens exactly one non-paid, environment-only motion prototype gate.
"""
from __future__ import annotations

import copy
import hashlib
import json
import struct
import zipfile
from pathlib import Path
from typing import Mapping, Sequence

EPISODE_ID = "episode-001-adam"
TIMEZONE = "Asia/Baghdad"
RECORDED_AT_BAGHDAD = "2026-07-29T23:07:00+03:00"
PREVIOUS_APPROVAL_BINDING_ID = "adam_master_visual_human_approval_binding_v1_28648755f2b7324e"
PREVIOUS_PROTOTYPE_GATE_ID = "adam_non_paid_master_style_frame_prototyping_gate_v1_3c36b23723726078"
PREVIOUS_STAGE = "NON_PAID_MASTER_STYLE_FRAMES_AND_KEYFRAME_PROTOTYPING_V1"
OPERATIONAL_NEXT_STAGE = "NON_PAID_SINGLE_SHOT_MOTION_PROTOTYPE_V1"

STYLE_APPROVAL_PHRASE = "نعم هكذا افضل .. اعتمد الصور الاخيرة بشريا"
TRANSITION_INSTRUCTION = "قم بانهاء عملية التثبيت الان حتى ننتقل لمرحلة الفيديو مباشرة"
STYLE_APPROVAL_PHRASE_SHA256 = hashlib.sha256(STYLE_APPROVAL_PHRASE.encode("utf-8")).hexdigest()
TRANSITION_INSTRUCTION_SHA256 = hashlib.sha256(TRANSITION_INSTRUCTION.encode("utf-8")).hexdigest()

REFERENCE_SET_STATUS = "HUMAN_APPROVED_PRELIMINARY_VISUAL_DIRECTION_REFERENCE_SET"
MOTION_GATE_STATUS = "OPEN_SINGLE_NON_PAID_ENVIRONMENT_SHOT_MOTION_PROTOTYPE_ONLY"
MOTION_AUTHORISATION = "AUTHORISED_SINGLE_NON_PAID_ENVIRONMENT_SHOT_ONLY"

ASSET_SPECS = (
    {
        "asset_id": "ADAM-PREF-001",
        "filename": "adam-pref-001-paradise-environment-wide.png",
        "role": "PARADISE_ENVIRONMENT_ART_DIRECTION",
        "context_ar": "مرجع لاتساع الجنة ووفرة الماء والنبات والضوء، بلا أشخاص.",
        "contains_people": False,
        "motion_source_eligible": True,
    },
    {
        "asset_id": "ADAM-PREF-002",
        "filename": "adam-pref-002-companionship-under-tree.png",
        "role": "PARADISE_COMPANIONSHIP_COMPOSITION",
        "context_ar": "مرجع تكويني لوجود آدم وحواء من الخلف مع ستر حواء بالكامل وعدم إظهار الملامح.",
        "contains_people": True,
        "motion_source_eligible": False,
    },
    {
        "asset_id": "ADAM-PREF-003",
        "filename": "adam-pref-003-walking-through-paradise.png",
        "role": "PARADISE_MOVEMENT_COMPOSITION",
        "context_ar": "مرجع لحركة الشخصيتين داخل بيئة الجنة مع الستر الكامل وعدم إظهار الوجه.",
        "contains_people": True,
        "motion_source_eligible": False,
    },
    {
        "asset_id": "ADAM-PREF-004",
        "filename": "adam-pref-004-repentance-mood-reference.png",
        "role": "REPENTANCE_MOOD_AND_LIGHT_REFERENCE",
        "context_ar": "مرجع للمزاج الروحي والانكسار والضوء؛ ليس اعتمادًا نهائيًا لتصوير نبي بعد الهبوط.",
        "contains_people": True,
        "motion_source_eligible": False,
    },
    {
        "asset_id": "ADAM-PREF-005",
        "filename": "adam-pref-005-clay-creation-symbolic.png",
        "role": "CLAY_CREATION_MATERIAL_AND_LIGHT_REFERENCE",
        "context_ar": "مرجع رمزي للطين والخامة والضوء دون تجسيد الملائكة أو ذات غيبية.",
        "contains_people": False,
        "motion_source_eligible": False,
    },
    {
        "asset_id": "ADAM-PREF-006",
        "filename": "adam-pref-006-tree-event-no-clear-face.png",
        "role": "TREE_EVENT_COMPOSITION_NO_CLEAR_FACE",
        "context_ar": "مرجع للحدث قرب الشجرة من الخلف، مع حجب ملامح آدم وستر حواء بالكامل.",
        "contains_people": True,
        "motion_source_eligible": False,
    },
    {
        "asset_id": "ADAM-PREF-007",
        "filename": "adam-pref-007-paradise-water-and-light.png",
        "role": "PARADISE_WATER_LIGHT_REFERENCE",
        "context_ar": "مرجع لوفرة الماء والشلالات والنبات والنور بلا جفاف أو نقص.",
        "contains_people": False,
        "motion_source_eligible": False,
    },
    {
        "asset_id": "ADAM-PREF-008",
        "filename": "adam-pref-008-paradise-depth-and-path.png",
        "role": "PARADISE_DEPTH_AND_PATH_REFERENCE",
        "context_ar": "مرجع للعمق والتكوين والمسار داخل بيئة مكتملة النعيم بلا أشخاص.",
        "contains_people": False,
        "motion_source_eligible": False,
    },
)


class PreliminaryStyleFrameBindingError(ValueError):
    pass


def canonical_sha256(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreliminaryStyleFrameBindingError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise PreliminaryStyleFrameBindingError(f"Expected JSON object: {path}")
    return value


def write_json(path: Path, value: Mapping[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def png_dimensions(data: bytes) -> tuple[int, int]:
    if len(data) < 24 or data[:8] != b"\x89PNG\r\n\x1a\n" or data[12:16] != b"IHDR":
        raise PreliminaryStyleFrameBindingError("Asset is not a valid PNG with an IHDR header.")
    return struct.unpack(">II", data[16:24])


def _deterministic_id(prefix: str, payload: Mapping[str, object]) -> str:
    return prefix + canonical_sha256(payload)[:16]


def validate_source_state(definition: Mapping[str, object], brief: Mapping[str, object]) -> None:
    if definition.get("episode_id") != EPISODE_ID:
        raise PreliminaryStyleFrameBindingError("Unexpected episode id.")
    if definition.get("master_visual_approval") is not False:
        raise PreliminaryStyleFrameBindingError("Final master visual approval must remain false.")
    if definition.get("next_stage") != PREVIOUS_STAGE:
        raise PreliminaryStyleFrameBindingError("Episode is not at the authorised style-frame stage.")
    approval = definition.get("master_visual_human_approval")
    if not isinstance(approval, Mapping) or approval.get("binding_id") != PREVIOUS_APPROVAL_BINDING_ID:
        raise PreliminaryStyleFrameBindingError("Previous visual-baseline approval binding is missing.")
    gate = definition.get("style_frame_prototyping_gate")
    if not isinstance(gate, Mapping) or gate.get("gate_id") != PREVIOUS_PROTOTYPE_GATE_ID:
        raise PreliminaryStyleFrameBindingError("Previous style-frame gate is missing.")
    if gate.get("video_generation") != "BLOCKED":
        raise PreliminaryStyleFrameBindingError("Previous broad video gate must remain blocked.")
    for label, artifact in (("episode", definition), ("production brief", brief)):
        if artifact.get("paid_execution") != "BLOCKED":
            raise PreliminaryStyleFrameBindingError(f"{label}: paid execution must remain blocked.")
        live = artifact.get("live_provider_execution", artifact.get("live_execution_status"))
        if live != "BLOCKED":
            raise PreliminaryStyleFrameBindingError(f"{label}: live execution must remain blocked.")
    if brief.get("direct_execution") != "BLOCKED" or brief.get("runware_execution") != "BLOCKED":
        raise PreliminaryStyleFrameBindingError("Direct and Runware execution must remain blocked.")
    if brief.get("generated_video_planned_seconds") != 0:
        raise PreliminaryStyleFrameBindingError("No generated video may already be allocated.")


def build_asset_records(asset_root: Path) -> list[dict]:
    records: list[dict] = []
    for spec in ASSET_SPECS:
        path = asset_root / str(spec["filename"])
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise PreliminaryStyleFrameBindingError(f"Missing approved image asset: {path}") from exc
        width, height = png_dimensions(data)
        if (width, height) != (1672, 941):
            raise PreliminaryStyleFrameBindingError(
                f"Unexpected dimensions for {spec['asset_id']}: {(width, height)}"
            )
        record = dict(spec)
        record.update(
            {
                "path": "cinematic/preliminary-style-frame-reference-set-v1/assets/" + str(spec["filename"]),
                "sha256": sha256_bytes(data),
                "byte_length": len(data),
                "width": width,
                "height": height,
                "format": "PNG",
                "approval_scope": "PRELIMINARY_ART_DIRECTION_REFERENCE_ONLY",
                "storyboard_binding_status": "NOT_FINAL_SHOT_BINDING",
            }
        )
        records.append(record)
    if len({r["sha256"] for r in records}) != 8:
        raise PreliminaryStyleFrameBindingError("The reference set must contain eight unique images.")
    return records


def build_visual_safety_policy() -> dict:
    policy = {
        "schema_version": "siraj-adam-preliminary-style-frame-visual-safety-policy-v1",
        "status": "HUMAN_DIRECTIVES_ACTIVE",
        "episode_id": EPISODE_ID,
        "rules": [
            {
                "rule_id": "NO_ANGEL_DEPICTION",
                "severity": "BLOCKING",
                "directive_ar": "يمنع تجسيد الملائكة بأي هيئة بشرية أو جسمية.",
            },
            {
                "rule_id": "NO_FEMALE_SKIN_OR_FORM_DISPLAY",
                "severity": "BLOCKING",
                "directive_ar": "يمنع ظهور بشرة المرأة أو مفاتنها؛ حواء مستورة بالكامل في كل إطار.",
            },
            {
                "rule_id": "ADAM_DARK_SKIN_WHEN_DEPICTED",
                "severity": "BLOCKING",
                "directive_ar": "عند السماح بإظهار آدم في المرجع يكون ذا بشرة داكنة، ولا تظهر ملامحه بوضوح.",
            },
            {
                "rule_id": "NO_CLEAR_PROPHET_FACE",
                "severity": "BLOCKING",
                "directive_ar": "يمنع إظهار ملامح وجه النبي بوضوح.",
            },
            {
                "rule_id": "NO_FULL_PROPHET_BODY_AFTER_DESCENT",
                "severity": "BLOCKING",
                "directive_ar": "بعد الهبوط إلى الأرض يمنع تصوير الأنبياء كأجساد كاملة؛ لا يظهر عضو إلا لضرورة نصية ذات أهمية سياقية.",
            },
            {
                "rule_id": "PARADISE_NO_DECAY_BARRENNESS_OR_DEPLETION",
                "severity": "BLOCKING",
                "directive_ar": "يمنع تصوير الجنة بجفاف أو فناء أو بقعة توحي بنفاد النعيم أو نقصه.",
            },
            {
                "rule_id": "TREE_SPECIES_NOT_ASSERTED",
                "severity": "BLOCKING",
                "directive_ar": "لا يعين نوع الشجرة بصريًا على أنه حقيقة ثابتة.",
            },
            {
                "rule_id": "PRELIMINARY_REFERENCE_NOT_FINAL_IDENTITY",
                "severity": "BLOCKING",
                "directive_ar": "اعتماد الصور مبدئي وقابل للتعديل عند التشغيل الفعلي، ولا يساوي اعتماد الهوية البصرية النهائية.",
            },
        ],
        "master_visual_approval": False,
        "final_master_visual_approval": False,
    }
    policy["policy_id"] = _deterministic_id("adam_preliminary_visual_safety_policy_v1_", policy)
    return policy


def build_reference_set(asset_records: Sequence[Mapping[str, object]], policy: Mapping[str, object]) -> dict:
    reference_set = {
        "schema_version": "siraj-adam-preliminary-style-frame-reference-set-v1",
        "status": REFERENCE_SET_STATUS,
        "episode_id": EPISODE_ID,
        "reference_asset_count": 8,
        "assets": [dict(item) for item in asset_records],
        "human_approval": True,
        "approval_scope": "PRELIMINARY_VISUAL_DIRECTION_REFERENCE_SET_ONLY",
        "storyboard_binding_status": "NOT_FINAL_SHOT_BINDING",
        "source_visual_baseline_approval_binding_id": PREVIOUS_APPROVAL_BINDING_ID,
        "source_style_frame_gate_id": PREVIOUS_PROTOTYPE_GATE_ID,
        "visual_safety_policy_id": policy["policy_id"],
        "master_visual_approval": False,
        "final_master_visual_approval": False,
        "generated_video_assets": 0,
        "paid_execution": "BLOCKED",
        "live_provider_execution": "BLOCKED",
        "direct_execution": "BLOCKED",
        "runware_execution": "BLOCKED",
    }
    reference_set["reference_set_id"] = _deterministic_id(
        "adam_preliminary_style_frame_reference_set_v1_", reference_set
    )
    return reference_set


def build_approval(reference_set: Mapping[str, object]) -> dict:
    approval = {
        "schema_version": "siraj-adam-preliminary-style-frame-human-approval-v1",
        "status": "RECORDED_HUMAN_PRELIMINARY_STYLE_FRAME_APPROVAL",
        "episode_id": EPISODE_ID,
        "human_approval": True,
        "approval_phrase": STYLE_APPROVAL_PHRASE,
        "approval_phrase_sha256": STYLE_APPROVAL_PHRASE_SHA256,
        "transition_instruction": TRANSITION_INSTRUCTION,
        "transition_instruction_sha256": TRANSITION_INSTRUCTION_SHA256,
        "recorded_at_baghdad": RECORDED_AT_BAGHDAD,
        "canonical_timezone": TIMEZONE,
        "reference_set_id": reference_set["reference_set_id"],
        "approved_reference_asset_ids": [item["asset_id"] for item in reference_set["assets"]],
        "approval_scope": "PRELIMINARY_REFERENCE_SET_AND_TRANSITION_TO_SINGLE_MOTION_PROTOTYPE",
        "storyboard_final_shot_binding": False,
        "master_visual_approval": False,
        "final_master_visual_approval": False,
    }
    approval["approval_id"] = _deterministic_id(
        "adam_preliminary_style_frame_human_approval_v1_", approval
    )
    return approval


def build_receipt(approval: Mapping[str, object]) -> dict:
    receipt = {
        "schema_version": "siraj-adam-preliminary-style-frame-human-approval-receipt-v1",
        "status": "RECORDED_EXACT_HUMAN_PRELIMINARY_APPROVAL",
        "episode_id": EPISODE_ID,
        "approval_id": approval["approval_id"],
        "approval_phrase_sha256": STYLE_APPROVAL_PHRASE_SHA256,
        "transition_instruction_sha256": TRANSITION_INSTRUCTION_SHA256,
        "reference_set_id": approval["reference_set_id"],
        "recorded_at_baghdad": RECORDED_AT_BAGHDAD,
        "master_visual_approval": False,
        "final_master_visual_approval": False,
    }
    receipt["receipt_id"] = _deterministic_id(
        "adam_preliminary_style_frame_human_approval_receipt_v1_", receipt
    )
    return receipt


def build_binding(
    reference_set: Mapping[str, object],
    policy: Mapping[str, object],
    approval: Mapping[str, object],
    receipt: Mapping[str, object],
) -> dict:
    binding = {
        "schema_version": "siraj-adam-preliminary-style-frame-human-approval-binding-v1",
        "status": "BOUND_PRELIMINARY_REFERENCE_SET_TO_HUMAN_APPROVAL_AND_SAFETY_POLICY",
        "episode_id": EPISODE_ID,
        "reference_set_id": reference_set["reference_set_id"],
        "visual_safety_policy_id": policy["policy_id"],
        "approval_id": approval["approval_id"],
        "approval_receipt_id": receipt["receipt_id"],
        "source_visual_baseline_approval_binding_id": PREVIOUS_APPROVAL_BINDING_ID,
        "asset_hashes": {
            item["asset_id"]: item["sha256"] for item in reference_set["assets"]
        },
        "storyboard_final_shot_binding": False,
        "master_visual_approval": False,
        "final_master_visual_approval": False,
    }
    binding["binding_id"] = _deterministic_id(
        "adam_preliminary_style_frame_human_approval_binding_v1_", binding
    )
    return binding


def build_motion_gate(
    reference_set: Mapping[str, object],
    policy: Mapping[str, object],
    binding: Mapping[str, object],
) -> dict:
    source = next(item for item in reference_set["assets"] if item["asset_id"] == "ADAM-PREF-001")
    if source["contains_people"] or not source["motion_source_eligible"]:
        raise PreliminaryStyleFrameBindingError("Motion source must be an approved environment-only asset.")
    gate = {
        "schema_version": "siraj-adam-non-paid-single-shot-motion-prototype-gate-v1",
        "status": MOTION_GATE_STATUS,
        "episode_id": EPISODE_ID,
        "video_prototype_authorisation": MOTION_AUTHORISATION,
        "source_reference_set_id": reference_set["reference_set_id"],
        "source_approval_binding_id": binding["binding_id"],
        "visual_safety_policy_id": policy["policy_id"],
        "source_asset_id": source["asset_id"],
        "source_asset_path": source["path"],
        "source_asset_sha256": source["sha256"],
        "source_contains_people": False,
        "output_count_limit": 1,
        "minimum_duration_seconds": 8,
        "maximum_duration_seconds": 12,
        "allowed_motion": [
            "SLOW_CINEMATIC_CAMERA_PUSH_OR_DRIFT",
            "WATER_AND_WATERFALL_MOTION",
            "SUBTLE_FOLIAGE_MOTION",
            "MIST_LIGHT_AND_DEPTH_PARALLAX",
        ],
        "forbidden_content": [
            "ANY_PERSON_OR_PROPHET",
            "ANGEL_DEPICTION",
            "NEW_CREATURE_OR_CHARACTER_INSERTION",
            "PARADISE_DECAY_BARRENNESS_OR_DEPLETION",
            "CLEAR_RELIGIOUS_FIGURE_FACE",
        ],
        "audio_generation": "BLOCKED",
        "music_generation": "BLOCKED",
        "voice_generation": "BLOCKED",
        "dialogue_generation": "BLOCKED",
        "full_episode_video_generation": "BLOCKED",
        "timed_full_animatic_generation": "BLOCKED",
        "paid_execution": "BLOCKED",
        "live_provider_execution": "BLOCKED",
        "direct_execution": "BLOCKED",
        "runware_execution": "BLOCKED",
        "provider_selection": "DEFERRED_NON_PAID_PROTOTYPE_TOOLING",
        "budget_allocation": "ZERO_PAID_BUDGET",
        "generated_video_assets": 0,
        "master_visual_approval": False,
        "final_master_visual_approval": False,
        "operational_next_stage": OPERATIONAL_NEXT_STAGE,
    }
    gate["gate_id"] = _deterministic_id(
        "adam_non_paid_single_shot_motion_prototype_gate_v1_", gate
    )
    return gate


def update_episode_definition(
    definition: Mapping[str, object],
    reference_set: Mapping[str, object],
    policy: Mapping[str, object],
    approval: Mapping[str, object],
    receipt: Mapping[str, object],
    binding: Mapping[str, object],
    gate: Mapping[str, object],
) -> dict:
    updated = copy.deepcopy(dict(definition))
    updated["preliminary_style_frame_reference_set"] = {
        "status": reference_set["status"],
        "path": "cinematic/preliminary-style-frame-reference-set-v1.json",
        "reference_set_id": reference_set["reference_set_id"],
        "reference_asset_count": 8,
        "approval_scope": reference_set["approval_scope"],
        "storyboard_binding_status": reference_set["storyboard_binding_status"],
        "human_approval_id": approval["approval_id"],
        "human_approval_binding_id": binding["binding_id"],
        "master_visual_approval": False,
    }
    updated["preliminary_style_frame_human_approval"] = {
        "status": approval["status"],
        "path": "evidence/preliminary-style-frame-human-approval-v1.json",
        "approval_id": approval["approval_id"],
        "receipt_path": "evidence/preliminary-style-frame-human-approval-receipt-v1.json",
        "receipt_id": receipt["receipt_id"],
        "binding_path": "contracts/preliminary-style-frame-human-approval-binding-v1.json",
        "binding_id": binding["binding_id"],
        "final_master_visual_approval": False,
    }
    updated["preliminary_visual_safety_policy"] = {
        "status": policy["status"],
        "path": "cinematic/preliminary-style-frame-visual-safety-policy-v1.json",
        "policy_id": policy["policy_id"],
        "blocking_rule_count": len(policy["rules"]),
    }
    updated["single_shot_motion_prototype_gate"] = {
        "status": gate["status"],
        "path": "cinematic/non-paid-single-shot-motion-prototype-gate-v1.json",
        "gate_id": gate["gate_id"],
        "source_asset_id": gate["source_asset_id"],
        "video_prototype_authorisation": gate["video_prototype_authorisation"],
        "output_count_limit": 1,
        "duration_window_seconds": [8, 12],
        "audio_generation": "BLOCKED",
        "full_episode_video_generation": "BLOCKED",
    }
    # Keep the canonical prior stage marker for backward-compatible audit CLIs.
    updated["operational_next_stage"] = OPERATIONAL_NEXT_STAGE
    updated["master_visual_approval"] = False
    updated["live_execution_status"] = "BLOCKED"
    updated["paid_execution"] = "BLOCKED"
    return updated


def update_production_brief(
    brief: Mapping[str, object],
    reference_set: Mapping[str, object],
    policy: Mapping[str, object],
    approval: Mapping[str, object],
    binding: Mapping[str, object],
    gate: Mapping[str, object],
) -> dict:
    updated = copy.deepcopy(dict(brief))
    updated["preliminary_style_frame_reference_set_id"] = reference_set["reference_set_id"]
    updated["preliminary_style_frame_human_approval_id"] = approval["approval_id"]
    updated["preliminary_style_frame_human_approval_binding_id"] = binding["binding_id"]
    updated["preliminary_visual_safety_policy_id"] = policy["policy_id"]
    updated["single_shot_motion_prototype_gate_id"] = gate["gate_id"]
    updated["single_shot_motion_prototype_status"] = gate["status"]
    updated["single_shot_motion_source_asset_id"] = gate["source_asset_id"]
    updated["operational_next_stage"] = OPERATIONAL_NEXT_STAGE
    updated["master_visual_approval"] = False
    updated["generated_video_planned_seconds"] = 0
    updated["live_provider_execution"] = "BLOCKED"
    updated["paid_execution"] = "BLOCKED"
    updated["direct_execution"] = "BLOCKED"
    updated["runware_execution"] = "BLOCKED"
    return updated


def render_markdown(
    reference_set: Mapping[str, object],
    policy: Mapping[str, object],
    approval: Mapping[str, object],
    binding: Mapping[str, object],
    gate: Mapping[str, object],
) -> str:
    lines = [
        "# اعتماد الصور المرجعية المبدئي وفتح بوابة نموذج الحركة — حلقة آدم",
        "",
        "## القرار البشري",
        "",
        f"> {STYLE_APPROVAL_PHRASE}",
        "",
        f"> {TRANSITION_INSTRUCTION}",
        "",
        f"- Reference set: `{reference_set['reference_set_id']}`",
        f"- Approval: `{approval['approval_id']}`",
        f"- Binding: `{binding['binding_id']}`",
        f"- Safety policy: `{policy['policy_id']}`",
        f"- Motion gate: `{gate['gate_id']}`",
        "",
        "## النطاق المعتمد",
        "",
        "- ثماني صور كمرجع اتجاه فني مبدئي قابل للتعديل.",
        "- لا تمثل الصور ربطًا نهائيًا بلقطات الستوريبورد.",
        "- لا تمثل اعتمادًا نهائيًا للهوية البصرية.",
        "- فتح نموذج حركة واحد غير مدفوع من صورة جنة بيئية خالية من الأشخاص.",
        "- المدة المسموحة 8–12 ثانية، بلا صوت أو موسيقى أو حوار.",
        "- التشغيل المدفوع والمباشر وRunware والمزود الحي محظور.",
        "",
        "## المرحلة التشغيلية التالية",
        "",
        f"`{OPERATIONAL_NEXT_STAGE}`",
        "",
    ]
    return "\n".join(lines)


def build_all(
    *,
    asset_root: Path,
    episode_definition: Mapping[str, object],
    production_brief: Mapping[str, object],
) -> tuple[dict, dict, dict, dict, dict, dict, dict, dict, str]:
    validate_source_state(episode_definition, production_brief)
    assets = build_asset_records(asset_root)
    policy = build_visual_safety_policy()
    reference_set = build_reference_set(assets, policy)
    approval = build_approval(reference_set)
    receipt = build_receipt(approval)
    binding = build_binding(reference_set, policy, approval, receipt)
    gate = build_motion_gate(reference_set, policy, binding)
    definition = update_episode_definition(
        episode_definition, reference_set, policy, approval, receipt, binding, gate
    )
    brief = update_production_brief(
        production_brief, reference_set, policy, approval, binding, gate
    )
    markdown = render_markdown(reference_set, policy, approval, binding, gate)
    return reference_set, policy, approval, receipt, binding, gate, definition, brief, markdown


def write_deterministic_zip(path: Path, files: Mapping[str, bytes]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, files[name])


def write_outputs(
    *,
    output_root: Path,
    reference_set: Mapping[str, object],
    policy: Mapping[str, object],
    approval: Mapping[str, object],
    receipt: Mapping[str, object],
    binding: Mapping[str, object],
    gate: Mapping[str, object],
    episode_definition: Mapping[str, object],
    production_brief: Mapping[str, object],
    markdown: str,
) -> dict[str, Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    payloads = {
        "reference_set": ("preliminary-style-frame-reference-set-v1.json", reference_set),
        "policy": ("preliminary-style-frame-visual-safety-policy-v1.json", policy),
        "approval": ("preliminary-style-frame-human-approval-v1.json", approval),
        "receipt": ("preliminary-style-frame-human-approval-receipt-v1.json", receipt),
        "binding": ("preliminary-style-frame-human-approval-binding-v1.json", binding),
        "motion_gate": ("non-paid-single-shot-motion-prototype-gate-v1.json", gate),
        "episode_definition": ("episode-definition-v1.json", episode_definition),
        "production_brief": ("prestige-production-brief-v2-1.json", production_brief),
    }
    outputs: dict[str, Path] = {}
    archive_files: dict[str, bytes] = {}
    for key, (name, value) in payloads.items():
        path = output_root / name
        write_json(path, value)
        outputs[key] = path
        archive_files[name] = path.read_bytes()
    md = output_root / "preliminary-style-frame-human-approval-v1.md"
    md.write_text(markdown, encoding="utf-8", newline="\n")
    outputs["markdown"] = md
    archive_files[md.name] = md.read_bytes()
    archive = output_root.with_suffix(".zip")
    write_deterministic_zip(archive, archive_files)
    outputs["archive"] = archive
    return outputs
