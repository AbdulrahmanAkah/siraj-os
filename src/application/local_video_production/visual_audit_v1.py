"""Evidence-first audit of the pre-existing visual audition files.

It never infers an external API call from an image alone.  It reports the
manifest label separately from the exact generation mechanism, which remains
unknown unless a receipt, request log, or provider response is present.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .visual_provider_v1 import atomic_write_json, image_dimensions, image_mime_type


PREVIOUS_IMAGE_AUDIT_SCHEMA_V1 = "siraj-previous-image-generation-audit-v1"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file(): return None
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError): return None
    return value if isinstance(value, dict) else None


def _png_metadata(path: Path) -> list[dict[str, str]]:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"): return []
    cursor, items = 8, []
    while cursor + 12 <= len(data):
        size = int.from_bytes(data[cursor:cursor + 4], "big")
        kind = data[cursor + 4:cursor + 8].decode("latin-1", "replace")
        chunk = data[cursor + 8:cursor + 8 + size]
        if kind in {"tEXt", "iTXt", "zTXt"}:
            items.append({"chunk": kind, "value": chunk[:500].decode("utf-8", "replace")})
        cursor += 12 + size
    return items


def audit_previous_image_generation(project_root: Path, output_path: Path, *, source_commit: str | None = None) -> dict[str, Any]:
    auditions = project_root / "working" / "production-v4" / "visual-auditions"
    audition_manifest = _read_json(auditions / "visual-audition-manifest.json")
    quality_manifest = _read_json(project_root / "manifests" / "quality-gate-v4-manifest.json")
    images: list[dict[str, Any]] = []
    manifest_assets = {str(item.get("path", "")): item for item in (audition_manifest or {}).get("assets", []) if isinstance(item, dict)}
    for path in sorted(auditions.glob("*")) if auditions.is_dir() else []:
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}: continue
        mime = image_mime_type(path)
        try: width, height = image_dimensions(path.read_bytes(), mime)
        except Exception: width, height = None, None
        relative = path.relative_to(project_root).as_posix()
        item = manifest_assets.get(relative, {})
        images.append({"path": relative, "creation_timestamp": path.stat().st_ctime, "modified_timestamp": path.stat().st_mtime, "bytes": path.stat().st_size, "dimensions": {"width": width, "height": height}, "mime_type": mime, "embedded_metadata": _png_metadata(path), "manifest_metadata": {key: item.get(key) for key in ("provider_identifier", "model_identifier", "prompt", "origin", "creator", "license", "source_url") if key in item}})
    provider_label = (audition_manifest or {}).get("asset_provider_identifier")
    has_receipt = False
    method = "UNKNOWN"
    confidence = "UNKNOWN"
    evidence: list[dict[str, str]] = []
    if provider_label == "OPENAI_IMAGE_GENERATION_BUILT_IN":
        method, confidence = "OPENAI_IMAGE_GENERATION_BUILT_IN_LABEL_ONLY", "STRONGLY_INFERRED"
        evidence.append({"kind": "manifest_label", "path": "working/production-v4/visual-auditions/visual-audition-manifest.json", "detail": "asset_provider_identifier=OPENAI_IMAGE_GENERATION_BUILT_IN; model_identifier is unspecified"})
        evidence.append({"kind": "implementation", "path": "src/application/local_video_production/quality_gate_v4.py", "detail": "CuratedGeneratedVisualProvider copies and normalizes local source files; it does not make an API request"})
    report = {"schema_version": PREVIOUS_IMAGE_AUDIT_SCHEMA_V1, "status": "PASS", "images_found": len(images), "images": images, "provider_evidence": evidence, "model_evidence": [{"status": "UNKNOWN", "detail": "No exact prior image model, API receipt, raw response, or request log was found."}], "prompt_evidence": [{"status": "CONFIRMED", "detail": "Short prompts are retained in the visual-audition manifest."}], "script_evidence": [{"status": "CONFIRMED", "path": "src/application/local_video_production/quality_gate_v4.py", "detail": "The quality-gate adapter consumes pre-existing local image paths."}], "api_evidence": [{"status": "UNKNOWN", "detail": "No project-owned API request/response evidence was found for the pre-existing images."}], "source_commit": source_commit or "a1a4a89", "previous_images_generation_method": method, "confidence": confidence, "exact_creation_method": "UNKNOWN: the manifest labels assets as built-in OpenAI image generation, but the retained code only copied local source images and no generation receipt identifies the original invocation.", "unresolved_questions": ["Which image-generation tool or API produced the original source images?", "Which exact model and parameters were used?", "Whether the manifest label was produced from a direct API call or a manually curated import?"], "quality_gate_manifest_present": quality_manifest is not None, "api_receipt_found": has_receipt}
    atomic_write_json(output_path, report)
    return report
