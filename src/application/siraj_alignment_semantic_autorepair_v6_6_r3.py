from __future__ import annotations

# SIRAJ_R3_CANONICAL_VISUAL_TREATMENTS_V6_6_R8
R3_CANONICAL_VISUAL_TREATMENTS_V6_6_R8 = (
    "ANIMATED_STILL_COMPOSITING",
    "GENERATED_VIDEO",
    "GRAPHICS",
)

# SIRAJ_R3_EXECUTABLE_PROMPT_CONTRACT_V6_6_R7
R3_EXECUTABLE_PROMPT_REQUIREMENTS_V6_6_R7 = {
    "every_item_requires_runware_positive_prompt_en": True,
    "every_item_requires_runware_negative_prompt_en": True,
}

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Callable

from src.application.artifact_provenance_v1 import atomic_write_json, record_invalidation
from src.application.alignment_audit_schema_v1 import normalize_alignment_audit
from src.application.objective_convergence import (
    evaluate_candidate,
    failure_mode,
    objective_from_alignment_audit,
)

# SIRAJ_ALIGNMENT_STRUCTURAL_REPAIR_V6_6_R6
from src.application.siraj_alignment_structural_repair_v6_6_r6 import (
    next_iteration_number,
    validate_structural_repair_candidate,
)
# SIRAJ_ALIGNMENT_CONVERGENCE_GUARD_V6_6_R8_2
from src.application.siraj_audio_timeline_authority_v6_6_r8_2 import (
    guard_alignment_failure_before_luna,
)
from src.application.siraj_episode_master_authorization_v6_6 import (
    master_authorization_active,
    master_authorization_reference,
)
from src.application.siraj_luna_upstream_transport_v6_3 import (
    authorization_path,
    authorize_stage,
    canonical_sha256,
    execute_authorized_stage,
)

ALIGNMENT_STAGE = "NARRATION_VISUAL_ALIGNMENT_GATE"
LUNA_CONFIRMATION_PHRASE = "أوافق على تنفيذ مرحلة لونا المدفوعة"
PROMPTS_REL = Path("preproduction/luna-semantic-prompt-direction-v6-2-1.json")
AUDIT_REL = Path("preproduction/narration-visual-alignment-gate-v6-2-1.json")


class AlignmentSemanticAutoRepairV66R3Error(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise AlignmentSemanticAutoRepairV66R3Error("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    atomic_write_json(Path(path), value, preserve_previous=True)


def _sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def semantic_fail_artifact(repo_root: Path, episode_id: str) -> dict[str, Any] | None:
    path = Path(repo_root).resolve() / "projects" / episode_id / AUDIT_REL
    if not path.is_file():
        return None
    value = _read(path)
    if str(value.get("status") or "").upper() == "PASS":
        return None
    return value


def is_semantic_alignment_fail(repo_root: Path, episode_id: str, exc: Exception) -> bool:
    expected = "STAGE_DID_NOT_PRODUCE_PASS:" + ALIGNMENT_STAGE
    return expected in str(exc) and semantic_fail_artifact(repo_root, episode_id) is not None


def _shot_ids(payload: Mapping[str, Any]) -> list[str]:
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        raise AlignmentSemanticAutoRepairV66R3Error("PROMPT_ITEMS_REQUIRED")
    result: list[str] = []
    for item in items:
        if not isinstance(item, Mapping):
            raise AlignmentSemanticAutoRepairV66R3Error("PROMPT_ITEM_OBJECT_REQUIRED")
        shot_id = str(item.get("shot_id") or "").strip()
        if not shot_id:
            raise AlignmentSemanticAutoRepairV66R3Error("PROMPT_SHOT_ID_REQUIRED")
        result.append(shot_id)
    if len(result) != len(set(result)):
        raise AlignmentSemanticAutoRepairV66R3Error("PROMPT_SHOT_IDS_MUST_BE_UNIQUE")
    return result


def _root(repo: Path, episode_id: str) -> Path:
    return repo / "projects" / episode_id / "orchestration/alignment-semantic-autorepair-v6-6-r3"


def _journal_path(repo: Path, episode_id: str) -> Path:
    return _root(repo, episode_id) / "journal.jsonl"


def _journal_rows(repo: Path, episode_id: str) -> list[dict[str, Any]]:
    path = _journal_path(repo, episode_id)
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def _append_journal(repo: Path, episode_id: str, row: Mapping[str, Any]) -> None:
    path = _journal_path(repo, episode_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n")


def _archive_auth(repo: Path, episode_id: str, iteration_dir: Path, label: str) -> None:
    path = authorization_path(repo, episode_id, ALIGNMENT_STAGE)
    if not path.is_file():
        return
    destination = iteration_dir / (label + "-paid-authorization.json")
    destination.write_bytes(path.read_bytes())
    record_invalidation(
        repo,
        episode_id,
        path,
        reason="PAID_AUTHORIZATION_SUPERSEDED_BY_ALIGNMENT_REPAIR",
        classification="SUPERSEDED",
    )


def _annotate_master(repo: Path, episode_id: str, auth_path: Path, intent: str) -> None:
    value = _read(auth_path)
    master = master_authorization_reference(repo, episode_id)
    value["authorization_source"] = "DERIVED_FROM_EPISODE_MASTER_AUTHORIZATION"
    value["episode_master_authorization_path"] = master["path"]
    value["episode_master_authorization_sha256"] = master["sha256"]
    value["editorial_iteration_intent"] = intent
    value["automatic_retry"] = False
    value["automatic_resubmission"] = False
    _write(auth_path, value)


def _authorize_alignment_payload(
    repo: Path,
    episode_id: str,
    payload: Mapping[str, Any],
    iteration_dir: Path,
    archive_label: str,
    intent: str,
) -> Path:
    _archive_auth(repo, episode_id, iteration_dir, archive_label)
    path = authorize_stage(
        repo,
        episode_id,
        ALIGNMENT_STAGE,
        payload,
        LUNA_CONFIRMATION_PHRASE,
    )
    _annotate_master(repo, episode_id, path, intent)
    return path


def _normalize_repair(
    repo: Path,
    episode_id: str,
    original: Mapping[str, Any],
    result: Mapping[str, Any],
) -> dict[str, Any]:
    return validate_structural_repair_candidate(
        repo,
        episode_id,
        original,
        result,
    )


def repair_once(repo_root: Path, episode_id: str, script: Mapping[str, Any]) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    if not master_authorization_active(repo, episode_id):
        raise AlignmentSemanticAutoRepairV66R3Error("EPISODE_MASTER_AUTHORIZATION_REQUIRED")

    ep = repo / "projects" / episode_id
    prompts_path = ep / PROMPTS_REL
    audit_path = ep / AUDIT_REL
    prompts = _read(prompts_path)
    audit = _read(audit_path)
    if str(audit.get("status") or "").upper() == "PASS":
        return {"status": "ALREADY_PASS", "changed": False}

    guard_alignment_failure_before_luna(
        repo,
        episode_id,
        audit,
    )

    fingerprint = _sha({"prompts": prompts, "audit": audit})
    prior = _journal_rows(repo, episode_id)
    if any(row.get("semantic_fingerprint") == fingerprint for row in prior):
        raise AlignmentSemanticAutoRepairV66R3Error(
            "ALIGNMENT_SEMANTIC_NO_PROGRESS_HUMAN_REVIEW_REQUIRED"
        )

    iteration = next_iteration_number(
        _root(repo, episode_id),
        prior,
    )
    iteration_dir = _root(repo, episode_id) / f"iteration-{iteration:03d}"
    iteration_dir.mkdir(parents=True, exist_ok=False)
    (iteration_dir / "prompts-before.json").write_bytes(prompts_path.read_bytes())
    (iteration_dir / "failed-audit.json").write_bytes(audit_path.read_bytes())

    repair_payload = {
        "episode_id": episode_id,
        "script": script,
        "current_prompt_plan": prompts,
        "failed_alignment_audit": audit,
        "repair_contract": {
            "address_every_failed_finding": True,
            "preserve_shot_id_set_and_order": False,
            "structural_change_allowed_when_alignment_requires": True,
            "no_new_unsupported_event_or_theological_invention": True,
            "no_generated_arabic_text": True,
            "media_mix_policy": "SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2",
            "generated_video_min_ratio": 0.50,
            "generated_video_max_ratio": 0.75,
            "no_duplicate_or_looped_visual_function": True,
            "audio_bound_storyboard_timing_authoritative": True,
            "segment_binding_must_match_audio_overlap": True,
        },
    }

    _authorize_alignment_payload(
        repo,
        episode_id,
        repair_payload,
        iteration_dir,
        "before-repair",
        "TARGETED_SEMANTIC_PROMPT_REPAIR",
    )

    repair_output = iteration_dir / "repaired-prompt-plan.json"
    execute_authorized_stage(
        repo,
        episode_id,
        ALIGNMENT_STAGE,
        system_prompt="""
- حدود start_seconds/end_seconds وربط segment_ids/beat_id يجب أن تتوافق مع audio-bound-storyboard؛ لا تعالج تعارضًا زمنيًا deterministic بتمديد آخر لقطة أو نقل PRE_OUTRO.
- final_budget_treatment must be exactly one of ANIMATED_STILL_COMPOSITING, GENERATED_VIDEO, GRAPHICS. Do not invent treatment labels such as STATIC_BLACK_HOLD; a deliberate black hold is GRAPHICS with graphics_spec.
- كل item في الخطة المصححة يجب أن يبقى production-ready ويحتوي runware_positive_prompt_en وrunware_negative_prompt_en غير فارغين؛ لا تحذف برومبتات التنفيذ أثناء إصلاح Alignment.
أنت Luna، مدير إصلاح التطابق الدلالي لسراج في وضع MAX/PRO.
لديك خطة prompts ثم نتيجة بوابة تطابق السرد والصورة التي أعادت FAIL.

نفذ تصحيحًا موجّهًا فقط:
- عالج كل finding في failed_alignment_audit.
- يجوز split/merge/add/remove/reorder للقطات فقط عندما يتطلب إصلاح التطابق ذلك.\n- يجب أن تغطي الخطة المصححة كامل التايملاين بلا فجوات أو تداخل، وأن تلتزم بسياسة SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2 بين 50% و75% من الفيديو الحقيقي.
- حافظ على الحقيقة والمصدر والضبط الديني.
- لا تضف حدثًا جديدًا غير مسنود بالنص.
- أصلح generic visuals والتناقضات والتكرار والمشهد الذي لا يدعم الجملة.
- لا نص عربي مولد داخل الوسائط.
- الفيديو المولد لا يتجاوز ثلثي الحلقة.
- لا LOOP ولا إعادة استخدام أصل بلا سبب تحريري صريح.

أخرج JSON فقط:
status=PASS
items=[الخطة المصححة كاملة؛ عدد اللقطات وترتيبها ديناميكيان عند الضرورة]
repair_trace=[]
self_review={}
""",
        input_payload=repair_payload,
        output_path_relative=str(repair_output.relative_to(ep)).replace("\\", "/"),
        use_web_search=False,
    )

    repaired = _normalize_repair(repo, episode_id, prompts, _read(repair_output))
    (iteration_dir / "prompts-after.json").write_text(
        json.dumps(repaired, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    _write(prompts_path, repaired)

    next_audit_payload = {"script": script, "prompts": repaired}
    _authorize_alignment_payload(
        repo,
        episode_id,
        next_audit_payload,
        iteration_dir,
        "after-repair",
        "INDEPENDENT_ALIGNMENT_REAUDIT_AFTER_TARGETED_REPAIR",
    )

    row = {
        "schema_version": "siraj-alignment-semantic-autorepair-v6.6-r3",
        "episode_id": episode_id,
        "iteration": iteration,
        "semantic_fingerprint": fingerprint,
        "prompt_before_sha256": canonical_sha256(prompts),
        "prompt_after_sha256": canonical_sha256(repaired),
        "paid_retry": False,
        "editorial_iteration_under_master_authorization": True,
        "automatic_provider_retry": False,
        "created_at_utc": _now(),
    }
    _append_journal(repo, episode_id, row)
    return {"status": "REPAIRED_FOR_REAUDIT", "changed": True, "iteration": iteration}


def resolve_until_pass(
    repo_root: Path,
    episode_id: str,
    script: Mapping[str, Any],
    execute_alignment: Callable[[], str],
) -> str:
    repo = Path(repo_root).resolve()
    history = []
    while True:
        raw_audit = semantic_fail_artifact(repo, episode_id)
        if raw_audit is None:
            return ALIGNMENT_STAGE
        audit = normalize_alignment_audit(raw_audit)
        prompts = _read(repo / "projects" / episode_id / PROMPTS_REL)
        structural_fingerprint = canonical_sha256([
            {
                key: item.get(key)
                for key in ("shot_id", "segment_id", "beat_id", "start_seconds", "end_seconds")
            }
            for item in (prompts.get("items") or []) if isinstance(item, Mapping)
        ])
        vector = objective_from_alignment_audit(
            audit, structural_fingerprint=structural_fingerprint
        )
        decision = evaluate_candidate(history, vector)
        if failure_mode(vector) == "DETERMINISTIC_FAILURE":
            raise AlignmentSemanticAutoRepairV66R3Error(
                "DETERMINISTIC_ALIGNMENT_FAILURE_LOCAL_REPAIR_OR_STOP_ZERO_LUNA_CALLS:"
                + ",".join(vector.finding_ids)
            )
        if history and not decision.provider_call_allowed:
            raise AlignmentSemanticAutoRepairV66R3Error(
                "ALIGNMENT_CONVERGENCE_" + decision.reason + "_HUMAN_REVIEW_REQUIRED:["
                + ",".join(vector.finding_ids) + "]"
            )
        history.append(vector)
        repair_once(repo, episode_id, script)
        try:
            result = execute_alignment()
        except Exception as exc:
            if is_semantic_alignment_fail(repo, episode_id, exc):
                continue
            raise
        return str(result or ALIGNMENT_STAGE)
