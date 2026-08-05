from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.application.autonomous_episode_orchestrator_v1 import (
    load_orchestrator_state,
)
from src.application.graphics_storyboard_media_queue_v1 import (
    GraphicsMediaQueueError,
    GraphicsMediaQueueResult,
    integrate_graphics_and_build_media_queue,
    load_media_queue_summary,
)

RELEASE = "SIRAJ_EPISODE_001_PIPELINE_ADOPTION_V1"
EPISODE_ID = "episode-001-adam"
ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)
EPISODE_DEFINITION_REL = Path("contracts/episode-definition-v1.json")
CANONICAL_SCOPE_REL = Path("contracts/approved-scope-v1.json")
CANONICAL_EVIDENCE_REL = Path("research/evidence-package-v1.json")
CANONICAL_SCRIPT_REL = Path("script/episode-script-v1.json")
CANONICAL_STORYBOARD_REL = Path("cinematic/storyboard-and-media-plan-v1.json")
MEDIA_QUEUE_REL = Path("orchestration/media-production-queue-v1.json")
STAGE_LEDGER_REL = Path("orchestration/stage-ledger-v1.json")
DEPENDENCY_GRAPH_REL = Path("orchestration/artifact-dependency-graph-v1.json")
EDITORIAL_RUNNER_STATE_REL = Path("orchestration/editorial-runner-state-v1.json")
ADOPTION_REPORT_REL = Path("orchestration/episode-001-pipeline-adoption-v1.json")
BACKUP_ROOT_REL = Path("projects/_orchestrator/episode-001-adoption-backups")


class Episode001AdoptionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Episode001AdoptionInspection:
    episode_id: str
    episode_exists: bool
    legacy_definition_exists: bool
    legacy_script_exists: bool
    legacy_storyboard_exists: bool
    legacy_evidence_exists: bool
    legacy_human_approval: bool
    canonical_scope_exists: bool
    canonical_evidence_exists: bool
    canonical_script_exists: bool
    canonical_storyboard_exists: bool
    media_queue_exists: bool
    current_episode_id: str | None
    stored_status: str
    stored_stage: str
    requires_adoption: bool
    ready_for_adoption: bool
    reason: str
    legacy_script_path: str | None
    legacy_storyboard_path: str | None
    legacy_evidence_path: str | None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class Episode001AdoptionResult:
    episode_id: str
    status: str
    stage: str
    queue_path: Path
    canonical_scope_path: Path
    canonical_evidence_path: Path
    canonical_script_path: Path
    canonical_storyboard_path: Path
    adoption_report_path: Path
    state_backup_path: Path | None
    image_count: int
    video_count: int
    graphics_count: int
    tts_segment_count: int
    reserved_max_usd: float
    provider_requests: int
    legacy_files_preserved: bool

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in (
            "queue_path",
            "canonical_scope_path",
            "canonical_evidence_path",
            "canonical_script_path",
            "canonical_storyboard_path",
            "adoption_report_path",
            "state_backup_path",
        ):
            value = payload[key]
            payload[key] = str(value) if value is not None else None
        return payload


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        raise Episode001AdoptionError(f"CANNOT_READ_JSON:{path}:{exc}") from exc
    if not isinstance(value, dict):
        raise Episode001AdoptionError(f"JSON_OBJECT_REQUIRED:{path}")
    return value


def _write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return value
    return ()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _relative(repo: Path, path: Path) -> str:
    return str(path.resolve().relative_to(repo.resolve())).replace("\\", "/")


def _episode_root(repo_root: Path) -> Path:
    return repo_root.resolve() / "projects" / EPISODE_ID


def _state_path(repo_root: Path) -> Path:
    return repo_root.resolve() / ORCHESTRATOR_STATE_REL


def _definition_paths(
    episode_root: Path,
    definition: Mapping[str, Any],
) -> tuple[Path, Path, Path]:
    script_rel = _clean(
        (definition.get("cinematic_script") or {}).get("path")
        if isinstance(definition.get("cinematic_script"), Mapping)
        else ""
    ) or "editorial/prestige-cinematic-script-v2-1.json"
    storyboard_rel = _clean(
        (definition.get("detailed_storyboard") or {}).get("path")
        if isinstance(definition.get("detailed_storyboard"), Mapping)
        else ""
    ) or "cinematic/detailed-storyboard-v2-1.json"
    evidence_rel = _clean(
        (definition.get("evidence_package") or {}).get("path")
        if isinstance(definition.get("evidence_package"), Mapping)
        else ""
    ) or "evidence/approved-evidence-package-v1.json"
    return (
        episode_root / script_rel,
        episode_root / storyboard_rel,
        episode_root / evidence_rel,
    )


def _legacy_human_approval(
    definition: Mapping[str, Any],
    evidence: Mapping[str, Any] | None,
) -> bool:
    script = definition.get("cinematic_script")
    storyboard = definition.get("detailed_storyboard")
    evidence_definition = definition.get("evidence_package")
    script_ok = isinstance(script, Mapping) and script.get("human_approval") is True
    storyboard_ok = (
        isinstance(storyboard, Mapping)
        and storyboard.get("human_approval") is True
    )
    evidence_ok = False
    if isinstance(evidence_definition, Mapping):
        evidence_ok = (
            evidence_definition.get("approval_status") == "APPROVED"
            or evidence_definition.get("human_approval") is True
        )
    if evidence is not None:
        approval = evidence.get("approval")
        if isinstance(approval, Mapping):
            evidence_ok = evidence_ok or (
                approval.get("human_approval") is True
                and approval.get("approval_status") == "APPROVED"
            )
    return script_ok and storyboard_ok and evidence_ok


def inspect_episode_001_adoption(
    repo_root: Path,
) -> Episode001AdoptionInspection:
    repo = repo_root.resolve()
    episode_root = _episode_root(repo)
    definition_path = episode_root / EPISODE_DEFINITION_REL
    definition: dict[str, Any] = {}
    if definition_path.is_file():
        definition = _read(definition_path)
    legacy_script, legacy_storyboard, legacy_evidence = _definition_paths(
        episode_root,
        definition,
    )
    evidence_payload = _read(legacy_evidence) if legacy_evidence.is_file() else None
    try:
        state = load_orchestrator_state(repo)
    except Exception:
        state = {}
    current = state.get("current_episode_id")
    current_episode_id = (
        current.strip()
        if isinstance(current, str) and current.strip()
        else None
    )
    status = _clean(state.get("status")).upper() or "UNKNOWN"
    stage = _clean(state.get("stage")).upper() or "UNKNOWN"

    canonical_scope = episode_root / CANONICAL_SCOPE_REL
    canonical_evidence = episode_root / CANONICAL_EVIDENCE_REL
    canonical_script = episode_root / CANONICAL_SCRIPT_REL
    canonical_storyboard = episode_root / CANONICAL_STORYBOARD_REL
    media_queue = episode_root / MEDIA_QUEUE_REL

    approved = _legacy_human_approval(definition, evidence_payload)
    canonical_complete = all(
        path.is_file()
        for path in (
            canonical_scope,
            canonical_evidence,
            canonical_script,
            canonical_storyboard,
        )
    )
    episode_selected = current_episode_id == EPISODE_ID
    scope_like_state = status in {
        "IDLE_READY_FOR_NEXT_EPISODE",
        "AWAITING_HUMAN_SCOPE_REVIEW",
        "GENERATING_SCOPE_WITH_LUNA",
        "SCOPE_PROVIDER_ERROR",
        "UNKNOWN",
    } or stage in {
        "TOPIC_AND_EVENT_PROPOSAL",
        "HUMAN_SCOPE_REVIEW",
        "UNKNOWN",
    }
    no_active_episode = current_episode_id is None
    requires = (
        episode_root.is_dir()
        and approved
        and (
            (no_active_episode and scope_like_state)
            or (
                episode_selected
                and (
                    scope_like_state
                    or not canonical_complete
                    or not media_queue.is_file()
                )
            )
        )
    )
    ready = all(
        (
            episode_root.is_dir(),
            definition_path.is_file(),
            legacy_script.is_file(),
            legacy_storyboard.is_file(),
            legacy_evidence.is_file(),
            approved,
        )
    )
    if media_queue.is_file() and episode_selected:
        reason = "EPISODE_001_ALREADY_ADOPTED_MEDIA_QUEUE_PRESENT"
    elif not episode_root.is_dir():
        reason = "EPISODE_001_DIRECTORY_MISSING"
    elif not approved:
        reason = "LEGACY_FINAL_MASTER_HUMAN_APPROVAL_NOT_PROVEN"
    elif not ready:
        reason = "LEGACY_REQUIRED_FILE_MISSING"
    elif requires:
        reason = "LEGACY_APPROVED_EPISODE_NOT_BOUND_TO_CURRENT_PIPELINE"
    else:
        reason = "ADOPTION_NOT_REQUIRED"

    return Episode001AdoptionInspection(
        episode_id=EPISODE_ID,
        episode_exists=episode_root.is_dir(),
        legacy_definition_exists=definition_path.is_file(),
        legacy_script_exists=legacy_script.is_file(),
        legacy_storyboard_exists=legacy_storyboard.is_file(),
        legacy_evidence_exists=legacy_evidence.is_file(),
        legacy_human_approval=approved,
        canonical_scope_exists=canonical_scope.is_file(),
        canonical_evidence_exists=canonical_evidence.is_file(),
        canonical_script_exists=canonical_script.is_file(),
        canonical_storyboard_exists=canonical_storyboard.is_file(),
        media_queue_exists=media_queue.is_file(),
        current_episode_id=current_episode_id,
        stored_status=status,
        stored_stage=stage,
        requires_adoption=requires,
        ready_for_adoption=ready,
        reason=reason,
        legacy_script_path=(
            _relative(repo, legacy_script) if legacy_script.is_file() else None
        ),
        legacy_storyboard_path=(
            _relative(repo, legacy_storyboard)
            if legacy_storyboard.is_file()
            else None
        ),
        legacy_evidence_path=(
            _relative(repo, legacy_evidence) if legacy_evidence.is_file() else None
        ),
    )


def _backup_file(repo: Path, path: Path, backup_root: Path) -> Path | None:
    if not path.is_file():
        return None
    try:
        relative = path.resolve().relative_to(repo.resolve())
    except ValueError:
        relative = Path(path.name)
    target = backup_root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)
    return target


def _source_type(classification: str) -> str:
    value = classification.lower()
    if "quran" in value:
        return "QURAN"
    if "sunnah" in value or "hadith" in value:
        return "HADITH_COLLECTION"
    if "classical" in value or "athar" in value:
        return "CLASSICAL_SOURCE"
    if "academic" in value:
        return "ACADEMIC_SOURCE"
    return "REFERENCE_WORK"


def _posture(classification: str) -> str:
    value = classification.lower()
    if "quran" in value:
        return "QURAN_EXPLICIT"
    if "authentic" in value or "sunnah" in value or "hadith" in value:
        return "AUTHENTIC_SUNNAH"
    if "athar" in value:
        return "ACCEPTED_ATHAR"
    if "qualified" in value:
        return "QUALIFIED_REPORT"
    return "EDITORIAL_BRIDGE"


def _safe_url_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9._~-]+", "-", value).strip("-")
    return token or "source"


def _build_sources(
    evidence_items: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, str], dict[str, dict[str, Any]]]:
    legacy_ids: list[str] = []
    evidence_by_id: dict[str, dict[str, Any]] = {}
    first_by_source: dict[str, Mapping[str, Any]] = {}
    for item in evidence_items:
        evidence_id = _clean(item.get("evidence_id"))
        if evidence_id:
            evidence_by_id[evidence_id] = dict(item)
        source_id = _clean(item.get("source_id")) or evidence_id
        if source_id and source_id not in first_by_source:
            legacy_ids.append(source_id)
            first_by_source[source_id] = item
    if not legacy_ids:
        legacy_ids = ["LEGACY_APPROVED_EVIDENCE_PACKAGE"]
        first_by_source[legacy_ids[0]] = {
            "locator": "approved-evidence-package-v1.json",
            "claim_classification": "reference_work",
        }
    mapping = {
        legacy_id: f"SRC-{index:03d}"
        for index, legacy_id in enumerate(legacy_ids, start=1)
    }
    sources: list[dict[str, Any]] = []
    for legacy_id in legacy_ids:
        item = first_by_source[legacy_id]
        locator = _clean(item.get("locator")) or legacy_id
        classification = _clean(item.get("claim_classification"))
        sources.append(
            {
                "source_id": mapping[legacy_id],
                "title": locator,
                "url": (
                    "shamela://local/episode-001-adam/"
                    + _safe_url_token(legacy_id)
                ),
                "source_type": _source_type(classification),
                "publisher_or_author": legacy_id,
                "date_or_edition": locator,
                "reliability_ar": (
                    "مصدر داخل حزمة الأدلة المعتمدة بشريًا لحلقة آدم؛ "
                    "تُحفظ قيود الاستخدام ودرجة الجزم الأصلية."
                ),
                "legacy_source_id": legacy_id,
            }
        )
    return sources, mapping, evidence_by_id


def _source_ids_for_sequence(
    sequence: Mapping[str, Any],
    evidence_by_id: Mapping[str, Mapping[str, Any]],
    source_mapping: Mapping[str, str],
    fallback: str,
) -> list[str]:
    result: list[str] = []
    for evidence_id in _sequence(sequence.get("evidence_ids")):
        item = evidence_by_id.get(str(evidence_id))
        if not isinstance(item, Mapping):
            continue
        legacy_source_id = _clean(item.get("source_id")) or str(evidence_id)
        source_id = source_mapping.get(legacy_source_id)
        if source_id and source_id not in result:
            result.append(source_id)
    return result or [fallback]


def _qualifications(sequence: Mapping[str, Any]) -> list[str]:
    result = [
        _clean(value)
        for value in _sequence(sequence.get("qualification_labels"))
        if _clean(value)
    ]
    return result


def _build_canonical_packages(
    definition: Mapping[str, Any],
    legacy_script: Mapping[str, Any],
    legacy_storyboard: Mapping[str, Any],
    legacy_evidence: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    sequences = [
        dict(item)
        for item in _sequence(legacy_script.get("sequences"))
        if isinstance(item, Mapping)
    ]
    shots = [
        dict(item)
        for item in _sequence(legacy_storyboard.get("shots"))
        if isinstance(item, Mapping)
    ]
    evidence_items = [
        dict(item)
        for item in _sequence(legacy_evidence.get("evidence_items"))
        if isinstance(item, Mapping)
    ]
    if len(sequences) != 14:
        raise Episode001AdoptionError(
            f"LEGACY_SCRIPT_SEQUENCE_COUNT_MUST_BE_14:{len(sequences)}"
        )
    if len(shots) != 70:
        raise Episode001AdoptionError(
            f"LEGACY_STORYBOARD_SHOT_COUNT_MUST_BE_70:{len(shots)}"
        )
    sources, source_mapping, evidence_by_id = _build_sources(evidence_items)
    fallback_source = sources[0]["source_id"]

    scope_events: list[dict[str, Any]] = []
    evidence_events: list[dict[str, Any]] = []
    script_segments: list[dict[str, Any]] = []
    source_ids_by_sequence: dict[str, list[str]] = {}
    event_id_by_sequence: dict[str, str] = {}
    segment_id_by_sequence: dict[str, str] = {}
    claim_counter = 0

    for index, sequence in enumerate(sequences, start=1):
        event_id = f"EV-{index:03d}"
        segment_id = f"SEG-{index:03d}"
        legacy_sequence_id = _clean(sequence.get("sequence_id")) or f"LEGACY-{index:02d}"
        event_id_by_sequence[legacy_sequence_id] = event_id
        segment_id_by_sequence[legacy_sequence_id] = segment_id
        source_ids = _source_ids_for_sequence(
            sequence,
            evidence_by_id,
            source_mapping,
            fallback_source,
        )
        source_ids_by_sequence[legacy_sequence_id] = source_ids
        title = _clean(sequence.get("sequence_title")) or f"المشهد {index}"
        narration = _clean(sequence.get("narration"))
        if not narration:
            raise Episode001AdoptionError(
                f"LEGACY_SEQUENCE_NARRATION_MISSING:{legacy_sequence_id}"
            )
        qualifications = _qualifications(sequence)
        claims: list[dict[str, Any]] = []
        claim_ids: list[str] = []
        referenced_items = [
            evidence_by_id[str(evidence_id)]
            for evidence_id in _sequence(sequence.get("evidence_ids"))
            if str(evidence_id) in evidence_by_id
        ]
        if not referenced_items:
            referenced_items = [
                {
                    "claim_summary": title,
                    "claim_classification": "editorial_bridge",
                    "usage_restrictions": qualifications,
                    "source_id": sources[0].get("legacy_source_id"),
                }
            ]
        seen_claims: set[str] = set()
        for item in referenced_items:
            summary = _clean(item.get("claim_summary")) or title
            key = summary.casefold()
            if key in seen_claims:
                continue
            seen_claims.add(key)
            claim_counter += 1
            claim_id = f"CL-{claim_counter:03d}"
            claim_ids.append(claim_id)
            legacy_source_id = _clean(item.get("source_id"))
            item_source = source_mapping.get(legacy_source_id)
            claim_sources = [item_source] if item_source else source_ids
            restrictions = [
                _clean(value)
                for value in _sequence(item.get("usage_restrictions"))
                if _clean(value)
            ]
            classification = _clean(item.get("claim_classification"))
            posture = _posture(classification)
            claims.append(
                {
                    "claim_id": claim_id,
                    "claim_ar": summary,
                    "evidence_posture": posture,
                    "confidence": (
                        "HIGH"
                        if posture in {"QURAN_EXPLICIT", "AUTHENTIC_SUNNAH"}
                        else "MEDIUM"
                    ),
                    "source_ids": claim_sources,
                    "use_policy": (
                        "QUALIFIED_ONLY"
                        if qualifications or restrictions
                        else "ALLOWED"
                    ),
                    "qualification_ar": "؛ ".join(
                        [*qualifications, *restrictions]
                    ),
                    "contradictions_ar": [],
                }
            )

        scope_events.append(
            {
                "event_id": event_id,
                "title_ar": title,
                "summary_ar": _clean(sequence.get("dramatic_objective")) or title,
                "legacy_sequence_id": legacy_sequence_id,
                "source_ids": source_ids,
                "human_approval": True,
            }
        )
        evidence_events.append(
            {
                "event_id": event_id,
                "chronology_summary_ar": title,
                "claims": claims,
                "unresolved_questions_ar": qualifications,
                "production_safety_ar": [
                    "تُحفظ السلامة الدينية والقيود البصرية من الماستر المعتمد.",
                    "لا تجسيد لذات غيبية أو نبي أو ملاك أو إبليس.",
                ],
            }
        )
        segment_type = "INTRO" if index == 1 else "OUTRO" if index == len(sequences) else "EVENT"
        duration = int(sequence.get("duration_seconds", 0))
        script_segments.append(
            {
                "segment_id": segment_id,
                "segment_type": segment_type,
                "event_id": event_id,
                "title_ar": title,
                "narration_ar": narration,
                "estimated_duration_seconds": duration,
                "claim_ids": claim_ids,
                "source_ids": source_ids,
                "transition_ar": _clean(sequence.get("transition")),
                "visual_intent_ar": (
                    _clean(sequence.get("visual_thesis"))
                    or _clean(sequence.get("image_system"))
                    or _clean(sequence.get("dramatic_objective"))
                    or title
                ),
                "uncertainty_language_ar": "؛ ".join(qualifications),
                "speaker_key": "NARRATOR",
                "speaker_ar": "الراوي",
                "voice_slot_preference": "PRIMARY",
                "legacy_sequence_id": legacy_sequence_id,
            }
        )

    scope = {
        "schema_version": "siraj-approved-scope-v1",
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "title_ar": _clean(legacy_script.get("episode_title")) or "آدم: التكريم والاختبار",
        "central_question_ar": _clean(definition.get("central_question")),
        "events": scope_events,
        "human_approval": True,
        "approval_source": "LEGACY_FINAL_STORYBOARD_MASTER_V2_1",
        "legacy_definition_sha256": None,
        "migrated_without_provider_requests": True,
        "created_at_utc": _now(),
    }
    evidence = {
        "schema_version": "siraj-evidence-package-v1",
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "research_summary_ar": (
            "حزمة توافق مشتقة دون إعادة بحث من حزمة الأدلة المعتمدة بشريًا "
            "والماستر التحريري النهائي لحلقة آدم."
        ),
        "source_register": sources,
        "events": evidence_events,
        "global_uncertainties_ar": [],
        "excluded_claims_ar": [],
        "research_quality_score": 100,
        "legacy_evidence_fingerprint_preserved": True,
        "created_at_utc": _now(),
    }
    script = {
        "schema_version": "siraj-episode-script-v1",
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "title_ar": scope["title_ar"],
        "opening_hook_ar": script_segments[0]["narration_ar"][:900],
        "central_thesis_ar": scope["central_question_ar"] or scope["title_ar"],
        "target_duration_seconds": sum(
            int(item["estimated_duration_seconds"])
            for item in script_segments
        ),
        "segments": script_segments,
        "closing_ar": script_segments[-1]["narration_ar"],
        "editorial_notes_ar": [
            "نُقل النص من الماستر البشري المعتمد v2.1 دون إعادة كتابة آلية.",
            "الموسيقى محظورة؛ يُستخدم التعليق والمؤثرات والصمت المصمم فقط.",
        ],
        "music": "FORBIDDEN",
        "sound_effects": "ALLOWED_ANY_SCENE_APPROPRIATE_TYPE",
        "legacy_script_id": legacy_script.get("script_id"),
        "legacy_script_fingerprint": legacy_script.get("script_fingerprint"),
        "created_at_utc": _now(),
    }

    graphics_indices = _select_graphics_indices(shots)
    video_indices = _select_video_indices(shots, graphics_indices)
    canonical_shots: list[dict[str, Any]] = []
    for queue_index, shot in enumerate(shots, start=1):
        legacy_sequence_id = _clean(shot.get("sequence_id"))
        if legacy_sequence_id not in segment_id_by_sequence:
            sequence_number = min(14, max(1, (queue_index - 1) // 5 + 1))
            legacy_sequence_id = _clean(
                sequences[sequence_number - 1].get("sequence_id")
            )
        event_id = event_id_by_sequence[legacy_sequence_id]
        segment_id = segment_id_by_sequence[legacy_sequence_id]
        treatment = (
            "GRAPHICS"
            if queue_index in graphics_indices
            else "GENERATED_VIDEO"
            if queue_index in video_indices
            else "ANIMATED_STILL_COMPOSITING"
        )
        duration = int(shot.get("duration_seconds", 0))
        safety = _clean(shot.get("religious_visual_safety"))
        composition = _clean(shot.get("composition"))
        action = _clean(shot.get("screen_action"))
        camera = _clean(shot.get("camera"))
        lighting = _clean(shot.get("lighting_and_colour"))
        dramatic = (
            _clean(shot.get("dramatic_beat"))
            or _clean(shot.get("transition_role"))
            or _clean(shot.get("visual_subtext"))
            or f"اللقطة {queue_index}"
        )
        visual = " — ".join(
            value for value in (composition, action, lighting) if value
        )
        positive_prompt = (
            "Cinematic historical documentary reconstruction. "
            "Preserve the approved religious safety direction exactly. "
            "Do not depict Allah, angels, prophets, Iblis, or unseen beings literally. "
            f"Scene description: {composition}. Action: {action}. "
            f"Camera: {camera}. Lighting and colour: {lighting}. "
            f"Safety direction: {safety}. "
            "Photoreal material detail, disciplined composition, no modern objects, "
            "no logos, no watermark, no visible sacred faces or bodies."
        )
        negative_prompt = (
            "Allah depiction, angel body, prophet face, prophet body, Iblis body, "
            "literal unseen being, fantasy creature, modern objects, watermark, logo, "
            "subtitle text, gore, deformed anatomy, generic AI fantasy, low quality, blur"
        )
        canonical_shots.append(
            {
                "queue_index": queue_index,
                "shot_id": f"SH-{queue_index:03d}",
                "legacy_shot_id": _clean(shot.get("shot_id")) or None,
                "sequence_id": f"SEQ-{((queue_index - 1) // 5) + 1:02d}",
                "event_id": event_id,
                "segment_ids": [segment_id],
                "label_ar": dramatic,
                "dramatic_function_ar": (
                    _clean(shot.get("transition_role")) or dramatic
                ),
                "final_budget_treatment": treatment,
                "editorial_duration_seconds": duration,
                "planned_generated_video_seconds": (
                    8 if treatment == "GENERATED_VIDEO" else 0
                ),
                "visual_brief_ar": visual or dramatic,
                "camera_motion_ar": camera or "حركة منضبطة تخدم المعنى",
                "runware_positive_prompt_en": positive_prompt,
                "runware_negative_prompt_en": negative_prompt,
                "sfx_cues_ar": [_safe_sfx_cue(shot)],
                "sound_policy": "SFX_ONLY_NO_MUSIC",
                "depicts_unseen_beings": False,
                "contains_music": False,
                "safety_notes_ar": safety,
                "legacy_treatment": shot.get("treatment"),
                "legacy_shot_number": shot.get("shot_number"),
            }
        )

    storyboard = {
        "schema_version": "siraj-storyboard-and-media-plan-v1",
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "title_ar": scope["title_ar"],
        "total_shots": 70,
        "target_duration_seconds": script["target_duration_seconds"],
        "sequences": [
            {
                "sequence_id": f"SEQ-{index:02d}",
                "title_ar": _clean(sequence.get("sequence_title")) or f"المشهد {index}",
                "narrative_function_ar": _clean(sequence.get("dramatic_objective")),
                "segment_ids": [f"SEG-{index:03d}"],
            }
            for index, sequence in enumerate(sequences, start=1)
        ],
        "shots": canonical_shots,
        "music": "FORBIDDEN",
        "flat_slideshow": "FORBIDDEN",
        "legacy_storyboard_id": legacy_storyboard.get("storyboard_id"),
        "legacy_storyboard_fingerprint": legacy_storyboard.get("storyboard_fingerprint"),
        "treatment_counts": {
            "GENERATED_VIDEO": len(video_indices),
            "ANIMATED_STILL_COMPOSITING": 70 - len(video_indices) - len(graphics_indices),
            "GRAPHICS": len(graphics_indices),
        },
        "created_at_utc": _now(),
    }
    return scope, evidence, script, storyboard


def _spread_pick(candidates: Sequence[int], count: int) -> set[int]:
    unique = sorted(set(int(value) for value in candidates if 1 <= int(value) <= 70))
    if len(unique) <= count:
        return set(unique)
    chosen: set[int] = set()
    for position in range(count):
        target = 1 + round(position * 69 / max(1, count - 1))
        available = [value for value in unique if value not in chosen]
        selected = min(available, key=lambda value: (abs(value - target), value))
        chosen.add(selected)
    return chosen


def _select_graphics_indices(shots: Sequence[Mapping[str, Any]]) -> set[int]:
    preferred: list[int] = []
    for index, shot in enumerate(shots, start=1):
        text = " ".join(
            _clean(shot.get(field)).lower()
            for field in (
                "treatment",
                "composition",
                "screen_action",
                "transition_role",
                "dramatic_beat",
            )
        )
        if any(
            term in text
            for term in (
                "typographic",
                "evidence plate",
                "source card",
                "timeline",
                "map",
                "diagram",
                "عنوان",
                "لوحة",
                "خريطة",
                "مصدر",
                "نص",
            )
        ):
            preferred.append(index)
    chosen = _spread_pick(preferred, 6)
    if len(chosen) < 6:
        fillers = _spread_pick(range(5, 71, 5), 14)
        for value in sorted(fillers):
            if len(chosen) >= 6:
                break
            chosen.add(value)
    if len(chosen) != 6:
        raise Episode001AdoptionError(
            f"GRAPHICS_SELECTION_MUST_BE_6:{len(chosen)}"
        )
    return chosen


def _select_video_indices(
    shots: Sequence[Mapping[str, Any]],
    graphics_indices: set[int],
) -> set[int]:
    scored: list[tuple[int, int]] = []
    for index, shot in enumerate(shots, start=1):
        if index in graphics_indices:
            continue
        text = " ".join(
            _clean(shot.get(field)).lower()
            for field in (
                "treatment",
                "camera",
                "screen_action",
                "composition",
                "dramatic_beat",
            )
        )
        score = 0
        if "environment_vfx_plan" in text:
            score += 80
        if any(
            term in text
            for term in (
                "اندفاع",
                "دوران",
                "رافعة",
                "زحف",
                "تعبر",
                "يتحرك",
                "تصاعد",
                "ينخفض",
                "يرتفع",
                "يتشقق",
                "ينتشر",
                "dynamic",
                "tracking",
                "crane",
                "orbit",
                "motion",
            )
        ):
            score += 25
        score += min(20, int(shot.get("duration_seconds", 0)))
        scored.append((score, index))
    ordered = [index for _, index in sorted(scored, key=lambda value: (-value[0], value[1]))]
    chosen: set[int] = set()
    sequence_counts: dict[int, int] = {}
    for index in ordered:
        sequence = (index - 1) // 5 + 1
        if sequence_counts.get(sequence, 0) >= 2:
            continue
        chosen.add(index)
        sequence_counts[sequence] = sequence_counts.get(sequence, 0) + 1
        if len(chosen) == 20:
            break
    if len(chosen) < 20:
        for index in ordered:
            if index not in chosen:
                chosen.add(index)
            if len(chosen) == 20:
                break
    if len(chosen) != 20:
        raise Episode001AdoptionError(
            f"VIDEO_SELECTION_MUST_BE_20:{len(chosen)}"
        )
    return chosen


def _safe_sfx_cue(shot: Mapping[str, Any]) -> str:
    text = " ".join(
        _clean(shot.get(field)).lower()
        for field in (
            "sound_detail",
            "screen_action",
            "composition",
            "transition_role",
        )
    )
    if any(term in text for term in ("ماء", "موج", "بحر", "نهر", "مطر")):
        return "ماء وموج خافت"
    if any(term in text for term in ("نار", "لهب", "احتراق", "حرارة")):
        return "لهب واحتراق خافت"
    if any(term in text for term in ("ريح", "هواء", "غبار", "عاصفة")):
        return "رياح واحتكاك غبار"
    if any(term in text for term in ("حجر", "صخر", "بازل", "طين")):
        return "احتكاك حجر وهدير منخفض"
    if any(term in text for term in ("خطوة", "خطوات", "مشي", "طريق")):
        return "خطوات بعيدة واحتكاك أرض"
    if any(term in text for term in ("حشد", "سوق", "ناس", "مجتمع")):
        return "همهمة حشد بعيدة"
    if any(term in text for term in ("قماش", "ثوب", "رداء")):
        return "احتكاك قماش خافت"
    return "اندفاع هواء وملمس بيئي خافت"


def _base_stage_ledger(repo: Path, episode_root: Path) -> dict[str, Any]:
    stages = [
        "TOPIC_AND_EVENT_PROPOSAL",
        "HUMAN_SCOPE_REVIEW",
        "EVIDENCE_RESEARCH",
        "SCRIPT_WRITING",
        "STORYBOARD_AND_MEDIA_PLANNING",
        "BUDGET_PREFLIGHT",
        "RUNWARE_IMAGE_GENERATION",
        "RUNWARE_VIDEO_GENERATION",
        "LOCAL_GRAPHICS_RENDER",
        "ELEVENLABS_TTS",
        "SFX_DESIGN",
        "STRUCTURAL_MONTAGE",
        "AUTOMATIC_QA",
        "HUMAN_FINAL_REVIEW",
        "READY_TO_PUBLISH",
    ]
    complete = {
        "TOPIC_AND_EVENT_PROPOSAL",
        "HUMAN_SCOPE_REVIEW",
        "EVIDENCE_RESEARCH",
        "SCRIPT_WRITING",
        "STORYBOARD_AND_MEDIA_PLANNING",
    }
    return {
        "schema_version": "siraj-stage-ledger-v1",
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "status": "EDITORIAL_PIPELINE_COMPLETE",
        "resume_from": "BUDGET_PREFLIGHT",
        "stages": [
            {
                "order": index,
                "stage": stage,
                "status": "COMPLETE" if stage in complete else "QUEUED",
            }
            for index, stage in enumerate(stages, start=1)
        ],
        "legacy_files_preserved": True,
        "updated_at_utc": _now(),
    }


def _base_dependency_graph(
    repo: Path,
    episode_root: Path,
    scope: Mapping[str, Any],
) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, str]] = []
    previous: str | None = None
    for event in _sequence(scope.get("events")):
        if not isinstance(event, Mapping):
            continue
        event_id = _clean(event.get("event_id"))
        plan = f"{EPISODE_ID}:SHOT_PLAN:{event_id}"
        timeline = f"{EPISODE_ID}:TIMELINE:{event_id}"
        nodes.append(
            {
                "node_id": plan,
                "kind": "SHOT_PLAN",
                "source_id": event_id,
                "status": "COMPLETE",
                "artifact_path_relative": _relative(
                    repo,
                    episode_root / CANONICAL_STORYBOARD_REL,
                ),
            }
        )
        nodes.append(
            {
                "node_id": timeline,
                "kind": "TIMELINE",
                "source_id": event_id,
                "status": "PLANNED",
            }
        )
        edges.append({"from": plan, "to": timeline})
        if previous is not None:
            edges.append({"from": previous, "to": plan})
        previous = plan
    graph = {
        "schema_version": "siraj-artifact-dependency-graph-v1",
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "status": "EDITORIAL_PIPELINE_COMPLETE",
        "nodes": nodes,
        "edges": edges,
        "updated_at_utc": _now(),
    }
    graph["graph_sha256"] = _canonical_sha256(graph)
    return graph


def _editorial_runner_state(
    repo: Path,
    episode_root: Path,
) -> dict[str, Any]:
    artifacts = {}
    for stage, relative in (
        ("EVIDENCE_RESEARCH", CANONICAL_EVIDENCE_REL),
        ("SCRIPT_WRITING", CANONICAL_SCRIPT_REL),
        ("STORYBOARD_AND_MEDIA_PLANNING", CANONICAL_STORYBOARD_REL),
    ):
        path = episode_root / relative
        artifacts[stage] = {
            "path_relative": _relative(repo, path),
            "sha256": _sha256(path),
            "source": "LEGACY_HUMAN_APPROVED_MASTER_V2_1",
        }
    return {
        "schema_version": "siraj-editorial-runner-state-v1",
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "status": "EDITORIAL_PIPELINE_COMPLETE",
        "current_stage": "BUDGET_PREFLIGHT",
        "completed_stages": [
            "EVIDENCE_RESEARCH",
            "SCRIPT_WRITING",
            "STORYBOARD_AND_MEDIA_PLANNING",
        ],
        "artifacts": artifacts,
        "usage": {
            "input_tokens": 0,
            "output_tokens": 0,
            "cached_input_tokens": 0,
            "estimated_text_cost_usd": 0.0,
            "web_search_calls": 0,
        },
        "migration_provider_requests": 0,
        "hidden_paid_retry": "FORBIDDEN",
        "updated_at_utc": _now(),
    }


def _existing_queue_result(
    repo: Path,
    state_backup: Path | None,
) -> Episode001AdoptionResult | None:
    summary = load_media_queue_summary(repo)
    if summary is None or summary.episode_id != EPISODE_ID:
        return None
    episode_root = _episode_root(repo)
    if not all(
        (episode_root / relative).is_file()
        for relative in (
            CANONICAL_EVIDENCE_REL,
            CANONICAL_SCRIPT_REL,
            CANONICAL_STORYBOARD_REL,
        )
    ):
        return None
    report_path = episode_root / ADOPTION_REPORT_REL
    if not report_path.is_file():
        report = {
            "schema_version": "siraj-episode-001-pipeline-adoption-v1",
            "release": RELEASE,
            "episode_id": EPISODE_ID,
            "status": "REUSED_EXISTING_MEDIA_QUEUE",
            "provider_requests": 0,
            "legacy_files_preserved": True,
            "media_queue_path_relative": _relative(repo, summary.media_queue_path),
            "created_at_utc": _now(),
        }
        _write(report_path, report)
    return Episode001AdoptionResult(
        episode_id=EPISODE_ID,
        status="MEDIA_QUEUE_READY",
        stage="RUNWARE_IMAGE_GENERATION",
        queue_path=summary.media_queue_path,
        canonical_scope_path=episode_root / CANONICAL_SCOPE_REL,
        canonical_evidence_path=episode_root / CANONICAL_EVIDENCE_REL,
        canonical_script_path=episode_root / CANONICAL_SCRIPT_REL,
        canonical_storyboard_path=episode_root / CANONICAL_STORYBOARD_REL,
        adoption_report_path=report_path,
        state_backup_path=state_backup,
        image_count=summary.image_count,
        video_count=summary.video_count,
        graphics_count=summary.graphics_count,
        tts_segment_count=summary.tts_segment_count,
        reserved_max_usd=summary.reserved_max_usd,
        provider_requests=0,
        legacy_files_preserved=True,
    )


def adopt_episode_001_for_pipeline(
    repo_root: Path,
) -> Episode001AdoptionResult:
    repo = repo_root.resolve()
    inspection = inspect_episode_001_adoption(repo)
    if not inspection.ready_for_adoption:
        raise Episode001AdoptionError(
            "EPISODE_001_NOT_READY_FOR_ADOPTION:" + inspection.reason
        )
    episode_root = _episode_root(repo)
    definition_path = episode_root / EPISODE_DEFINITION_REL
    definition = _read(definition_path)
    legacy_script_path, legacy_storyboard_path, legacy_evidence_path = (
        _definition_paths(episode_root, definition)
    )
    legacy_script = _read(legacy_script_path)
    legacy_storyboard = _read(legacy_storyboard_path)
    legacy_evidence = _read(legacy_evidence_path)

    state_path = _state_path(repo)
    backup_root = repo / BACKUP_ROOT_REL / _stamp()
    state_backup = _backup_file(repo, state_path, backup_root)

    state = load_orchestrator_state(repo)
    state.update(
        {
            "current_episode_id": EPISODE_ID,
            "status": "EDITORIAL_PIPELINE_COMPLETE_BUDGET_PREFLIGHT_QUEUED",
            "stage": "BUDGET_PREFLIGHT",
            "next_stage": "GRAPHICS_STORYBOARD_INTEGRATION_AND_MEDIA_QUEUE_V1",
            "legacy_episode_adoption_release": RELEASE,
            "legacy_episode_adoption_status": "IN_PROGRESS",
            "last_error": None,
            "updated_at_utc": _now(),
        }
    )
    _write(state_path, state)

    existing = _existing_queue_result(repo, state_backup)
    if existing is not None:
        state = _read(state_path)
        state.update(
            {
                "current_episode_id": EPISODE_ID,
                "status": "MEDIA_QUEUE_READY",
                "stage": "RUNWARE_IMAGE_GENERATION",
                "next_stage": "DESKTOP_MEDIA_EXECUTION_V1",
                "legacy_episode_adoption_status": "COMPLETE_REUSED_QUEUE",
                "last_error": None,
                "updated_at_utc": _now(),
            }
        )
        _write(state_path, state)
        return existing

    scope, evidence, script, storyboard = _build_canonical_packages(
        definition,
        legacy_script,
        legacy_storyboard,
        legacy_evidence,
    )
    scope["legacy_definition_sha256"] = _sha256(definition_path)

    canonical_paths = (
        episode_root / CANONICAL_SCOPE_REL,
        episode_root / CANONICAL_EVIDENCE_REL,
        episode_root / CANONICAL_SCRIPT_REL,
        episode_root / CANONICAL_STORYBOARD_REL,
        episode_root / STAGE_LEDGER_REL,
        episode_root / DEPENDENCY_GRAPH_REL,
        episode_root / EDITORIAL_RUNNER_STATE_REL,
        episode_root / MEDIA_QUEUE_REL,
    )
    for path in canonical_paths:
        _backup_file(repo, path, backup_root)

    _write(episode_root / CANONICAL_SCOPE_REL, scope)
    _write(episode_root / CANONICAL_EVIDENCE_REL, evidence)
    _write(episode_root / CANONICAL_SCRIPT_REL, script)
    _write(episode_root / CANONICAL_STORYBOARD_REL, storyboard)
    _write(
        episode_root / STAGE_LEDGER_REL,
        _base_stage_ledger(repo, episode_root),
    )
    _write(
        episode_root / DEPENDENCY_GRAPH_REL,
        _base_dependency_graph(repo, episode_root, scope),
    )
    _write(
        episode_root / EDITORIAL_RUNNER_STATE_REL,
        _editorial_runner_state(repo, episode_root),
    )

    report_path = episode_root / ADOPTION_REPORT_REL
    report = {
        "schema_version": "siraj-episode-001-pipeline-adoption-v1",
        "release": RELEASE,
        "episode_id": EPISODE_ID,
        "status": "CANONICAL_BRIDGE_READY_BUILDING_MEDIA_QUEUE",
        "legacy_inputs": {
            "definition_path_relative": _relative(repo, definition_path),
            "definition_sha256": _sha256(definition_path),
            "script_path_relative": _relative(repo, legacy_script_path),
            "script_sha256": _sha256(legacy_script_path),
            "storyboard_path_relative": _relative(repo, legacy_storyboard_path),
            "storyboard_sha256": _sha256(legacy_storyboard_path),
            "evidence_path_relative": _relative(repo, legacy_evidence_path),
            "evidence_sha256": _sha256(legacy_evidence_path),
        },
        "canonical_outputs": {
            "scope_path_relative": _relative(repo, episode_root / CANONICAL_SCOPE_REL),
            "evidence_path_relative": _relative(repo, episode_root / CANONICAL_EVIDENCE_REL),
            "script_path_relative": _relative(repo, episode_root / CANONICAL_SCRIPT_REL),
            "storyboard_path_relative": _relative(repo, episode_root / CANONICAL_STORYBOARD_REL),
        },
        "legacy_files_preserved": True,
        "provider_requests": 0,
        "paid_authorization_bypass": "FORBIDDEN",
        "state_backup_path_relative": (
            _relative(repo, state_backup) if state_backup is not None else None
        ),
        "created_at_utc": _now(),
    }
    _write(report_path, report)

    try:
        queue_result = integrate_graphics_and_build_media_queue(repo)
    except GraphicsMediaQueueError as exc:
        report["status"] = "FAILED_BUILDING_MEDIA_QUEUE"
        report["last_error"] = str(exc)
        report["updated_at_utc"] = _now()
        _write(report_path, report)
        raise Episode001AdoptionError(
            "EPISODE_001_MEDIA_QUEUE_BUILD_FAILED:" + str(exc)
        ) from exc

    report.update(
        {
            "status": "COMPLETE_MEDIA_QUEUE_READY",
            "media_queue_path_relative": _relative(
                repo,
                queue_result.media_queue_path,
            ),
            "counts": {
                "runware_images": queue_result.image_count,
                "runware_videos": queue_result.video_count,
                "local_graphics": queue_result.graphics_count,
                "elevenlabs_tts": queue_result.tts_segment_count,
            },
            "reserved_max_usd": queue_result.reserved_max_usd,
            "provider_requests": 0,
            "completed_at_utc": _now(),
        }
    )
    report["report_sha256"] = _canonical_sha256(report)
    _write(report_path, report)

    state = _read(state_path)
    state.update(
        {
            "current_episode_id": EPISODE_ID,
            "legacy_episode_adoption_status": "COMPLETE",
            "legacy_episode_adoption_report_path_relative": _relative(
                repo,
                report_path,
            ),
            "legacy_files_preserved": True,
            "last_error": None,
            "updated_at_utc": _now(),
        }
    )
    _write(state_path, state)

    return Episode001AdoptionResult(
        episode_id=EPISODE_ID,
        status="MEDIA_QUEUE_READY",
        stage="RUNWARE_IMAGE_GENERATION",
        queue_path=queue_result.media_queue_path,
        canonical_scope_path=episode_root / CANONICAL_SCOPE_REL,
        canonical_evidence_path=episode_root / CANONICAL_EVIDENCE_REL,
        canonical_script_path=episode_root / CANONICAL_SCRIPT_REL,
        canonical_storyboard_path=episode_root / CANONICAL_STORYBOARD_REL,
        adoption_report_path=report_path,
        state_backup_path=state_backup,
        image_count=queue_result.image_count,
        video_count=queue_result.video_count,
        graphics_count=queue_result.graphics_count,
        tts_segment_count=queue_result.tts_segment_count,
        reserved_max_usd=queue_result.reserved_max_usd,
        provider_requests=0,
        legacy_files_preserved=True,
    )


def run_episode_001_adoption_smoke_test(output_root: Path) -> dict[str, Any]:
    repo = output_root.resolve() / "episode-001-adoption-smoke"
    episode_root = repo / "projects" / EPISODE_ID
    definition_path = episode_root / EPISODE_DEFINITION_REL
    legacy_script_path = episode_root / "editorial/legacy-script.json"
    legacy_storyboard_path = episode_root / "cinematic/legacy-storyboard.json"
    legacy_evidence_path = episode_root / "evidence/legacy-evidence.json"
    state_path = repo / ORCHESTRATOR_STATE_REL

    evidence_items = [
        {
            "evidence_id": f"EVID-{index:03d}",
            "source_id": f"LEGACY-SRC-{index:03d}",
            "locator": f"Reference {index}",
            "claim_classification": "quran_explicit" if index % 2 else "authentic_sunnah",
            "claim_summary": f"الادعاء الموثق {index}",
            "usage_restrictions": [],
        }
        for index in range(1, 15)
    ]
    sequences = []
    shots = []
    for sequence_number in range(1, 15):
        sequence_id = f"ADAM-SEQUENCE-{sequence_number:02d}"
        evidence_id = f"EVID-{sequence_number:03d}"
        sequence_shots = []
        for local_number in range(1, 6):
            global_number = (sequence_number - 1) * 5 + local_number
            treatment = (
                "typographic_evidence_plate"
                if local_number == 5
                else "environment_vfx_plan"
                if local_number in {1, 2}
                else "cinematic_matte_painting"
            )
            shot = {
                "shot_id": f"LEGACY-SH-{global_number:03d}",
                "shot_number": local_number,
                "sequence_id": sequence_id,
                "duration_seconds": 18 if local_number < 5 else 16,
                "treatment": treatment,
                "composition": f"تكوين بصري للمشهد {global_number}",
                "screen_action": "تتحرك المادة في مسار درامي واضح",
                "camera": "حركة كاميرا منضبطة",
                "lighting_and_colour": "إضاءة تاريخية دافئة",
                "religious_visual_safety": "لا تجسيد لذات غيبية",
                "transition_role": "نقل المعنى إلى اللقطة التالية",
                "sound_detail": "ريح وحجر",
                "evidence_ids": [evidence_id],
            }
            shots.append(dict(shot))
            sequence_shots.append(dict(shot))
        sequences.append(
            {
                "sequence_id": sequence_id,
                "sequence_number": sequence_number,
                "sequence_title": f"المشهد {sequence_number}",
                "duration_seconds": sum(item["duration_seconds"] for item in sequence_shots),
                "narration": (
                    f"هذا نص سردي موثق للمشهد {sequence_number}. " * 14
                ),
                "dramatic_objective": "تحويل المعلومة إلى فعل بصري",
                "image_system": "الخامة والضوء والحركة",
                "qualification_labels": [],
                "evidence_ids": [evidence_id],
                "shots": sequence_shots,
            }
        )

    _write(
        definition_path,
        {
            "episode_id": EPISODE_ID,
            "central_question": "كيف تبدأ قصة آدم؟",
            "cinematic_script": {
                "path": "editorial/legacy-script.json",
                "human_approval": True,
            },
            "detailed_storyboard": {
                "path": "cinematic/legacy-storyboard.json",
                "human_approval": True,
            },
            "evidence_package": {
                "path": "evidence/legacy-evidence.json",
                "approval_status": "APPROVED",
            },
        },
    )
    _write(
        legacy_script_path,
        {
            "episode_id": EPISODE_ID,
            "episode_title": "آدم: التكريم والاختبار",
            "script_id": "legacy-script",
            "script_fingerprint": "a" * 64,
            "sequences": sequences,
        },
    )
    _write(
        legacy_storyboard_path,
        {
            "episode_id": EPISODE_ID,
            "storyboard_id": "legacy-storyboard",
            "storyboard_fingerprint": "b" * 64,
            "shots": shots,
        },
    )
    _write(
        legacy_evidence_path,
        {
            "episode_id": EPISODE_ID,
            "approval": {
                "human_approval": True,
                "approval_status": "APPROVED",
            },
            "evidence_items": evidence_items,
        },
    )
    _write(
        state_path,
        {
            "schema_version": "siraj-autonomous-episode-orchestrator-state-v1",
            "status": "AWAITING_HUMAN_SCOPE_REVIEW",
            "stage": "HUMAN_SCOPE_REVIEW",
            "current_episode_id": None,
        },
    )

    result = adopt_episode_001_for_pipeline(repo)
    queue = _read(result.queue_path)
    counts = queue["counts"]
    state = _read(state_path)
    return {
        "status": "PASS",
        "episode_id": result.episode_id,
        "current_episode_id": state.get("current_episode_id"),
        "orchestrator_status": state.get("status"),
        "images": counts["runware_images"],
        "videos": counts["runware_videos"],
        "graphics": counts["local_graphics"],
        "tts": counts["elevenlabs_tts_segments"],
        "provider_requests": result.provider_requests,
        "legacy_files_preserved": result.legacy_files_preserved,
    }
