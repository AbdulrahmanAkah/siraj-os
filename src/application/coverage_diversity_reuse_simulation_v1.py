from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.application.episode_canonical_state_v1 import load_state
from src.application.pre_generation_review_book_v1 import (
    VISUAL_CONTRACT_SCHEMA,
    PreGenerationReviewError,
    validate_visual_contracts,
)

SCHEMA_VERSION = "siraj-coverage-diversity-reuse-simulation-v1"

# Coverage is hard: production must not begin with meaningful uncovered timeline.
MAX_ALLOWED_VISUAL_GAP_SECONDS = 0.150

# Diversity is editorial: warn before generation, do not hard-fail by itself.
WINDOW_SECONDS = 45.0
DOMINANCE_WARNING_RATIO = 0.70
CONSECUTIVE_REPEAT_WARNING_SHOTS = 4
CONSECUTIVE_REPEAT_WARNING_SECONDS = 20.0
REFERENCE_REUSE_WARNING_COUNT = 4
LONG_SHOT_WARNING_SECONDS = 18.0


class CoverageSimulationError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _artifact_record(state: dict[str, Any], slot: str) -> dict[str, Any]:
    record = state.get("artifacts", {}).get(slot)
    if not isinstance(record, dict):
        raise CoverageSimulationError("CANONICAL_ARTIFACT_NOT_BOUND:" + slot)
    path = Path(record["path"])
    if not path.is_file():
        raise CoverageSimulationError("CANONICAL_ARTIFACT_BYTES_MISSING:" + slot)
    actual = sha256_file(path)
    if actual != record["sha256"]:
        raise CoverageSimulationError(
            f"CANONICAL_ARTIFACT_SHA_MISMATCH:{slot}:{actual}:expected={record['sha256']}"
        )
    return record


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not intervals:
        return []
    intervals = sorted(intervals)
    merged: list[list[float]] = []
    for start, end in intervals:
        if end <= start:
            continue
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
        else:
            merged[-1][1] = max(merged[-1][1], end)
    return [(a, b) for a, b in merged]


def _coverage_gaps(
    domain_start: float,
    domain_end: float,
    covered: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    merged = _merge_intervals(covered)
    gaps: list[tuple[float, float]] = []
    cursor = domain_start
    for start, end in merged:
        if end <= domain_start or start >= domain_end:
            continue
        start = max(start, domain_start)
        end = min(end, domain_end)
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, end)
    if cursor < domain_end:
        gaps.append((cursor, domain_end))
    return gaps


def _duration(intervals: list[tuple[float, float]]) -> float:
    return sum(max(0.0, b - a) for a, b in intervals)


def _extract_reference_ids(shot: dict[str, Any]) -> list[str]:
    ids: list[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str) and value.strip():
            ids.append(value.strip())
        elif isinstance(value, dict):
            for key in ("reference_id", "id", "ref_id"):
                v = value.get(key)
                if isinstance(v, str) and v.strip():
                    ids.append(v.strip())
                    break

    for ref in shot.get("references", []):
        add(ref)

    for frame_key in ("first_frame", "last_frame"):
        frame = shot.get(frame_key) or {}
        for ref_id in frame.get("reference_ids", []) or []:
            add(ref_id)

    env = shot.get("environment") or {}
    add(env.get("reference_id"))

    for character in shot.get("characters", []) or []:
        add(character)

    return sorted(set(ids))


def _camera_key(shot: dict[str, Any]) -> str:
    camera = shot.get("camera") or {}
    return " | ".join(
        str(camera.get(k) or "").strip().lower()
        for k in ("height", "angle", "start_framing", "end_framing")
    )


def _semantic_key(shot: dict[str, Any]) -> str:
    value = str(shot.get("visual_purpose") or "").strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def _environment_key(shot: dict[str, Any]) -> str:
    env = shot.get("environment") or {}
    return str(env.get("environment_id") or "").strip()


def _run_warnings(
    shots: list[dict[str, Any]],
    key_fn,
    kind: str,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    if not shots:
        return warnings

    run_key = key_fn(shots[0])
    run_start = 0
    for i in range(1, len(shots) + 1):
        key = key_fn(shots[i]) if i < len(shots) else None
        if key != run_key:
            run = shots[run_start:i]
            if run_key:
                elapsed = float(run[-1]["audio_end"]) - float(run[0]["audio_start"])
                if (
                    len(run) >= CONSECUTIVE_REPEAT_WARNING_SHOTS
                    or elapsed >= CONSECUTIVE_REPEAT_WARNING_SECONDS
                ):
                    warnings.append(
                        {
                            "kind": kind,
                            "value": run_key,
                            "shot_ids": [s["shot_id"] for s in run],
                            "shot_count": len(run),
                            "range_seconds": [
                                round(float(run[0]["audio_start"]), 3),
                                round(float(run[-1]["audio_end"]), 3),
                            ],
                            "elapsed_seconds": round(elapsed, 3),
                        }
                    )
            if i < len(shots):
                run_key = key
                run_start = i
    return warnings


def _window_dominance(
    shots: list[dict[str, Any]],
    domain_start: float,
    domain_end: float,
) -> list[dict[str, Any]]:
    warnings: list[dict[str, Any]] = []
    start = domain_start
    while start < domain_end:
        end = min(domain_end, start + WINDOW_SECONDS)
        total = max(0.001, end - start)
        env_seconds: dict[str, float] = defaultdict(float)
        camera_seconds: dict[str, float] = defaultdict(float)
        semantic_seconds: dict[str, float] = defaultdict(float)

        for shot in shots:
            a = max(start, float(shot["audio_start"]))
            b = min(end, float(shot["audio_end"]))
            overlap = max(0.0, b - a)
            if overlap <= 0:
                continue
            env_seconds[_environment_key(shot)] += overlap
            camera_seconds[_camera_key(shot)] += overlap
            semantic_seconds[_semantic_key(shot)] += overlap

        for kind, bucket in (
            ("ENVIRONMENT_DOMINANCE", env_seconds),
            ("CAMERA_COMPOSITION_DOMINANCE", camera_seconds),
            ("SEMANTIC_FUNCTION_DOMINANCE", semantic_seconds),
        ):
            if not bucket:
                continue
            value, seconds = max(bucket.items(), key=lambda item: item[1])
            if not value:
                continue
            ratio = seconds / total
            if ratio >= DOMINANCE_WARNING_RATIO:
                warnings.append(
                    {
                        "kind": kind,
                        "value": value,
                        "window_seconds": [round(start, 3), round(end, 3)],
                        "dominance_ratio": round(ratio, 4),
                        "dominant_seconds": round(seconds, 3),
                    }
                )
        start += WINDOW_SECONDS
    return warnings


def simulate(
    *,
    state_path: Path,
    contracts_path: Path,
) -> dict[str, Any]:
    state = load_state(state_path)
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
    shots = sorted(
        validated["validated_shots"],
        key=lambda s: (int(s["order"]), float(s["audio_start"])),
    )

    timing_data = json.loads(timing_path.read_text(encoding="utf-8-sig"))
    words = [
        word
        for sentence in timing_data["sentences"]
        for word in sentence.get("words", [])
    ]
    if not words:
        raise CoverageSimulationError("TIMING_WORDS_REQUIRED")

    speech_start = min(float(w["start"]) for w in words)
    speech_end = max(float(w["end"]) for w in words)

    intervals = [
        (float(shot["audio_start"]), float(shot["audio_end"]))
        for shot in shots
    ]
    merged = _merge_intervals(intervals)
    gaps = _coverage_gaps(speech_start, speech_end, merged)
    hard_gaps = [
        (a, b)
        for a, b in gaps
        if (b - a) > MAX_ALLOWED_VISUAL_GAP_SECONDS
    ]

    uncovered_words = []
    for word in words:
        ws, we = float(word["start"]), float(word["end"])
        word_duration = max(0.001, we - ws)
        covered_seconds = 0.0
        for a, b in merged:
            covered_seconds += max(0.0, min(we, b) - max(ws, a))
        ratio = min(1.0, covered_seconds / word_duration)
        if ratio < 0.98:
            uncovered_words.append(
                {
                    "word_id": word.get("word_id"),
                    "text": word.get("text"),
                    "start": round(ws, 3),
                    "end": round(we, 3),
                    "coverage_ratio": round(ratio, 4),
                }
            )

    domain_duration = max(0.001, speech_end - speech_start)
    covered_duration = domain_duration - _duration(gaps)
    visual_coverage_ratio = max(0.0, min(1.0, covered_duration / domain_duration))

    generation_counts = Counter(shot["generation_class"] for shot in shots)
    planned_video_seconds = sum(
        float(s["audio_end"]) - float(s["audio_start"]) for s in shots
    )
    # Planning effort proxy, not provider billing:
    # A = first frame + last frame + video
    # B = first frame + video
    # C = video only
    planned_generation_units = (
        generation_counts.get("A_FIRST_LAST", 0) * 3
        + generation_counts.get("B_FIRST_ONLY", 0) * 2
        + generation_counts.get("C_DIRECT", 0)
    )

    reference_usage: Counter[str] = Counter()
    reference_shots: dict[str, list[str]] = defaultdict(list)
    for shot in shots:
        for ref_id in _extract_reference_ids(shot):
            reference_usage[ref_id] += 1
            reference_shots[ref_id].append(shot["shot_id"])

    reuse_warnings = [
        {
            "reference_id": ref_id,
            "usage_count": count,
            "shot_ids": reference_shots[ref_id],
        }
        for ref_id, count in sorted(
            reference_usage.items(),
            key=lambda item: (-item[1], item[0]),
        )
        if count >= REFERENCE_REUSE_WARNING_COUNT
    ]

    diversity_warnings = []
    diversity_warnings.extend(
        _run_warnings(shots, _environment_key, "CONSECUTIVE_ENVIRONMENT_REPETITION")
    )
    diversity_warnings.extend(
        _run_warnings(shots, _camera_key, "CONSECUTIVE_CAMERA_REPETITION")
    )
    diversity_warnings.extend(
        _run_warnings(shots, _semantic_key, "CONSECUTIVE_SEMANTIC_FUNCTION_REPETITION")
    )
    diversity_warnings.extend(
        _window_dominance(shots, speech_start, speech_end)
    )

    long_shot_warnings = [
        {
            "shot_id": shot["shot_id"],
            "duration_seconds": round(
                float(shot["audio_end"]) - float(shot["audio_start"]), 3
            ),
        }
        for shot in shots
        if (float(shot["audio_end"]) - float(shot["audio_start"]))
        >= LONG_SHOT_WARNING_SECONDS
    ]

    hard_failures = []
    if hard_gaps:
        hard_failures.append("ZERO_COVERAGE_TIMELINE_GAPS")
    if uncovered_words:
        hard_failures.append("UNCOVERED_NARRATION_WORDS")

    status = (
        "BLOCKED_ZERO_COVERAGE"
        if hard_failures
        else "PASS_READY_FOR_HUMAN_PRE_GENERATION_REVIEW"
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now(),
        "episode_id": state["episode_id"],
        "canonical_stage": state["stage"],
        "status": status,
        "hard_failures": hard_failures,
        "coverage": {
            "speech_domain_seconds": [
                round(speech_start, 3),
                round(speech_end, 3),
            ],
            "speech_domain_duration_seconds": round(domain_duration, 3),
            "covered_duration_seconds": round(covered_duration, 3),
            "visual_coverage_ratio": round(visual_coverage_ratio, 6),
            "allowed_gap_seconds": MAX_ALLOWED_VISUAL_GAP_SECONDS,
            "all_gaps": [
                {
                    "start": round(a, 3),
                    "end": round(b, 3),
                    "duration": round(b - a, 3),
                }
                for a, b in gaps
            ],
            "hard_gaps": [
                {
                    "start": round(a, 3),
                    "end": round(b, 3),
                    "duration": round(b - a, 3),
                }
                for a, b in hard_gaps
            ],
            "uncovered_words": uncovered_words,
        },
        "production_forecast": {
            "shot_count": len(shots),
            "planned_video_seconds_sum": round(planned_video_seconds, 3),
            "generation_class_counts": dict(sorted(generation_counts.items())),
            "planned_generation_units_proxy": planned_generation_units,
            "proxy_definition": {
                "A_FIRST_LAST": 3,
                "B_FIRST_ONLY": 2,
                "C_DIRECT": 1,
            },
            "note": "PROXY_ONLY_NOT_PROVIDER_COST_OR_BILLING",
        },
        "reuse": {
            "unique_reference_count": len(reference_usage),
            "reference_usage": dict(sorted(reference_usage.items())),
            "warnings": reuse_warnings,
        },
        "diversity": {
            "window_seconds": WINDOW_SECONDS,
            "dominance_warning_ratio": DOMINANCE_WARNING_RATIO,
            "warnings": diversity_warnings,
            "long_shot_warnings": long_shot_warnings,
        },
        "inputs": {
            "contracts_path": str(contracts_path.resolve()),
            "contracts_sha256": sha256_file(contracts_path),
            "narration_sha256": narration["sha256"],
            "audio_sha256": audio["sha256"],
            "timing_sha256": timing["sha256"],
        },
        "network_calls": 0,
        "provider_calls": 0,
        "paid_calls": 0,
    }


def render_html(report: dict[str, Any]) -> str:
    coverage = report["coverage"]
    forecast = report["production_forecast"]
    reuse = report["reuse"]
    diversity = report["diversity"]

    def esc(x: Any) -> str:
        return html.escape(str(x))

    def rows(items: list[dict[str, Any]], fields: list[str]) -> str:
        if not items:
            return "<tr><td colspan='%d'>لا توجد</td></tr>" % len(fields)
        return "".join(
            "<tr>" + "".join(f"<td>{esc(item.get(field, ''))}</td>" for field in fields) + "</tr>"
            for item in items
        )

    css = """
    body{font-family:Tahoma,Arial,sans-serif;background:#f5f5f5;color:#171717;margin:0}
    main{max-width:1150px;margin:auto;padding:28px}
    .card{background:#fff;border:1px solid #ddd;border-radius:12px;padding:18px;margin:16px 0}
    .ok{border-right:6px solid #2d7d46}.bad{border-right:6px solid #b42318}.warn{border-right:6px solid #c27a00}
    .grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}
    .kv{background:#fafafa;border:1px solid #e5e5e5;border-radius:8px;padding:10px}
    .k{font-size:12px;color:#666}.v{font-weight:700;font-size:18px}
    table{width:100%;border-collapse:collapse}th,td{border:1px solid #ddd;padding:8px;text-align:right}th{background:#f0f0f0}
    pre{white-space:pre-wrap;direction:ltr;text-align:left;background:#f7f7f7;padding:12px;border-radius:8px}
    @media(max-width:800px){.grid{grid-template-columns:1fr}}
    """
    status_class = "ok" if report["status"].startswith("PASS") else "bad"

    gap_rows = rows(coverage["hard_gaps"], ["start", "end", "duration"])
    uncovered_rows = rows(
        coverage["uncovered_words"],
        ["word_id", "text", "start", "end", "coverage_ratio"],
    )

    div_rows = rows(
        diversity["warnings"],
        ["kind", "value", "window_seconds", "shot_count", "elapsed_seconds", "dominance_ratio"],
    )
    reuse_rows = rows(reuse["warnings"], ["reference_id", "usage_count", "shot_ids"])
    long_rows = rows(diversity["long_shot_warnings"], ["shot_id", "duration_seconds"])

    return f"""<!doctype html>
<html lang="ar" dir="rtl">
<head><meta charset="utf-8"><title>{esc(report["episode_id"])} Coverage / Diversity / Reuse Simulation</title><style>{css}</style></head>
<body><main>
<section class="card {status_class}">
<h1>سراج — محاكاة التغطية والتنوع وإعادة الاستخدام قبل التوليد</h1>
<p><strong>الحالة:</strong> {esc(report["status"])}</p>
<div class="grid">
<div class="kv"><div class="k">Coverage</div><div class="v">{coverage["visual_coverage_ratio"]*100:.2f}%</div></div>
<div class="kv"><div class="k">Shots</div><div class="v">{forecast["shot_count"]}</div></div>
<div class="kv"><div class="k">Generation Units Proxy</div><div class="v">{forecast["planned_generation_units_proxy"]}</div></div>
<div class="kv"><div class="k">Class A</div><div class="v">{forecast["generation_class_counts"].get("A_FIRST_LAST",0)}</div></div>
<div class="kv"><div class="k">Class B</div><div class="v">{forecast["generation_class_counts"].get("B_FIRST_ONLY",0)}</div></div>
<div class="kv"><div class="k">Class C</div><div class="v">{forecast["generation_class_counts"].get("C_DIRECT",0)}</div></div>
</div>
</section>

<section class="card">
<h2>Hard Coverage Gaps</h2>
<table><thead><tr><th>Start</th><th>End</th><th>Duration</th></tr></thead>
<tbody>{gap_rows}</tbody></table>

<h2>Uncovered Narration Words</h2>
<table><thead><tr><th>Word ID</th><th>Text</th><th>Start</th><th>End</th><th>Coverage</th></tr></thead>
<tbody>{uncovered_rows}</tbody></table>
</section>

<section class="card warn">
<h2>Diversity Warnings</h2>
<table><thead><tr><th>Kind</th><th>Value</th><th>Window</th><th>Shots</th><th>Elapsed</th><th>Dominance</th></tr></thead>
<tbody>{div_rows}</tbody></table>

<h2>Long Shot Warnings</h2>
<table><thead><tr><th>Shot</th><th>Duration</th></tr></thead>
<tbody>{long_rows}</tbody></table>
</section>

<section class="card warn">
<h2>Reuse Warnings</h2>
<table><thead><tr><th>Reference</th><th>Count</th><th>Shots</th></tr></thead>
<tbody>{reuse_rows}</tbody></table>
</section>

<section class="card">
<h2>Production Forecast</h2>
<pre>{esc(json.dumps(forecast, ensure_ascii=False, indent=2, sort_keys=True))}</pre>
</section>

<section class="card">
<p>Coverage failures are hard blockers. Diversity/reuse findings are warnings for human pre-generation review, not constitutional hard failures.</p>
</section>
</main></body></html>
"""


def run_and_write(
    *,
    state_path: Path,
    contracts_path: Path,
    output_json: Path,
    output_html: Path,
) -> dict[str, Any]:
    report = simulate(state_path=state_path, contracts_path=contracts_path)
    atomic_write_json(output_json, report)
    atomic_write_text(output_html, render_html(report))
    return report


def cli() -> int:
    p = argparse.ArgumentParser(description="SIRAJ coverage/diversity/reuse simulation v1")
    sub = p.add_subparsers(dest="cmd", required=True)

    p_sim = sub.add_parser("simulate")
    p_sim.add_argument("--state", required=True)
    p_sim.add_argument("--contracts", required=True)
    p_sim.add_argument("--output-json", required=True)
    p_sim.add_argument("--output-html", required=True)

    args = p.parse_args()

    if args.cmd == "simulate":
        report = run_and_write(
            state_path=Path(args.state),
            contracts_path=Path(args.contracts),
            output_json=Path(args.output_json),
            output_html=Path(args.output_html),
        )
        print("STATUS=" + report["status"])
        print("COVERAGE_RATIO=" + str(report["coverage"]["visual_coverage_ratio"]))
        print("SHOT_COUNT=" + str(report["production_forecast"]["shot_count"]))
        print("GENERATION_UNITS_PROXY=" + str(report["production_forecast"]["planned_generation_units_proxy"]))
        print("DIVERSITY_WARNINGS=" + str(len(report["diversity"]["warnings"])))
        print("REUSE_WARNINGS=" + str(len(report["reuse"]["warnings"])))
        print("OUTPUT_JSON=" + str(Path(args.output_json).resolve()))
        print("OUTPUT_HTML=" + str(Path(args.output_html).resolve()))
        return 0 if report["status"].startswith("PASS") else 2

    raise AssertionError(args.cmd)


if __name__ == "__main__":
    raise SystemExit(cli())
