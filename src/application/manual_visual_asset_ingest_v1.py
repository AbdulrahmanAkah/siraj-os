"""Fail-closed ingest, validation, replacement, and SHA lock for manual visuals."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from src.application.manual_visual_production_pack_v1 import (
    ManualVisualPackError,
    validate_pack_document,
)

LEDGER_SCHEMA = "siraj-manual-visual-asset-ledger-v1"
LOCK_SCHEMA = "siraj-sha-bound-manual-visual-lock-v1"
INVALIDATION_SCHEMA = "siraj-manual-visual-scoped-invalidation-v1"
SUPPORTED_IMAGES = {".png", ".jpg", ".jpeg", ".webp"}
SUPPORTED_VIDEOS = {".mp4", ".mov", ".mkv", ".webm"}


class ManualVisualIngestError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _read(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ManualVisualIngestError("JSON_UNREADABLE:" + str(path)) from exc
    if not isinstance(value, dict):
        raise ManualVisualIngestError("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(
            json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _ffprobe_path() -> str:
    configured = str(os.environ.get("SIRAJ_FFPROBE_BIN") or "").strip()
    found = configured or shutil.which("ffprobe") or ""
    if not found or not Path(found).is_file():
        raise ManualVisualIngestError("FFPROBE_NOT_AVAILABLE")
    return found


def _probe_video(path: Path) -> dict[str, Any]:
    process = subprocess.run(
        [
            _ffprobe_path(), "-v", "error", "-print_format", "json",
            "-show_streams", "-show_format", str(path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=60,
    )
    if process.returncode != 0:
        raise ManualVisualIngestError("VIDEO_FFPROBE_FAILED:" + path.name)
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError as exc:
        raise ManualVisualIngestError("VIDEO_FFPROBE_JSON_INVALID:" + path.name) from exc
    streams = payload.get("streams") if isinstance(payload, dict) else None
    if not isinstance(streams, list):
        raise ManualVisualIngestError("VIDEO_STREAMS_MISSING:" + path.name)
    videos = [x for x in streams if isinstance(x, Mapping) and x.get("codec_type") == "video"]
    if len(videos) != 1:
        raise ManualVisualIngestError("VIDEO_STREAM_COUNT_INVALID:" + path.name)
    video = videos[0]
    try:
        duration = float((payload.get("format") or {}).get("duration") or video.get("duration") or 0)
        width = int(video.get("width") or 0)
        height = int(video.get("height") or 0)
    except (TypeError, ValueError) as exc:
        raise ManualVisualIngestError("VIDEO_PROBE_VALUES_INVALID:" + path.name) from exc
    rate = str(video.get("avg_frame_rate") or "0/1")
    try:
        numerator, denominator = rate.split("/", 1)
        fps = float(numerator) / float(denominator) if float(denominator) else 0.0
    except (ValueError, ZeroDivisionError):
        fps = 0.0
    if duration <= 0 or width <= 0 or height <= 0 or fps <= 0:
        raise ManualVisualIngestError("VIDEO_PROBE_VALUES_INVALID:" + path.name)
    return {
        "duration": round(duration, 6), "width": width, "height": height,
        "fps": round(fps, 6), "codec": str(video.get("codec_name") or ""),
        "container": str((payload.get("format") or {}).get("format_name") or ""),
    }


def _probe_image(path: Path) -> dict[str, Any]:
    try:
        from PIL import Image
    except ImportError as exc:
        raise ManualVisualIngestError("PILLOW_NOT_AVAILABLE") from exc
    try:
        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            image_format = str(image.format or "")
    except Exception as exc:
        raise ManualVisualIngestError("IMAGE_CORRUPT_OR_UNREADABLE:" + path.name) from exc
    if width <= 0 or height <= 0:
        raise ManualVisualIngestError("IMAGE_DIMENSIONS_INVALID:" + path.name)
    return {
        "duration": None, "width": int(width), "height": int(height),
        "fps": None, "codec": image_format, "container": image_format,
    }


def _validate_geometry(probe: Mapping[str, Any], filename: str) -> None:
    width = int(probe["width"])
    height = int(probe["height"])
    if width < 1280 or height < 720:
        raise ManualVisualIngestError("ASSET_RESOLUTION_INSUFFICIENT:" + filename)
    ratio = width / height
    if not 1.45 <= ratio <= 2.05:
        raise ManualVisualIngestError("ASSET_ASPECT_RATIO_UNSUPPORTED:" + filename)


def _selected_path(entry: Mapping[str, Any], ingest_dir: Path) -> Path:
    selected = entry.get("selected_path")
    if isinstance(selected, str) and selected.strip():
        path = Path(selected)
        return path.resolve() if path.is_absolute() else (ingest_dir / path).resolve()
    return (ingest_dir / str(entry.get("expected_filename") or "")).resolve()


def record_human_asset_selection(
    *,
    ingest_template_path: Path,
    ingest_dir: Path,
    human_actor: str,
) -> dict[str, Any]:
    """Record explicit human selection/constitutional acceptance in the template."""

    actor = str(human_actor or "").strip()
    if not actor:
        raise ManualVisualIngestError("HUMAN_ASSET_SELECTOR_REQUIRED")
    path = Path(ingest_template_path).resolve()
    directory = Path(ingest_dir).resolve()
    template = _read(path)
    entries = template.get("assets")
    if not isinstance(entries, list) or not entries:
        raise ManualVisualIngestError("INGEST_TEMPLATE_ASSETS_REQUIRED")
    missing: list[str] = []
    for raw in entries:
        if not isinstance(raw, dict):
            raise ManualVisualIngestError("INGEST_TEMPLATE_ASSET_OBJECT_REQUIRED")
        if not _selected_path(raw, directory).is_file():
            missing.append(str(raw.get("shot_id") or "UNKNOWN"))
    if missing:
        raise ManualVisualIngestError("CANNOT_ACCEPT_MISSING_ASSETS:" + ",".join(sorted(missing)))
    accepted_at = _now()
    for raw in entries:
        raw["human_selected"] = True
        raw["constitution_acceptance"] = True
        raw["human_actor"] = actor
        raw["human_accepted_at"] = accepted_at
    template["human_selection_receipt"] = {
        "human_actor": actor,
        "accepted_at": accepted_at,
        "asset_count": len(entries),
        "decision": "APPROVED_FOR_TECHNICAL_VALIDATION",
        "autonomous_approval": False,
    }
    _write(path, template)
    return {"status": "HUMAN_ASSET_SELECTION_RECORDED", "template_path": str(path), "asset_count": len(entries)}


def ingest_manual_visuals(
    *,
    episode_root: Path,
    pack_path: Path,
    ingest_template_path: Path,
    ingest_dir: Path,
    expected_pack_sha256: str,
) -> dict[str, Any]:
    episode_root = Path(episode_root).resolve()
    pack_path = Path(pack_path).resolve()
    template_path = Path(ingest_template_path).resolve()
    ingest_dir = Path(ingest_dir).resolve()
    pack = _read(pack_path)
    template = _read(template_path)
    if sha256_file(pack_path) != str(expected_pack_sha256 or ""):
        raise ManualVisualIngestError("MANUAL_VISUAL_PACK_CANONICAL_SHA_MISMATCH")
    try:
        validate_pack_document(pack)
    except ManualVisualPackError as exc:
        raise ManualVisualIngestError(str(exc)) from exc
    if template.get("episode_id") != pack.get("episode_id"):
        raise ManualVisualIngestError("INGEST_TEMPLATE_EPISODE_MISMATCH")
    if template.get("pack_sha256") != sha256_file(pack_path):
        raise ManualVisualIngestError("INGEST_TEMPLATE_PACK_SHA_STALE")
    entries = template.get("assets")
    if not isinstance(entries, list):
        raise ManualVisualIngestError("INGEST_TEMPLATE_ASSETS_REQUIRED")
    by_shot = {str(x.get("shot_id")): x for x in entries if isinstance(x, Mapping)}
    if len(by_shot) != len(entries):
        raise ManualVisualIngestError("INGEST_TEMPLATE_DUPLICATE_OR_INVALID_SHOT")
    ledger_path = episode_root / "manual-visuals" / "manual-visual-asset-ledger-v1.json"
    old = _read(ledger_path) if ledger_path.is_file() else {
        "schema_version": LEDGER_SCHEMA, "episode_id": pack["episode_id"], "revision": 0,
        "visual_mode": "MANUAL_USER_PRODUCTION", "assets": [], "invalidations": [],
    }
    if old.get("schema_version") != LEDGER_SCHEMA or old.get("episode_id") != pack.get("episode_id"):
        raise ManualVisualIngestError("EXISTING_LEDGER_AUTHORITY_MISMATCH")
    old_current = {
        str(x.get("shot_id")): x for x in old.get("assets", [])
        if isinstance(x, Mapping) and x.get("current") is True
    }
    new_records: list[dict[str, Any]] = []
    missing: list[str] = []
    failures: list[dict[str, str]] = []
    seen_sha: dict[str, str] = {}
    replacements: list[dict[str, str]] = []
    accepted_root = episode_root / "manual-visuals" / "accepted"
    for shot in pack.get("shots", []):
        if not isinstance(shot, Mapping):
            raise ManualVisualIngestError("PACK_SHOT_OBJECT_REQUIRED")
        shot_id = str(shot.get("shot_id") or "")
        entry = by_shot.get(shot_id)
        if entry is None:
            missing.append(shot_id)
            continue
        if entry.get("asset_slot") != shot.get("asset_slot") or entry.get("asset_type") != shot.get("recommended_asset_type"):
            failures.append({"shot_id": shot_id, "code": "SHOT_MAPPING_MISMATCH"})
            continue
        source = _selected_path(entry, ingest_dir)
        if not source.is_file():
            missing.append(shot_id)
            continue
        if entry.get("human_selected") is not True or entry.get("constitution_acceptance") is not True:
            failures.append({"shot_id": shot_id, "code": "HUMAN_ASSET_ACCEPTANCE_REQUIRED"})
            continue
        asset_type = str(shot["recommended_asset_type"])
        extension = source.suffix.lower()
        try:
            if asset_type == "IMAGE":
                if extension not in SUPPORTED_IMAGES:
                    raise ManualVisualIngestError("IMAGE_EXTENSION_UNSUPPORTED:" + source.name)
                probe = _probe_image(source)
            else:
                if extension not in SUPPORTED_VIDEOS:
                    raise ManualVisualIngestError("VIDEO_EXTENSION_UNSUPPORTED:" + source.name)
                probe = _probe_video(source)
                if float(probe["duration"] or 0) + 0.05 < float(shot["duration"]):
                    raise ManualVisualIngestError("VIDEO_TOO_SHORT_FOR_SHOT:" + source.name)
            _validate_geometry(probe, source.name)
        except ManualVisualIngestError as exc:
            failures.append({"shot_id": shot_id, "code": str(exc)})
            continue
        digest = sha256_file(source)
        if digest in seen_sha and entry.get("reuse_approved") is not True:
            failures.append({"shot_id": shot_id, "code": "DUPLICATE_ASSET_REUSE_NOT_APPROVED"})
            continue
        seen_sha[digest] = shot_id
        destination = accepted_root / shot_id / f"{digest[:16]}-{shot['expected_filename']}"
        if destination.exists():
            if not destination.is_file() or sha256_file(destination) != digest:
                raise ManualVisualIngestError("IMMUTABLE_ACCEPTED_ASSET_COLLISION:" + shot_id)
        else:
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(f".{destination.name}.{uuid.uuid4().hex}.tmp")
            try:
                shutil.copyfile(source, temporary)
                if sha256_file(temporary) != digest:
                    raise ManualVisualIngestError("ASSET_COPY_SHA_MISMATCH:" + shot_id)
                os.replace(temporary, destination)
            finally:
                temporary.unlink(missing_ok=True)
        previous = old_current.get(shot_id)
        previous_sha = str(previous.get("sha256") or "") if previous else ""
        if previous_sha and previous_sha != digest:
            replacements.append({"shot_id": shot_id, "old_sha256": previous_sha, "new_sha256": digest})
        record = {
            "episode_id": pack["episode_id"], "shot_id": shot_id,
            "asset_slot": shot["asset_slot"], "asset_type": asset_type,
            "source": "MANUAL_USER_SUPPLIED", "original_filename": source.name,
            "canonical_filename": shot["expected_filename"], "stored_path": str(destination),
            "sha256": digest, "duration": probe["duration"], "width": probe["width"],
            "height": probe["height"], "fps": probe["fps"], "codec": probe["codec"],
            "container": probe["container"], "ingested_at": _now(),
            "validation_status": "PASS", "human_selected": True,
            "constitution_acceptance": True, "current": True,
            "supersedes_sha256": previous_sha or None,
            "probe_sha256": _canonical_sha(probe),
        }
        new_records.append(record)
    missing_report = {
        "schema_version": "siraj-missing-manual-visual-assets-v1",
        "episode_id": pack["episode_id"], "missing_shot_ids": sorted(missing),
        "invalid_assets": failures, "status": "PASS" if not missing and not failures else "BLOCKED",
        "created_at": _now(),
    }
    missing_path = episode_root / "manual-visuals" / "missing-manual-visual-assets-v1.json"
    _write(missing_path, missing_report)
    if missing or failures:
        return {
            "status": "MISSING_MANUAL_VISUAL_ASSETS", "missing": sorted(missing),
            "failures": failures, "report_path": str(missing_path),
        }
    required_shots = {str(x.get("shot_id")) for x in pack.get("shots", []) if isinstance(x, Mapping)}
    if {x["shot_id"] for x in new_records} != required_shots:
        raise ManualVisualIngestError("MANUAL_VISUAL_COMPLETENESS_MISMATCH")
    if (
        old.get("status") == "PASS_COMPLETE_VALIDATED"
        and set(old_current) == required_shots
        and all(str(old_current[item["shot_id"]].get("sha256")) == item["sha256"] for item in new_records)
    ):
        return {
            "status": "PASS_COMPLETE_VALIDATED", "ledger_path": str(ledger_path),
            "ledger_sha256": sha256_file(ledger_path), "asset_count": len(new_records),
            "replacements": [], "missing_report_path": str(missing_path), "reused": True,
        }
    historical = []
    replaced_shots = {x["shot_id"] for x in replacements}
    for item in old.get("assets", []):
        if not isinstance(item, Mapping):
            continue
        copy = dict(item)
        if copy.get("shot_id") in replaced_shots and copy.get("current") is True:
            copy["current"] = False
            replacement = next(x for x in replacements if x["shot_id"] == copy.get("shot_id"))
            copy["superseded_by_sha256"] = replacement["new_sha256"]
        if copy.get("shot_id") not in required_shots or copy.get("current") is not True or copy.get("sha256") not in {x["sha256"] for x in new_records}:
            historical.append(copy)
    invalidations = list(old.get("invalidations") or [])
    if replacements:
        invalidations.append(
            {
                "schema_version": INVALIDATION_SCHEMA, "at": _now(),
                "affected_shot_ids": sorted(replaced_shots), "replacements": replacements,
                "invalidated_nodes": ["ASSEMBLY", "MONTAGE", "AUDIO_SYNC", "QA", "MASTER", "SHORTS", "ARCHIVE"],
                "scope": "SHOT_SCOPED_INPUT_WITH_DOWNSTREAM_RECEIPT_INVALIDATION",
            }
        )
    ledger = {
        "schema_version": LEDGER_SCHEMA, "episode_id": pack["episode_id"],
        "visual_mode": "MANUAL_USER_PRODUCTION", "revision": int(old.get("revision") or 0) + 1,
        "pack_path": str(pack_path), "pack_sha256": sha256_file(pack_path),
        "assets": historical + new_records, "invalidations": invalidations,
        "current_asset_count": len(new_records), "required_shot_count": len(required_shots),
        "status": "PASS_COMPLETE_VALIDATED", "updated_at": _now(),
    }
    ledger["ledger_content_sha256"] = _canonical_sha(ledger)
    _write(ledger_path, ledger)
    return {
        "status": "PASS_COMPLETE_VALIDATED", "ledger_path": str(ledger_path),
        "ledger_sha256": sha256_file(ledger_path), "asset_count": len(new_records),
        "replacements": replacements, "missing_report_path": str(missing_path),
    }


def lock_manual_visuals(
    *,
    pack_path: Path,
    ledger_path: Path,
    output_path: Path,
    expected_pack_sha256: str,
    expected_ledger_sha256: str,
) -> dict[str, Any]:
    pack = _read(Path(pack_path))
    ledger = _read(Path(ledger_path))
    if sha256_file(Path(pack_path)) != expected_pack_sha256:
        raise ManualVisualIngestError("MANUAL_VISUAL_PACK_CANONICAL_SHA_MISMATCH")
    if sha256_file(Path(ledger_path)) != expected_ledger_sha256:
        raise ManualVisualIngestError("MANUAL_VISUAL_LEDGER_CANONICAL_SHA_MISMATCH")
    try:
        validate_pack_document(pack)
    except ManualVisualPackError as exc:
        raise ManualVisualIngestError(str(exc)) from exc
    if ledger.get("status") != "PASS_COMPLETE_VALIDATED":
        raise ManualVisualIngestError("MANUAL_VISUAL_LEDGER_NOT_COMPLETE")
    if ledger.get("pack_sha256") != sha256_file(Path(pack_path)):
        raise ManualVisualIngestError("MANUAL_VISUAL_LEDGER_PACK_SHA_STALE")
    required = {str(x.get("shot_id")) for x in pack.get("shots", []) if isinstance(x, Mapping)}
    current = [x for x in ledger.get("assets", []) if isinstance(x, Mapping) and x.get("current") is True]
    if {str(x.get("shot_id")) for x in current} != required or len(current) != len(required):
        raise ManualVisualIngestError("MANUAL_VISUAL_LOCK_COMPLETENESS_FAILED")
    for asset in current:
        path = Path(str(asset.get("stored_path") or ""))
        if not path.is_file() or sha256_file(path) != asset.get("sha256"):
            raise ManualVisualIngestError("MANUAL_VISUAL_ASSET_STALE:" + str(asset.get("shot_id")))
    lock = {
        "schema_version": LOCK_SCHEMA, "episode_id": pack["episode_id"],
        "status": "SHA_BOUND_VISUAL_LOCK", "visual_mode": "MANUAL_USER_PRODUCTION",
        "pack_sha256": sha256_file(Path(pack_path)), "ledger_sha256": sha256_file(Path(ledger_path)),
        "assets": [{"shot_id": x["shot_id"], "sha256": x["sha256"], "stored_path": x["stored_path"]} for x in current],
        "automatic_visual_generation": False, "provider_visual_fallback": False,
        "locked_at": _now(),
    }
    lock["lock_content_sha256"] = _canonical_sha(lock)
    _write(Path(output_path), lock)
    return {"status": "SHA_BOUND_VISUAL_LOCK", "lock_path": str(Path(output_path)), "lock_sha256": sha256_file(Path(output_path))}
