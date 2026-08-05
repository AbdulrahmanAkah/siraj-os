from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

HARD_CAP_USD = 40.0
DEFAULT_EPISODE_ID = "episode-001-adam"
ORCHESTRATOR_STATE_REL = Path(
    "projects/_orchestrator/autonomous-episode-orchestrator-state-v1.json"
)

CATEGORY_DEFINITIONS = (
    ("OPENAI_LUNA", "GPT-5.6 Luna / OpenAI"),
    ("RUNWARE_IMAGES", "Runware — الصور"),
    ("RUNWARE_VIDEO", "Runware — الفيديو"),
    ("ELEVENLABS_TTS", "ElevenLabs — التعليق الصوتي"),
    ("SOUND_EFFECTS", "المؤثرات الصوتية"),
    ("OTHER", "أخرى"),
)
CATEGORY_KEYS = {item[0] for item in CATEGORY_DEFINITIONS}


@dataclass(frozen=True, slots=True)
class CostCategorySnapshot:
    category: str
    label_ar: str
    actual_cost_usd: float
    estimated_cost_usd: float
    recorded_total_usd: float
    paid_operations: int


@dataclass(frozen=True, slots=True)
class EpisodeCostBreakdown:
    episode_id: str
    hard_cap_usd: float
    actual_cost_usd: float
    estimated_cost_usd: float
    recorded_total_usd: float
    remaining_usd: float
    paid_operations: int
    unclassified_operations: int
    categories: tuple[CostCategorySnapshot, ...]
    receipt_paths: tuple[Path, ...]
    pending_scope_estimated_usd: float


def _read_json_if_possible(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _active_episode_id(repo_root: Path) -> str:
    repo = repo_root.resolve()
    state = _read_json_if_possible(repo / ORCHESTRATOR_STATE_REL)
    if state is not None:
        candidate = state.get("current_episode_id")
        if isinstance(candidate, str) and candidate.strip():
            episode_id = candidate.strip()
            if (repo / "projects" / episode_id).is_dir():
                return episode_id
    return DEFAULT_EPISODE_ID


def _pending_scope_estimated_usd(repo_root: Path) -> float:
    state = _read_json_if_possible(
        repo_root.resolve() / ORCHESTRATOR_STATE_REL
    )
    if state is None:
        return 0.0
    usage = state.get("active_scope_luna_usage")
    if not isinstance(usage, Mapping):
        return 0.0
    value = usage.get("estimated_text_cost_usd", 0.0)
    if not isinstance(value, (int, float)) or float(value) < 0:
        return 0.0
    return round(float(value), 8)


def _explicit_category(record: Mapping[str, Any]) -> str | None:
    value = str(record.get("cost_category", "")).strip().upper()
    return value if value in CATEGORY_KEYS else None


def _classification_text(path: Path, record: Mapping[str, Any]) -> str:
    fields = (
        "provider",
        "service",
        "task_type",
        "taskType",
        "media_type",
        "model",
        "schema_version",
        "cost_category",
    )
    values = [str(path).lower()]
    for field in fields:
        value = record.get(field)
        if value is not None:
            values.append(str(value).lower())
    return " ".join(values)


def _classify(path: Path, record: Mapping[str, Any]) -> str:
    explicit = _explicit_category(record)
    if explicit is not None:
        return explicit

    text = _classification_text(path, record)
    if "openai" in text or "luna" in text or "gpt-5.6" in text:
        return "OPENAI_LUNA"
    if "elevenlabs" in text or "text-to-speech" in text or "tts" in text:
        return "ELEVENLABS_TTS"
    if "sound-effect" in text or "sound_effect" in text or "sfx" in text:
        return "SOUND_EFFECTS"
    if "runware" in text or "videoinference" in text or "imageinference" in text:
        if (
            "image" in text
            and "video" not in text
            and "videoinference" not in text
        ):
            return "RUNWARE_IMAGES"
        return "RUNWARE_VIDEO"
    if "video" in text:
        return "RUNWARE_VIDEO"
    if "image" in text or "visual" in text:
        return "RUNWARE_IMAGES"
    return "OTHER"


def _number(record: Mapping[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = record.get(key)
        if isinstance(value, (int, float)) and float(value) >= 0:
            return float(value)
    return None


def _cost_pair(record: Mapping[str, Any]) -> tuple[float, float]:
    actual = _number(record, "actual_cost_usd", "provider_cost_usd")
    estimated = _number(
        record,
        "estimated_cost_usd",
        "estimated_text_cost_usd",
    )
    if actual is not None:
        return actual, 0.0
    if estimated is not None:
        return 0.0, estimated
    return 0.0, 0.0


def _identity(path: Path, record: Mapping[str, Any], repo: Path) -> str:
    for key in (
        "task_uuid",
        "taskUUID",
        "provider_response_id",
        "response_id",
        "receipt_id",
    ):
        value = record.get(key)
        if value is not None and str(value).strip():
            return f"{key}:{str(value).strip()}"
    return "path:" + str(path.relative_to(repo)).replace("\\", "/")


def scan_episode_costs(
    repo_root: Path,
    episode_id: str | None = None,
) -> EpisodeCostBreakdown:
    repo = repo_root.resolve()
    resolved_episode_id = episode_id or _active_episode_id(repo)
    episode_root = repo / "projects" / resolved_episode_id

    totals: dict[str, dict[str, float | int]] = {
        key: {"actual": 0.0, "estimated": 0.0, "operations": 0}
        for key, _ in CATEGORY_DEFINITIONS
    }
    seen: set[str] = set()
    receipt_paths: list[Path] = []
    unclassified = 0

    if episode_root.is_dir():
        candidates = sorted(
            path
            for path in episode_root.rglob("*.json")
            if "receipt" in path.name.lower()
        )
    else:
        candidates = []

    for path in candidates:
        record = _read_json_if_possible(path)
        if record is None:
            continue
        actual, estimated = _cost_pair(record)
        if actual <= 0 and estimated <= 0:
            continue
        identity = _identity(path, record, repo)
        if identity in seen:
            continue
        seen.add(identity)
        category = _classify(path, record)
        bucket = totals[category]
        bucket["actual"] = float(bucket["actual"]) + actual
        bucket["estimated"] = float(bucket["estimated"]) + estimated
        bucket["operations"] = int(bucket["operations"]) + 1
        if category == "OTHER":
            unclassified += 1
        receipt_paths.append(path)

    categories: list[CostCategorySnapshot] = []
    actual_total = 0.0
    estimated_total = 0.0
    operations = 0
    for key, label in CATEGORY_DEFINITIONS:
        bucket = totals[key]
        actual = round(float(bucket["actual"]), 8)
        estimated = round(float(bucket["estimated"]), 8)
        count = int(bucket["operations"])
        categories.append(
            CostCategorySnapshot(
                category=key,
                label_ar=label,
                actual_cost_usd=actual,
                estimated_cost_usd=estimated,
                recorded_total_usd=round(actual + estimated, 8),
                paid_operations=count,
            )
        )
        actual_total += actual
        estimated_total += estimated
        operations += count

    actual_total = round(actual_total, 8)
    estimated_total = round(estimated_total, 8)
    recorded_total = round(actual_total + estimated_total, 8)
    remaining = round(max(0.0, HARD_CAP_USD - recorded_total), 8)

    return EpisodeCostBreakdown(
        episode_id=resolved_episode_id,
        hard_cap_usd=HARD_CAP_USD,
        actual_cost_usd=actual_total,
        estimated_cost_usd=estimated_total,
        recorded_total_usd=recorded_total,
        remaining_usd=remaining,
        paid_operations=operations,
        unclassified_operations=unclassified,
        categories=tuple(categories),
        receipt_paths=tuple(receipt_paths),
        pending_scope_estimated_usd=_pending_scope_estimated_usd(repo),
    )


def current_episode_cost_breakdown(repo_root: Path) -> EpisodeCostBreakdown:
    return scan_episode_costs(repo_root)
