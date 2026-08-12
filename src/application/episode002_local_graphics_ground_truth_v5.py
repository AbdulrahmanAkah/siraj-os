"""Deterministic ground-truth local graphics renderer for SIRAJ Episode 002.

SIRAJ_EP002_GROUND_TRUTH_LOCAL_GRAPHICS_V5
Local-only. No network/provider/paid calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any, Mapping

EPISODE_ID = "episode-002-adam-temptation-fall-repentance"
RESEARCH_REL = Path("research/luna-research-final-v4.json")
PROMPT_REL = Path("preproduction/luna-semantic-prompt-direction-v6-2-1.json")
PREFLIGHT_REL = Path("orchestration/media-cost-preflight-v2.json")
EXPECTED_SOURCES = {
    "SRC-002": "القرآن الكريم، البقرة 2:35-38",
    "SRC-003": "القرآن الكريم، الأعراف 7:19-25",
    "SRC-004": "القرآن الكريم، طه 20:115-123",
    "SRC-005": "صحيح البخاري، حديث محاجة آدم وموسى، 3409",
    "SRC-006": "صحيح مسلم، حديث محاجة آدم وموسى، 2652d",
}
GRAPHICS_PROVENANCE = {
    "EP002-SH-032-G01": {
        "shot_id": "EP002-SH-032",
        "segment_ids": ["SEG-007"],
        "source_ids": ["SRC-002", "SRC-003", "SRC-004"],
        "binding_mode": "GROUND_TRUTH_COMPATIBILITY_PROVENANCE",
        "reason": (
            "The authored visual intentionally contains no source text; the "
            "final canonical Quran source register is conservatively bound as "
            "provenance for the guidance/reception segment."
        ),
    },
    "EP002-SH-040-G01": {
        "shot_id": "EP002-SH-040",
        "segment_ids": ["SEG-009"],
        "source_ids": ["SRC-005", "SRC-006"],
        "binding_mode": "GROUND_TRUTH_COMPATIBILITY_PROVENANCE",
        "reason": "The authored card explicitly names Sahih al-Bukhari and Sahih Muslim only.",
    },
    "EP002-SH-041-G01": {
        "shot_id": "EP002-SH-041",
        "segment_ids": ["SEG-009"],
        "source_ids": ["SRC-005", "SRC-006"],
        "binding_mode": "GROUND_TRUTH_COMPATIBILITY_PROVENANCE",
        "reason": "The analytical trajectories belong to the Adam-Moses hadith argument segment.",
    },
    "EP002-SH-042-G01": {
        "shot_id": "EP002-SH-042",
        "segment_ids": ["SEG-009"],
        "source_ids": ["SRC-005", "SRC-006"],
        "binding_mode": "GROUND_TRUTH_COMPATIBILITY_PROVENANCE",
        "reason": "The analytical timeline belongs to the Adam-Moses hadith argument segment.",
    },
}

EXPECTED_AUTHORED = {
    "EP002-SH-032-G01": {
        "format": "animated_vector_plate",
        "text_policy": "no_text_generated_or_rendered",
    },
    "EP002-SH-040-G01": {
        "format": "post_production_source_card",
        "text_overlay_ar": ["صحيح البخاري", "صحيح مسلم"],
    },
    "EP002-SH-041-G01": {
        "format": "animated_vector_diagram",
        "text_policy": "no_text_generated_or_rendered",
    },
    "EP002-SH-042-G01": {
        "format": "animated_vector_timeline",
        "text_policy": "no_text_generated_or_rendered",
    },
}

class GroundTruthGraphicsError(RuntimeError):
    pass


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise GroundTruthGraphicsError("JSON_OBJECT_REQUIRED:" + str(path))
    return value


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(dict(value), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def _canonical_sha(value: Any) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _find_row(document: Mapping[str, Any], shot_id: str) -> dict[str, Any]:
    items = document.get("items")
    if not isinstance(items, list):
        raise GroundTruthGraphicsError("PROMPT_ITEMS_REQUIRED")
    matches = [
        item for item in items
        if isinstance(item, Mapping) and str(item.get("shot_id") or "") == shot_id
    ]
    if len(matches) != 1:
        raise GroundTruthGraphicsError(
            "PROMPT_SHOT_MATCH_COUNT:" + shot_id + ":" + str(len(matches))
        )
    return dict(matches[0])


def _unit(preflight: Mapping[str, Any], unit_id: str) -> dict[str, Any]:
    units = preflight.get("units")
    if not isinstance(units, list):
        raise GroundTruthGraphicsError("PREFLIGHT_UNITS_REQUIRED")
    matches = [
        row for row in units
        if isinstance(row, Mapping)
        and str(row.get("unit_id") or row.get("request_id") or "") == unit_id
    ]
    if len(matches) != 1:
        raise GroundTruthGraphicsError(
            "PREFLIGHT_UNIT_MATCH_COUNT:" + unit_id + ":" + str(len(matches))
        )
    row = dict(matches[0])
    if str(row.get("media_kind") or "") != "LOCAL_GRAPHICS":
        raise GroundTruthGraphicsError("NOT_LOCAL_GRAPHICS:" + unit_id)
    return row


def validate_ground_truth(repo_root: Path, unit_id: str) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    episode = repo / "projects" / EPISODE_ID
    if unit_id not in GRAPHICS_PROVENANCE:
        raise GroundTruthGraphicsError("UNSUPPORTED_LOCAL_GRAPHICS_UNIT:" + unit_id)

    research_path = episode / RESEARCH_REL
    if not research_path.is_file():
        raise GroundTruthGraphicsError("FINAL_RESEARCH_FILE_REQUIRED")
    research_sha256 = _sha256(research_path)
    research = _read(research_path)
    source_register = research.get("source_register")
    if not isinstance(source_register, list):
        raise GroundTruthGraphicsError("FINAL_SOURCE_REGISTER_REQUIRED")
    observed = {
        str(row.get("source_id") or ""): str(row.get("title") or "")
        for row in source_register
        if isinstance(row, Mapping)
    }
    for source_id, title in EXPECTED_SOURCES.items():
        if observed.get(source_id) != title:
            raise GroundTruthGraphicsError(
                "FINAL_SOURCE_REGISTER_MISMATCH:" + source_id
            )

    preflight = _read(episode / PREFLIGHT_REL)
    unit = _unit(preflight, unit_id)
    binding = GRAPHICS_PROVENANCE[unit_id]
    if str(unit.get("shot_id") or "") != binding["shot_id"]:
        raise GroundTruthGraphicsError("LOCAL_GRAPHICS_SHOT_BINDING_CHANGED:" + unit_id)

    prompt_path = episode / PROMPT_REL
    prompt = _read(prompt_path)
    row = _find_row(prompt, binding["shot_id"])
    graphics_spec = row.get("graphics_spec")
    if not isinstance(graphics_spec, Mapping):
        raise GroundTruthGraphicsError("AUTHORED_GRAPHICS_SPEC_REQUIRED:" + unit_id)
    expected = EXPECTED_AUTHORED[unit_id]
    for key, value in expected.items():
        if graphics_spec.get(key) != value:
            raise GroundTruthGraphicsError(
                "AUTHORED_GRAPHICS_INTENT_CHANGED:" + unit_id + ":" + key
            )
    segments = [str(v) for v in (row.get("segment_ids") or [])]
    if segments != binding["segment_ids"]:
        raise GroundTruthGraphicsError("AUTHORED_GRAPHICS_SEGMENT_CHANGED:" + unit_id)

    duration = float(unit.get("timeline_coverage_seconds") or 0.0)
    if duration <= 0:
        raise GroundTruthGraphicsError("LOCAL_GRAPHICS_DURATION_REQUIRED:" + unit_id)

    return {
        "unit": unit,
        "prompt_item": row,
        "authored_graphics_spec": dict(graphics_spec),
        "authored_graphics_spec_sha256": _canonical_sha(graphics_spec),
        "source_ids": list(binding["source_ids"]),
        "binding_mode": binding["binding_mode"],
        "binding_reason": binding["reason"],
        "research_path": str(research_path.relative_to(repo)).replace("\\", "/"),
        "research_sha256": research_sha256,
        "prompt_path": str(prompt_path.relative_to(repo)).replace("\\", "/"),
        "prompt_sha256": _sha256(prompt_path),
        "duration_seconds": duration,
    }


def _ffmpeg(repo: Path) -> Path:
    try:
        from src.application.siraj_local_assembly_montage_v6_2_1 import _exe
        return Path(_exe("ffmpeg", "SIRAJ_FFMPEG_EXE"))
    except Exception:
        found = shutil.which("ffmpeg")
        if found:
            return Path(found)
    raise GroundTruthGraphicsError("FFMPEG_NOT_FOUND")


def _ffprobe(repo: Path) -> Path | None:
    try:
        from src.application.siraj_local_assembly_montage_v6_2_1 import _exe
        return Path(_exe("ffprobe", "SIRAJ_FFPROBE_EXE"))
    except Exception:
        found = shutil.which("ffprobe")
        return Path(found) if found else None


def _ease(value: float) -> float:
    value = min(1.0, max(0.0, value))
    return value * value * (3.0 - 2.0 * value)


def _draw_frame(unit_id: str, t: float, duration: float, path: Path) -> None:
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import (
        QColor,
        QFont,
        QImage,
        QLinearGradient,
        QPainter,
        QPainterPath,
        QPen,
    )

    width, height = 1280, 720
    image = QImage(width, height, QImage.Format.Format_ARGB32)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

    if unit_id.endswith("032-G01"):
        base = QLinearGradient(0, 0, width, height)
        base.setColorAt(0.0, QColor(244, 244, 240))
        base.setColorAt(0.55, QColor(226, 232, 236))
        base.setColorAt(1.0, QColor(205, 216, 226))
        painter.fillRect(image.rect(), base)
        phase = t / max(duration, 0.001)
        contrast = 1.0 - _ease(min(1.0, phase / 0.68))
        overlay = QColor(198, 211, 224, int(120 * contrast))
        painter.fillRect(image.rect(), overlay)
        # Restrained central tonal seam settles, clears, then becomes unmarked.
        seam_alpha = int(75 * max(0.0, 1.0 - _ease((phase - 0.12) / 0.58)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(126, 145, 164, seam_alpha))
        painter.drawRoundedRect(QRectF(width * 0.42, 0, width * 0.16, height), 48, 48)
        if phase > 0.62:
            matte = int(210 * _ease((phase - 0.62) / 0.24))
            painter.setBrush(QColor(235, 237, 236, matte))
            painter.drawRect(QRectF(0, 0, width, height))

    elif unit_id.endswith("040-G01"):
        bg = QLinearGradient(0, 0, width, height)
        bg.setColorAt(0.0, QColor(17, 27, 41))
        bg.setColorAt(1.0, QColor(45, 55, 66))
        painter.fillRect(image.rect(), bg)
        painter.setPen(QPen(QColor(227, 217, 191, 24), 1))
        for y in range(80, height, 64):
            painter.drawLine(70, y, width - 70, y)
        p = t / max(duration, 0.001)
        intro = _ease(p / 0.18)
        outro = 1.0 - _ease((p - 0.82) / 0.18) if p > 0.82 else 1.0
        visibility = max(0.0, min(intro, outro))
        slide = (1.0 - intro) * 90.0 + (1.0 - outro) * -70.0
        card = QRectF(180 + slide, 445, 920, 176)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(7, 13, 22, int(220 * visibility)))
        painter.drawRoundedRect(card, 18, 18)
        painter.setPen(QPen(QColor(220, 188, 111, int(220 * visibility)), 3))
        painter.drawLine(card.left() + 36, card.top() + 28, card.left() + 36, card.bottom() - 28)
        font = QFont("Segoe UI", 31)
        font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(QColor(246, 243, 235, int(255 * visibility)))
        top = QRectF(card.left() + 70, card.top() + 22, card.width() - 110, 62)
        bottom = QRectF(card.left() + 70, card.top() + 92, card.width() - 110, 62)
        flags = Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        painter.drawText(top, flags, "صحيح البخاري")
        painter.drawText(bottom, flags, "صحيح مسلم")

    elif unit_id.endswith("041-G01"):
        painter.fillRect(image.rect(), QColor(232, 226, 210))
        painter.setPen(QPen(QColor(78, 72, 62, 40), 1))
        for x in range(0, width, 48):
            painter.drawLine(x, 0, x, height)
        for y in range(0, height, 48):
            painter.drawLine(0, y, width, y)
        center = QPointF(width * 0.5, height * 0.52)
        p = t / max(duration, 0.001)
        a = _ease(p / 0.46)
        b = _ease((p - 0.28) / 0.50)
        path_a = QPainterPath(QPointF(90, height * 0.30))
        path_a.cubicTo(330, 210, 420, 420, center.x() - 28, center.y())
        path_b = QPainterPath(QPointF(width - 90, height * 0.72))
        path_b.cubicTo(930, 550, 820, 280, center.x() + 28, center.y())
        def draw_partial(path_obj: Any, frac: float, color: QColor) -> None:
            painter.setPen(QPen(color, 11, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            steps = 140
            points = [path_obj.pointAtPercent(i / steps) for i in range(int(steps * frac) + 1)]
            for left, right in zip(points, points[1:]):
                painter.drawLine(left, right)
        draw_partial(path_a, a, QColor(72, 103, 132))
        draw_partial(path_b, b, QColor(145, 96, 71))
        painter.setPen(QPen(QColor(51, 48, 43), 4))
        painter.setBrush(QColor(236, 191, 88))
        painter.drawEllipse(center, 18, 18)

    elif unit_id.endswith("042-G01"):
        painter.fillRect(image.rect(), QColor(22, 29, 39))
        y = height * 0.54
        left_x, mid_x, right_x = 230.0, 640.0, 1050.0
        painter.setPen(QPen(QColor(204, 210, 214), 7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(left_x, y), QPointF(right_x, y))
        for x, fill in (
            (left_x, QColor(127, 159, 177)),
            (mid_x, QColor(220, 180, 91)),
            (right_x, QColor(127, 159, 177)),
        ):
            painter.setPen(QPen(QColor(238, 239, 236), 3))
            painter.setBrush(fill)
            painter.drawEllipse(QPointF(x, y), 18, 18)
        p = t / max(duration, 0.001)
        travel = _ease((p - 0.28) / 0.50)
        x = right_x - (right_x - mid_x - 30) * travel
        painter.setPen(QPen(QColor(225, 117, 92), 10, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        painter.drawLine(QPointF(right_x - 20, y - 105), QPointF(x, y - 105))
        if travel > 0.02:
            tip = QPointF(x, y - 105)
            painter.drawLine(tip, QPointF(x + 30, y - 126))
            painter.drawLine(tip, QPointF(x + 30, y - 84))
        # A subtle forward spatial order remains visible with no labels.
        painter.setPen(QPen(QColor(109, 136, 151, 80), 2))
        painter.drawLine(QPointF(left_x, y + 78), QPointF(right_x, y + 78))
    else:
        painter.end()
        raise GroundTruthGraphicsError("UNSUPPORTED_DRAW_UNIT:" + unit_id)

    painter.end()
    if not image.save(str(path), "PNG"):
        raise GroundTruthGraphicsError("FRAME_WRITE_FAILED:" + str(path))


def render_graphic(
    repo_root: Path,
    unit_id: str,
    output_path: Path,
    receipt_path: Path,
) -> dict[str, Any]:
    repo = Path(repo_root).resolve()
    truth = validate_ground_truth(repo, unit_id)
    duration = float(truth["duration_seconds"])
    output = Path(output_path).resolve()
    receipt = Path(receipt_path).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    receipt.parent.mkdir(parents=True, exist_ok=True)

    if output.is_file() and receipt.is_file():
        prior = _read(receipt)
        if (
            prior.get("schema_version") == "siraj-ep002-ground-truth-local-graphics-v5"
            and prior.get("status") == "PASS"
            and prior.get("unit_id") == unit_id
            and prior.get("output_sha256") == _sha256(output)
            and prior.get("authored_graphics_spec_sha256") == truth["authored_graphics_spec_sha256"]
            and prior.get("source_ids") == truth["source_ids"]
        ):
            return prior

    # QPainter can create raster images without a window, but a QGuiApplication
    # is required for deterministic font discovery/shaping (SH-040 Arabic).
    from PySide6.QtGui import QGuiApplication
    app = QGuiApplication.instance()
    if app is None:
        app = QGuiApplication([])

    fps = 24
    ffmpeg = _ffmpeg(repo)
    with tempfile.TemporaryDirectory(prefix="siraj_ep002_gfx_v5_") as temp:
        frames = Path(temp)
        frame_count = max(1, int(math.ceil(duration * fps)))
        for index in range(frame_count):
            t = min(duration, index / fps)
            _draw_frame(unit_id, t, duration, frames / f"frame-{index:05d}.png")
        command = [
            str(ffmpeg), "-hide_banner", "-loglevel", "error", "-y",
            "-framerate", str(fps), "-i", str(frames / "frame-%05d.png"),
            "-t", f"{duration:.6f}", "-an", "-c:v", "libx264",
            "-preset", "medium", "-crf", "17", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", str(output),
        ]
        process = subprocess.run(
            command,
            cwd=str(repo),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3600,
        )
        if process.returncode != 0:
            raise GroundTruthGraphicsError(
                "LOCAL_GRAPHICS_FFMPEG_FAILED:" + unit_id + ":" + process.stderr[-3000:]
            )
    if not output.is_file() or output.stat().st_size <= 0:
        raise GroundTruthGraphicsError("LOCAL_GRAPHICS_OUTPUT_MISSING:" + unit_id)

    probe = _ffprobe(repo)
    observed_duration = None
    if probe is not None:
        process = subprocess.run(
            [str(probe), "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(output)],
            cwd=str(repo), capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60,
        )
        if process.returncode != 0:
            raise GroundTruthGraphicsError("LOCAL_GRAPHICS_FFPROBE_FAILED:" + unit_id)
        observed_duration = float(process.stdout.strip())
        if abs(observed_duration - duration) > 0.15:
            raise GroundTruthGraphicsError(
                "LOCAL_GRAPHICS_DURATION_MISMATCH:" + unit_id + ":" + str(observed_duration)
            )

    payload = {
        "schema_version": "siraj-ep002-ground-truth-local-graphics-v5",
        "release": "SIRAJ_EP002_GROUND_TRUTH_FINALIZATION_RELEASE_V5",
        "status": "PASS",
        "episode_id": EPISODE_ID,
        "unit_id": unit_id,
        "shot_id": truth["unit"]["shot_id"],
        "duration_seconds": duration,
        "observed_duration_seconds": observed_duration,
        "output_path_relative": str(output.relative_to(repo)).replace("\\", "/"),
        "output_sha256": _sha256(output),
        "renderer": "PYSIDE6_QPAINTER_PLUS_FFMPEG",
        "render_policy": "AUTHORED_SEMANTICS_PRESERVED_NO_GENERATIVE_MODEL",
        "binding_mode": truth["binding_mode"],
        "binding_reason": truth["binding_reason"],
        "source_ids": truth["source_ids"],
        "canonical_research_path": truth["research_path"],
        "canonical_research_sha256": truth["research_sha256"],
        "canonical_prompt_path": truth["prompt_path"],
        "canonical_prompt_sha256": truth["prompt_sha256"],
        "authored_graphics_spec": truth["authored_graphics_spec"],
        "authored_graphics_spec_sha256": truth["authored_graphics_spec_sha256"],
        "provider_calls": 0,
        "paid_calls": 0,
        "automatic_paid_retry": False,
        "automatic_paid_resubmission": False,
    }
    _atomic_json(receipt, payload)
    return payload


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--unit", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    args = parser.parse_args()
    result = render_graphic(args.repo, args.unit, args.output, args.receipt)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
