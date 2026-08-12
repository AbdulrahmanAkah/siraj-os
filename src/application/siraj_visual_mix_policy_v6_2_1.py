"""Historical V6.2.1 visual-mix policy retained for forensic compatibility.

This module is not the active production policy.  Canonical planning and
pre-spend execution use ``siraj_cinematic_media_mix_policy_v2``; the legacy
constants remain import-compatible for old fixture tests and reports only.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
from pathlib import Path
from typing import Any

POLICY_SCHEMA = "siraj-visual-mix-duplicate-policy-v6.2.1"
LEGACY_POLICY_ACTIVE = False

# Creative policy requested by the human owner:
# generated video may occupy at most two thirds of the final episode timeline.
MAX_GENERATED_VIDEO_RATIO = 2.0 / 3.0
MIN_NON_GENERATED_VIDEO_RATIO = 1.0 / 3.0

# This is NOT a creative scene-duration limit.
# It is the current transport compatibility fallback inherited from the
# existing Runware/Veo integration. A long scene is represented by multiple
# distinct progressive subshots under one scene_continuity_id.
PROVIDER_REQUEST_FALLBACK_MAX_SECONDS = 8.0

PROMPT_NEAR_DUPLICATE_THRESHOLD = 0.92
SEMANTIC_NEAR_DUPLICATE_THRESHOLD = 0.94

# Perceptual gate is intentionally conservative: it catches exact/near exact
# visual reuse without over-penalizing legitimate continuity.
PERCEPTUAL_HASH_MAX_AVG_HAMMING = 3.0
PERCEPTUAL_HASH_MAX_SAMPLE_HAMMING = 4

SERIES_POLICY_REL = Path(
    "projects/_series/siraj-visual-mix-duplicate-policy-v6.2.1.json"
)


@dataclass(frozen=True, slots=True)
class VisualMixPolicy:
    schema_version: str = POLICY_SCHEMA
    status: str = "ACTIVE"
    generated_video_max_ratio: float = MAX_GENERATED_VIDEO_RATIO
    non_generated_video_min_ratio: float = MIN_NON_GENERATED_VIDEO_RATIO
    provider_request_fallback_max_seconds: float = (
        PROVIDER_REQUEST_FALLBACK_MAX_SECONDS
    )
    provider_request_limit_is_creative_scene_limit: bool = False
    long_scene_via_progressive_subshots: bool = True
    generated_asset_default_reuse: str = "FORBIDDEN"
    explicit_reuse_justification_required: bool = True
    automatic_paid_regeneration_on_duplicate: bool = False
    prompt_duplicate_gate: bool = True
    semantic_duplicate_gate: bool = True
    perceptual_duplicate_gate: bool = True
    adjacent_shot_duplicate_gate: bool = True
    exact_asset_sha_duplicate_gate: bool = True
    automatic_paid_retry: bool = False

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def write_series_policy(repo_root: Path) -> Path:
    repo = Path(repo_root).resolve()
    path = repo / SERIES_POLICY_REL
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            VisualMixPolicy().as_dict(),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path
