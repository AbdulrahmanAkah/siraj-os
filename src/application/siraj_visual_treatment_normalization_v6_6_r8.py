from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
from typing import Any, Mapping

CANONICAL_TREATMENTS = frozenset(
    {
        "ANIMATED_STILL_COMPOSITING",
        "GENERATED_VIDEO",
        "GRAPHICS",
    }
)

BLACK_HOLD_ALIASES = frozenset(
    {
        "STATIC_BLACK_HOLD",
        "BLACK_HOLD",
        "STATIC_BLACK",
        "HOLD_ON_BLACK",
    }
)

BLACK_HOLD_POSITIVE_PROMPT = (
    "Pure black frame held continuously, no visible subject, "
    "no text, no logo, no texture, no gradients, no scenery."
)
BLACK_HOLD_NEGATIVE_PROMPT = (
    "text, logo, watermark, visible objects, people, scenery, "
    "gradients, texture, noise, glow, highlights"
)


class VisualTreatmentNormalizationV66R8Error(RuntimeError):
    pass


@dataclass(frozen=True)
class LocalBlackHoldRenderResult:
    output_sha256: str
    duration_seconds: float
    output_path: Path
    receipt_path: Path


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(
        Path(path).read_text(encoding="utf-8-sig")
    )
    if not isinstance(value, dict):
        raise VisualTreatmentNormalizationV66R8Error(
            "JSON_OBJECT_REQUIRED:" + str(path)
        )
    return value


def _write(path: Path, value: Mapping[str, Any]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(
        path.name
        + "."
        + str(os.getpid())
        + ".tmp"
    )
    tmp.write_text(
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
    os.replace(tmp, path)


def _sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(
            lambda: handle.read(1024 * 1024),
            b"",
        ):
            digest.update(block)
    return digest.hexdigest()


def _treatment(item: Mapping[str, Any]) -> str:
    return str(
        item.get("final_budget_treatment")
        or item.get("treatment")
        or ""
    ).strip().upper()


def _duration(item: Mapping[str, Any]) -> float:
    try:
        start = float(item["start_seconds"])
        end = float(item["end_seconds"])
    except (KeyError, TypeError, ValueError) as exc:
        raise VisualTreatmentNormalizationV66R8Error(
            "VISUAL_TREATMENT_TIMING_REQUIRED:"
            + str(item.get("shot_id") or "")
        ) from exc
    duration = end - start
    if duration <= 0:
        raise VisualTreatmentNormalizationV66R8Error(
            "VISUAL_TREATMENT_DURATION_INVALID:"
            + str(item.get("shot_id") or "")
        )
    return duration


def _black_hold_spec(
    item: Mapping[str, Any],
    original_treatment: str,
) -> dict[str, Any]:
    return {
        "schema_version": (
            "siraj-local-static-black-hold-v6.6-r8"
        ),
        "kind": "STATIC_BLACK_HOLD",
        "background_hex": "#000000",
        "foreground": "NONE",
        "text": None,
        "width": 1920,
        "height": 1080,
        "fps": 30,
        "duration_seconds": _duration(item),
        "source_editorial_treatment": original_treatment,
        "provider_required": False,
    }


def normalize_visual_treatment(
    raw: Mapping[str, Any],
) -> tuple[dict[str, Any], bool]:
    item = dict(raw)
    treatment = _treatment(item)

    if treatment in CANONICAL_TREATMENTS:
        return item, False

    if treatment not in BLACK_HOLD_ALIASES:
        return item, False

    item["final_budget_treatment"] = "GRAPHICS"
    item["treatment"] = "GRAPHICS"
    item["graphics_spec"] = _black_hold_spec(
        item,
        treatment,
    )
    if not str(
        item.get("runware_positive_prompt_en")
        or ""
    ).strip():
        item[
            "runware_positive_prompt_en"
        ] = BLACK_HOLD_POSITIVE_PROMPT
    if not str(
        item.get("runware_negative_prompt_en")
        or ""
    ).strip():
        item[
            "runware_negative_prompt_en"
        ] = BLACK_HOLD_NEGATIVE_PROMPT
    item["contains_people"] = False
    item["visual_treatment_normalization"] = {
        "version": "V6.6-R8",
        "original_treatment": treatment,
        "canonical_treatment": "GRAPHICS",
        "local_renderer_kind": "STATIC_BLACK_HOLD",
        "semantic_content_changed": False,
        "provider_required": False,
    }
    return item, True


def normalize_visual_treatments(
    raw_items: list[Any],
) -> list[Any]:
    normalized: list[Any] = []
    for raw in raw_items:
        if not isinstance(raw, Mapping):
            normalized.append(raw)
            continue
        item, _ = normalize_visual_treatment(raw)
        normalized.append(item)
    return normalized


def normalize_prompt_plan(
    payload: Mapping[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    value = dict(payload)
    raw_items = value.get("items")
    if not isinstance(raw_items, list):
        raise VisualTreatmentNormalizationV66R8Error(
            "PROMPT_ITEMS_REQUIRED"
        )

    items: list[Any] = []
    changes: list[dict[str, Any]] = []

    for raw in raw_items:
        if not isinstance(raw, Mapping):
            items.append(raw)
            continue

        item, changed = normalize_visual_treatment(raw)
        items.append(item)

        if changed:
            norm = item.get(
                "visual_treatment_normalization"
            )
            original = (
                str(norm.get("original_treatment") or "")
                if isinstance(norm, Mapping)
                else ""
            )
            changes.append(
                {
                    "shot_id": str(
                        item.get("shot_id") or ""
                    ),
                    "original_treatment": original,
                    "canonical_treatment": "GRAPHICS",
                    "local_renderer_kind": "STATIC_BLACK_HOLD",
                }
            )

    value["items"] = items

    if changes:
        value[
            "visual_treatment_normalization_v6_6_r8"
        ] = {
            "status": "PASS",
            "change_count": len(changes),
            "changes": changes,
            "semantic_content_changed": False,
        }

    return value, changes


def is_static_black_hold_spec(
    spec: Mapping[str, Any],
) -> bool:
    return (
        str(spec.get("kind") or "").strip().upper()
        == "STATIC_BLACK_HOLD"
    )


def _ffmpeg() -> Path:
    configured = os.environ.get(
        "SIRAJ_FFMPEG_EXE",
        "",
    ).strip()
    if configured and Path(configured).is_file():
        return Path(configured)

    found = shutil.which("ffmpeg")
    if not found:
        raise VisualTreatmentNormalizationV66R8Error(
            "FFMPEG_NOT_AVAILABLE_FOR_STATIC_BLACK_HOLD"
        )
    return Path(found)


def render_static_black_hold(
    spec_path: Path,
    output_path: Path,
    *,
    receipt_path: Path,
) -> LocalBlackHoldRenderResult:
    spec_path = Path(spec_path)
    output_path = Path(output_path)
    receipt_path = Path(receipt_path)

    spec = _read(spec_path)
    if not is_static_black_hold_spec(spec):
        raise VisualTreatmentNormalizationV66R8Error(
            "STATIC_BLACK_HOLD_SPEC_REQUIRED:"
            + str(spec_path)
        )

    try:
        duration = float(spec["duration_seconds"])
        width = int(spec.get("width", 1920))
        height = int(spec.get("height", 1080))
        fps = int(spec.get("fps", 30))
    except (KeyError, TypeError, ValueError) as exc:
        raise VisualTreatmentNormalizationV66R8Error(
            "STATIC_BLACK_HOLD_SPEC_INVALID:"
            + str(spec_path)
        ) from exc

    if duration <= 0 or width <= 0 or height <= 0 or fps <= 0:
        raise VisualTreatmentNormalizationV66R8Error(
            "STATIC_BLACK_HOLD_SPEC_RANGE_INVALID:"
            + str(spec_path)
        )

    output_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    receipt_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    process = subprocess.run(
        [
            str(_ffmpeg()),
            "-y",
            "-f",
            "lavfi",
            "-i",
            (
                "color=c=black:"
                f"s={width}x{height}:"
                f"r={fps}:"
                f"d={duration:.6f}"
            ),
            "-an",
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            str(output_path),
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if process.returncode:
        raise VisualTreatmentNormalizationV66R8Error(
            "STATIC_BLACK_HOLD_FFMPEG_FAILED:"
            + process.stderr[-4000:]
        )

    if (
        not output_path.is_file()
        or output_path.stat().st_size <= 0
    ):
        raise VisualTreatmentNormalizationV66R8Error(
            "STATIC_BLACK_HOLD_OUTPUT_MISSING:"
            + str(output_path)
        )

    digest = _sha(output_path)

    receipt = {
        "schema_version": (
            "siraj-local-static-black-hold-receipt-v6.6-r8"
        ),
        "status": "PASS",
        "media_kind": "LOCAL_GRAPHICS",
        "renderer": "FFMPEG_LAVFI_COLOR",
        "provider": "LOCAL",
        "paid_provider_request": False,
        "network_call": False,
        "kind": "STATIC_BLACK_HOLD",
        "duration_seconds": duration,
        "output_path": str(output_path),
        "output_sha256": digest,
    }
    _write(
        receipt_path,
        receipt,
    )

    return LocalBlackHoldRenderResult(
        output_sha256=digest,
        duration_seconds=duration,
        output_path=output_path,
        receipt_path=receipt_path,
    )
