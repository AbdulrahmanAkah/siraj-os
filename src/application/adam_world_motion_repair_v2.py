"""Repair Adam world domains, motion treatment, and narration handoff."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Any, Mapping, Sequence


VIDEO_TARGET_USD = 30.0
VIDEO_HARD_CAP_USD = 35.0
OBSERVED_VIDEO_COST_PER_SECOND_USD = 5.3 / 160.0
PROVIDER_CLIP_SECONDS = 8

HEAVENLY_SEQUENCES = frozenset(
    {
        "SEQ-01",
        "SEQ-03",
        "SEQ-04",
        "SEQ-06",
        "SEQ-07",
        "SEQ-08",
        "SEQ-09",
        "SEQ-10",
        "SEQ-11",
        "SEQ-12",
        "SEQ-13",
        "SEQ-14",
    }
)
TRANSITIONAL_SEQUENCES = frozenset({"SEQ-02"})
EARTHLY_SEQUENCES = frozenset({"SEQ-05"})

MOTION_TERMS = (
    "يتغير",
    "يتغيّر",
    "يتشقق",
    "يتشقّق",
    "يجف",
    "يجفّ",
    "يصير كالفخار",
    "يتكوّن",
    "يتكون",
    "يتشكّل",
    "يتشكل",
    "يتحوّل",
    "يتحول",
    "تتجمع",
    "تتشكّل",
    "تتشكل",
    "ينفتح",
    "ينغلق",
    "يهبط",
    "يصعد",
    "يتحرك",
    "تتحرك",
    "formation",
    "transform",
    "crack",
    "drying",
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!؟؛:])\s+|\n+")


class AdamWorldMotionRepairError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class RepairResult:
    storyboard: dict[str, Any]
    production_plan: dict[str, Any]
    visual_summary: dict[str, Any]


def _shot_text(shot: Mapping[str, Any]) -> str:
    return " ".join(
        str(shot.get(key) or "")
        for key in (
            "label_ar",
            "dramatic_function_ar",
            "visual_brief_ar",
            "runware_positive_prompt_en",
            "camera_motion_ar",
        )
    ).lower()


def _duration(shot: Mapping[str, Any]) -> int:
    for key in (
        "planned_seconds",
        "editorial_duration_seconds",
        "duration_seconds",
    ):
        try:
            value = int(round(float(shot.get(key, 0))))
        except (TypeError, ValueError):
            continue
        if value > 0:
            return value
    raise AdamWorldMotionRepairError(
        f"SHOT_DURATION_REQUIRED:{shot.get('shot_id')}"
    )


def _requires_motion(shot: Mapping[str, Any]) -> bool:
    treatment = str(
        shot.get("final_budget_treatment")
        or shot.get("treatment")
        or ""
    ).upper()
    if treatment in {
        "AUTHORED_GRAPHICS",
        "GRAPHICS",
        "DOCUMENT_OR_MAP",
        "DOCUMENT",
        "MAP",
    }:
        return False
    if str(shot.get("motion_necessity") or "").upper() == "REQUIRED":
        return True
    text = _shot_text(shot)
    return any(term in text for term in MOTION_TERMS)


def _domain_for_sequence(sequence_id: str) -> tuple[str, str, str]:
    if sequence_id in HEAVENLY_SEQUENCES:
        return (
            "HEAVENLY_UNSEEN_SYMBOLIC",
            "SYMBOLIC_UNSEEN",
            "SYMBOLIC_NON_DEFINITIVE",
        )
    if sequence_id in TRANSITIONAL_SEQUENCES:
        return (
            "TRANSITIONAL_REALM",
            "ABSTRACT",
            "SYMBOLIC_NON_DEFINITIVE",
        )
    if sequence_id in EARTHLY_SEQUENCES:
        return (
            "EARTHLY_WORLD",
            "EVIDENCE_BASED_RECONSTRUCTION",
            "EVIDENCE_BASED",
        )
    raise AdamWorldMotionRepairError(
        f"UNMAPPED_ADAM_SEQUENCE_DOMAIN:{sequence_id}"
    )


def _character_location(
    sequence_id: str,
    shot: Mapping[str, Any],
) -> str:
    text = _shot_text(shot)
    if sequence_id == "SEQ-05":
        return (
            "ADAM_EARTHLY_MATERIAL_FORMATION"
            if any(term in text for term in ("آدم", "الطين", "الفخار", "جوف"))
            else "NONE"
        )
    if sequence_id in HEAVENLY_SEQUENCES:
        if any(
            term in text
            for term in (
                "آدم",
                "السجود",
                "الأسماء",
                "الجنة",
                "الشجرة",
                "الزوج",
                "الميثاق",
                "الحمد",
            )
        ):
            return "ADAM_IN_HEAVEN_SYMBOLIC"
        return "NONE"
    return "NONE"


def _negative_prompt_for_unseen(value: str) -> str:
    additions = (
        " ordinary earthly valley, familiar terrestrial geography,"
        " blue daytime sky, visible sun as the light source,"
        " tourist landscape, ordinary Earth mountains,"
        " literal depiction of the unseen realm"
    )
    text = str(value or "").strip()
    if "ordinary earthly valley" not in text:
        text = (text.rstrip(", ") + "," + additions).strip(", ")
    return text


def _dynamic_still_fields(duration: int) -> dict[str, Any]:
    panels = max(1, math.ceil(duration / 6.0))
    return {
        "final_budget_treatment": "DYNAMIC_STILL_SEQUENCE",
        "planned_generated_video_seconds": 0,
        "estimated_generated_video_cost_usd": 0.0,
        "provider_clip_seconds": 0,
        "provider_clip_count": 0,
        "still_panel_count": panels,
        "maximum_still_panel_seconds": round(duration / panels, 3),
        "motion_profile": "LAYERED_PARALLAX_MULTI_AXIS",
    }


def _video_fields(duration: int) -> dict[str, Any]:
    return {
        "final_budget_treatment": "GENERATED_VIDEO",
        "planned_generated_video_seconds": duration,
        "estimated_generated_video_cost_usd": round(
            duration * OBSERVED_VIDEO_COST_PER_SECOND_USD,
            6,
        ),
        "provider_clip_seconds": PROVIDER_CLIP_SECONDS,
        "provider_clip_count": max(
            1,
            math.ceil(duration / PROVIDER_CLIP_SECONDS),
        ),
        "still_panel_count": 0,
        "maximum_still_panel_seconds": 0,
        "motion_profile": "GENERATED_CONTINUOUS_MOTION",
    }


def _video_spend(shots: Sequence[Mapping[str, Any]]) -> float:
    return round(
        sum(
            float(shot.get("estimated_generated_video_cost_usd", 0) or 0)
            for shot in shots
            if str(shot.get("final_budget_treatment")) == "GENERATED_VIDEO"
        ),
        6,
    )


def _video_seconds(shots: Sequence[Mapping[str, Any]]) -> int:
    return sum(
        int(shot.get("planned_generated_video_seconds", 0) or 0)
        for shot in shots
        if str(shot.get("final_budget_treatment")) == "GENERATED_VIDEO"
    )


def repair_visual_plan(
    storyboard: Mapping[str, Any],
    production_plan: Mapping[str, Any],
) -> RepairResult:
    raw_story = storyboard.get("shots")
    raw_plan = production_plan.get("shots")
    if not isinstance(raw_story, list) or not isinstance(raw_plan, list):
        raise AdamWorldMotionRepairError("SHOT_LISTS_REQUIRED")
    if len(raw_story) != len(raw_plan):
        raise AdamWorldMotionRepairError(
            "STORYBOARD_PLAN_SHOT_COUNT_MISMATCH"
        )

    story_shots: list[dict[str, Any]] = []
    plan_shots: list[dict[str, Any]] = []
    sh023_found = False

    for index, (story_raw, plan_raw) in enumerate(
        zip(raw_story, raw_plan, strict=True),
        start=1,
    ):
        if not isinstance(story_raw, Mapping) or not isinstance(plan_raw, Mapping):
            raise AdamWorldMotionRepairError(
                f"SHOT_OBJECT_REQUIRED:{index}"
            )
        story = dict(story_raw)
        plan = dict(plan_raw)
        sequence_id = str(
            story.get("sequence_id") or plan.get("sequence_id") or ""
        )
        domain, representation, claim = _domain_for_sequence(sequence_id)
        location = _character_location(sequence_id, story)
        duration = _duration(story)

        shared = {
            "scene_domain": domain,
            "representation_mode": representation,
            "representation_claim": claim,
            "character_location": location,
            "earthly_visual_default": False,
        }
        if index > 1:
            previous_sequence = str(
                raw_story[index - 2].get("sequence_id")
                if isinstance(raw_story[index - 2], Mapping)
                else ""
            )
            if previous_sequence != sequence_id:
                shared["location_transition"] = (
                    "EDITORIALLY_PLANNED_SEQUENCE_TRANSITION"
                )

        story.update(shared)
        plan.update(shared)

        if domain == "HEAVENLY_UNSEEN_SYMBOLIC":
            story["runware_negative_prompt_en"] = (
                _negative_prompt_for_unseen(
                    str(story.get("runware_negative_prompt_en") or "")
                )
            )
            story["unseen_visual_direction_v2"] = (
                "Non-earthly scale, source-less light, suspended spatial layers, "
                "no familiar terrestrial horizon; symbolic and non-definitive."
            )

        shot_id = str(story.get("shot_id") or "")
        if shot_id == "SH-023":
            sh023_found = True

        if _requires_motion(story):
            story["motion_necessity"] = "REQUIRED"
            plan["motion_necessity"] = "REQUIRED"
            story.update(_video_fields(duration))
            plan.update(_video_fields(duration))

        story_shots.append(story)
        plan_shots.append(plan)

    if not sh023_found:
        raise AdamWorldMotionRepairError("SH_023_NOT_FOUND")

    spend = _video_spend(story_shots)
    if spend > VIDEO_TARGET_USD + 1e-9:
        candidates: list[tuple[int, int, int]] = []
        for index, shot in enumerate(story_shots):
            if str(shot.get("final_budget_treatment")) != "GENERATED_VIDEO":
                continue
            if _requires_motion(shot):
                continue
            if str(shot.get("shot_id")) == "SH-023":
                continue
            priority = int(shot.get("video_priority_v2", 50) or 50)
            candidates.append((priority, -_duration(shot), index))
        candidates.sort()
        for _, _, index in candidates:
            duration = _duration(story_shots[index])
            replacement = _dynamic_still_fields(duration)
            story_shots[index].update(replacement)
            plan_shots[index].update(replacement)
            spend = _video_spend(story_shots)
            if spend <= VIDEO_TARGET_USD + 1e-9:
                break

    spend = _video_spend(story_shots)
    if spend > VIDEO_HARD_CAP_USD + 1e-9:
        raise AdamWorldMotionRepairError(
            f"VIDEO_HARD_CAP_EXCEEDED:{spend:.6f}"
        )

    remaining_motion_issues = [
        str(shot.get("shot_id"))
        for shot in story_shots
        if _requires_motion(shot)
        and str(shot.get("final_budget_treatment")) != "GENERATED_VIDEO"
    ]
    if remaining_motion_issues:
        raise AdamWorldMotionRepairError(
            "MOTION_REQUIRED_NOT_VIDEO:"
            + ",".join(remaining_motion_issues)
        )

    treatment_counts = Counter(
        str(shot.get("final_budget_treatment") or "MISSING")
        for shot in story_shots
    )
    domain_counts = Counter(
        str(shot.get("scene_domain") or "MISSING")
        for shot in story_shots
    )
    max_panel = max(
        (
            float(shot.get("maximum_still_panel_seconds", 0) or 0)
            for shot in story_shots
            if str(shot.get("final_budget_treatment"))
            == "DYNAMIC_STILL_SEQUENCE"
        ),
        default=0.0,
    )

    updated_storyboard = dict(storyboard)
    updated_storyboard["shots"] = story_shots
    updated_storyboard["status"] = (
        "V2_WORLD_AND_MOTION_REPAIR_READY_FOR_HUMAN_REVIEW"
    )
    updated_storyboard["generated_video_budget"] = {
        "target_usd": VIDEO_TARGET_USD,
        "hard_cap_usd": VIDEO_HARD_CAP_USD,
        "estimated_cost_per_second_usd": round(
            OBSERVED_VIDEO_COST_PER_SECOND_USD,
            9,
        ),
        "estimated_spend_usd": spend,
        "planned_generated_video_seconds": _video_seconds(story_shots),
        "seconds_target": "NONE_COST_AND_QUALITY_DRIVEN",
    }

    updated_plan = dict(production_plan)
    updated_plan["shots"] = plan_shots
    updated_plan["status"] = (
        "V2_WORLD_AND_MOTION_REPAIR_READY_FOR_HUMAN_REVIEW"
    )
    updated_plan["treatment_counts"] = dict(
        sorted(treatment_counts.items())
    )
    updated_plan["generated_video_budget"] = dict(
        updated_storyboard["generated_video_budget"]
    )
    updated_plan["next_stage"] = (
        "ARABIC_PERFORMANCE_SCRIPT_V2_AND_HUMAN_VISUAL_REVIEW"
    )

    summary = {
        "schema_version": "siraj-adam-world-motion-repair-summary-v2",
        "status": "PASS_READY_FOR_HUMAN_VISUAL_REVIEW",
        "shot_count": len(story_shots),
        "generated_video": {
            "shot_count": treatment_counts["GENERATED_VIDEO"],
            "seconds": _video_seconds(story_shots),
            "estimated_spend_usd": spend,
            "target_usd": VIDEO_TARGET_USD,
            "hard_cap_usd": VIDEO_HARD_CAP_USD,
        },
        "treatment_counts": dict(sorted(treatment_counts.items())),
        "scene_domain_counts": dict(sorted(domain_counts.items())),
        "sh_023": {
            "treatment": next(
                shot["final_budget_treatment"]
                for shot in story_shots
                if shot.get("shot_id") == "SH-023"
            ),
            "motion_necessity": "REQUIRED",
        },
        "remaining_motion_required_not_video": remaining_motion_issues,
        "maximum_dynamic_still_panel_seconds": max_panel,
        "human_visual_review_required": True,
        "paid_execution_authorized": False,
        "next_stage": "FULL_ARABIC_DIACRITIZATION_AND_PERFORMANCE_REVIEW",
    }
    return RepairResult(
        storyboard=updated_storyboard,
        production_plan=updated_plan,
        visual_summary=summary,
    )


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(
        value,
        (str, bytes, bytearray),
    ):
        return value
    return ()


def _clean(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _narration(segment: Mapping[str, Any]) -> str:
    for key in (
        "narration_ar",
        "final_narration_ar",
        "script_text_ar",
        "text_ar",
        "narration",
    ):
        text = _clean(segment.get(key))
        if text:
            return text
    blocks = segment.get("performance_blocks")
    if isinstance(blocks, list):
        joined = " ".join(
            _clean(block.get("canonical_text_ar") or block.get("text_ar"))
            for block in blocks
            if isinstance(block, Mapping)
        ).strip()
        if joined:
            return joined
    raise AdamWorldMotionRepairError(
        f"SEGMENT_NARRATION_REQUIRED:{segment.get('segment_id')}"
    )


def _split_blocks(text: str, maximum_chars: int = 220) -> list[str]:
    sentences = [
        item.strip()
        for item in _SENTENCE_SPLIT.split(text)
        if item.strip()
    ]
    blocks: list[str] = []
    current = ""
    for sentence in sentences:
        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > maximum_chars:
            blocks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        blocks.append(current)
    return blocks or [text]


def build_narration_export(
    script: Mapping[str, Any],
    source_path: str,
) -> dict[str, Any]:
    sections = script.get("segments")
    source_structure = "segments"
    if not isinstance(sections, list) or not sections:
        sections = script.get("sequences")
        source_structure = "sequences"
    if not isinstance(sections, list) or not sections:
        raise AdamWorldMotionRepairError(
            "SCRIPT_SEGMENTS_OR_SEQUENCES_REQUIRED"
        )
    exported_segments: list[dict[str, Any]] = []
    total_blocks = 0
    total_words = 0
    for segment_index, raw in enumerate(sections, start=1):
        if not isinstance(raw, Mapping):
            raise AdamWorldMotionRepairError(
                f"SCRIPT_SEGMENT_OBJECT_REQUIRED:{segment_index}"
            )
        text = _narration(raw)
        chunks = _split_blocks(text)
        blocks: list[dict[str, Any]] = []
        for block_index, chunk in enumerate(chunks, start=1):
            total_blocks += 1
            total_words += len(chunk.split())
            blocks.append(
                {
                    "block_id": (
                        f"VB-{segment_index:03d}-{block_index:02d}"
                    ),
                    "canonical_text_ar": chunk,
                    "tts_text_ar": None,
                    "pace": "SLOW_DOCUMENTARY",
                    "pause_before_ms": 200 if block_index > 1 else 350,
                    "pause_after_ms": (
                        750 if block_index == len(chunks) else 450
                    ),
                    "emotion": "MEASURED_AWE",
                    "emphasis_words": [],
                    "human_diacritization_required": True,
                    "human_language_review_required": True,
                }
            )
        exported_segments.append(
            {
                "segment_id": str(
                    raw.get("segment_id")
                    or raw.get("sequence_id")
                    or f"SEG-{segment_index:03d}"
                ),
                "source_sequence_id": str(
                    raw.get("sequence_id") or ""
                ),
                "title_ar": _clean(
                    raw.get("title_ar")
                    or raw.get("sequence_title")
                    or raw.get("label_ar")
                ),
                "canonical_narration_ar": text,
                "performance_blocks": blocks,
            }
        )
    return {
        "schema_version": "siraj-arabic-performance-source-v2",
        "status": "AWAITING_FULL_DIACRITIZATION_AND_HUMAN_REVIEW",
        "source_script_path": source_path,
        "source_structure": source_structure,
        "segments": exported_segments,
        "metrics": {
            "segment_count": len(exported_segments),
            "performance_block_count": total_blocks,
            "word_count": total_words,
        },
        "instructions": {
            "fill_only": "tts_text_ar",
            "preserve_meaning_and_canonical_text": True,
            "full_diacritization_required": True,
            "human_language_review_required": True,
            "do_not_send_to_tts_until_approved": True,
        },
    }


def narration_export_text(payload: Mapping[str, Any]) -> str:
    lines = [
        "# SIRAJ — Arabic Performance Source V2",
        "# املأ النص المشكول داخل tts_text_ar في ملف JSON.",
        "",
    ]
    for segment in _sequence(payload.get("segments")):
        if not isinstance(segment, Mapping):
            continue
        lines.append(
            f"## {segment.get('segment_id')} — {segment.get('title_ar', '')}"
        )
        for block in _sequence(segment.get("performance_blocks")):
            if not isinstance(block, Mapping):
                continue
            lines.append(f"[{block.get('block_id')}]")
            lines.append(str(block.get("canonical_text_ar") or ""))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"
