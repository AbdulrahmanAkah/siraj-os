"""Single source of truth for the PR01 technical delivery profile.

The JSON profile is authoritative.  This module exposes read-only constants
for older local runtime modules without reproducing delivery numbers in each
module.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


PROFILE_REL = Path("config/technical_delivery/siraj_technical_delivery_profile_v1.json")


def load_delivery_profile(repo_root: Path | None = None) -> dict[str, Any]:
    root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve()
    return json.loads((root / PROFILE_REL).read_text(encoding="utf-8-sig"))


_PROFILE = load_delivery_profile()
_AUDIO = _PROFILE["audio_delivery"]

TARGET_INTEGRATED_LOUDNESS_LUFS = float(_AUDIO["target_integrated_loudness_lufs"])
PASS_LOUDNESS_MIN_LUFS = float(_AUDIO["pass_loudness_min_lufs"])
PASS_LOUDNESS_MAX_LUFS = float(_AUDIO["pass_loudness_max_lufs"])
TARGET_TRUE_PEAK_DBTP = float(_AUDIO["target_true_peak_dbtp"])
TRUE_PEAK_CEILING_DBTP = float(_AUDIO["true_peak_ceiling_dbtp"])
LOUDNESS_RANGE_LU = float(_AUDIO["loudness_range_lu"])
NARRATION_TARGET_LUFS = float(_AUDIO["narration_target_lufs"])
SAMPLE_RATE_HZ = int(_AUDIO["sample_rate_hz"])
CHANNEL_POLICY = str(_AUDIO["channel_policy"])
