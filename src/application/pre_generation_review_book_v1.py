from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import unicodedata
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.application.episode_canonical_state_v1 import (
    CanonicalStateError,
    EpisodeStage,
    bind_artifact,
    load_state,
    transition,
)

VISUAL_CONTRACT_SCHEMA = "siraj-visual-shot-contracts-v1"
REVIEW_BOOK_SCHEMA = "siraj-pre-generation-review-book-v1"
DECISIONS_SCHEMA = "siraj-pre-generation-decisions-v1"
APPROVAL_SCHEMA = "siraj-pre-generation-approval-v1"

GENERATION_CLASSES = {"A_FIRST_LAST", "B_FIRST_ONLY", "C_DIRECT"}
RISK_LEVELS = {"LOW", "MEDIUM", "HIGH"}
LOCATION_CERTAINTY = {"CERTAIN", "UNSPECIFIED", "SYMBOLIC_ONLY"}
DECISION_STATUSES = {"PENDING", "APPROVE", "REVISE", "REMOVE", "MERGE", "SPLIT"}

BOUNDARY_TOLERANCE_SECONDS = 0.120
MAX_SHOT_DURATION_SECONDS = 30.0
MIN_SHOT_DURATION_SECONDS = 0.35


class PreGenerationReviewError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_text(path: Path, text: str, *, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding=encoding, newline="\n")
    os.replace(tmp, path)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write_text(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text)).strip()


def normalize_alignment_text(text: str) -> str:
    # Alignment comparison is intentionally tolerant of punctuation/harakat differences
    # but not of lexical differences.
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = re.sub(r"[^\w\u0600-\u06FF]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _require_str(obj: dict[str, Any], key: str, label: str) -> str:
    value = obj.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PreGenerationReviewError(f"{label}_{key.upper()}_REQUIRED")
    return value.strip()


def _require_list(obj: dict[str, Any], key: str, label: str, *, allow_empty: bool = False) -> list[Any]:
    value = obj.get(key)
    if not isinstance(value, list):
        raise PreGenerationReviewError(f"{label}_{key.upper()}_MUST_BE_LIST")
    if not allow_empty and not value:
        raise PreGenerationReviewError(f"{label}_{key.upper()}_REQUIRED")
    return value


def _number(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise PreGenerationReviewError(f"{label}_MUST_BE_NUMBER")
    return float(value)


def load_timing_map(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise PreGenerationReviewError("TIMING_MAP_MISSING:" + str(path))
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or not isinstance(data.get("sentences"), list):
        raise PreGenerationReviewError("TIMING_MAP_INVALID")
    return data


def timing_words(timing: dict[str, Any]) -> list[dict[str, Any]]:
    words: list[dict[str, Any]] = []
    for sentence in timing["sentences"]:
        sid = sentence.get("sentence_id")
        for word in sentence.get("words", []):
            words.append(
                {
                    "sentence_id": sid,
                    "word_id": word.get("word_id"),
                    "text": str(word.get("text") or ""),
                    "start": float(word["start"]),
                    "end": float(word["end"]),
                }
            )
    words.sort(key=lambda w: (w["start"], w["end"]))
    if not words:
        raise PreGenerationReviewError("TIMING_MAP_HAS_NO_WORDS")
    return words


def nearest_word_boundary_delta(value: float, words: list[dict[str, Any]]) -> float:
    boundaries = []
    for word in words:
        boundaries.extend([word["start"], word["end"]])
    return min(abs(value - boundary) for boundary in boundaries)


def words_for_range(
    start: float,
    end: float,
    words: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    selected = []
    for word in words:
        # Include words whose audible interval materially intersects the shot.
        overlap = min(end, word["end"]) - max(start, word["start"])
        if overlap > 0.015:
            selected.append(word)
    return selected


def validate_generation_class(shot: dict[str, Any], label: str) -> None:
    generation_class = _require_str(shot, "generation_class", label)
    if generation_class not in GENERATION_CLASSES:
        raise PreGenerationReviewError(
            f"{label}_INVALID_GENERATION_CLASS:{generation_class}"
        )

    first = shot.get("first_frame")
    last = shot.get("last_frame")
    if not isinstance(first, dict) or not isinstance(last, dict):
        raise PreGenerationReviewError(f"{label}_FIRST_LAST_FRAME_OBJECTS_REQUIRED")

    first_required = bool(first.get("required"))
    last_required = bool(last.get("required"))

    if generation_class == "A_FIRST_LAST":
        if not first_required or not last_required:
            raise PreGenerationReviewError(
                f"{label}_CLASS_A_REQUIRES_FIRST_AND_LAST_FRAME"
            )
    elif generation_class == "B_FIRST_ONLY":
        if not first_required or last_required:
            raise PreGenerationReviewError(
                f"{label}_CLASS_B_REQUIRES_FIRST_ONLY"
            )
    elif generation_class == "C_DIRECT":
        if first_required or last_required:
            raise PreGenerationReviewError(
                f"{label}_CLASS_C_MUST_NOT_REQUIRE_FIRST_OR_LAST"
            )

    if first_required:
        for key in ("description", "composition", "camera_position"):
            _require_str(first, key, label + "_FIRST_FRAME")
        _require_list(first, "subject_positions", label + "_FIRST_FRAME")
        _require_list(first, "reference_ids", label + "_FIRST_FRAME", allow_empty=True)

    if last_required:
        for key in ("description", "expected_end_state", "continuity_target"):
            _require_str(last, key, label + "_LAST_FRAME")
        _require_list(last, "reference_ids", label + "_LAST_FRAME", allow_empty=True)


def validate_camera(shot: dict[str, Any], label: str) -> None:
    camera = shot.get("camera")
    if not isinstance(camera, dict):
        raise PreGenerationReviewError(f"{label}_CAMERA_REQUIRED")
    for key in (
        "height",
        "angle",
        "lens_behavior",
        "start_framing",
        "end_framing",
    ):
        _require_str(camera, key, label + "_CAMERA")
    _require_list(camera, "allowed_movement", label + "_CAMERA", allow_empty=True)
    _require_list(camera, "forbidden_movement", label + "_CAMERA", allow_empty=True)


def validate_environment(shot: dict[str, Any], label: str) -> None:
    env = shot.get("environment")
    if not isinstance(env, dict):
        raise PreGenerationReviewError(f"{label}_ENVIRONMENT_REQUIRED")
    _require_str(env, "environment_id", label + "_ENVIRONMENT")
    certainty = _require_str(env, "location_certainty", label + "_ENVIRONMENT")
    if certainty not in LOCATION_CERTAINTY:
        raise PreGenerationReviewError(
            f"{label}_INVALID_LOCATION_CERTAINTY:{certainty}"
        )
    if not isinstance(env.get("literal_location_allowed"), bool):
        raise PreGenerationReviewError(
            f"{label}_ENVIRONMENT_LITERAL_LOCATION_ALLOWED_MUST_BE_BOOL"
        )
    for key in ("lighting", "color_palette", "time_state"):
        _require_str(env, key, label + "_ENVIRONMENT")


def validate_risk(shot: dict[str, Any], label: str) -> None:
    risk = shot.get("risk")
    if not isinstance(risk, dict):
        raise PreGenerationReviewError(f"{label}_RISK_REQUIRED")
    for key in (
        "constitution",
        "semantic",
        "continuity",
        "repetition",
        "provider",
    ):
        value = _require_str(risk, key, label + "_RISK")
        if value not in RISK_LEVELS:
            raise PreGenerationReviewError(
                f"{label}_INVALID_RISK_{key.upper()}:{value}"
            )


def validate_visual_contracts(
    *,
    episode_id: str,
    contracts_path: Path,
    narration_sha256: str,
    audio_sha256: str,
    timing_path: Path,
) -> dict[str, Any]:
    if not contracts_path.is_file():
        raise PreGenerationReviewError("VISUAL_CONTRACTS_MISSING:" + str(contracts_path))
    timing = load_timing_map(timing_path)
    words = timing_words(timing)

    contracts = json.loads(contracts_path.read_text(encoding="utf-8-sig"))
    if not isinstance(contracts, dict):
        raise PreGenerationReviewError("VISUAL_CONTRACTS_ROOT_NOT_OBJECT")
    if contracts.get("schema_version") != VISUAL_CONTRACT_SCHEMA:
        raise PreGenerationReviewError("VISUAL_CONTRACT_SCHEMA_MISMATCH")
    if contracts.get("episode_id") != episode_id:
        raise PreGenerationReviewError("VISUAL_CONTRACT_EPISODE_ID_MISMATCH")
    if contracts.get("narration_sha256") != narration_sha256:
        raise PreGenerationReviewError("VISUAL_CONTRACT_NARRATION_SHA_MISMATCH")
    if contracts.get("audio_sha256") != audio_sha256:
        raise PreGenerationReviewError("VISUAL_CONTRACT_AUDIO_SHA_MISMATCH")
    if contracts.get("timing_sha256") != sha256_file(timing_path):
        raise PreGenerationReviewError("VISUAL_CONTRACT_TIMING_SHA_MISMATCH")

    shots = contracts.get("shots")
    if not isinstance(shots, list) or not shots:
        raise PreGenerationReviewError("VISUAL_CONTRACT_SHOTS_REQUIRED")

    seen_ids: set[str] = set()
    seen_orders: set[int] = set()
    previous_start = -1.0
    summary = {
        "shot_count": len(shots),
        "generation_classes": {x: 0 for x in sorted(GENERATION_CLASSES)},
        "risk_counts": {x: 0 for x in sorted(RISK_LEVELS)},
        "boundary_warnings": [],
        "long_shot_warnings": [],
    }

    validated_shots = []
    for index, shot in enumerate(shots, start=1):
        if not isinstance(shot, dict):
            raise PreGenerationReviewError(f"SHOT_{index:03d}_NOT_OBJECT")
        label = f"SHOT_{index:03d}"
        shot_id = _require_str(shot, "shot_id", label)
        if shot_id in seen_ids:
            raise PreGenerationReviewError("DUPLICATE_SHOT_ID:" + shot_id)
        seen_ids.add(shot_id)

        order = shot.get("order")
        if isinstance(order, bool) or not isinstance(order, int) or order < 1:
            raise PreGenerationReviewError(f"{label}_ORDER_INVALID")
        if order in seen_orders:
            raise PreGenerationReviewError(f"DUPLICATE_SHOT_ORDER:{order}")
        seen_orders.add(order)

        for key in ("segment_id", "beat_id"):
            _require_str(shot, key, label)

        start = _number(shot.get("audio_start"), label + "_AUDIO_START")
        end = _number(shot.get("audio_end"), label + "_AUDIO_END")
        if start < 0 or end <= start:
            raise PreGenerationReviewError(
                f"{label}_INVALID_AUDIO_RANGE:{start}->{end}"
            )
        duration = end - start
        if duration < MIN_SHOT_DURATION_SECONDS:
            raise PreGenerationReviewError(f"{label}_SHOT_TOO_SHORT:{duration:.3f}")
        if duration > MAX_SHOT_DURATION_SECONDS:
            summary["long_shot_warnings"].append(
                {"shot_id": shot_id, "duration_seconds": round(duration, 3)}
            )

        if start < previous_start - 0.001:
            raise PreGenerationReviewError(f"{label}_SHOT_ORDER_NOT_TIMELINE_ORDER")
        previous_start = start

        start_delta = nearest_word_boundary_delta(start, words)
        end_delta = nearest_word_boundary_delta(end, words)
        if start_delta > BOUNDARY_TOLERANCE_SECONDS:
            raise PreGenerationReviewError(
                f"{label}_START_NOT_WORD_BOUNDARY:{start:.3f}:delta={start_delta:.3f}"
            )
        if end_delta > BOUNDARY_TOLERANCE_SECONDS:
            raise PreGenerationReviewError(
                f"{label}_END_NOT_WORD_BOUNDARY:{end:.3f}:delta={end_delta:.3f}"
            )

        ranged_words = words_for_range(start, end, words)
        if not ranged_words:
            raise PreGenerationReviewError(f"{label}_NO_NARRATION_WORDS_IN_RANGE")

        exact_text = _require_str(shot, "exact_narration_text", label)
        derived_text = " ".join(word["text"] for word in ranged_words)
        if normalize_alignment_text(exact_text) != normalize_alignment_text(derived_text):
            raise PreGenerationReviewError(
                f"{label}_EXACT_NARRATION_TEXT_MISMATCH:"
                f"declared={normalize_space(exact_text)!r}:"
                f"derived={normalize_space(derived_text)!r}"
            )

        for key in (
            "visual_purpose",
            "visual_description",
            "core_action",
            "semantic_requirement",
            "generation_prompt_draft",
        ):
            _require_str(shot, key, label)

        _require_list(shot, "must_show", label)
        _require_list(shot, "must_not_show", label)
        _require_list(shot, "unknown_unsupported_details", label, allow_empty=True)
        _require_list(shot, "constitution_hard_rules", label)
        _require_list(shot, "characters", label, allow_empty=True)
        _require_list(shot, "references", label, allow_empty=True)

        motion = shot.get("motion")
        if not isinstance(motion, dict):
            raise PreGenerationReviewError(f"{label}_MOTION_REQUIRED")
        for key in ("subject_motion", "camera_motion", "environment_motion"):
            _require_str(motion, key, label + "_MOTION")
        _require_list(motion, "forbidden_motion", label + "_MOTION", allow_empty=True)

        continuity = shot.get("continuity")
        if not isinstance(continuity, dict):
            raise PreGenerationReviewError(f"{label}_CONTINUITY_REQUIRED")
        _require_list(
            continuity,
            "must_remain_identical",
            label + "_CONTINUITY",
            allow_empty=True,
        )
        _require_list(
            continuity,
            "allowed_to_change",
            label + "_CONTINUITY",
            allow_empty=True,
        )

        validate_generation_class(shot, label)
        validate_camera(shot, label)
        validate_environment(shot, label)
        validate_risk(shot, label)

        human = shot.get("human_decision")
        if not isinstance(human, dict):
            raise PreGenerationReviewError(f"{label}_HUMAN_DECISION_REQUIRED")
        status = _require_str(human, "status", label + "_HUMAN_DECISION")
        if status not in DECISION_STATUSES:
            raise PreGenerationReviewError(
                f"{label}_INVALID_HUMAN_DECISION:{status}"
            )

        generation_class = shot["generation_class"]
        summary["generation_classes"][generation_class] += 1
        summary["risk_counts"][shot["risk"]["constitution"]] += 1

        validated = deepcopy(shot)
        validated["duration_seconds"] = round(duration, 6)
        validated["derived_word_ids"] = [w["word_id"] for w in ranged_words]
        validated["derived_sentence_ids"] = sorted(
            {w["sentence_id"] for w in ranged_words}
        )
        validated_shots.append(validated)

    expected_orders = list(range(1, len(shots) + 1))
    if sorted(seen_orders) != expected_orders:
        raise PreGenerationReviewError(
            "SHOT_ORDER_MUST_BE_CONTIGUOUS_1_TO_N:"
            + json.dumps(sorted(seen_orders))
        )

    return {
        "contracts": contracts,
        "validated_shots": validated_shots,
        "summary": summary,
    }


def _artifact_record(state: dict[str, Any], slot: str) -> dict[str, Any]:
    record = state.get("artifacts", {}).get(slot)
    if not isinstance(record, dict):
        raise PreGenerationReviewError("CANONICAL_ARTIFACT_NOT_BOUND:" + slot)
    path = Path(record["path"])
    if not path.is_file():
        raise PreGenerationReviewError("CANONICAL_ARTIFACT_BYTES_MISSING:" + slot)
    actual = sha256_file(path)
    if actual != record["sha256"]:
        raise PreGenerationReviewError(
            f"CANONICAL_ARTIFACT_SHA_MISMATCH:{slot}:{actual}:expected={record['sha256']}"
        )
    return record


def _li(items: list[Any]) -> str:
    if not items:
        return "<span class='muted'>—</span>"
    return "<ul>" + "".join(
        "<li>" + html.escape(str(x)) + "</li>" for x in items
    ) + "</ul>"


def _kv(label: str, value: Any) -> str:
    return (
        "<div class='kv'><div class='k'>"
        + html.escape(label)
        + "</div><div class='v'>"
        + html.escape(str(value))
        + "</div></div>"
    )


def _object_pretty(obj: Any) -> str:
    return html.escape(json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=True))


def render_review_html(review: dict[str, Any]) -> str:
    css = """
    body{font-family:Tahoma,Arial,sans-serif;background:#f5f5f5;color:#171717;margin:0}
    main{max-width:1180px;margin:auto;padding:28px}
    h1,h2,h3{margin:0 0 12px}
    .card{background:white;border:1px solid #ddd;border-radius:12px;padding:18px;margin:16px 0}
    .grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
    .kv{border:1px solid #e6e6e6;border-radius:8px;padding:9px;background:#fafafa}
    .k{font-size:12px;color:#666;margin-bottom:4px}.v{font-weight:700}
    .shot{border-right:5px solid #333}
    .narration{font-size:18px;line-height:1.9;background:#fffdf6;padding:12px;border-radius:8px}
    .prompt{white-space:pre-wrap;background:#f2f4f7;padding:12px;border-radius:8px;direction:ltr;text-align:left}
    .code{white-space:pre-wrap;background:#f7f7f7;padding:12px;border-radius:8px;font-family:Consolas,monospace;font-size:12px;direction:ltr;text-align:left}
    .muted{color:#777}
    .warning{background:#fff4e5;border:1px solid #f0c36d;padding:12px;border-radius:8px}
    table{width:100%;border-collapse:collapse;background:white}th,td{border:1px solid #ddd;padding:8px;text-align:right}
    th{background:#f0f0f0}
    @media(max-width:850px){.grid{grid-template-columns:1fr}}
    @media print{body{background:white}.card{break-inside:avoid}}
    """
    episode = review["episode"]
    summary = review["summary"]
    rows = []
    for shot in review["shots"]:
        rows.append(
            "<tr>"
            f"<td>{shot['order']}</td>"
            f"<td>{html.escape(shot['shot_id'])}</td>"
            f"<td>{shot['audio_start']:.3f}–{shot['audio_end']:.3f}</td>"
            f"<td>{shot['duration_seconds']:.3f}s</td>"
            f"<td>{html.escape(shot['generation_class'])}</td>"
            f"<td>{html.escape(shot['risk']['constitution'])}</td>"
            f"<td>{html.escape(shot['human_decision']['status'])}</td>"
            "</tr>"
        )

    shot_cards = []
    for shot in review["shots"]:
        shot_cards.append(
            f"""
<section class="card shot">
<h2>{shot['order']:03d} — {html.escape(shot['shot_id'])}</h2>
<div class="grid">
{_kv("Segment", shot["segment_id"])}
{_kv("Beat", shot["beat_id"])}
{_kv("Audio", f'{shot["audio_start"]:.3f} → {shot["audio_end"]:.3f}')}
{_kv("Duration", f'{shot["duration_seconds"]:.3f}s')}
{_kv("Generation Class", shot["generation_class"])}
{_kv("Human Decision", shot["human_decision"]["status"])}
</div>

<h3>النص المنطوق الدقيق داخل اللقطة</h3>
<div class="narration">{html.escape(shot["exact_narration_text"])}</div>

<h3>الوظيفة والمعنى</h3>
<div class="grid">
{_kv("Visual Purpose", shot["visual_purpose"])}
{_kv("Core Action", shot["core_action"])}
{_kv("Semantic Requirement", shot["semantic_requirement"])}
</div>
<p><strong>الوصف البصري:</strong> {html.escape(shot["visual_description"])}</p>

<div class="grid">
<div><h3>Must Show</h3>{_li(shot["must_show"])}</div>
<div><h3>Must Not Show</h3>{_li(shot["must_not_show"])}</div>
<div><h3>Unknown / Unsupported</h3>{_li(shot["unknown_unsupported_details"])}</div>
</div>

<h3>القواعد الدستورية الصلبة</h3>
{_li(shot["constitution_hard_rules"])}

<h3>الشخصيات</h3>
<div class="code">{_object_pretty(shot["characters"])}</div>

<h3>البيئة</h3>
<div class="code">{_object_pretty(shot["environment"])}</div>

<h3>الكاميرا</h3>
<div class="code">{_object_pretty(shot["camera"])}</div>

<h3>First Frame Contract</h3>
<div class="code">{_object_pretty(shot["first_frame"])}</div>

<h3>Last Frame Contract</h3>
<div class="code">{_object_pretty(shot["last_frame"])}</div>

<h3>Motion Contract</h3>
<div class="code">{_object_pretty(shot["motion"])}</div>

<h3>Continuity</h3>
<div class="code">{_object_pretty(shot["continuity"])}</div>

<h3>References</h3>
<div class="code">{_object_pretty(shot["references"])}</div>

<h3>Risk</h3>
<div class="code">{_object_pretty(shot["risk"])}</div>

<h3>Generation Prompt Draft</h3>
<div class="prompt">{html.escape(shot["generation_prompt_draft"])}</div>

<h3>قرار المراجعة البشرية</h3>
<div class="code">{_object_pretty(shot["human_decision"])}</div>
</section>
"""
        )

    long_warning = ""
    if summary["long_shot_warnings"]:
        long_warning = (
            "<div class='warning'><strong>تحذير:</strong> توجد لقطات أطول من "
            f"{MAX_SHOT_DURATION_SECONDS:.0f} ثانية. هذا تحذير تحريري وليس Hard Fail."
            "</div>"
        )

    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head><meta charset="utf-8"><title>{html.escape(str(episode["episode_id"]))} Pre-Generation Review Book</title><style>{css}</style></head>
<body><main>
<section class="card">
<h1>سراج — كتاب مراجعة ما قبل التوليد</h1>
<p>هذا الملف هو آخر نقطة مراجعة بشرية قبل أي توليد بصري. لا يولّد أي صورة أو فيديو.</p>
<div class="grid">
{_kv("Episode", episode["episode_id"])}
{_kv("Canonical Stage", episode["canonical_stage"])}
{_kv("Audio Duration", f'{episode["audio_duration_seconds"]:.3f}s')}
{_kv("Shots", summary["shot_count"])}
{_kv("Class A", summary["generation_classes"].get("A_FIRST_LAST", 0))}
{_kv("Class B", summary["generation_classes"].get("B_FIRST_ONLY", 0))}
{_kv("Class C", summary["generation_classes"].get("C_DIRECT", 0))}
{_kv("Constitution", episode["constitution_version"])}
{_kv("Review Status", review["review_status"])}
</div>
{long_warning}
</section>

<section class="card">
<h2>السكربت الكامل</h2>
<div class="narration">{html.escape(review["script_text"]).replace(chr(10), "<br>")}</div>
</section>

<section class="card">
<h2>نص التعليق الصوتي الكامل</h2>
<div class="narration">{html.escape(review["narration_text"]).replace(chr(10), "<br>")}</div>
</section>

<section class="card">
<h2>الـStoryboard الزمني</h2>
<table><thead><tr><th>#</th><th>Shot</th><th>Audio</th><th>Duration</th><th>Class</th><th>Constitution Risk</th><th>Decision</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table>
</section>

{''.join(shot_cards)}

<section class="card">
<h2>طريقة القرار</h2>
<p>الـReview Book نفسه Immutable ومربوط بـSHA. إن وجدت مشكلة، عدّل السكربت/الستوري بورد upstream ثم أعد توليد الكتاب. عند الموافقة النهائية استخدم ملف القرارات المنفصل.</p>
</section>
</main></body></html>
"""


def build_decisions_template(review: dict[str, Any], review_json_path: Path) -> dict[str, Any]:
    return {
        "schema_version": DECISIONS_SCHEMA,
        "episode_id": review["episode"]["episode_id"],
        "review_book_json_path": str(review_json_path.resolve()),
        "review_book_json_sha256": sha256_file(review_json_path),
        "overall_decision": "PENDING",
        "shots": [
            {
                "shot_id": shot["shot_id"],
                "decision": "PENDING",
                "notes": "",
            }
            for shot in review["shots"]
        ],
        "human_notes": "",
    }


def build_review_book(
    *,
    state_path: Path,
    contracts_path: Path,
    output_json: Path,
    output_html: Path,
    decisions_template_path: Path,
) -> dict[str, Any]:
    state = load_state(state_path)
    if state["stage"] not in {
        EpisodeStage.AUDIO_LOCKED.value,
        EpisodeStage.STORYBOARD_READY.value,
    }:
        raise PreGenerationReviewError(
            "REVIEW_BUILD_REQUIRES_AUDIO_LOCKED_OR_STORYBOARD_READY:"
            + state["stage"]
        )

    script = _artifact_record(state, "script")
    narration = _artifact_record(state, "narration")
    audio = _artifact_record(state, "audio")
    timing = _artifact_record(state, "timing")

    timing_path = Path(timing["path"])
    validated = validate_visual_contracts(
        episode_id=state["episode_id"],
        contracts_path=contracts_path,
        narration_sha256=narration["sha256"],
        audio_sha256=audio["sha256"],
        timing_path=timing_path,
    )

    review = {
        "schema_version": REVIEW_BOOK_SCHEMA,
        "review_status": "PENDING_HUMAN_PRE_GENERATION_REVIEW",
        "generated_at": utc_now(),
        "episode": {
            "episode_id": state["episode_id"],
            "canonical_stage": state["stage"],
            "canonical_state_revision": state["revision"],
            "constitution_version": state["constitution"]["version"],
            "constitution_sha256": state["constitution"]["bundle_manifest_sha256"],
            "script_sha256": script["sha256"],
            "narration_sha256": narration["sha256"],
            "audio_sha256": audio["sha256"],
            "timing_sha256": timing["sha256"],
            "audio_duration_seconds": float(
                timing.get("metadata", {}).get("audio_duration_seconds", 0.0)
            ),
        },
        "script_text": Path(script["path"]).read_text(encoding="utf-8-sig"),
        "narration_text": Path(narration["path"]).read_text(encoding="utf-8-sig"),
        "contracts_path": str(contracts_path.resolve()),
        "contracts_sha256": sha256_file(contracts_path),
        "summary": validated["summary"],
        "shots": validated["validated_shots"],
        "human_gate_rule": (
            "NO_IMAGE_OR_VIDEO_GENERATION_BEFORE_PRE_GENERATION_APPROVED"
        ),
    }
    atomic_write_json(output_json, review)
    atomic_write_text(output_html, render_review_html(review))

    decisions = build_decisions_template(review, output_json)
    atomic_write_json(decisions_template_path, decisions)

    return review


def stage_pre_generation_review(
    *,
    state_path: Path,
    contracts_path: Path,
    output_json: Path,
    output_html: Path,
    decisions_template_path: Path,
) -> dict[str, Any]:
    state = load_state(state_path)
    if state["stage"] != EpisodeStage.AUDIO_LOCKED.value:
        raise PreGenerationReviewError(
            "STAGE_REVIEW_REQUIRES_AUDIO_LOCKED:" + state["stage"]
        )

    original_state = state_path.read_bytes()
    created = []
    try:
        # Validate/build before committing state transition.
        review = build_review_book(
            state_path=state_path,
            contracts_path=contracts_path,
            output_json=output_json,
            output_html=output_html,
            decisions_template_path=decisions_template_path,
        )
        for p in (output_json, output_html, decisions_template_path):
            if p.is_file():
                created.append(p)

        bind_artifact(
            state_path,
            "storyboard",
            contracts_path,
            metadata={
                "schema_version": VISUAL_CONTRACT_SCHEMA,
                "shot_count": review["summary"]["shot_count"],
                "review_book_version": REVIEW_BOOK_SCHEMA,
            },
        )
        transition(state_path, EpisodeStage.STORYBOARD_READY.value)

        bind_artifact(
            state_path,
            "pre_generation_review",
            output_json,
            metadata={
                "review_html": str(output_html.resolve()),
                "decisions_template": str(decisions_template_path.resolve()),
                "contracts_sha256": review["contracts_sha256"],
                "shot_count": review["summary"]["shot_count"],
                "status": "PENDING_HUMAN_PRE_GENERATION_REVIEW",
            },
        )
        final_state = transition(
            state_path, EpisodeStage.PRE_GENERATION_REVIEW.value
        )

        return {
            "status": "PASS_PRE_GENERATION_REVIEW_STAGED",
            "episode_id": final_state["episode_id"],
            "stage": final_state["stage"],
            "review_json": str(output_json.resolve()),
            "review_html": str(output_html.resolve()),
            "decisions_template": str(decisions_template_path.resolve()),
            "review_json_sha256": sha256_file(output_json),
            "contracts_sha256": sha256_file(contracts_path),
            "shot_count": review["summary"]["shot_count"],
            "generation_classes": review["summary"]["generation_classes"],
        }

    except Exception:
        tmp = state_path.with_suffix(state_path.suffix + ".restore.tmp")
        tmp.write_bytes(original_state)
        os.replace(tmp, state_path)
        for p in reversed(created):
            try:
                if p.is_file():
                    p.unlink()
            except Exception:
                pass
        raise


def approve_pre_generation_review(
    *,
    state_path: Path,
    decisions_path: Path,
    approval_output: Path,
) -> dict[str, Any]:
    state = load_state(state_path)
    if state["stage"] != EpisodeStage.PRE_GENERATION_REVIEW.value:
        raise PreGenerationReviewError(
            "APPROVAL_REQUIRES_PRE_GENERATION_REVIEW:" + state["stage"]
        )
    review_record = _artifact_record(state, "pre_generation_review")
    review_path = Path(review_record["path"])

    if not decisions_path.is_file():
        raise PreGenerationReviewError("DECISIONS_FILE_MISSING")
    decisions = json.loads(decisions_path.read_text(encoding="utf-8-sig"))
    if decisions.get("schema_version") != DECISIONS_SCHEMA:
        raise PreGenerationReviewError("DECISIONS_SCHEMA_MISMATCH")
    if decisions.get("episode_id") != state["episode_id"]:
        raise PreGenerationReviewError("DECISIONS_EPISODE_ID_MISMATCH")
    if decisions.get("review_book_json_sha256") != review_record["sha256"]:
        raise PreGenerationReviewError("DECISIONS_REVIEW_BOOK_SHA_MISMATCH")
    if decisions.get("overall_decision") != "APPROVE":
        raise PreGenerationReviewError("OVERALL_DECISION_MUST_BE_APPROVE")

    review = json.loads(review_path.read_text(encoding="utf-8-sig"))
    expected_ids = [shot["shot_id"] for shot in review["shots"]]
    actual_entries = decisions.get("shots")
    if not isinstance(actual_entries, list):
        raise PreGenerationReviewError("DECISION_SHOTS_MUST_BE_LIST")
    actual_by_id = {}
    for item in actual_entries:
        if not isinstance(item, dict):
            raise PreGenerationReviewError("DECISION_SHOT_ENTRY_NOT_OBJECT")
        shot_id = str(item.get("shot_id") or "")
        if shot_id in actual_by_id:
            raise PreGenerationReviewError("DUPLICATE_DECISION_SHOT_ID:" + shot_id)
        actual_by_id[shot_id] = item

    if set(actual_by_id) != set(expected_ids):
        raise PreGenerationReviewError("DECISION_SHOT_SET_MISMATCH")
    not_approved = [
        shot_id
        for shot_id in expected_ids
        if actual_by_id[shot_id].get("decision") != "APPROVE"
    ]
    if not_approved:
        raise PreGenerationReviewError(
            "SHOTS_NOT_APPROVED:" + ",".join(not_approved)
        )

    approval = {
        "schema_version": APPROVAL_SCHEMA,
        "status": "APPROVED",
        "episode_id": state["episode_id"],
        "approved_at": utc_now(),
        "review_book_json": str(review_path.resolve()),
        "review_book_json_sha256": review_record["sha256"],
        "decisions_file": str(decisions_path.resolve()),
        "decisions_sha256": sha256_file(decisions_path),
        "shot_count": len(expected_ids),
        "all_shots_approved": True,
        "generation_gate": "OPEN_AFTER_THIS_APPROVAL_ONLY",
    }

    original_state = state_path.read_bytes()
    created = False
    try:
        atomic_write_json(approval_output, approval)
        created = True
        bind_artifact(
            state_path,
            "pre_generation_approval",
            approval_output,
            status="APPROVED",
            metadata={
                "review_book_json_sha256": review_record["sha256"],
                "decisions_sha256": approval["decisions_sha256"],
                "shot_count": len(expected_ids),
            },
        )
        final_state = transition(
            state_path, EpisodeStage.PRE_GENERATION_APPROVED.value
        )
        approval["canonical_stage"] = final_state["stage"]
        approval["canonical_state_revision"] = final_state["revision"]
        return approval
    except Exception:
        tmp = state_path.with_suffix(state_path.suffix + ".restore.tmp")
        tmp.write_bytes(original_state)
        os.replace(tmp, state_path)
        if created and approval_output.is_file():
            approval_output.unlink()
        raise


def template_payload(
    *,
    episode_id: str,
    narration_sha256: str,
    audio_sha256: str,
    timing_sha256: str,
) -> dict[str, Any]:
    return {
        "schema_version": VISUAL_CONTRACT_SCHEMA,
        "episode_id": episode_id,
        "narration_sha256": narration_sha256,
        "audio_sha256": audio_sha256,
        "timing_sha256": timing_sha256,
        "shots": [
            {
                "shot_id": f"{episode_id}-SH-001",
                "order": 1,
                "segment_id": "SEG-001",
                "beat_id": "BEAT-001",
                "audio_start": 0.0,
                "audio_end": 1.0,
                "exact_narration_text": "<AUTO-DERIVED_FROM_WORD_TIMING>",
                "visual_purpose": "<WHY_THIS_SHOT_EXISTS>",
                "visual_description": "<WHAT_WE_SEE>",
                "core_action": "<CORE_VISIBLE_ACTION>",
                "semantic_requirement": "<MEANING_THAT_MUST_LAND>",
                "must_show": ["<REQUIRED_ELEMENT>"],
                "must_not_show": ["<FORBIDDEN_ELEMENT>"],
                "unknown_unsupported_details": [],
                "constitution_hard_rules": ["<RULE_ID_OR_EXPLICIT_RULE>"],
                "generation_class": "A_FIRST_LAST",
                "characters": [],
                "environment": {
                    "environment_id": "<ENV-ID>",
                    "location_certainty": "UNSPECIFIED",
                    "literal_location_allowed": False,
                    "reference_id": None,
                    "lighting": "<LIGHTING>",
                    "color_palette": "<PALETTE>",
                    "time_state": "<TIME_STATE>",
                },
                "camera": {
                    "height": "<HEIGHT>",
                    "angle": "<ANGLE>",
                    "lens_behavior": "<LENS_BEHAVIOR>",
                    "start_framing": "<START>",
                    "end_framing": "<END>",
                    "allowed_movement": [],
                    "forbidden_movement": [],
                },
                "first_frame": {
                    "required": True,
                    "description": "<FIRST_FRAME_DESCRIPTION>",
                    "composition": "<COMPOSITION>",
                    "subject_positions": ["<POSITION>"],
                    "camera_position": "<CAMERA_POSITION>",
                    "reference_ids": [],
                },
                "last_frame": {
                    "required": True,
                    "description": "<LAST_FRAME_DESCRIPTION>",
                    "expected_end_state": "<END_STATE>",
                    "continuity_target": "<CONTINUITY_TARGET>",
                    "reference_ids": [],
                },
                "motion": {
                    "subject_motion": "<SUBJECT_MOTION>",
                    "camera_motion": "<CAMERA_MOTION>",
                    "environment_motion": "<ENVIRONMENT_MOTION>",
                    "forbidden_motion": [],
                },
                "references": [],
                "continuity": {
                    "from_shot_id": None,
                    "to_shot_id": None,
                    "must_remain_identical": [],
                    "allowed_to_change": [],
                },
                "risk": {
                    "constitution": "HIGH",
                    "semantic": "HIGH",
                    "continuity": "MEDIUM",
                    "repetition": "LOW",
                    "provider": "MEDIUM",
                },
                "generation_prompt_draft": "<DRAFT_PROMPT_FOR_HUMAN_REVIEW>",
                "human_decision": {
                    "status": "PENDING",
                    "notes": "",
                },
            }
        ],
    }


def cli() -> int:
    p = argparse.ArgumentParser(description="SIRAJ pre-generation review book v1")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_template = sub.add_parser("template")
    p_template.add_argument("--state", required=True)
    p_template.add_argument("--output", required=True)

    p_validate = sub.add_parser("validate")
    p_validate.add_argument("--state", required=True)
    p_validate.add_argument("--contracts", required=True)

    p_stage = sub.add_parser("stage-review")
    p_stage.add_argument("--state", required=True)
    p_stage.add_argument("--contracts", required=True)
    p_stage.add_argument("--output-json", required=True)
    p_stage.add_argument("--output-html", required=True)
    p_stage.add_argument("--decisions-template", required=True)

    p_approve = sub.add_parser("approve")
    p_approve.add_argument("--state", required=True)
    p_approve.add_argument("--decisions", required=True)
    p_approve.add_argument("--approval-output", required=True)

    args = p.parse_args()
    state_path = Path(args.state)

    if args.cmd == "template":
        state = load_state(state_path)
        narration = _artifact_record(state, "narration")
        audio = _artifact_record(state, "audio")
        timing = _artifact_record(state, "timing")
        payload = template_payload(
            episode_id=state["episode_id"],
            narration_sha256=narration["sha256"],
            audio_sha256=audio["sha256"],
            timing_sha256=timing["sha256"],
        )
        atomic_write_json(Path(args.output), payload)
        print("STATUS=PASS_VISUAL_CONTRACT_TEMPLATE_CREATED")
        print("OUTPUT=" + str(Path(args.output).resolve()))
        return 0

    if args.cmd == "validate":
        state = load_state(state_path)
        narration = _artifact_record(state, "narration")
        audio = _artifact_record(state, "audio")
        timing = _artifact_record(state, "timing")
        result = validate_visual_contracts(
            episode_id=state["episode_id"],
            contracts_path=Path(args.contracts),
            narration_sha256=narration["sha256"],
            audio_sha256=audio["sha256"],
            timing_path=Path(timing["path"]),
        )
        print("STATUS=PASS_VISUAL_CONTRACT_VALIDATION")
        print(json.dumps(result["summary"], ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.cmd == "stage-review":
        result = stage_pre_generation_review(
            state_path=state_path,
            contracts_path=Path(args.contracts),
            output_json=Path(args.output_json),
            output_html=Path(args.output_html),
            decisions_template_path=Path(args.decisions_template),
        )
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    if args.cmd == "approve":
        result = approve_pre_generation_review(
            state_path=state_path,
            decisions_path=Path(args.decisions),
            approval_output=Path(args.approval_output),
        )
        print("STATUS=PASS_PRE_GENERATION_APPROVED")
        print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        return 0

    raise AssertionError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(cli())
