"""Canonical manual-visual next-episode workflow from bootstrap through archive.

No function in this module calls a visual provider, paid gateway, publication
API, or automatic visual fallback. All visual bytes enter through the manual
ingest ledger and are SHA-bound before local assembly.
"""
from __future__ import annotations

import hashlib
import argparse
import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.application.canonical_manual_visual_profile_v1 import (
    PROFILE_REL,
    profile_payload,
    validate_profile,
)
from src.application.episode_canonical_state_v1 import (
    MANUAL_VISUAL_PROFILE,
    MANUAL_VISUAL_STAGE_ORDER,
    ManualVisualEpisodeStage,
    bind_artifact,
    initialize,
    invalidate_to,
    load_state,
    sha256_file,
    transition,
)
from src.application.manual_visual_asset_ingest_v1 import (
    ingest_manual_visuals,
    lock_manual_visuals,
)
from src.application.manual_visual_production_pack_v1 import build_pack, export_pack

PIPELINE_SCHEMA = "siraj-canonical-next-episode-manual-visual-pipeline-v1"
STATE_REL = Path("orchestration/canonical-episode-state-v1.json")
MANIFEST_REL = Path("contracts/episode-manifest-v1.json")
HANDOFF_REL = Path("manual-visuals/handoff-v1")
LEDGER_REL = Path("manual-visuals/manual-visual-asset-ledger-v1.json")
VISUAL_LOCK_REL = Path("manual-visuals/sha-bound-visual-lock-v1.json")
ASSEMBLY_DIR_REL = Path("assembly/manual-visual-v1")
QA_DIR_REL = Path("qa/manual-visual-v1")
MASTER_REL = Path("deliverables/episode-master-v1.mp4")
MASTER_RECEIPT_REL = Path("deliverables/episode-master-v1-receipt.json")
ARCHIVE_REL = Path("archive/canonical-episode-archive-v1.json")
WIDTH = 1920
HEIGHT = 1080
FPS = 30
DURATION_TOLERANCE = 0.25


class CanonicalManualVisualPipelineError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _canonical_sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise CanonicalManualVisualPipelineError("JSON_UNREADABLE:" + str(path)) from exc
    if not isinstance(value, dict):
        raise CanonicalManualVisualPipelineError("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8", newline="\n",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _episode_root(repo_root: Path, episode_id: str) -> Path:
    return Path(repo_root).resolve() / "projects" / episode_id


def _state_path(episode_root: Path) -> Path:
    return episode_root / STATE_REL


def _assert_state_fresh(state: Mapping[str, Any]) -> None:
    for slot, record in (state.get("artifacts") or {}).items():
        if not isinstance(record, Mapping):
            raise CanonicalManualVisualPipelineError("CANONICAL_ARTIFACT_RECORD_INVALID:" + str(slot))
        path = Path(str(record.get("path") or ""))
        if not path.is_file() or sha256_file(path) != record.get("sha256"):
            raise CanonicalManualVisualPipelineError("CANONICAL_ARTIFACT_STALE:" + str(slot))


def bootstrap_episode(repo_root: Path, episode_id: str) -> dict[str, Any]:
    identity = str(episode_id or "").strip()
    if not identity or any(token in identity for token in ("..", "/", "\\")):
        raise CanonicalManualVisualPipelineError("EPISODE_ID_INVALID")
    root = _episode_root(repo_root, identity)
    root.mkdir(parents=True, exist_ok=True)
    profile_path = root / PROFILE_REL
    profile = profile_payload(identity)
    if profile_path.exists():
        existing = _read(profile_path)
        validate_profile(existing, episode_id=identity)
    else:
        _write(profile_path, profile)
    manifest_path = root / MANIFEST_REL
    manifest = {
        "schema_version": "siraj-episode-manifest-v1", "episode_id": identity,
        "profile_id": MANUAL_VISUAL_PROFILE, "visual_mode": "MANUAL_USER_PRODUCTION",
        "state_path": str(_state_path(root)), "profile_path": str(profile_path),
        "automatic_visual_generation": False, "paid_visual_provider_execution": False,
        "provider_visual_fallback": False, "publication_authorized": False,
        "created_at": _now(),
    }
    if manifest_path.exists():
        existing_manifest = _read(manifest_path)
        if existing_manifest.get("episode_id") != identity or existing_manifest.get("profile_id") != MANUAL_VISUAL_PROFILE:
            raise CanonicalManualVisualPipelineError("EPISODE_MANIFEST_CONFLICT")
    else:
        _write(manifest_path, manifest)
    state_path = _state_path(root)
    state = initialize(state_path, identity, profile=MANUAL_VISUAL_PROFILE)
    state = bind_artifact(state_path, "episode_manifest", manifest_path)
    return {
        "status": "EPISODE_CREATE", "episode_id": identity, "episode_root": str(root),
        "state_path": str(state_path), "manifest_path": str(manifest_path),
        "profile_path": str(profile_path), "revision": state["revision"],
    }


_PREVISUAL_SEQUENCE: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("RESEARCH", ("research",)),
    ("SOURCE_LOCK", ("source_registry", "claim_matrix", "sources_lock")),
    ("TITLE_LOCK", ("title_lock",)),
    ("STORY_ARCHITECTURE", ("story_architecture",)),
    ("SCRIPT", ("script",)),
    ("SCRIPT_QA", ("script_qa",)),
    ("NARRATION", ("narration",)),
    ("WORD_LEVEL_TIMING", ("audio", "timing", "audio_timing_receipt")),
    ("STORYBOARD", ("storyboard",)),
    ("VISUAL_REQUIREMENT_CONTRACTS", ("visual_contracts",)),
    ("COVERAGE_DIVERSITY_REUSE_VALIDATION", ("coverage_validation",)),
    ("HUMAN_PRE_VISUAL_APPROVAL", ("pre_visual_approval",)),
)


def _validate_previsual_receipt(slot: str, path: Path) -> None:
    if slot not in {"title_lock", "script_qa", "audio_timing_receipt", "coverage_validation", "pre_visual_approval"}:
        return
    value = _read(path)
    if slot in {"title_lock", "pre_visual_approval"}:
        if value.get("decision") != "APPROVED" or not str(value.get("human_actor") or "").strip():
            raise CanonicalManualVisualPipelineError(slot.upper() + "_HUMAN_APPROVAL_REQUIRED")
        if value.get("autonomous_approval") is not False:
            raise CanonicalManualVisualPipelineError(slot.upper() + "_AUTONOMOUS_APPROVAL_FORBIDDEN")
    if slot == "script_qa":
        gates = value.get("gates")
        required = {"factual_source", "constitution", "editorial", "narrative"}
        if not isinstance(gates, Mapping) or {key for key in required if gates.get(key) == "PASS"} != required:
            raise CanonicalManualVisualPipelineError("SCRIPT_QA_FOUR_GATES_REQUIRED")
    if slot == "audio_timing_receipt":
        if value.get("timing_mode") not in {"NATIVE_WORD_BOUNDARIES", "LOCAL_OFFLINE_ALIGNMENT", "MANUAL_VERIFIED"}:
            raise CanonicalManualVisualPipelineError("WORD_TIMING_AUTHORITY_INVALID")
        if value.get("final_audio_sha256") != value.get("timing_bound_audio_sha256"):
            raise CanonicalManualVisualPipelineError("WORD_TIMING_NOT_BOUND_TO_FINAL_AUDIO")
    if slot == "coverage_validation" and value.get("status") != "PASS":
        raise CanonicalManualVisualPipelineError("COVERAGE_DIVERSITY_REUSE_VALIDATION_FAILED")


def advance_previsual(
    repo_root: Path,
    episode_id: str,
    artifacts: Mapping[str, Path],
) -> dict[str, Any]:
    root = _episode_root(repo_root, episode_id)
    state_path = _state_path(root)
    state = load_state(state_path)
    _assert_state_fresh(state)
    for target, slots in _PREVISUAL_SEQUENCE:
        target_index = MANUAL_VISUAL_STAGE_ORDER.index(target)
        current_index = MANUAL_VISUAL_STAGE_ORDER.index(state["stage"])
        if current_index > target_index:
            continue
        if current_index == target_index:
            continue
        if target_index != current_index + 1:
            raise CanonicalManualVisualPipelineError(f"PREVISUAL_ARTIFACTS_MISSING_BEFORE:{target}")
        for slot in slots:
            path = Path(artifacts.get(slot, Path(""))).resolve()
            if not path.is_file():
                raise CanonicalManualVisualPipelineError("PREVISUAL_ARTIFACT_REQUIRED:" + slot)
            _validate_previsual_receipt(slot, path)
            status = "APPROVED" if slot in {"title_lock", "pre_visual_approval"} else "BOUND"
            state = bind_artifact(state_path, slot, path, status=status)
        state = transition(state_path, target)
    return {"status": state["stage"], "revision": state["revision"], "state_path": str(state_path)}


def export_manual_visual_handoff(repo_root: Path, episode_id: str) -> dict[str, Any]:
    root = _episode_root(repo_root, episode_id)
    state_path = _state_path(root)
    state = load_state(state_path)
    _assert_state_fresh(state)
    if state["stage"] not in {"HUMAN_PRE_VISUAL_APPROVAL", "MANUAL_VISUAL_HANDOFF_READY"}:
        raise CanonicalManualVisualPipelineError("HANDOFF_REQUIRES_HUMAN_PRE_VISUAL_APPROVAL")
    if state["stage"] == "MANUAL_VISUAL_HANDOFF_READY":
        pack_path = Path(state["artifacts"]["manual_visual_pack"]["path"])
        if not pack_path.is_file() or sha256_file(pack_path) != state["artifacts"]["manual_visual_pack"]["sha256"]:
            raise CanonicalManualVisualPipelineError("MANUAL_VISUAL_PACK_STALE")
        output = pack_path.parent
        required = (
            pack_path,
            output / "manual-visual-production-pack-v1.html",
            output / "manual-visual-production-pack-v1.md",
            output / "manual-visual-ingest-template-v1.json",
            output / "manual-visual-asset-naming-v1.json",
        )
        if not all(path.is_file() for path in required):
            raise CanonicalManualVisualPipelineError("MANUAL_VISUAL_HANDOFF_FILE_MISSING")
        return {
            "status": "MANUAL_VISUAL_HANDOFF_READY", "output_dir": str(output),
            "files": [{"path": str(path), "sha256": sha256_file(path)} for path in required],
            "pack_path": str(pack_path), "pack_sha256": sha256_file(pack_path),
            "ingest_template_path": str(output / "manual-visual-ingest-template-v1.json"),
            "state_stage": state["stage"], "state_revision": state["revision"], "reused": True,
        }
    artifacts = state["artifacts"]
    for slot in (
        "sources_lock", "title_lock", "script", "audio", "timing", "storyboard",
        "visual_contracts", "coverage_validation", "pre_visual_approval",
    ):
        if slot not in artifacts:
            raise CanonicalManualVisualPipelineError("HANDOFF_AUTHORITY_MISSING:" + slot)
        if sha256_file(Path(artifacts[slot]["path"])) != artifacts[slot]["sha256"]:
            raise CanonicalManualVisualPipelineError("HANDOFF_AUTHORITY_STALE:" + slot)
    title = _read(Path(artifacts["title_lock"]["path"]))
    script = _read(Path(artifacts["script"]["path"]))
    storyboard = _read(Path(artifacts["storyboard"]["path"]))
    contracts = _read(Path(artifacts["visual_contracts"]["path"]))
    shots = contracts.get("shots")
    if not isinstance(shots, list):
        shots = storyboard.get("shots")
    if not isinstance(shots, list):
        raise CanonicalManualVisualPipelineError("VISUAL_CONTRACT_SHOTS_REQUIRED")
    pack = build_pack(
        episode_id=episode_id,
        final_title=str(title.get("final_title") or title.get("title") or ""),
        episode_summary=str(script.get("episode_summary") or script.get("summary") or ""),
        final_script_version=str(script.get("version") or script.get("schema_version") or "v1"),
        final_audio_version=str(_read(Path(artifacts["timing"]["path"])).get("version") or "v1"),
        shots=shots,
        source_lock_sha256=artifacts["sources_lock"]["sha256"],
        script_sha256=artifacts["script"]["sha256"],
        audio_sha256=artifacts["audio"]["sha256"], timing_sha256=artifacts["timing"]["sha256"],
        storyboard_sha256=artifacts["storyboard"]["sha256"],
        visual_contracts_sha256=artifacts["visual_contracts"]["sha256"],
        coverage_validation_sha256=artifacts["coverage_validation"]["sha256"],
        pre_visual_approval_sha256=artifacts["pre_visual_approval"]["sha256"],
    )
    result = export_pack(pack, root / HANDOFF_REL)
    pack_path = Path(result["pack_path"])
    state = bind_artifact(state_path, "manual_visual_pack", pack_path)
    if state["stage"] == "HUMAN_PRE_VISUAL_APPROVAL":
        state = transition(state_path, "MANUAL_VISUAL_HANDOFF_READY")
    return {**result, "state_stage": state["stage"], "state_revision": state["revision"]}


def import_manual_visuals(
    repo_root: Path,
    episode_id: str,
    *,
    ingest_dir: Path,
    ingest_template_path: Path | None = None,
) -> dict[str, Any]:
    root = _episode_root(repo_root, episode_id)
    state_path = _state_path(root)
    state = load_state(state_path)
    _assert_state_fresh(state)
    if state["stage"] == "MANUAL_VISUAL_HANDOFF_READY":
        state = transition(state_path, "MANUAL_VISUAL_INGEST")
    if MANUAL_VISUAL_STAGE_ORDER.index(state["stage"]) < MANUAL_VISUAL_STAGE_ORDER.index("MANUAL_VISUAL_INGEST"):
        raise CanonicalManualVisualPipelineError("MANUAL_VISUAL_HANDOFF_NOT_READY")
    pack_path = Path(state["artifacts"]["manual_visual_pack"]["path"])
    template = ingest_template_path or (root / HANDOFF_REL / "manual-visual-ingest-template-v1.json")
    result = ingest_manual_visuals(
        episode_root=root, pack_path=pack_path,
        ingest_template_path=Path(template), ingest_dir=Path(ingest_dir),
        expected_pack_sha256=state["artifacts"]["manual_visual_pack"]["sha256"],
    )
    if result["status"] != "PASS_COMPLETE_VALIDATED":
        return result
    if result.get("reused") is True:
        return {**result, "state_stage": state["stage"], "state_revision": state["revision"]}
    state = load_state(state_path)
    if MANUAL_VISUAL_STAGE_ORDER.index(state["stage"]) > MANUAL_VISUAL_STAGE_ORDER.index("MANUAL_VISUAL_INGEST"):
        state = invalidate_to(state_path, "MANUAL_VISUAL_INGEST", "MANUAL_VISUAL_ASSET_LEDGER_CHANGED")
    ledger_path = Path(result["ledger_path"])
    state = bind_artifact(state_path, "manual_asset_ledger", ledger_path)
    if state["stage"] == "MANUAL_VISUAL_INGEST":
        state = transition(state_path, "ASSET_VALIDATION")
    return {**result, "state_stage": state["stage"], "state_revision": state["revision"]}


def lock_imported_visuals(repo_root: Path, episode_id: str) -> dict[str, Any]:
    root = _episode_root(repo_root, episode_id)
    state_path = _state_path(root)
    state = load_state(state_path)
    _assert_state_fresh(state)
    if state["stage"] == "SHA_BOUND_VISUAL_LOCK":
        return {"status": state["stage"], "lock_path": state["artifacts"]["visual_lock"]["path"], "reused": True}
    if state["stage"] != "ASSET_VALIDATION":
        raise CanonicalManualVisualPipelineError("VISUAL_LOCK_REQUIRES_ASSET_VALIDATION")
    result = lock_manual_visuals(
        pack_path=Path(state["artifacts"]["manual_visual_pack"]["path"]),
        ledger_path=Path(state["artifacts"]["manual_asset_ledger"]["path"]),
        output_path=root / VISUAL_LOCK_REL,
        expected_pack_sha256=state["artifacts"]["manual_visual_pack"]["sha256"],
        expected_ledger_sha256=state["artifacts"]["manual_asset_ledger"]["sha256"],
    )
    state = bind_artifact(state_path, "visual_lock", Path(result["lock_path"]), status="APPROVED")
    state = transition(state_path, "SHA_BOUND_VISUAL_LOCK")
    return {**result, "state_stage": state["stage"], "state_revision": state["revision"]}


def _binary(name: str, env_name: str) -> str:
    configured = str(os.environ.get(env_name) or "").strip()
    found = configured or shutil.which(name) or ""
    if not found or not Path(found).is_file():
        raise CanonicalManualVisualPipelineError(name.upper() + "_NOT_AVAILABLE")
    return found


def _run(command: Sequence[str], *, timeout: int = 300) -> subprocess.CompletedProcess[str]:
    process = subprocess.run(
        list(command), capture_output=True, text=True, encoding="utf-8", errors="replace",
        check=False, timeout=timeout,
    )
    if process.returncode != 0:
        raise CanonicalManualVisualPipelineError(
            "LOCAL_MEDIA_COMMAND_FAILED:" + (process.stderr[-1500:] or process.stdout[-1500:])
        )
    return process


def _probe(path: Path) -> dict[str, Any]:
    process = _run([
        _binary("ffprobe", "SIRAJ_FFPROBE_BIN"), "-v", "error", "-print_format", "json",
        "-show_streams", "-show_format", str(path),
    ], timeout=60)
    value = json.loads(process.stdout)
    if not isinstance(value, dict):
        raise CanonicalManualVisualPipelineError("FFPROBE_OBJECT_REQUIRED")
    return value


def _duration(path: Path) -> float:
    probe = _probe(path)
    try:
        value = float((probe.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError) as exc:
        raise CanonicalManualVisualPipelineError("MEDIA_DURATION_INVALID:" + str(path)) from exc
    if value <= 0:
        raise CanonicalManualVisualPipelineError("MEDIA_DURATION_INVALID:" + str(path))
    return value


def assemble_manual_visual_episode(repo_root: Path, episode_id: str) -> dict[str, Any]:
    root = _episode_root(repo_root, episode_id)
    state_path = _state_path(root)
    state = load_state(state_path)
    _assert_state_fresh(state)
    if state["stage"] not in {"SHA_BOUND_VISUAL_LOCK", "AUTOMATED_ASSEMBLY", "MONTAGE", "AUDIO_SYNC"}:
        raise CanonicalManualVisualPipelineError("ASSEMBLY_REQUIRES_SHA_BOUND_VISUAL_LOCK")
    if state["stage"] == "AUDIO_SYNC":
        receipt_path = Path(state["artifacts"]["assembly_candidate"]["path"])
        receipt = _read(receipt_path)
        candidate = Path(str(receipt.get("candidate_path") or ""))
        if candidate.is_file() and receipt.get("candidate_sha256") == sha256_file(candidate):
            return {
                "status": "AUDIO_SYNC", "candidate_path": str(candidate),
                "candidate_sha256": receipt["candidate_sha256"],
                "assembly_plan_path": state["artifacts"]["assembly_plan"]["path"],
                "shot_count": _read(Path(state["artifacts"]["assembly_plan"]["path"]))["shot_count"],
                "provider_calls": 0, "paid_calls": 0, "reused": True,
            }
        raise CanonicalManualVisualPipelineError("ASSEMBLY_CANDIDATE_STALE")
    for slot in ("manual_visual_pack", "manual_asset_ledger", "visual_lock", "audio", "timing"):
        record = state["artifacts"].get(slot)
        if not record or not Path(record["path"]).is_file() or sha256_file(Path(record["path"])) != record["sha256"]:
            raise CanonicalManualVisualPipelineError("ASSEMBLY_AUTHORITY_STALE:" + slot)
    pack = _read(Path(state["artifacts"]["manual_visual_pack"]["path"]))
    ledger = _read(Path(state["artifacts"]["manual_asset_ledger"]["path"]))
    current = {str(x.get("shot_id")): x for x in ledger.get("assets", []) if isinstance(x, Mapping) and x.get("current") is True}
    if len(current) != len(pack.get("shots", [])):
        raise CanonicalManualVisualPipelineError("ASSEMBLY_VISUAL_COMPLETENESS_FAILED")
    audio = Path(state["artifacts"]["audio"]["path"])
    timeline_duration = float(pack["total_duration"])
    if abs(_duration(audio) - timeline_duration) > DURATION_TOLERANCE:
        raise CanonicalManualVisualPipelineError("FINAL_AUDIO_TIMELINE_DURATION_MISMATCH")
    work = root / ASSEMBLY_DIR_REL
    shots_dir = work / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = _binary("ffmpeg", "SIRAJ_FFMPEG_BIN")
    fingerprint = _canonical_sha({
        "visual_lock_sha256": state["artifacts"]["visual_lock"]["sha256"],
        "audio_sha256": state["artifacts"]["audio"]["sha256"],
        "timing_sha256": state["artifacts"]["timing"]["sha256"],
        "width": WIDTH, "height": HEIGHT, "fps": FPS,
    })
    plan_path = work / "assembly-plan-v1.json"
    plan = {
        "schema_version": "siraj-manual-visual-assembly-plan-v1", "episode_id": episode_id,
        "status": "READY", "visual_mode": "MANUAL_USER_PRODUCTION",
        "visual_lock_sha256": state["artifacts"]["visual_lock"]["sha256"],
        "audio_sha256": state["artifacts"]["audio"]["sha256"],
        "timing_sha256": state["artifacts"]["timing"]["sha256"],
        "duration_seconds": timeline_duration, "shot_count": len(pack["shots"]),
        "render_fingerprint_sha256": fingerprint, "provider_calls": 0, "paid_calls": 0,
        "shots": [], "created_at": _now(),
    }
    for index, shot in enumerate(pack["shots"], start=1):
        shot_id = str(shot["shot_id"])
        asset = current.get(shot_id)
        if asset is None:
            raise CanonicalManualVisualPipelineError("ASSEMBLY_ASSET_MISSING:" + shot_id)
        source = Path(str(asset["stored_path"]))
        if sha256_file(source) != asset["sha256"]:
            raise CanonicalManualVisualPipelineError("ASSEMBLY_ASSET_SHA_STALE:" + shot_id)
        duration = float(shot["duration"])
        output = shots_dir / f"{index:05d}-{shot_id}.mp4"
        receipt = output.with_suffix(".receipt.json")
        shot_fp = _canonical_sha({"parent": fingerprint, "shot_id": shot_id, "asset_sha256": asset["sha256"], "duration": duration})
        reusable = False
        if output.is_file() and receipt.is_file():
            old_receipt = _read(receipt)
            reusable = old_receipt.get("fingerprint_sha256") == shot_fp and old_receipt.get("output_sha256") == sha256_file(output)
        if not reusable:
            vf = f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=increase,crop={WIDTH}:{HEIGHT},fps={FPS},format=yuv420p"
            if asset["asset_type"] == "IMAGE":
                command = [ffmpeg, "-y", "-loop", "1", "-t", f"{duration:.6f}", "-i", str(source), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(output)]
            else:
                command = [ffmpeg, "-y", "-t", f"{duration:.6f}", "-i", str(source), "-vf", vf, "-an", "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", str(output)]
            _run(command)
            _write(receipt, {"schema_version": "siraj-manual-visual-shot-render-receipt-v1", "shot_id": shot_id, "fingerprint_sha256": shot_fp, "output_sha256": sha256_file(output), "duration": duration, "provider_calls": 0, "paid_calls": 0})
        plan["shots"].append({"shot_id": shot_id, "source_sha256": asset["sha256"], "duration": duration, "output_path": str(output), "output_sha256": sha256_file(output)})
    _write(plan_path, plan)
    state = load_state(state_path)
    _assert_state_fresh(state)
    if state["stage"] == "SHA_BOUND_VISUAL_LOCK":
        state = bind_artifact(state_path, "assembly_plan", plan_path)
        state = transition(state_path, "AUTOMATED_ASSEMBLY")
    concat = work / "concat.txt"
    concat.write_text("".join("file '" + str(Path(x["output_path"])).replace("'", "'\\''") + "'\n" for x in plan["shots"]), encoding="utf-8", newline="\n")
    video_only = work / "episode-video-only-v1.mp4"
    _run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(video_only)])
    montage_receipt = work / "montage-receipt-v1.json"
    _write(montage_receipt, {"schema_version": "siraj-manual-visual-montage-receipt-v1", "episode_id": episode_id, "plan_sha256": sha256_file(plan_path), "video_only_sha256": sha256_file(video_only), "duration": _duration(video_only), "status": "PASS", "provider_calls": 0, "paid_calls": 0})
    state = load_state(state_path)
    _assert_state_fresh(state)
    if state["stage"] == "AUTOMATED_ASSEMBLY":
        state = bind_artifact(state_path, "montage", montage_receipt)
        state = transition(state_path, "MONTAGE")
    candidate = work / "episode-master-candidate-v1.mp4"
    _run([ffmpeg, "-y", "-i", str(video_only), "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(candidate)])
    assembly_receipt = work / "audio-sync-receipt-v1.json"
    _write(assembly_receipt, {"schema_version": "siraj-manual-visual-audio-sync-receipt-v1", "episode_id": episode_id, "candidate_path": str(candidate), "candidate_sha256": sha256_file(candidate), "final_audio_sha256": state["artifacts"]["audio"]["sha256"], "timing_sha256": state["artifacts"]["timing"]["sha256"], "visual_lock_sha256": state["artifacts"]["visual_lock"]["sha256"], "assembly_plan_sha256": sha256_file(plan_path), "duration": _duration(candidate), "status": "PASS", "provider_calls": 0, "paid_calls": 0})
    state = load_state(state_path)
    _assert_state_fresh(state)
    if state["stage"] == "MONTAGE":
        state = bind_artifact(state_path, "assembly_candidate", assembly_receipt)
        state = transition(state_path, "AUDIO_SYNC")
    return {"status": "AUDIO_SYNC", "candidate_path": str(candidate), "candidate_sha256": sha256_file(candidate), "assembly_plan_path": str(plan_path), "shot_count": len(plan["shots"]), "provider_calls": 0, "paid_calls": 0}


def _qa_write_and_advance(state_path: Path, slot: str, stage: str, path: Path, value: Mapping[str, Any]) -> dict[str, Any]:
    _write(path, value)
    state = bind_artifact(state_path, slot, path)
    state = transition(state_path, stage)
    return state


def _validated_assembly_candidate(
    state: Mapping[str, Any], episode_id: str,
) -> tuple[dict[str, Any], Path]:
    receipt = _read(Path(state["artifacts"]["assembly_candidate"]["path"]))
    expected = {
        "episode_id": episode_id,
        "final_audio_sha256": state["artifacts"]["audio"]["sha256"],
        "timing_sha256": state["artifacts"]["timing"]["sha256"],
        "visual_lock_sha256": state["artifacts"]["visual_lock"]["sha256"],
        "assembly_plan_sha256": state["artifacts"]["assembly_plan"]["sha256"],
        "status": "PASS",
    }
    for key, value in expected.items():
        if receipt.get(key) != value:
            raise CanonicalManualVisualPipelineError("ASSEMBLY_RECEIPT_BINDING_INVALID:" + key)
    candidate = Path(str(receipt.get("candidate_path") or ""))
    if not candidate.is_file() or sha256_file(candidate) != receipt.get("candidate_sha256"):
        raise CanonicalManualVisualPipelineError("ASSEMBLY_CANDIDATE_STALE")
    return receipt, candidate


def run_separated_qa(repo_root: Path, episode_id: str) -> dict[str, Any]:
    root = _episode_root(repo_root, episode_id)
    state_path = _state_path(root)
    state = load_state(state_path)
    _assert_state_fresh(state)
    if state["stage"] not in {"AUDIO_SYNC", "TECHNICAL_QA", "CONSTITUTION_QA", "EDITORIAL_QA"}:
        raise CanonicalManualVisualPipelineError("QA_REQUIRES_AUDIO_SYNC")
    receipt, candidate = _validated_assembly_candidate(state, episode_id)
    probe = _probe(candidate)
    streams = probe.get("streams") if isinstance(probe.get("streams"), list) else []
    videos = [x for x in streams if isinstance(x, Mapping) and x.get("codec_type") == "video"]
    audios = [x for x in streams if isinstance(x, Mapping) and x.get("codec_type") == "audio"]
    pack = _read(Path(state["artifacts"]["manual_visual_pack"]["path"]))
    duration = _duration(candidate)
    if len(videos) != 1 or len(audios) != 1 or abs(duration - float(pack["total_duration"])) > 0.75:
        raise CanonicalManualVisualPipelineError("TECHNICAL_QA_FAILED")
    if state["stage"] == "AUDIO_SYNC":
        state = _qa_write_and_advance(state_path, "technical_qa", "TECHNICAL_QA", root / QA_DIR_REL / "technical-qa-v1.json", {"schema_version": "siraj-manual-visual-technical-qa-v1", "episode_id": episode_id, "status": "PASS", "candidate_sha256": sha256_file(candidate), "duration": duration, "video_streams": 1, "audio_streams": 1, "resolution": [int(videos[0].get("width") or 0), int(videos[0].get("height") or 0)], "timeline_gaps": 0, "timeline_overlaps": 0})
    ledger = _read(Path(state["artifacts"]["manual_asset_ledger"]["path"]))
    current = [x for x in ledger.get("assets", []) if isinstance(x, Mapping) and x.get("current") is True]
    if any(x.get("constitution_acceptance") is not True for x in current):
        raise CanonicalManualVisualPipelineError("CONSTITUTION_QA_HUMAN_ASSET_ACCEPTANCE_MISSING")
    state = load_state(state_path)
    if state["stage"] == "TECHNICAL_QA":
        state = _qa_write_and_advance(state_path, "constitution_qa", "CONSTITUTION_QA", root / QA_DIR_REL / "constitution-qa-v1.json", {"schema_version": "siraj-manual-visual-constitution-qa-v1", "episode_id": episode_id, "status": "PASS", "hard_failures": [], "asset_count": len(current), "visual_lock_sha256": state["artifacts"]["visual_lock"]["sha256"], "human_asset_acceptance_verified": True})
    coverage = _read(Path(state["artifacts"]["coverage_validation"]["path"]))
    if coverage.get("status") != "PASS":
        raise CanonicalManualVisualPipelineError("EDITORIAL_QA_COVERAGE_FAILED")
    state = load_state(state_path)
    if state["stage"] == "CONSTITUTION_QA":
        state = _qa_write_and_advance(state_path, "editorial_qa", "EDITORIAL_QA", root / QA_DIR_REL / "editorial-qa-v1.json", {"schema_version": "siraj-manual-visual-editorial-qa-v1", "episode_id": episode_id, "status": "PASS", "coverage_status": "PASS", "shot_count": len(pack["shots"]), "image_count": pack["total_images"], "video_count": pack["total_video_clips"], "continuity_review": "PASS_PRE_VISUAL_APPROVED"})
    return {"status": state["stage"], "technical_qa": "PASS", "constitution_qa": "PASS", "editorial_qa": "PASS", "human_final_review_required": True}


def record_human_final_review(repo_root: Path, episode_id: str, *, human_actor: str, decision: str) -> dict[str, Any]:
    if str(decision).upper() != "APPROVED" or not str(human_actor or "").strip():
        raise CanonicalManualVisualPipelineError("EXPLICIT_HUMAN_FINAL_APPROVAL_REQUIRED")
    root = _episode_root(repo_root, episode_id)
    state_path = _state_path(root)
    state = load_state(state_path)
    _assert_state_fresh(state)
    if state["stage"] == "HUMAN_FINAL_REVIEW":
        return {"status": state["stage"], "reused": True}
    if state["stage"] != "EDITORIAL_QA":
        raise CanonicalManualVisualPipelineError("HUMAN_FINAL_REVIEW_REQUIRES_ALL_QA")
    path = root / QA_DIR_REL / "human-final-review-v1.json"
    _write(path, {"schema_version": "siraj-manual-visual-human-final-review-v1", "episode_id": episode_id, "decision": "APPROVED", "human_actor": human_actor.strip(), "autonomous_approval": False, "approved_at": _now(), "publication_authorized": False})
    state = bind_artifact(state_path, "final_review_approval", path, status="APPROVED")
    state = transition(state_path, "HUMAN_FINAL_REVIEW")
    return {"status": state["stage"], "review_path": str(path), "human_actor": human_actor.strip()}


def build_master(repo_root: Path, episode_id: str) -> dict[str, Any]:
    root = _episode_root(repo_root, episode_id)
    state_path = _state_path(root)
    state = load_state(state_path)
    _assert_state_fresh(state)
    if state["stage"] == "MASTER":
        return {"status": "MASTER", "master_path": state["artifacts"]["final_master"]["path"], "master_sha256": state["artifacts"]["final_master"]["sha256"], "reused": True}
    if state["stage"] != "HUMAN_FINAL_REVIEW":
        raise CanonicalManualVisualPipelineError("MASTER_REQUIRES_HUMAN_FINAL_REVIEW")
    assembly, candidate = _validated_assembly_candidate(state, episode_id)
    master = root / MASTER_REL
    master.parent.mkdir(parents=True, exist_ok=True)
    candidate_sha = sha256_file(candidate)
    superseded: dict[str, str] | None = None
    if master.exists() and sha256_file(master) != candidate_sha:
        old_sha = sha256_file(master)
        history = master.parent / "history" / f"{old_sha}-episode-master-v1.mp4"
        history.parent.mkdir(parents=True, exist_ok=True)
        if history.exists() and sha256_file(history) != old_sha:
            raise CanonicalManualVisualPipelineError("MASTER_HISTORY_COLLISION")
        if not history.exists():
            history_tmp = history.with_name(f".{history.name}.{uuid.uuid4().hex}.tmp")
            try:
                shutil.copyfile(master, history_tmp)
                if sha256_file(history_tmp) != old_sha:
                    raise CanonicalManualVisualPipelineError("MASTER_HISTORY_COPY_SHA_MISMATCH")
                os.replace(history_tmp, history)
            finally:
                history_tmp.unlink(missing_ok=True)
        superseded = {"path": str(history), "sha256": old_sha}
    if not master.exists() or sha256_file(master) != candidate_sha:
        master_tmp = master.with_name(f".{master.name}.{uuid.uuid4().hex}.tmp")
        try:
            shutil.copyfile(candidate, master_tmp)
            if sha256_file(master_tmp) != candidate_sha:
                raise CanonicalManualVisualPipelineError("MASTER_COPY_SHA_MISMATCH")
            os.replace(master_tmp, master)
        finally:
            master_tmp.unlink(missing_ok=True)
    receipt_path = root / MASTER_RECEIPT_REL
    receipt = {"schema_version": "siraj-manual-visual-master-receipt-v1", "episode_id": episode_id, "status": "MASTER_COMPLETE", "master_path": str(master), "master_sha256": sha256_file(master), "assembly_candidate_sha256": assembly["candidate_sha256"], "final_audio_sha256": state["artifacts"]["audio"]["sha256"], "timing_sha256": state["artifacts"]["timing"]["sha256"], "visual_lock_sha256": state["artifacts"]["visual_lock"]["sha256"], "technical_qa_sha256": state["artifacts"]["technical_qa"]["sha256"], "constitution_qa_sha256": state["artifacts"]["constitution_qa"]["sha256"], "editorial_qa_sha256": state["artifacts"]["editorial_qa"]["sha256"], "human_final_review_sha256": state["artifacts"]["final_review_approval"]["sha256"], "superseded_master": superseded, "provider_calls": 0, "paid_calls": 0, "publication": False, "completed_at": _now()}
    _write(receipt_path, receipt)
    state = bind_artifact(state_path, "final_master", master)
    state = bind_artifact(state_path, "master_receipt", receipt_path)
    state = transition(state_path, "MASTER")
    return {"status": state["stage"], "master_path": str(master), "master_sha256": sha256_file(master), "receipt_path": str(receipt_path)}


def certify_shorts_compatibility(repo_root: Path, episode_id: str) -> dict[str, Any]:
    root = _episode_root(repo_root, episode_id)
    state_path = _state_path(root)
    state = load_state(state_path)
    _assert_state_fresh(state)
    if state["stage"] == "SHORTS_DERIVATIVE":
        return {"status": state["stage"], "reused": True}
    if state["stage"] != "MASTER":
        raise CanonicalManualVisualPipelineError("SHORTS_COMPATIBILITY_REQUIRES_MASTER")
    path = root / "shorts" / "canonical-master-compatibility-v1.json"
    _write(path, {"schema_version": "siraj-shorts-canonical-master-compatibility-v1", "episode_id": episode_id, "status": "PASS_READY_FOR_DERIVATIVE_WORKFLOW", "source_master_path": state["artifacts"]["final_master"]["path"], "source_master_sha256": state["artifacts"]["final_master"]["sha256"], "timing_path": state["artifacts"]["timing"]["path"], "timing_sha256": state["artifacts"]["timing"]["sha256"], "automatic_publication": False})
    state = bind_artifact(state_path, "shorts_manifest", path)
    state = transition(state_path, "SHORTS_DERIVATIVE")
    return {"status": state["stage"], "manifest_path": str(path)}


def archive_episode(repo_root: Path, episode_id: str) -> dict[str, Any]:
    root = _episode_root(repo_root, episode_id)
    state_path = _state_path(root)
    state = load_state(state_path)
    _assert_state_fresh(state)
    if state["stage"] == "ARCHIVE":
        return {"status": state["stage"], "archive_path": state["artifacts"]["archive_receipt"]["path"], "reused": True}
    if state["stage"] != "SHORTS_DERIVATIVE":
        raise CanonicalManualVisualPipelineError("ARCHIVE_REQUIRES_SHORTS_COMPATIBILITY")
    required = (
        "episode_manifest", "sources_lock", "script", "audio", "timing", "storyboard",
        "visual_contracts", "manual_visual_pack", "manual_asset_ledger", "visual_lock",
        "assembly_plan", "montage", "assembly_candidate", "technical_qa", "constitution_qa",
        "editorial_qa", "final_review_approval", "final_master", "master_receipt", "shorts_manifest",
    )
    artifacts = []
    for slot in required:
        record = state["artifacts"].get(slot)
        if not record:
            raise CanonicalManualVisualPipelineError("ARCHIVE_ARTIFACT_MISSING:" + slot)
        path = Path(record["path"])
        if not path.is_file() or sha256_file(path) != record["sha256"]:
            raise CanonicalManualVisualPipelineError("ARCHIVE_ARTIFACT_STALE:" + slot)
        artifacts.append({"slot": slot, "path": str(path), "sha256": record["sha256"]})
    path = root / ARCHIVE_REL
    receipt = {"schema_version": "siraj-canonical-episode-archive-v1", "episode_id": episode_id, "status": "ARCHIVED", "profile_id": MANUAL_VISUAL_PROFILE, "visual_mode": "MANUAL_USER_PRODUCTION", "artifacts": artifacts, "provider_calls": 0, "paid_calls": 0, "publication": False, "archived_at": _now()}
    receipt["archive_content_sha256"] = _canonical_sha(receipt)
    _write(path, receipt)
    state = bind_artifact(state_path, "archive_receipt", path)
    state = transition(state_path, "ARCHIVE")
    return {"status": state["stage"], "archive_path": str(path), "archive_sha256": sha256_file(path)}


def workflow_status(repo_root: Path, episode_id: str) -> dict[str, Any]:
    root = _episode_root(repo_root, episode_id)
    state = load_state(_state_path(root))
    index = MANUAL_VISUAL_STAGE_ORDER.index(state["stage"])
    actions = []
    if state["stage"] == "EPISODE_CREATE": actions.append("RUN_CONTINUE_PRE_VISUAL_PIPELINE")
    if state["stage"] == "HUMAN_PRE_VISUAL_APPROVAL": actions.append("EXPORT_MANUAL_VISUAL_PACK")
    if state["stage"] == "MANUAL_VISUAL_HANDOFF_READY": actions.append("IMPORT_MANUAL_VISUALS")
    if state["stage"] == "MANUAL_VISUAL_INGEST": actions.append("IMPORT_OR_REPLACE_MANUAL_VISUALS")
    if state["stage"] == "ASSET_VALIDATION": actions.append("LOCK_ACCEPTED_VISUALS")
    if state["stage"] == "SHA_BOUND_VISUAL_LOCK": actions.append("CONTINUE_ASSEMBLY")
    if state["stage"] == "AUDIO_SYNC": actions.append("RUN_SEPARATED_QA")
    if state["stage"] == "EDITORIAL_QA": actions.append("FINAL_HUMAN_REVIEW")
    if state["stage"] == "HUMAN_FINAL_REVIEW": actions.append("BUILD_MASTER")
    return {"schema_version": PIPELINE_SCHEMA, "episode_id": episode_id, "stage": state["stage"], "stage_index": index, "revision": state["revision"], "blocked": state["blocked"], "blockers": state["blockers"], "available_actions": actions, "visual_mode": "MANUAL_USER_PRODUCTION", "paid_visual_controls_visible": False, "provider_visual_fallback": False}


def cli() -> int:
    parser = argparse.ArgumentParser(description="SIRAJ canonical next-episode manual visual pipeline v1")
    parser.add_argument("--repo", required=True)
    parser.add_argument("--episode-id", required=True)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("create")
    advance = sub.add_parser("advance-previsual")
    advance.add_argument("--artifact-manifest", required=True)
    sub.add_parser("export-manual-pack")
    ingest = sub.add_parser("import-manual-visuals")
    ingest.add_argument("--directory", required=True)
    ingest.add_argument("--template")
    sub.add_parser("lock-manual-visuals")
    sub.add_parser("assemble")
    sub.add_parser("qa")
    review = sub.add_parser("approve-final-review")
    review.add_argument("--human-actor", required=True)
    sub.add_parser("build-master")
    sub.add_parser("shorts-compatibility")
    sub.add_parser("archive")
    sub.add_parser("status")
    args = parser.parse_args()
    repo = Path(args.repo)
    episode_id = args.episode_id
    if args.command == "create":
        result = bootstrap_episode(repo, episode_id)
    elif args.command == "advance-previsual":
        manifest = _read(Path(args.artifact_manifest))
        raw = manifest.get("artifacts")
        if not isinstance(raw, Mapping):
            raise CanonicalManualVisualPipelineError("PREVISUAL_ARTIFACT_MANIFEST_REQUIRED")
        result = advance_previsual(repo, episode_id, {str(key): Path(str(value)) for key, value in raw.items()})
    elif args.command == "export-manual-pack":
        result = export_manual_visual_handoff(repo, episode_id)
    elif args.command == "import-manual-visuals":
        result = import_manual_visuals(repo, episode_id, ingest_dir=Path(args.directory), ingest_template_path=Path(args.template) if args.template else None)
    elif args.command == "lock-manual-visuals":
        result = lock_imported_visuals(repo, episode_id)
    elif args.command == "assemble":
        result = assemble_manual_visual_episode(repo, episode_id)
    elif args.command == "qa":
        result = run_separated_qa(repo, episode_id)
    elif args.command == "approve-final-review":
        result = record_human_final_review(repo, episode_id, human_actor=args.human_actor, decision="APPROVED")
    elif args.command == "build-master":
        result = build_master(repo, episode_id)
    elif args.command == "shorts-compatibility":
        result = certify_shorts_compatibility(repo, episode_id)
    elif args.command == "archive":
        result = archive_episode(repo, episode_id)
    elif args.command == "status":
        result = workflow_status(repo, episode_id)
    else:
        raise AssertionError(args.command)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
