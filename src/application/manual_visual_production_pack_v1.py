"""Provider-agnostic manual visual production pack for canonical episodes."""
from __future__ import annotations

import hashlib
import html
import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

PACK_SCHEMA = "siraj-manual-visual-production-pack-v1"
INGEST_TEMPLATE_SCHEMA = "siraj-manual-visual-ingest-template-v1"
NAMING_SCHEMA = "siraj-manual-visual-asset-naming-v1"
REQUIRED_SHOT_FIELDS = (
    "shot_id", "audio_start", "audio_end", "exact_audio_text",
    "script_section", "visual_purpose", "visual_priority",
    "recommended_asset_type", "what_to_create", "what_must_be_visible",
    "what_must_not_be_visible", "character_reference",
    "environment_reference", "continuity_from", "continuity_to",
    "composition", "camera_intent", "subject_motion_intent",
    "style_direction", "constitution_rules", "risk_class", "risk_reasons",
    "negative_constraints", "human_acceptance_checklist",
)


class ManualVisualPackError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_sha(value: Mapping[str, Any]) -> str:
    payload = json.dumps(dict(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8", newline="\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    _write(path, json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def _episode_code(episode_id: str) -> str:
    matches = re.findall(r"\d+", episode_id)
    if matches:
        return f"EP{int(matches[-1]):03d}"
    cleaned = re.sub(r"[^A-Za-z0-9]+", "-", episode_id).strip("-").upper()
    if not cleaned:
        raise ManualVisualPackError("EPISODE_ID_INVALID")
    return cleaned[:24]


def _required_text(shot: Mapping[str, Any], key: str, label: str) -> str:
    value = shot.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ManualVisualPackError(f"{label}_{key.upper()}_REQUIRED")
    return value.strip()


def _required_list(shot: Mapping[str, Any], key: str, label: str) -> list[Any]:
    value = shot.get(key)
    if not isinstance(value, list):
        raise ManualVisualPackError(f"{label}_{key.upper()}_LIST_REQUIRED")
    return value


def validate_shots(episode_id: str, shots: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not shots:
        raise ManualVisualPackError("VISUAL_SHOTS_REQUIRED")
    normalized: list[dict[str, Any]] = []
    previous_end = 0.0
    seen: set[str] = set()
    code = _episode_code(episode_id)
    for index, raw in enumerate(shots, start=1):
        if not isinstance(raw, Mapping):
            raise ManualVisualPackError(f"SHOT_{index:03d}_OBJECT_REQUIRED")
        label = f"SHOT_{index:03d}"
        for key in REQUIRED_SHOT_FIELDS:
            if key in {"constitution_rules", "risk_reasons", "negative_constraints", "human_acceptance_checklist"}:
                _required_list(raw, key, label)
            elif key in {"audio_start", "audio_end"}:
                if raw.get(key) is None:
                    raise ManualVisualPackError(f"{label}_{key.upper()}_REQUIRED")
            else:
                _required_text(raw, key, label)
        shot_id = str(raw["shot_id"]).strip()
        if shot_id in seen:
            raise ManualVisualPackError("DUPLICATE_SHOT_ID:" + shot_id)
        seen.add(shot_id)
        try:
            start = float(raw["audio_start"])
            end = float(raw["audio_end"])
        except (TypeError, ValueError) as exc:
            raise ManualVisualPackError(f"{label}_TIMING_INVALID") from exc
        if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
            raise ManualVisualPackError(f"{label}_TIMING_INVALID")
        if index > 1 and abs(start - previous_end) > 0.12:
            raise ManualVisualPackError(f"SHOT_TIMELINE_GAP_OR_OVERLAP:{shot_id}")
        asset_type = str(raw["recommended_asset_type"]).strip().upper()
        if asset_type not in {"IMAGE", "VIDEO"}:
            raise ManualVisualPackError(f"{label}_ASSET_TYPE_MUST_BE_IMAGE_OR_VIDEO")
        extension = ".png" if asset_type == "IMAGE" else ".mp4"
        expected = f"{code}-{shot_id}-{'I' if asset_type == 'IMAGE' else 'V'}01{extension}"
        item = dict(raw)
        item.update(
            {
                "audio_start": round(start, 6),
                "audio_end": round(end, 6),
                "duration": round(end - start, 6),
                "recommended_asset_type": asset_type,
                "asset_slot": f"{shot_id}:{asset_type}:01",
                "expected_filename": expected,
                "technical_requirements": {
                    "minimum_width": 1280,
                    "minimum_height": 720,
                    "target_aspect_ratio": "16:9",
                    "video_minimum_duration_seconds": round(end - start, 6) if asset_type == "VIDEO" else None,
                    "audio_in_visual_asset": "IGNORED_AND_STRIPPED",
                },
            }
        )
        normalized.append(item)
        previous_end = end
    return normalized


def build_pack(
    *,
    episode_id: str,
    final_title: str,
    episode_summary: str,
    final_script_version: str,
    final_audio_version: str,
    shots: Sequence[Mapping[str, Any]],
    source_lock_sha256: str,
    script_sha256: str,
    audio_sha256: str,
    timing_sha256: str,
    storyboard_sha256: str,
    visual_contracts_sha256: str,
    coverage_validation_sha256: str,
    pre_visual_approval_sha256: str,
) -> dict[str, Any]:
    for label, value in (
        ("EPISODE_ID", episode_id), ("FINAL_TITLE", final_title),
        ("EPISODE_SUMMARY", episode_summary), ("FINAL_SCRIPT_VERSION", final_script_version),
        ("FINAL_AUDIO_VERSION", final_audio_version),
    ):
        if not str(value or "").strip():
            raise ManualVisualPackError(label + "_REQUIRED")
    normalized = validate_shots(episode_id, shots)
    image = [shot for shot in normalized if shot["recommended_asset_type"] == "IMAGE"]
    video = [shot for shot in normalized if shot["recommended_asset_type"] == "VIDEO"]
    if not image or not video:
        raise ManualVisualPackError("IMAGE_AND_VIDEO_ALLOCATION_REQUIRED")
    total_duration = round(sum(float(shot["duration"]) for shot in normalized), 6)
    value: dict[str, Any] = {
        "schema_version": PACK_SCHEMA,
        "episode_id": episode_id,
        "final_title": final_title.strip(),
        "episode_summary": episode_summary.strip(),
        "final_script_version": final_script_version.strip(),
        "final_audio_version": final_audio_version.strip(),
        "total_duration": total_duration,
        "total_shots": len(normalized),
        "total_images": len(image),
        "total_video_clips": len(video),
        "image_duration_coverage": round(sum(float(x["duration"]) for x in image), 6),
        "video_duration_coverage": round(sum(float(x["duration"]) for x in video), 6),
        "source_lock_status": "LOCKED_SHA_BOUND",
        "script_qa_status": "PASS",
        "constitution_status": "PASS_PRE_VISUAL_HUMAN_APPROVED",
        "handoff_status": "MANUAL_VISUAL_HANDOFF_READY",
        "visual_mode": "MANUAL_USER_PRODUCTION",
        "automatic_visual_generation": False,
        "provider_visual_fallback": False,
        "bindings": {
            "source_lock_sha256": source_lock_sha256,
            "script_sha256": script_sha256,
            "audio_sha256": audio_sha256,
            "timing_sha256": timing_sha256,
            "storyboard_sha256": storyboard_sha256,
            "visual_contracts_sha256": visual_contracts_sha256,
            "coverage_validation_sha256": coverage_validation_sha256,
            "pre_visual_approval_sha256": pre_visual_approval_sha256,
        },
        "shots": normalized,
        "generated_at": _now(),
    }
    value["pack_content_sha256"] = _canonical_sha(value)
    return value


def validate_pack_document(pack: Mapping[str, Any]) -> dict[str, Any]:
    if pack.get("schema_version") != PACK_SCHEMA:
        raise ManualVisualPackError("MANUAL_VISUAL_PACK_SCHEMA_INVALID")
    episode_id = str(pack.get("episode_id") or "").strip()
    raw_shots = pack.get("shots")
    if not isinstance(raw_shots, list):
        raise ManualVisualPackError("MANUAL_VISUAL_PACK_SHOTS_REQUIRED")
    normalized = validate_shots(episode_id, raw_shots)
    images = [x for x in normalized if x["recommended_asset_type"] == "IMAGE"]
    videos = [x for x in normalized if x["recommended_asset_type"] == "VIDEO"]
    if not images or not videos:
        raise ManualVisualPackError("IMAGE_AND_VIDEO_ALLOCATION_REQUIRED")
    expected = dict(pack)
    declared_content_sha = str(expected.pop("pack_content_sha256", ""))
    if len(declared_content_sha) != 64 or _canonical_sha(expected) != declared_content_sha:
        raise ManualVisualPackError("MANUAL_VISUAL_PACK_CONTENT_SHA_INVALID")
    total = round(sum(float(x["duration"]) for x in normalized), 6)
    derived = {
        "total_duration": total,
        "total_shots": len(normalized),
        "total_images": len(images),
        "total_video_clips": len(videos),
        "image_duration_coverage": round(sum(float(x["duration"]) for x in images), 6),
        "video_duration_coverage": round(sum(float(x["duration"]) for x in videos), 6),
    }
    for key, value in derived.items():
        if pack.get(key) != value:
            raise ManualVisualPackError("MANUAL_VISUAL_PACK_DERIVED_FIELD_INVALID:" + key)
    bindings = pack.get("bindings")
    if not isinstance(bindings, Mapping):
        raise ManualVisualPackError("MANUAL_VISUAL_PACK_BINDINGS_REQUIRED")
    required_bindings = {
        "source_lock_sha256", "script_sha256", "audio_sha256", "timing_sha256",
        "storyboard_sha256", "visual_contracts_sha256",
        "coverage_validation_sha256", "pre_visual_approval_sha256",
    }
    for key in required_bindings:
        digest = str(bindings.get(key) or "")
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
            raise ManualVisualPackError("MANUAL_VISUAL_PACK_BINDING_INVALID:" + key)
    if pack.get("visual_mode") != "MANUAL_USER_PRODUCTION":
        raise ManualVisualPackError("MANUAL_VISUAL_PACK_MODE_INVALID")
    if pack.get("automatic_visual_generation") is not False or pack.get("provider_visual_fallback") is not False:
        raise ManualVisualPackError("MANUAL_VISUAL_PACK_PROVIDER_POLICY_INVALID")
    return {"episode_id": episode_id, "shots": normalized, **derived}


def _markdown(pack: Mapping[str, Any]) -> str:
    lines = [
        "# SIRAJ Manual Visual Production Pack V1", "",
        f"EPISODE_ID: {pack['episode_id']}",
        f"FINAL_TITLE: {pack['final_title']}",
        f"TOTAL_DURATION: {pack['total_duration']}",
        f"TOTAL_SHOTS: {pack['total_shots']}",
        f"TOTAL_IMAGES: {pack['total_images']}",
        f"TOTAL_VIDEO_CLIPS: {pack['total_video_clips']}", "",
    ]
    for shot in pack["shots"]:
        lines.extend(
            [
                f"## {shot['shot_id']} — {shot['recommended_asset_type']}", "",
                f"- Timecode: {shot['audio_start']:.3f} → {shot['audio_end']:.3f}",
                f"- Exact narration: {shot['exact_audio_text']}",
                f"- Purpose: {shot['visual_purpose']}",
                f"- Create: {shot['what_to_create']}",
                f"- Must be visible: {shot['what_must_be_visible']}",
                f"- Must not be visible: {shot['what_must_not_be_visible']}",
                f"- Composition: {shot['composition']}",
                f"- Camera: {shot['camera_intent']}",
                f"- Motion: {shot['subject_motion_intent']}",
                f"- Expected filename: `{shot['expected_filename']}`", "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _html(pack: Mapping[str, Any]) -> str:
    rows = []
    for shot in pack["shots"]:
        cells = [
            shot["shot_id"], f"{shot['audio_start']:.3f}–{shot['audio_end']:.3f}",
            shot["exact_audio_text"], shot["recommended_asset_type"],
            shot["what_to_create"], shot["what_must_be_visible"],
            shot["what_must_not_be_visible"], shot["composition"],
            shot["camera_intent"], shot["expected_filename"], shot["risk_class"],
        ]
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in cells) + "</tr>")
    return f"""<!doctype html><html lang=\"ar\" dir=\"rtl\"><head><meta charset=\"utf-8\"><title>{html.escape(str(pack['episode_id']))} — Manual Visual Pack</title><style>body{{font-family:Segoe UI,Tahoma,Arial,sans-serif;margin:24px;color:#202124}}table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid #bbb;padding:8px;vertical-align:top}}th{{background:#eee;position:sticky;top:0}}.meta{{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:18px}}.meta div{{background:#f5f5f5;padding:8px}}</style></head><body><h1>{html.escape(str(pack['final_title']))}</h1><div class=\"meta\"><div>Episode: {html.escape(str(pack['episode_id']))}</div><div>Shots: {pack['total_shots']}</div><div>Duration: {pack['total_duration']}</div><div>Images: {pack['total_images']}</div><div>Videos: {pack['total_video_clips']}</div><div>Status: {pack['handoff_status']}</div></div><table><thead><tr><th>Shot</th><th>Time</th><th>Narration</th><th>Type</th><th>Create</th><th>Visible</th><th>Forbidden</th><th>Composition</th><th>Camera</th><th>Filename</th><th>Risk</th></tr></thead><tbody>{''.join(rows)}</tbody></table></body></html>"""


def export_pack(pack: Mapping[str, Any], output_dir: Path) -> dict[str, Any]:
    output = Path(output_dir).resolve()
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "manual-visual-production-pack-v1.json"
    html_path = output / "manual-visual-production-pack-v1.html"
    markdown_path = output / "manual-visual-production-pack-v1.md"
    ingest_path = output / "manual-visual-ingest-template-v1.json"
    naming_path = output / "manual-visual-asset-naming-v1.json"
    _write_json(json_path, pack)
    _write(html_path, _html(pack))
    _write(markdown_path, _markdown(pack))
    ingest = {
        "schema_version": INGEST_TEMPLATE_SCHEMA,
        "episode_id": pack["episode_id"],
        "pack_sha256": _sha256(json_path),
        "assets": [
            {
                "shot_id": shot["shot_id"],
                "asset_slot": shot["asset_slot"],
                "asset_type": shot["recommended_asset_type"],
                "expected_filename": shot["expected_filename"],
                "selected_path": None,
                "human_selected": False,
                "constitution_acceptance": False,
            }
            for shot in pack["shots"]
        ],
    }
    _write_json(ingest_path, ingest)
    naming = {
        "schema_version": NAMING_SCHEMA,
        "episode_id": pack["episode_id"],
        "pattern": "{EPISODE_CODE}-{SHOT_ID}-{I|V}{NN}.{extension}",
        "mapping_authority": "manual-visual-ingest-template-v1.json",
        "items": [{"shot_id": shot["shot_id"], "filename": shot["expected_filename"]} for shot in pack["shots"]],
    }
    _write_json(naming_path, naming)
    files = [json_path, html_path, markdown_path, ingest_path, naming_path]
    return {
        "status": "MANUAL_VISUAL_HANDOFF_READY",
        "output_dir": str(output),
        "files": [{"path": str(path), "sha256": _sha256(path)} for path in files],
        "pack_path": str(json_path),
        "pack_sha256": _sha256(json_path),
        "ingest_template_path": str(ingest_path),
    }
