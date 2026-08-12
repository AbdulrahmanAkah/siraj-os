from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.application.artifact_provenance_v1 import record_invalidation
from src.application.objective_convergence import (
    evaluate_candidate,
    objective_from_duplicate_problems,
)

from src.application.siraj_duplicate_gates_v6_2_1 import (
    validate_pre_spend_duplicates,
)
from src.application.siraj_episode_master_authorization_v6_6 import (
    master_authorization_active,
    master_authorization_reference,
)
from src.application.siraj_luna_upstream_transport_v6_3 import (
    authorization_path,
    authorize_stage,
    execute_authorized_stage,
)

PROMPT_STAGE = "LUNA_SEMANTIC_PROMPT_DIRECTION"
ALIGNMENT_STAGE = "NARRATION_VISUAL_ALIGNMENT_GATE"
LUNA_CONFIRMATION_PHRASE = "أوافق على تنفيذ مرحلة لونا المدفوعة"

PROMPTS_REL = Path(
    "preproduction/luna-semantic-prompt-direction-v6-2-1.json"
)
ALIGNMENT_REL = Path(
    "preproduction/narration-visual-alignment-gate-v6-2-1.json"
)
DUPLICATE_REL = Path(
    "preproduction/prompt-similarity-duplicate-gate-v6-1.json"
)
QUEUE_REL = Path(
    "orchestration/media-production-queue-v6-2-1.json"
)
COST_REL = Path(
    "orchestration/media-cost-preflight-v6-2-1.json"
)

ROOT_REL = Path(
    "orchestration/pre-spend-prompt-autorepair-v6-6-r7"
)

POSITIVE_ALIASES = (
    "runware_positive_prompt_en",
    "positive_prompt_en",
    "visual_prompt_en",
    "production_prompt_en",
    "provider_prompt_en",
    "image_prompt_en",
    "video_prompt_en",
    "prompt_en",
    "prompt_text",
    "prompt",
)
NEGATIVE_ALIASES = (
    "runware_negative_prompt_en",
    "negative_prompt_en",
    "visual_negative_prompt_en",
    "provider_negative_prompt_en",
)

ALLOWED_PATCH_FIELDS = {
    "semantic_beat",
    "subject",
    "environment",
    "composition",
    "camera_angle",
    "camera_movement",
    "scene_continuity_id",
    "visual_progression_id",
    "runware_positive_prompt_en",
    "runware_negative_prompt_en",
    "contains_people",
}

WORD_RE = re.compile(r"\s+")


class PreSpendPromptAutoRepairV66R7Error(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise PreSpendPromptAutoRepairV66R7Error(
            "JSON_OBJECT_REQUIRED:" + str(path)
        )
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(
        path.name
        + "."
        + str(os.getpid())
        + "."
        + hashlib.sha256(
            (_now() + str(path)).encode("utf-8")
        ).hexdigest()[:16]
        + ".tmp"
    )
    try:
        temp.write_text(
            json.dumps(
                value,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temp, path)
    except Exception:
        raise


def _canonical_sha(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _text(value: Any) -> str:
    return WORD_RE.sub(" ", str(value or "").strip())


def _first_text(
    item: Mapping[str, Any],
    names: tuple[str, ...],
) -> str:
    for name in names:
        value = _text(item.get(name))
        if value:
            return value
    return ""


def _positive_prompt(item: Mapping[str, Any]) -> str:
    return _first_text(item, POSITIVE_ALIASES)


def _negative_prompt(item: Mapping[str, Any]) -> str:
    return _first_text(item, NEGATIVE_ALIASES)


def _items(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    raw = payload.get("items")
    if not isinstance(raw, list) or not raw:
        raise PreSpendPromptAutoRepairV66R7Error(
            "PROMPT_ITEMS_REQUIRED"
        )
    result: list[dict[str, Any]] = []
    for value in raw:
        if not isinstance(value, Mapping):
            raise PreSpendPromptAutoRepairV66R7Error(
                "PROMPT_ITEM_OBJECT_REQUIRED"
            )
        item = dict(value)
        if not str(item.get("shot_id") or "").strip():
            raise PreSpendPromptAutoRepairV66R7Error(
                "PROMPT_SHOT_ID_REQUIRED"
            )
        result.append(item)
    return result


def _normalize_aliases(
    items: list[dict[str, Any]],
) -> int:
    changed = 0
    for item in items:
        positive = _positive_prompt(item)
        if (
            positive
            and not _text(
                item.get("runware_positive_prompt_en")
            )
        ):
            item["runware_positive_prompt_en"] = positive
            changed += 1

        negative = _negative_prompt(item)
        if (
            negative
            and not _text(
                item.get("runware_negative_prompt_en")
            )
        ):
            item["runware_negative_prompt_en"] = negative

        raw_subshots = item.get("video_subshots")
        if isinstance(raw_subshots, list):
            normalized_subshots: list[Any] = []
            for raw in raw_subshots:
                if not isinstance(raw, Mapping):
                    normalized_subshots.append(raw)
                    continue
                sub = dict(raw)
                sub_positive = _positive_prompt(sub)
                if (
                    sub_positive
                    and not _text(
                        sub.get("runware_positive_prompt_en")
                    )
                ):
                    sub[
                        "runware_positive_prompt_en"
                    ] = sub_positive
                sub_negative = _negative_prompt(sub)
                if (
                    sub_negative
                    and not _text(
                        sub.get("runware_negative_prompt_en")
                    )
                ):
                    sub[
                        "runware_negative_prompt_en"
                    ] = sub_negative
                normalized_subshots.append(sub)
            item["video_subshots"] = normalized_subshots
    return changed


def _semantic_signature(
    item: Mapping[str, Any],
) -> tuple[str, ...]:
    return tuple(
        _text(item.get(key)).casefold()
        for key in (
            "semantic_beat",
            "subject",
            "environment",
            "composition",
            "camera_angle",
            "camera_movement",
        )
    )


def _safe_history_match(
    current: Mapping[str, Any],
    historical: Mapping[str, Any],
) -> bool:
    if str(current.get("shot_id")) != str(
        historical.get("shot_id")
    ):
        return False

    current_semantic = _text(
        current.get("semantic_beat")
    ).casefold()
    historical_semantic = _text(
        historical.get("semantic_beat")
    ).casefold()

    if (
        current_semantic
        and historical_semantic
        and current_semantic == historical_semantic
    ):
        return True

    current_signature = _semantic_signature(current)
    historical_signature = _semantic_signature(historical)

    comparable = [
        (a, b)
        for a, b in zip(
            current_signature,
            historical_signature,
        )
        if a and b
    ]
    if len(comparable) < 3:
        return False

    return all(a == b for a, b in comparable)


def _historical_plan_paths(ep: Path) -> list[Path]:
    candidates: list[Path] = []
    patterns = (
        "orchestration/alignment-semantic-autorepair-v6-6-r3/"
        "iteration-*/prompts-before.json",
        "orchestration/alignment-semantic-autorepair-v6-6-r3/"
        "iteration-*/prompts-after.json",
        "orchestration/alignment-structural-repair-v6-6-r6/"
        "recovery-*/prompt-plan-before.json",
        "orchestration/alignment-structural-repair-v6-6-r6/"
        "recovery-*/prompt-plan-after.json",
        "orchestration/visual-timeline-coverage-autorepair-v6-6-r4/"
        "iteration-*/prompt-plan-before.json",
        "orchestration/visual-timeline-coverage-autorepair-v6-6-r4/"
        "iteration-*/prompt-plan-after.json",
    )
    for pattern in patterns:
        candidates.extend(
            path
            for path in ep.glob(pattern)
            if path.is_file()
        )

    candidates.sort(
        key=lambda path: (
            path.stat().st_mtime_ns,
            str(path),
        ),
        reverse=True,
    )
    return candidates


def _restore_from_history(
    ep: Path,
    items: list[dict[str, Any]],
) -> tuple[int, list[str]]:
    unresolved = {
        str(item["shot_id"])
        for item in items
        if not _positive_prompt(item)
    }
    if not unresolved:
        return 0, []

    by_id = {
        str(item["shot_id"]): item
        for item in items
    }
    restored = 0

    for path in _historical_plan_paths(ep):
        if not unresolved:
            break
        try:
            payload = _read(path)
            historical_items = _items(payload)
        except Exception:
            continue

        for historical in historical_items:
            shot_id = str(
                historical.get("shot_id") or ""
            )
            if shot_id not in unresolved:
                continue
            current = by_id[shot_id]
            if not _safe_history_match(
                current,
                historical,
            ):
                continue

            positive = _positive_prompt(historical)
            if not positive:
                continue

            current[
                "runware_positive_prompt_en"
            ] = positive

            negative = _negative_prompt(historical)
            if negative:
                current[
                    "runware_negative_prompt_en"
                ] = negative

            restored += 1
            unresolved.remove(shot_id)

    return restored, sorted(unresolved)


def _archive_authorization(
    repo: Path,
    episode_id: str,
    stage: str,
    root: Path,
) -> None:
    path = authorization_path(
        repo,
        episode_id,
        stage,
    )
    if not path.is_file():
        return

    destination = (
        root
        / (
            stage.lower()
            + "-authorization-before.json"
        )
    )
    destination.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    shutil.copy2(
        path,
        destination,
    )
    record_invalidation(
        repo,
        episode_id,
        path,
        reason="PAID_AUTHORIZATION_SUPERSEDED_BY_PRESPEND_REPAIR",
        classification="SUPERSEDED",
    )


def _annotate_master(
    repo: Path,
    episode_id: str,
    path: Path,
) -> None:
    value = _read(path)
    master = master_authorization_reference(
        repo,
        episode_id,
    )
    value[
        "authorization_source"
    ] = "DERIVED_FROM_EPISODE_MASTER_AUTHORIZATION"
    value[
        "episode_master_authorization_path"
    ] = master["path"]
    value[
        "episode_master_authorization_sha256"
    ] = master["sha256"]
    value[
        "editorial_iteration_intent"
    ] = "PRE_SPEND_EXECUTABLE_PROMPT_REPAIR"
    value["automatic_retry"] = False
    value["automatic_resubmission"] = False
    _write(path, value)


def _authorize_luna(
    repo: Path,
    episode_id: str,
    payload: Mapping[str, Any],
    root: Path,
) -> Path:
    _archive_authorization(
        repo,
        episode_id,
        PROMPT_STAGE,
        root,
    )
    path = authorize_stage(
        repo,
        episode_id,
        PROMPT_STAGE,
        payload,
        LUNA_CONFIRMATION_PHRASE,
    )
    _annotate_master(
        repo,
        episode_id,
        path,
    )
    return path


def _problem_shot_ids(
    problems: list[dict[str, Any]],
) -> list[str]:
    result: set[str] = set()
    for problem in problems:
        for key in (
            "shot_id",
            "a",
            "b",
        ):
            value = str(
                problem.get(key) or ""
            ).strip()
            if value:
                result.add(value)
    return sorted(result)


def _apply_luna_patches(
    items: list[dict[str, Any]],
    result: Mapping[str, Any],
) -> int:
    if str(result.get("status") or "").upper() != "PASS":
        raise PreSpendPromptAutoRepairV66R7Error(
            "PROMPT_REPAIR_LUNA_RESULT_NOT_PASS"
        )

    patches = (
        result.get("item_patches")
        or result.get("prompt_patches")
    )
    if not isinstance(patches, list) or not patches:
        raise PreSpendPromptAutoRepairV66R7Error(
            "PROMPT_REPAIR_PATCHES_REQUIRED"
        )

    by_id = {
        str(item["shot_id"]): item
        for item in items
    }
    applied = 0

    for raw in patches:
        if not isinstance(raw, Mapping):
            raise PreSpendPromptAutoRepairV66R7Error(
                "PROMPT_REPAIR_PATCH_OBJECT_REQUIRED"
            )
        shot_id = str(
            raw.get("shot_id") or ""
        ).strip()
        if shot_id not in by_id:
            raise PreSpendPromptAutoRepairV66R7Error(
                "PROMPT_REPAIR_UNKNOWN_SHOT_ID:"
                + shot_id
            )

        illegal = (
            set(raw.keys())
            - ALLOWED_PATCH_FIELDS
            - {"shot_id"}
        )
        if illegal:
            raise PreSpendPromptAutoRepairV66R7Error(
                "PROMPT_REPAIR_ILLEGAL_FIELDS:"
                + shot_id
                + ":"
                + ",".join(
                    sorted(illegal)
                )
            )

        target = by_id[shot_id]
        for key in ALLOWED_PATCH_FIELDS:
            if key in raw:
                target[key] = raw[key]

        if not _positive_prompt(target):
            raise PreSpendPromptAutoRepairV66R7Error(
                "PROMPT_REPAIR_STILL_EMPTY:"
                + shot_id
            )

        target[
            "runware_positive_prompt_en"
        ] = _positive_prompt(target)

        negative = _negative_prompt(target)
        if negative:
            target[
                "runware_negative_prompt_en"
            ] = negative

        applied += 1

    return applied


def _archive_stale(
    ep: Path,
    root: Path,
) -> dict[str, bool]:
    archived: dict[str, bool] = {}
    for label, relative in (
        ("alignment", ALIGNMENT_REL),
        ("duplicate", DUPLICATE_REL),
        ("queue", QUEUE_REL),
        ("cost", COST_REL),
    ):
        source = ep / relative
        if not source.is_file():
            archived[label] = False
            continue

        destination = (
            root
            / "stale-artifacts"
            / relative
        )
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        shutil.copy2(
            source,
            destination,
        )
        record_invalidation(
            ep.parents[1],
            ep.name,
            source,
            reason="PRESPEND_REPAIR_INPUT_CHANGED",
            classification="STALE_BUT_PRESERVED",
        )
        archived[label] = True

    alignment_auth = authorization_path(
        ep.parents[1],
        ep.name,
        ALIGNMENT_STAGE,
    )
    if alignment_auth.is_file():
        destination = (
            root
            / "stale-artifacts"
            / "alignment-authorization.json"
        )
        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        shutil.copy2(
            alignment_auth,
            destination,
        )
        record_invalidation(
            ep.parents[1],
            ep.name,
            alignment_auth,
            reason="ALIGNMENT_AUTHORIZATION_SUPERSEDED_BY_PRESPEND_REPAIR",
            classification="SUPERSEDED",
        )
        archived[
            "alignment_authorization"
        ] = True
    else:
        archived[
            "alignment_authorization"
        ] = False

    return archived


def is_pre_spend_duplicate_failure(
    exc: Exception,
) -> bool:
    return (
        "PRE_SPEND_DUPLICATE_GATE_FAILED:"
        in str(exc)
    )


def repair_pre_spend_duplicate_gate(
    repo_root: Path,
    episode_id: str,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    if not master_authorization_active(
        repo,
        episode_id,
    ):
        raise PreSpendPromptAutoRepairV66R7Error(
            "EPISODE_MASTER_AUTHORIZATION_REQUIRED"
        )

    ep = repo / "projects" / episode_id
    prompts_path = ep / PROMPTS_REL
    plan = _read(prompts_path)
    items = _items(plan)

    before_sha = _canonical_sha(plan)
    initial_problems = (
        validate_pre_spend_duplicates(items)
    )
    if not initial_problems:
        return {
            "status": "ALREADY_PASS",
            "changed": False,
            "item_count": len(items),
        }

    stamp = datetime.now().strftime(
        "%Y%m%d-%H%M%S"
    )
    root = (
        ep
        / ROOT_REL
        / ("repair-" + stamp)
    )
    root.mkdir(
        parents=True,
        exist_ok=False,
    )
    shutil.copy2(
        prompts_path,
        root / "prompt-plan-before.json",
    )

    alias_normalized = _normalize_aliases(
        items
    )
    history_restored, _ = (
        _restore_from_history(
            ep,
            items,
        )
    )

    problems = (
        validate_pre_spend_duplicates(items)
    )

    luna_calls = 0
    luna_patches = 0
    fingerprints: set[str] = set()
    structural_fingerprint = _canonical_sha([
        {key: item.get(key) for key in (
            "shot_id", "queue_index", "start_seconds", "end_seconds",
            "final_budget_treatment", "beat_id", "segment_ids",
        )}
        for item in items
    ])
    objective_history = [objective_from_duplicate_problems(
        problems, structural_fingerprint=structural_fingerprint
    )] if problems else []

    while problems:
        fingerprint = _canonical_sha(
            {
                "items": items,
                "problems": problems,
            }
        )
        if fingerprint in fingerprints:
            raise PreSpendPromptAutoRepairV66R7Error(
                "PRE_SPEND_PROMPT_REPAIR_NO_PROGRESS_HUMAN_REVIEW_REQUIRED"
            )
        fingerprints.add(fingerprint)

        affected = _problem_shot_ids(
            problems
        )
        affected_items = [
            dict(item)
            for item in items
            if str(item["shot_id"])
            in affected
        ]

        payload = {
            "episode_id": episode_id,
            "current_items": affected_items,
            "pre_spend_duplicate_problems": problems,
            "repair_contract": {
                "freeze_shot_id": True,
                "freeze_queue_index": True,
                "freeze_start_seconds": True,
                "freeze_end_seconds": True,
                "freeze_final_budget_treatment": True,
                "freeze_beat_id": True,
                "freeze_segment_ids": True,
                "no_new_event_or_theological_invention": True,
                "no_generated_arabic_text": True,
                "media_mix_policy": "SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2",
                "generated_video_min_ratio": 0.50,
                "generated_video_max_ratio": 0.75,
                "repair_only_allowed_visual_fields": sorted(
                    ALLOWED_PATCH_FIELDS
                ),
                "return_item_patches_only": True,
            },
        }

        _authorize_luna(
            repo,
            episode_id,
            payload,
            root,
        )

        output = (
            root
            / (
                "luna-prompt-repair-"
                + f"{luna_calls + 1:03d}"
                + ".json"
            )
        )

        execute_authorized_stage(
            repo,
            episode_id,
            PROMPT_STAGE,
            system_prompt="""
أنت Luna، مديرة إصلاح ما قبل الإنفاق في سراج، في وضع MAX/PRO.

بوابة duplicate/pre-spend فشلت على خطة بصرية موجودة ومعتمدة بنيويًا.
لا تعِد بناء الحلقة ولا تغيّر التوقيت أو عدد اللقطات أو ترتيبها.

القانون الصارم:
- shot_id وqueue_index وstart_seconds وend_seconds وfinal_budget_treatment
  وbeat_id وsegment_ids مجمدة تمامًا.
- أصلح فقط الحقول البصرية المسموحة في repair_contract.
- EMPTY_PROMPT: أنشئ runware_positive_prompt_en إنتاجيًا دقيقًا ومفصلًا
  من الدلالة الموجودة في اللقطة، مع runware_negative_prompt_en مناسب.
- PROMPT_NEAR_DUPLICATE: ميّز البرومبت بصريًا مع الحفاظ على معنى السرد.
- SEMANTIC_NEAR_DUPLICATE أو ADJACENT_SHOT_VISUAL_STRUCTURE_DUPLICATE:
  غيّر التكوين/الكاميرا/الحركة/التقدم البصري بما يخدم نفس السرد دون اختراع.
- DUPLICATE_VISUAL_PROGRESSION_ID: أصلح visual_progression_id ليكون فريدًا
  ويعبّر عن تقدم حقيقي.
- لا نص عربي داخل وسائط المزوّد.
- لا LOOP ولا تكرار لنفس الوظيفة البصرية.
- التزم بسياسة SIRAJ_CINEMATIC_MEDIA_MIX_POLICY_V2: تغطية الفيديو الحقيقي بين 50% و75%؛ النسبة اختيار إخراجي وليست حصة آلية.

أخرج JSON فقط:
status=PASS
item_patches=[
  {
    "shot_id":"...",
    ... فقط الحقول المسموحة التي تحتاج تعديلًا ...
  }
]
self_review={}
""",
            input_payload=payload,
            output_path_relative=str(
                output.relative_to(ep)
            ).replace("\\", "/"),
            use_web_search=False,
        )

        luna_calls += 1
        result = _read(output)
        luna_patches += _apply_luna_patches(
            items,
            result,
        )
        _normalize_aliases(items)

        new_problems = (
            validate_pre_spend_duplicates(
                items
            )
        )
        candidate = objective_from_duplicate_problems(
            new_problems, structural_fingerprint=structural_fingerprint
        )
        decision = evaluate_candidate(objective_history, candidate)
        if new_problems and not decision.provider_call_allowed:
            raise PreSpendPromptAutoRepairV66R7Error(
                "PRE_SPEND_PROMPT_REPAIR_" + decision.reason
                + "_HUMAN_REVIEW_REQUIRED"
            )
        objective_history.append(candidate)
        problems = new_problems

    repaired = dict(plan)
    repaired["items"] = items
    repaired["status"] = "PASS"
    repaired[
        "pre_spend_prompt_autorepair"
    ] = {
        "version": "V6.6-R7",
        "initial_problem_count": len(
            initial_problems
        ),
        "alias_normalized_count": (
            alias_normalized
        ),
        "history_restored_count": (
            history_restored
        ),
        "luna_editorial_call_count": (
            luna_calls
        ),
        "luna_patch_count": (
            luna_patches
        ),
        "final_problem_count": 0,
    }

    _write(
        prompts_path,
        repaired,
    )
    _write(
        root / "prompt-plan-after.json",
        repaired,
    )

    archived = _archive_stale(
        ep,
        root,
    )

    record = {
        "schema_version": (
            "siraj-pre-spend-prompt-autorepair-v6.6-r7"
        ),
        "status": "PASS",
        "episode_id": episode_id,
        "item_count": len(items),
        "initial_problem_count": len(
            initial_problems
        ),
        "alias_normalized_count": (
            alias_normalized
        ),
        "history_restored_count": (
            history_restored
        ),
        "luna_editorial_call_count": (
            luna_calls
        ),
        "luna_patch_count": luna_patches,
        "prompt_before_sha256": before_sha,
        "prompt_after_sha256": (
            _canonical_sha(repaired)
        ),
        "stale_artifacts_archived": archived,
        "editorial_iterations_under_master_authorization": True,
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
        "created_at_utc": _now(),
    }
    _write(
        root / "repair.json",
        record,
    )
    return record
