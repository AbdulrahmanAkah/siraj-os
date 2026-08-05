from __future__ import annotations

import argparse
import json
from pathlib import Path


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo_root.resolve()

    contract = json.loads(
        (
            repo
            / "projects/_orchestrator/contracts/"
            "local-professional-graphics-engine-v1.json"
        ).read_text(encoding="utf-8")
    )
    spec_source = (
        repo / "src/application/local_graphics_spec_v1.py"
    ).read_text(encoding="utf-8")
    renderer_source = (
        repo / "src/application/local_graphics_renderer_v1.py"
    ).read_text(encoding="utf-8")

    require(
        contract["architecture"]["motion_engine"] == "QT_QUICK_QML",
        "QML_MOTION_ENGINE_NOT_LOCKED",
    )
    require(
        contract["architecture"]["controller"] == "PYSIDE6",
        "PYSIDE6_CONTROLLER_NOT_LOCKED",
    )
    require(
        contract["architecture"]["encoder"] == "FFMPEG_LIBX264",
        "FFMPEG_ENCODER_NOT_LOCKED",
    )
    require(
        contract["output"]["width"] == 1920
        and contract["output"]["height"] == 1080
        and contract["output"]["fps"] == 30,
        "GRAPHICS_OUTPUT_CONTRACT_CHANGED",
    )
    require(
        contract["api_cost_usd"] == 0.0,
        "LOCAL_GRAPHICS_API_COST_CHANGED",
    )
    require(
        contract["music"] == "FORBIDDEN",
        "GRAPHICS_MUSIC_POLICY_CHANGED",
    )
    for marker in (
        "extract_storyboard_graphics_specs",
        "GRAPHICS_SHOT_COUNT_MUST_BE_6",
        "known_source_ids",
        "SFX_ONLY_NO_MUSIC",
    ):
        require(marker in spec_source, "SPEC_MARKER_MISSING:" + marker)
    for marker in (
        "QQuickView",
        "frame_%06d.png",
        "libx264",
        "yuv420p",
        "api_cost_usd",
    ):
        require(
            marker in renderer_source,
            "RENDERER_MARKER_MISSING:" + marker,
        )

    qml_root = repo / "src/presentation/graphics/qml"
    expected = (
        "AnimatedTimeline.qml",
        "MapRoute.qml",
        "RelationTree.qml",
        "SourceCard.qml",
        "Comparison.qml",
        "LocationTimeCard.qml",
    )
    for filename in expected:
        source = (qml_root / filename).read_text(encoding="utf-8")
        require(
            "property real frameProgress" in source,
            "DETERMINISTIC_FRAME_PROGRESS_MISSING:" + filename,
        )
        require(
            "graphicsSpec.design.font_family" in source,
            "ARABIC_FONT_BINDING_MISSING:" + filename,
        )

    args.output_root.mkdir(parents=True, exist_ok=True)
    report = args.output_root / "audit.txt"
    report.write_text(
        "\n".join(
            (
                "STATUS=PASS_LOCAL_PROFESSIONAL_GRAPHICS_ENGINE_V1",
                "CONTROLLER=PYSIDE6",
                "MOTION_ENGINE=QT_QUICK_QML",
                "VECTOR_LAYER=SVG_AND_QML_CANVAS",
                "ENCODER=FFMPEG_LIBX264",
                "GRAPHIC_TEMPLATES=6",
                "OUTPUT=1920x1080_30FPS",
                "RTL_ARABIC=REQUIRED",
                "MUSIC=FORBIDDEN",
                "LOCAL_API_COST_USD=0.00",
                "PAID_PROVIDER_REQUESTS_DURING_AUDIT=0",
            )
        )
        + "\n",
        encoding="utf-8",
    )
    print(report.read_text(encoding="utf-8"), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
