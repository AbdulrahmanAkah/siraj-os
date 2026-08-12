"""Runware request contract normalization for SIRAJ V6.6 R9."""
from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping

VEO_31_MODELS = {
    "google:veo@3.1-lite",
    "google:3@2",
    "google:3@3",
}


def is_veo_31_model(model: Any) -> bool:
    value = str(model or "").strip().lower()
    return value in VEO_31_MODELS or value.startswith("google:veo@3.1")


def sanitize_runware_task_for_submission(task: Mapping[str, Any]) -> dict[str, Any]:
    """Return provider-valid task without mutating the queue draft.

    Veo 3.1 family uses a single positivePrompt field in Runware's model
    contract. SIRAJ may retain negative constraints internally for QA and
    duplicate/text-safety checks, but the unsupported negativePrompt field is
    never sent to Veo. The constraints are folded into positivePrompt text so
    the creative intent is not discarded.
    """
    value = deepcopy(dict(task))
    if not is_veo_31_model(value.get("model")):
        return value

    negatives: list[str] = []
    for key in ("negativePrompt", "negative_prompt", "videoNegativePrompt"):
        raw = value.pop(key, None)
        if isinstance(raw, str) and raw.strip():
            negatives.append(raw.strip())

    if negatives:
        positive = str(value.get("positivePrompt") or "").strip()
        constraint = " ; ".join(negatives)
        suffix = (
            "\n\nVisual exclusion constraints for this shot: do not show or introduce "
            + constraint
            + "."
        )
        if suffix.strip() not in positive:
            value["positivePrompt"] = positive + suffix

    return value
