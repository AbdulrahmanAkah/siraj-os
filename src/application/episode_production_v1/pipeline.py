"""Composition helpers for an episode-production run.

AVAILABLE is assigned only when a caller supplies a Python-callable adapter.
No provider client is constructed here.
"""
from __future__ import annotations

from dataclasses import replace
from typing import Any

from src.application.episode_orchestration_v1.runtime import build_default_stage_registry


def build_episode_production_registry(*, runners: dict[str, Any]) -> tuple[Any, ...]:
    """Promote only supplied adapters; leave every other registry fact unchanged."""
    result = []
    for stage in build_default_stage_registry():
        if stage.stage_id not in runners:
            result.append(stage)
            continue
        external = stage.stage_id in {"narrative_script", "production_tts", "visual_provider", "video_provider"}
        result.append(replace(
            stage, runner=f"episode_production_v1:{stage.stage_id}", external_provider_required=external,
            current_implementation_status="AVAILABLE_EXTERNAL_ADAPTER" if external else "AVAILABLE_LOCAL_ADAPTER",
        ))
    return tuple(result)


def composed_runners(*, narrative: Any | None = None, tts: Any | None = None, subtitles: Any | None = None, storyboard: Any | None = None, visual: Any | None = None, video: Any | None = None, render: Any | None = None) -> dict[str, Any]:
    values = {"narrative_script": narrative, "production_tts": tts, "subtitles": subtitles, "storyboard": storyboard, "visual_provider": visual, "video_provider": video, "render": render}
    return {stage_id: adapter.run for stage_id, adapter in values.items() if adapter is not None and callable(getattr(adapter, "run", None))}
