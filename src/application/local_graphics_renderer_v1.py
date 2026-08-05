from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from src.application.local_graphics_spec_v1 import (
    FPS,
    HEIGHT,
    RELEASE,
    WIDTH,
    LocalGraphicsSpec,
    load_graphics_spec,
    validate_graphics_spec,
)

QML_ROOT_REL = Path("src/presentation/graphics/qml")
TEMPLATE_BY_TYPE = {
    "ANIMATED_TIMELINE": "AnimatedTimeline.qml",
    "MAP_ROUTE": "MapRoute.qml",
    "RELATION_TREE": "RelationTree.qml",
    "SOURCE_CARD": "SourceCard.qml",
    "COMPARISON": "Comparison.qml",
    "LOCATION_TIME_CARD": "LocationTimeCard.qml",
}


class LocalGraphicsRenderError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class GraphicsEnvironment:
    pyside6_ready: bool
    qt_quick_ready: bool
    ffmpeg_path: Path | None
    ffmpeg_version_line: str
    qml_root: Path
    missing_templates: tuple[str, ...]

    @property
    def render_ready(self) -> bool:
        return (
            self.pyside6_ready
            and self.qt_quick_ready
            and self.ffmpeg_path is not None
            and not self.missing_templates
        )


@dataclass(frozen=True, slots=True)
class LocalGraphicsRenderResult:
    graphic_id: str
    shot_id: str
    graphic_type: str
    output_path: Path
    output_sha256: str
    duration_seconds: float
    frame_count: int
    width: int
    height: int
    fps: int
    ffmpeg_path: Path
    receipt_path: Path


def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat().replace(
        "+00:00",
        "Z",
    )


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _atomic_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(temporary, path)


def _ffmpeg_candidate() -> Path | None:
    configured = os.environ.get("SIRAJ_FFMPEG_EXE", "").strip()
    if configured:
        path = Path(configured)
        if path.is_file():
            return path.resolve()
    found = shutil.which("ffmpeg")
    return Path(found).resolve() if found else None


def inspect_graphics_environment(
    repo_root: Path,
) -> GraphicsEnvironment:
    pyside6_ready = False
    qt_quick_ready = False
    try:
        import PySide6  # noqa: F401
        pyside6_ready = True
        from PySide6.QtQml import QQmlEngine  # noqa: F401
        from PySide6.QtQuick import QQuickView  # noqa: F401
        qt_quick_ready = True
    except ImportError:
        pass

    ffmpeg = _ffmpeg_candidate()
    version_line = ""
    if ffmpeg is not None:
        process = subprocess.run(
            [str(ffmpeg), "-version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if process.returncode == 0:
            version_line = (
                process.stdout.splitlines()[0]
                if process.stdout.splitlines()
                else ""
            )
        else:
            ffmpeg = None

    qml_root = repo_root.resolve() / QML_ROOT_REL
    missing = tuple(
        filename
        for filename in TEMPLATE_BY_TYPE.values()
        if not (qml_root / filename).is_file()
    )
    return GraphicsEnvironment(
        pyside6_ready=pyside6_ready,
        qt_quick_ready=qt_quick_ready,
        ffmpeg_path=ffmpeg,
        ffmpeg_version_line=version_line,
        qml_root=qml_root,
        missing_templates=missing,
    )


def require_graphics_environment(
    repo_root: Path,
) -> GraphicsEnvironment:
    environment = inspect_graphics_environment(repo_root)
    errors: list[str] = []
    if not environment.pyside6_ready:
        errors.append("PYSIDE6_NOT_AVAILABLE")
    if not environment.qt_quick_ready:
        errors.append("QT_QUICK_NOT_AVAILABLE")
    if environment.ffmpeg_path is None:
        errors.append("FFMPEG_NOT_AVAILABLE")
    if environment.missing_templates:
        errors.append(
            "QML_TEMPLATES_MISSING:"
            + ",".join(environment.missing_templates)
        )
    if errors:
        raise LocalGraphicsRenderError(
            "GRAPHICS_ENVIRONMENT_NOT_READY:"
            + "|".join(errors)
        )
    return environment


def build_ffmpeg_command(
    ffmpeg_path: Path,
    frame_directory: Path,
    output_path: Path,
    *,
    fps: int = FPS,
) -> list[str]:
    return [
        str(ffmpeg_path),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-framerate",
        str(fps),
        "-start_number",
        "0",
        "-i",
        str(frame_directory / "frame_%06d.png"),
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "16",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def _render_png_frames(
    spec: LocalGraphicsSpec,
    qml_path: Path,
    frame_directory: Path,
) -> None:
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ.setdefault("QSG_RHI_BACKEND", "software")

    from PySide6.QtCore import QUrl
    from PySide6.QtGui import QGuiApplication
    from PySide6.QtQuick import QQuickView

    app = QGuiApplication.instance()
    owns_app = app is None
    if app is None:
        app = QGuiApplication(
            ["siraj-local-professional-graphics-engine-v1"]
        )

    view = QQuickView()
    try:
        try:
            view.setResizeMode(
                QQuickView.ResizeMode.SizeRootObjectToView
            )
        except AttributeError:
            view.setResizeMode(QQuickView.SizeRootObjectToView)

        view.rootContext().setContextProperty(
            "graphicsSpec",
            spec.payload,
        )
        view.setSource(QUrl.fromLocalFile(str(qml_path.resolve())))
        if view.status() == QQuickView.Status.Error:
            messages = "; ".join(
                error.toString()
                for error in view.errors()
            )
            raise LocalGraphicsRenderError(
                "QML_TEMPLATE_LOAD_FAILED:" + messages
            )
        view.resize(WIDTH, HEIGHT)
        view.show()
        for _ in range(4):
            app.processEvents()

        root = view.rootObject()
        if root is None:
            raise LocalGraphicsRenderError(
                "QML_ROOT_OBJECT_MISSING"
            )

        frame_directory.mkdir(parents=True, exist_ok=True)
        frame_count = spec.frame_count
        denominator = max(1, frame_count - 1)
        for frame_index in range(frame_count):
            progress = frame_index / denominator
            root.setProperty("frameProgress", progress)
            root.setProperty("frameIndex", frame_index)
            for _ in range(2):
                app.processEvents()
            image = view.grabWindow()
            if image.isNull():
                raise LocalGraphicsRenderError(
                    f"QML_FRAME_CAPTURE_FAILED:{frame_index}"
                )
            path = frame_directory / f"frame_{frame_index:06d}.png"
            if not image.save(str(path), "PNG"):
                raise LocalGraphicsRenderError(
                    f"QML_FRAME_SAVE_FAILED:{frame_index}"
                )
    finally:
        view.close()
        if owns_app:
            app.quit()


def render_graphic(
    repo_root: Path,
    spec_input: LocalGraphicsSpec | Mapping[str, Any] | Path,
    output_path: Path,
    *,
    keep_frames: bool = False,
    receipt_path: Path | None = None,
) -> LocalGraphicsRenderResult:
    if isinstance(spec_input, LocalGraphicsSpec):
        spec = spec_input
    elif isinstance(spec_input, Path):
        spec = load_graphics_spec(spec_input)
    else:
        spec = validate_graphics_spec(spec_input)

    environment = require_graphics_environment(repo_root)
    template_name = TEMPLATE_BY_TYPE.get(spec.graphic_type)
    if template_name is None:
        raise LocalGraphicsRenderError(
            f"GRAPHICS_TEMPLATE_NOT_MAPPED:{spec.graphic_type}"
        )
    qml_path = environment.qml_root / template_name
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temporary_root = Path(
        tempfile.mkdtemp(
            prefix=f"siraj-{spec.graphic_id.lower()}-frames-",
            dir=str(output_path.parent),
        )
    )
    try:
        _render_png_frames(
            spec,
            qml_path,
            temporary_root,
        )
        command = build_ffmpeg_command(
            environment.ffmpeg_path,
            temporary_root,
            output_path,
        )
        process = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        if process.returncode != 0:
            raise LocalGraphicsRenderError(
                "FFMPEG_GRAPHICS_ENCODE_FAILED:"
                + process.stderr[-2000:]
            )
        if not output_path.is_file() or output_path.stat().st_size <= 0:
            raise LocalGraphicsRenderError(
                "GRAPHICS_OUTPUT_MISSING_OR_EMPTY"
            )

        output_hash = _sha256(output_path)
        resolved_receipt = (
            receipt_path.resolve()
            if receipt_path is not None
            else output_path.with_suffix(".receipt.json")
        )
        receipt = {
            "schema_version": "siraj-local-graphics-render-receipt-v1",
            "release": RELEASE,
            "graphic_id": spec.graphic_id,
            "shot_id": spec.shot_id,
            "graphic_type": spec.graphic_type,
            "status": "PASS",
            "renderer": {
                "controller": "PYSIDE6",
                "motion_engine": "QT_QUICK_QML",
                "vector_layer": "SVG_AND_QML_CANVAS",
                "encoder": "FFMPEG_LIBX264",
            },
            "output_path": str(output_path),
            "output_sha256": output_hash,
            "duration_seconds": spec.duration_seconds,
            "frame_count": spec.frame_count,
            "width": WIDTH,
            "height": HEIGHT,
            "fps": FPS,
            "music": "FORBIDDEN",
            "api_cost_usd": 0.0,
            "ffmpeg_path": str(environment.ffmpeg_path),
            "ffmpeg_version_line": environment.ffmpeg_version_line,
            "created_at_utc": _now_utc(),
        }
        _atomic_json(resolved_receipt, receipt)
        return LocalGraphicsRenderResult(
            graphic_id=spec.graphic_id,
            shot_id=spec.shot_id,
            graphic_type=spec.graphic_type,
            output_path=output_path,
            output_sha256=output_hash,
            duration_seconds=spec.duration_seconds,
            frame_count=spec.frame_count,
            width=WIDTH,
            height=HEIGHT,
            fps=FPS,
            ffmpeg_path=environment.ffmpeg_path,
            receipt_path=resolved_receipt,
        )
    finally:
        if not keep_frames:
            shutil.rmtree(temporary_root, ignore_errors=True)


def environment_report(
    repo_root: Path,
) -> dict[str, Any]:
    value = inspect_graphics_environment(repo_root)
    return {
        "schema_version": "siraj-local-graphics-environment-v1",
        "release": RELEASE,
        "pyside6_ready": value.pyside6_ready,
        "qt_quick_ready": value.qt_quick_ready,
        "ffmpeg_ready": value.ffmpeg_path is not None,
        "ffmpeg_path": (
            str(value.ffmpeg_path)
            if value.ffmpeg_path is not None
            else None
        ),
        "ffmpeg_version_line": value.ffmpeg_version_line,
        "qml_root": str(value.qml_root),
        "missing_templates": list(value.missing_templates),
        "render_ready": value.render_ready,
    }
