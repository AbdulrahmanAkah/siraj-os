"""Deterministic Short-to-Longform conversion direction.

This module is deliberately independent from the Shorts engine.  It consumes
the engine's existing candidate contract (or its serialized mapping), adds
conversion-specific signals and gates, and returns immutable, hash-friendly
plain data.  It does not create narration, captions, CTA text, provider
requests, renders, or publication actions.

The director is extractive by construction: endpoint variants may only be
assembled from explicitly supplied source segments at safe boundaries.  A
missing or ambiguous source signal is never filled by a generated sentence or
an assumed episode conclusion.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = "siraj-shorts-conversion-director-v1"
DIRECTOR_VERSION = "1.0.0"

CONVERSION_SIGNAL_FIELDS = (
    "SHORT_QUALITY",
    "HOOK_STRENGTH",
    "RETENTION_POTENTIAL",
    "STANDALONE_VALUE",
    "OPEN_LOOP_STRENGTH",
    "LONGFORM_CONVERSION_SCORE",
    "SPOILER_COST",
    "PAYOFF_DISCLOSURE_LEVEL",
    "PAYOFF_OVERDISCLOSURE",
    "WITHHELD_PAYOFF_SUMMARY",
    "CONVERSION_BRIDGE_STATUS",
    "CONVERSION_BRIDGE_REASON",
    "SOURCE_EPISODE_ID",
)

CONVERSION_GATE_NAMES = (
    "FULL_PAYOFF_ALREADY_REVEALED",
    "SHORT_SUMMARIZES_WHOLE_ANSWER",
    "NO_REASON_TO_WATCH_LONGFORM",
    "MISLEADING_OPEN_LOOP",
    "CONTEXT_REQUIRED_BUT_MISSING",
    "FABRICATED_CURIOSITY",
)

DEFAULT_THRESHOLDS = {
    # Audience-growth teaser policy: these are ranking/advisory signals.
    "full_payoff": 1.0,
    "whole_answer": 1.0,
    "no_reason_open_loop": 0.0,
    "no_reason_payoff": 1.0,
    "context_dependence": 1.0,
    "overdisclosure_spoiler": 1.0,
    "overdisclosure_payoff": 1.0,
    "minimum_open_loop": 0.0,
}

_MISSING = object()


class ConversionDirectorError(ValueError):
    """Base error for malformed conversion-director inputs."""


class ConversionDirectorBlocked(ConversionDirectorError):
    """Raised only by strict callers that request fail-closed exceptions."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_value(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value)).hexdigest()


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        result = to_dict()
        if isinstance(result, Mapping):
            return result
    # Existing frozen dataclasses with slots do not expose __dict__.  Read
    # only the known public candidate fields in that case.
    fields = (
        "candidate_id",
        "episode_id",
        "source_episode_id",
        "text",
        "total_score",
        "source_episode_sha256",
        "context_dependence_score",
        "missing_context_items",
        "score_breakdown",
        "longform_conversion_score",
        "spoiler_cost",
        "payoff_disclosure_level",
        "cta_plan",
        "hard_gate_results",
        "metadata",
        "conversion_signals",
        "conversion_gates",
        "source_claim_ids",
        "claim_ids",
        "beat_ids",
        "payoff_claim_ids",
        "endpoint_variants",
        "segments",
        "source_segments",
    )
    result = {name: getattr(value, name) for name in fields if hasattr(value, name)}
    if result:
        return result
    raise ConversionDirectorError("CANDIDATE_MAPPING_REQUIRED")


def _first(mapping: Mapping[str, Any], names: Iterable[str], default: Any = _MISSING) -> Any:
    containers: list[Mapping[str, Any]] = [mapping]
    for container_name in (
        "conversion_signals",
        "conversion",
        "conversion_gates",
        "metadata",
        "editorial_metadata",
        "source_metadata",
    ):
        container = mapping.get(container_name)
        if isinstance(container, Mapping):
            containers.append(container)
    for name in names:
        for container in containers:
            if name in container and container[name] is not None:
                return container[name]
    return default


def _first_gate(mapping: Mapping[str, Any], gate_name: str) -> Any:
    lower = gate_name.lower()
    aliases = (gate_name, gate_name.upper(), lower, gate_name.replace("_", "-"), lower.replace("_", "-"))
    containers: list[Mapping[str, Any]] = [mapping]
    for container_name in ("conversion_gates", "conversion", "metadata", "hard_gate_results"):
        container = mapping.get(container_name)
        if isinstance(container, Mapping):
            containers.append(container)
    for container in containers:
        for alias in aliases:
            if alias in container:
                return container[alias]
    return _MISSING


def _dimension_value(value: Any) -> Any:
    if isinstance(value, Mapping) and "value" in value:
        return value["value"]
    if hasattr(value, "value"):
        return getattr(value, "value")
    return value


def _score_breakdown_value(candidate: Mapping[str, Any], names: Iterable[str]) -> Any:
    breakdown = candidate.get("score_breakdown")
    if not isinstance(breakdown, Mapping):
        return _MISSING
    for name in names:
        if name in breakdown:
            return _dimension_value(breakdown[name])
    return _MISSING


def _number(value: Any, name: str, *, default: float | None = None) -> float:
    if value is _MISSING or value is None:
        if default is not None:
            return default
        raise ConversionDirectorError(f"{name}:NUMBER_REQUIRED")
    if isinstance(value, bool):
        raise ConversionDirectorError(f"{name}:NUMBER_REQUIRED")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ConversionDirectorError(f"{name}:NUMBER_REQUIRED") from exc
    if not math.isfinite(result):
        raise ConversionDirectorError(f"{name}:FINITE_REQUIRED")
    if result < 0.0 or result > 1.0:
        raise ConversionDirectorError(f"{name}:RANGE_0_1_REQUIRED")
    return result


def _time_number(value: Any, name: str) -> float:
    if value is None or value is _MISSING or isinstance(value, bool):
        raise ConversionDirectorError(f"{name}:NUMBER_REQUIRED")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ConversionDirectorError(f"{name}:NUMBER_REQUIRED") from exc
    if not math.isfinite(result) or result < 0.0:
        raise ConversionDirectorError(f"{name}:FINITE_NONNEGATIVE_REQUIRED")
    return result


def _bool(value: Any) -> bool | None:
    if value is _MISSING or value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().upper()
        if normalized in {"TRUE", "YES", "PASS", "REJECT", "FAIL", "BLOCKED"}:
            return True
        if normalized in {"FALSE", "NO", "NONE", "OFF", "CLEAR"}:
            return False
    return None


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _candidate_id(candidate: Mapping[str, Any]) -> str:
    value = _first(candidate, ("candidate_id", "short_id", "id"), default="")
    return _clean_text(value) or "UNNAMED_CANDIDATE"


def _source_episode_id(candidate: Mapping[str, Any], explicit: str | None) -> str:
    value = explicit if explicit is not None else _first(candidate, ("SOURCE_EPISODE_ID", "source_episode_id", "episode_id"), default="")
    result = _clean_text(value)
    if not result or result.upper() in {"UNKNOWN", "UNSET", "DEFAULT"}:
        raise ConversionDirectorError("SOURCE_EPISODE_ID:REQUIRED")
    return result


def _explicit_true(candidate: Mapping[str, Any], names: Iterable[str]) -> tuple[bool, list[str]]:
    evidence: list[str] = []
    for name in names:
        value = _first_gate(candidate, name)
        if isinstance(value, Mapping):
            status = str(value.get("status", value.get("decision", ""))).strip().upper()
            value = status in {"FAIL", "REJECT", "REJECTED", "BLOCKED", "TRUE"}
        parsed = _bool(value)
        if parsed is True:
            evidence.append(name)
    return bool(evidence), evidence


def _gate_result(name: str, failed: bool, evidence: Iterable[str], *, impact: str = "NONE") -> "GateResult":
    evidence_tuple = tuple(sorted({str(item) for item in evidence if str(item)}))
    return GateResult(
        gate_id=name,
        status="FAIL" if failed else "PASS",
        code=name if failed else None,
        evidence=evidence_tuple,
        impact=impact if failed else "NONE",
    )


@dataclass(frozen=True, slots=True)
class GateResult:
    gate_id: str
    status: str
    code: str | None
    evidence: tuple[str, ...]
    impact: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "status": self.status,
            "code": self.code,
            "evidence": list(self.evidence),
            "impact": self.impact,
        }


@dataclass(frozen=True, slots=True)
class ConversionEvaluation:
    """A serialized, deterministic evaluation of one source-derived candidate."""

    candidate_id: str
    source_episode_id: str
    signals: Mapping[str, Any]
    gates: Mapping[str, GateResult]
    status: str
    rank_score: float
    rejection_reasons: tuple[str, ...]
    source_provenance: Mapping[str, Any]
    director_version: str = DIRECTOR_VERSION

    def __getitem__(self, key: str) -> Any:
        return self.to_dict()[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.to_dict().get(key, default)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "director_version": self.director_version,
            "candidate_id": self.candidate_id,
            "signals": dict(self.signals),
            "gates": {key: value.to_dict() for key, value in self.gates.items()},
            "status": self.status,
            "rank_score": round(float(self.rank_score), 6),
            "rejection_reasons": list(self.rejection_reasons),
            "source_provenance": dict(self.source_provenance),
            "evaluation_sha256": "",
        }
        result.update(dict(self.signals))
        result["SOURCE_EPISODE_ID"] = self.source_episode_id
        unsigned = dict(result)
        unsigned["evaluation_sha256"] = ""
        result["evaluation_sha256"] = _sha256_value(unsigned)
        return result


def _derive_signal(candidate: Mapping[str, Any], aliases: Iterable[str], breakdown_aliases: Iterable[str], *, default: float | None = None, required: bool = False, name: str) -> float:
    value = _first(candidate, aliases, default=_MISSING)
    if value is _MISSING:
        value = _score_breakdown_value(candidate, breakdown_aliases)
    if value is _MISSING and required:
        raise ConversionDirectorError(f"{name}:EVIDENCE_REQUIRED")
    return _number(value, name, default=default)


def _extract_signal_values(candidate: Mapping[str, Any], thresholds: Mapping[str, float]) -> tuple[dict[str, Any], dict[str, Any]]:
    hook = _derive_signal(
        candidate,
        ("HOOK_STRENGTH", "hook_strength", "hook_score"),
        ("HOOK_STRENGTH", "HOOK"),
        default=0.0,
        name="HOOK_STRENGTH",
    )
    retention = _derive_signal(
        candidate,
        ("RETENTION_POTENTIAL", "retention_potential", "retention_score"),
        ("RETENTION_POTENTIAL",),
        default=max(hook, _number(_first(candidate, ("surprise_signal",), default=0.0), "surprise_signal")),
        name="RETENTION_POTENTIAL",
    )
    standalone = _derive_signal(
        candidate,
        ("STANDALONE_VALUE", "standalone_value", "standalone_potential"),
        ("STANDALONE_VALUE", "STANDALONE_CLARITY"),
        default=1.0 - _number(_first(candidate, ("context_dependence_score",), default=0.0), "context_dependence_score"),
        name="STANDALONE_VALUE",
    )
    context_dependence = _number(_first(candidate, ("context_dependence_score",), default=1.0 - standalone), "context_dependence_score")
    curiosity_value = _first(candidate, ("curiosity_signal",), default=_MISSING)
    if curiosity_value is _MISSING:
        curiosity_value = _score_breakdown_value(candidate, ("CURIOSITY", "OPEN_LOOP_STRENGTH"))
    curiosity = _number(curiosity_value, "curiosity_signal", default=0.0)
    payoff = _derive_signal(
        candidate,
        ("PAYOFF_DISCLOSURE_LEVEL", "payoff_disclosure_level", "payoff_coverage"),
        ("PAYOFF_DISCLOSURE_LEVEL",),
        default=_number(_first(candidate, ("payoff_signal",), default=0.0), "payoff_signal"),
        name="PAYOFF_DISCLOSURE_LEVEL",
    )
    spoiler = _derive_signal(
        candidate,
        ("SPOILER_COST", "spoiler_cost"),
        ("SPOILER_COST",),
        default=payoff,
        name="SPOILER_COST",
    )
    open_loop_value = _first(candidate, ("OPEN_LOOP_STRENGTH", "open_loop_strength"), default=_MISSING)
    if open_loop_value is _MISSING:
        cta_plan = candidate.get("cta_plan")
        if isinstance(cta_plan, Mapping) and cta_plan.get("mode") in {"NATURAL_OPEN_LOOP", "EXISTING_SOURCE_CONTINUATION"}:
            open_loop_value = max(curiosity, 1.0 - payoff)
        else:
            open_loop_value = curiosity
    open_loop = _number(open_loop_value, "OPEN_LOOP_STRENGTH")
    longform_conversion = _derive_signal(
        candidate,
        ("LONGFORM_CONVERSION_SCORE", "longform_conversion_score"),
        ("LONGFORM_CONVERSION_SCORE", "LONGFORM_CONVERSION_POTENTIAL"),
        default=max(0.0, min(1.0, 0.45 * open_loop + 0.35 * (1.0 - spoiler) + 0.20 * standalone)),
        name="LONGFORM_CONVERSION_SCORE",
    )
    short_quality = _derive_signal(
        candidate,
        ("SHORT_QUALITY", "short_quality", "total_score"),
        ("SHORT_QUALITY",),
        default=(hook + retention + standalone) / 3.0,
        name="SHORT_QUALITY",
    )
    overdisclosure_value = _first(candidate, ("PAYOFF_OVERDISCLOSURE", "payoff_overdisclosure"), default=_MISSING)
    overdisclosure = _bool(overdisclosure_value)
    if overdisclosure is None:
        overdisclosure = spoiler >= thresholds["overdisclosure_spoiler"] or payoff >= thresholds["overdisclosure_payoff"]
    summary_value = _first(
        candidate,
        ("WITHHELD_PAYOFF_SUMMARY", "withheld_payoff_summary", "withheld_payoff"),
        default=_MISSING,
    )
    if summary_value is _MISSING:
        withheld_summary: Mapping[str, Any] = {
            "status": "PRESENT" if open_loop >= thresholds["minimum_open_loop"] and not overdisclosure else "NOT_ESTABLISHED",
            "source": "SOURCE_STRUCTURE_SIGNAL" if open_loop >= thresholds["minimum_open_loop"] and not overdisclosure else "NO_SOURCE_EVIDENCE",
            "text": None,
        }
    elif isinstance(summary_value, Mapping):
        withheld_summary = dict(summary_value)
    else:
        withheld_summary = {"status": "PRESENT", "source": "SOURCE_DERIVED_FIELD", "text": str(summary_value)}
    signals = {
        "SHORT_QUALITY": round(short_quality, 6),
        "HOOK_STRENGTH": round(hook, 6),
        "RETENTION_POTENTIAL": round(retention, 6),
        "STANDALONE_VALUE": round(standalone, 6),
        "OPEN_LOOP_STRENGTH": round(open_loop, 6),
        "LONGFORM_CONVERSION_SCORE": round(longform_conversion, 6),
        "SPOILER_COST": round(spoiler, 6),
        "PAYOFF_DISCLOSURE_LEVEL": round(payoff, 6),
        "PAYOFF_OVERDISCLOSURE": bool(overdisclosure),
        "WITHHELD_PAYOFF_SUMMARY": withheld_summary,
    }
    context_evidence = []
    missing_context = candidate.get("missing_context_items")
    if isinstance(missing_context, Sequence) and not isinstance(missing_context, (str, bytes, bytearray)):
        context_evidence.extend(str(item) for item in missing_context if str(item))
    if context_dependence > thresholds["context_dependence"]:
        context_evidence.append(f"context_dependence_score={context_dependence:.6f}")
    explicit_full, full_evidence = _explicit_true(candidate, ("full_payoff_already_revealed", "full_payoff", "reveals_full_answer"))
    explicit_summary, summary_evidence = _explicit_true(candidate, ("short_summarizes_whole_answer", "summarizes_whole_answer", "whole_answer_summary"))
    explicit_no_reason, no_reason_evidence = _explicit_true(candidate, ("no_reason_to_watch_longform", "no_longform_reason"))
    explicit_misleading, misleading_evidence = _explicit_true(candidate, ("misleading_open_loop", "false_hook", "misleading_cold_open", "open_loop_is_false"))
    explicit_context, explicit_context_evidence = _explicit_true(candidate, ("context_required_but_missing", "requires_missing_context"))
    explicit_fabricated, fabricated_evidence = _explicit_true(candidate, ("fabricated_curiosity", "invented_curiosity", "invented_hook"))
    if not explicit_misleading:
        hard_gate_results = candidate.get("hard_gate_results")
        hook_gate = hard_gate_results.get("HOOK_INTEGRITY") if isinstance(hard_gate_results, Mapping) else None
        if isinstance(hook_gate, Mapping) and str(hook_gate.get("status", "")).upper() in {"FAIL", "REJECT", "BLOCKED"}:
            explicit_misleading = True
            misleading_evidence.append("hard_gate_results.HOOK_INTEGRITY")
    cta = candidate.get("cta_plan")
    invented_cta = False
    invented_cta_evidence: list[str] = []
    if isinstance(cta, Mapping):
        for key in ("invented", "generated", "new_narration", "new_text", "promotional", "subscribe_text", "source_derived"):
            parsed = _bool(cta.get(key))
            if key == "source_derived" and parsed is False:
                invented_cta = True
                invented_cta_evidence.append(f"cta_plan.{key}=FALSE")
            elif key != "source_derived" and parsed is True:
                invented_cta = True
                invented_cta_evidence.append(f"cta_plan.{key}=TRUE")
        mode = str(cta.get("mode", "")).upper()
        if mode in {"GENERATED_CTA", "PROMOTIONAL_CTA", "INVENTED", "NEW_NARRATION"}:
            invented_cta = True
            invented_cta_evidence.append(f"cta_plan.mode={mode}")
    if invented_cta:
        explicit_fabricated = True
        fabricated_evidence.extend(invented_cta_evidence)
    whole_answer_value = _first(candidate, ("whole_answer_coverage", "payoff_coverage", "answer_coverage"), default=_MISSING)
    if whole_answer_value is not _MISSING:
        whole_answer = _number(whole_answer_value, "whole_answer_coverage")
        if whole_answer >= thresholds["whole_answer"]:
            explicit_summary = True
            summary_evidence.append(f"whole_answer_coverage={whole_answer:.6f}")
    if not explicit_full and payoff >= thresholds["full_payoff"] and spoiler >= thresholds["full_payoff"]:
        explicit_full = True
        full_evidence.append("payoff_and_spoiler_threshold")
    if not explicit_no_reason and open_loop <= thresholds["no_reason_open_loop"] and payoff >= thresholds["no_reason_payoff"]:
        explicit_no_reason = True
        no_reason_evidence.append("open_loop_and_payoff_threshold")
    gates = {
        "FULL_PAYOFF_ALREADY_REVEALED": _gate_result("FULL_PAYOFF_ALREADY_REVEALED", explicit_full, full_evidence, impact="REJECT_AND_NEVER_TOP"),
        "SHORT_SUMMARIZES_WHOLE_ANSWER": _gate_result("SHORT_SUMMARIZES_WHOLE_ANSWER", explicit_summary, summary_evidence, impact="REJECT"),
        "NO_REASON_TO_WATCH_LONGFORM": _gate_result("NO_REASON_TO_WATCH_LONGFORM", explicit_no_reason, no_reason_evidence, impact="REJECT"),
        "MISLEADING_OPEN_LOOP": _gate_result("MISLEADING_OPEN_LOOP", explicit_misleading, misleading_evidence, impact="REJECT"),
        "CONTEXT_REQUIRED_BUT_MISSING": _gate_result("CONTEXT_REQUIRED_BUT_MISSING", explicit_context or bool(context_evidence), explicit_context_evidence + context_evidence, impact="REJECT"),
        "FABRICATED_CURIOSITY": _gate_result("FABRICATED_CURIOSITY", explicit_fabricated, fabricated_evidence, impact="REJECT"),
    }
    return signals, gates


def _source_provenance(candidate: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key in (
        "source_episode_sha256",
        "source_episode_id",
        "source_metadata_hashes",
        "source_claim_ids",
        "claim_ids",
        "beat_ids",
        "source_segment_ids",
        "text_provenance",
        "source_provenance",
    ):
        if key in candidate and candidate[key] is not None:
            value = candidate[key]
            result[key] = dict(value) if isinstance(value, Mapping) else list(value) if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)) else value
    return result


def _evaluate_mapping(candidate: Mapping[str, Any], *, source_episode_id: str | None, thresholds: Mapping[str, float]) -> ConversionEvaluation:
    candidate_id = _candidate_id(candidate)
    try:
        episode_id = _source_episode_id(candidate, source_episode_id)
    except ConversionDirectorError as exc:
        return ConversionEvaluation(
            candidate_id=candidate_id,
            source_episode_id="UNKNOWN",
            signals={
                "SHORT_QUALITY": 0.0,
                "HOOK_STRENGTH": 0.0,
                "RETENTION_POTENTIAL": 0.0,
                "STANDALONE_VALUE": 0.0,
                "OPEN_LOOP_STRENGTH": 0.0,
                "LONGFORM_CONVERSION_SCORE": 0.0,
                "SPOILER_COST": 1.0,
                "PAYOFF_DISCLOSURE_LEVEL": 1.0,
                "PAYOFF_OVERDISCLOSURE": True,
                "WITHHELD_PAYOFF_SUMMARY": {"status": "UNKNOWN", "source": "INPUT_ERROR", "text": None},
                "CONVERSION_BRIDGE_STATUS": "BLOCKED",
                "CONVERSION_BRIDGE_REASON": str(exc),
                "SOURCE_EPISODE_ID": "UNKNOWN",
            },
            gates={},
            status="BLOCKED",
            rank_score=0.0,
            rejection_reasons=(str(exc),),
            source_provenance=_source_provenance(candidate),
        )
    try:
        signals, gates = _extract_signal_values(candidate, thresholds)
    except ConversionDirectorError as exc:
        return ConversionEvaluation(
            candidate_id=candidate_id,
            source_episode_id=episode_id,
            signals={
                "SHORT_QUALITY": 0.0,
                "HOOK_STRENGTH": 0.0,
                "RETENTION_POTENTIAL": 0.0,
                "STANDALONE_VALUE": 0.0,
                "OPEN_LOOP_STRENGTH": 0.0,
                "LONGFORM_CONVERSION_SCORE": 0.0,
                "SPOILER_COST": 1.0,
                "PAYOFF_DISCLOSURE_LEVEL": 1.0,
                "PAYOFF_OVERDISCLOSURE": True,
                "WITHHELD_PAYOFF_SUMMARY": {"status": "UNKNOWN", "source": "INPUT_ERROR", "text": None},
                "CONVERSION_BRIDGE_STATUS": "BLOCKED",
                "CONVERSION_BRIDGE_REASON": str(exc),
                "SOURCE_EPISODE_ID": episode_id,
            },
            gates={},
            status="BLOCKED",
            rank_score=0.0,
            rejection_reasons=(str(exc),),
            source_provenance=_source_provenance(candidate),
        )
    reasons = tuple(sorted(gate.code for gate in gates.values() if gate.status != "PASS" and gate.code))
    base = (
        0.25 * float(signals["SHORT_QUALITY"])
        + 0.15 * float(signals["HOOK_STRENGTH"])
        + 0.15 * float(signals["RETENTION_POTENTIAL"])
        + 0.10 * float(signals["STANDALONE_VALUE"])
        + 0.15 * float(signals["OPEN_LOOP_STRENGTH"])
        + 0.15 * float(signals["LONGFORM_CONVERSION_SCORE"])
        + 0.05 * (1.0 - float(signals["SPOILER_COST"]
        ))
    )
    if bool(signals["PAYOFF_OVERDISCLOSURE"]):
        base *= 0.35
    if gates["FULL_PAYOFF_ALREADY_REVEALED"].status != "PASS":
        base *= 0.25
    rank_score = max(0.0, min(1.0, base))
    status = "REJECTED" if reasons else "PASS"
    if status == "PASS" and float(signals["OPEN_LOOP_STRENGTH"]) < thresholds["minimum_open_loop"]:
        status = "REJECTED"
        reasons = ("NO_REASON_TO_WATCH_LONGFORM",)
        gates = dict(gates)
        gates["NO_REASON_TO_WATCH_LONGFORM"] = _gate_result(
            "NO_REASON_TO_WATCH_LONGFORM",
            True,
            ("open_loop_below_minimum",),
            impact="REJECT",
        )
    if reasons:
        bridge_status = "REJECT"
        bridge_reason = ";".join(reasons)
    elif float(signals["OPEN_LOOP_STRENGTH"]) >= thresholds["minimum_open_loop"]:
        bridge_status = "PASS"
        bridge_reason = "SOURCE_STRUCTURE_PRESERVES_UNRESOLVED_LARGER_QUESTION"
    else:
        bridge_status = "DOWNRANK"
        bridge_reason = "OPEN_LOOP_NOT_ESTABLISHED"
    signals = dict(signals)
    signals["CONVERSION_BRIDGE_STATUS"] = bridge_status
    signals["CONVERSION_BRIDGE_REASON"] = bridge_reason
    signals["SOURCE_EPISODE_ID"] = episode_id
    return ConversionEvaluation(
        candidate_id=candidate_id,
        source_episode_id=episode_id,
        signals=signals,
        gates=gates,
        status=status,
        rank_score=rank_score,
        rejection_reasons=tuple(sorted(set(reasons))),
        source_provenance=_source_provenance(candidate),
    )


class ConversionDirector:
    """Pure local conversion evaluator and portfolio accountant."""

    def __init__(self, *, thresholds: Mapping[str, float] | None = None, strict: bool = False) -> None:
        merged = dict(DEFAULT_THRESHOLDS)
        if thresholds:
            for key, value in thresholds.items():
                merged[str(key)] = _number(value, str(key))
        self.thresholds = merged
        self.strict = bool(strict)

    def evaluate_candidate(self, candidate: Any, *, source_episode_id: str | None = None) -> ConversionEvaluation:
        try:
            result = _evaluate_mapping(_mapping(candidate), source_episode_id=source_episode_id, thresholds=self.thresholds)
        except ConversionDirectorError:
            if self.strict:
                raise ConversionDirectorBlocked("CONVERSION_CANDIDATE_BLOCKED")
            raise
        if self.strict and result.status == "BLOCKED":
            raise ConversionDirectorBlocked("CONVERSION_CANDIDATE_BLOCKED")
        return result

    def score_candidate(self, candidate: Any, *, source_episode_id: str | None = None) -> dict[str, Any]:
        return self.evaluate_candidate(candidate, source_episode_id=source_episode_id).to_dict()

    def rank_candidates(self, candidates: Iterable[Any], *, source_episode_id: str | None = None) -> tuple[ConversionEvaluation, ...]:
        evaluated = [self.evaluate_candidate(item, source_episode_id=source_episode_id) for item in candidates]
        return tuple(sorted(evaluated, key=lambda item: (-item.rank_score, item.candidate_id)))

    def account_portfolio(
        self,
        candidates: Iterable[Any],
        *,
        selected_candidate_ids: Sequence[str] | None = None,
        max_cumulative_spoiler_cost: float = 0.80,
        max_cumulative_payoff_coverage: float = 0.80,
        source_episode_id: str | None = None,
    ) -> dict[str, Any]:
        return account_portfolio(
            candidates,
            selected_candidate_ids=selected_candidate_ids,
            max_cumulative_spoiler_cost=max_cumulative_spoiler_cost,
            max_cumulative_payoff_coverage=max_cumulative_payoff_coverage,
            source_episode_id=source_episode_id,
            director=self,
        )


class ShortsConversionDirector(ConversionDirector):
    """Backwards- and desktop-friendly name for :class:`ConversionDirector`.

    The aliases intentionally delegate to the already-established pure APIs;
    they do not add a second scoring or portfolio implementation.
    """

    assess_candidate = ConversionDirector.evaluate_candidate
    score_candidate = ConversionDirector.score_candidate
    select_portfolio = ConversionDirector.account_portfolio
    evaluate_portfolio = ConversionDirector.account_portfolio


def evaluate_candidate(candidate: Any, *, source_episode_id: str | None = None, director: ConversionDirector | None = None) -> ConversionEvaluation:
    return (director or ConversionDirector()).evaluate_candidate(candidate, source_episode_id=source_episode_id)


def score_candidate(candidate: Any, *, source_episode_id: str | None = None, director: ConversionDirector | None = None) -> dict[str, Any]:
    return evaluate_candidate(candidate, source_episode_id=source_episode_id, director=director).to_dict()


def _sequence(value: Any) -> tuple[str, ...]:
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(str(item) for item in value if str(item))
    return ()


def _coverage_ids(candidate: Mapping[str, Any], *, payoff: bool = False) -> tuple[str, ...]:
    names = ("payoff_claim_ids", "payoff_segments", "payoff_beat_ids") if payoff else ("source_claim_ids", "claim_ids", "beat_ids", "source_segment_ids")
    for name in names:
        value = candidate.get(name)
        ids = _sequence(value)
        if ids:
            return ids
    return (_candidate_id(candidate),)


def account_portfolio(
    candidates: Iterable[Any],
    *,
    selected_candidate_ids: Sequence[str] | None = None,
    max_cumulative_spoiler_cost: float = 0.80,
    max_cumulative_payoff_coverage: float = 0.80,
    source_episode_id: str | None = None,
    director: ConversionDirector | None = None,
) -> dict[str, Any]:
    active = director or ConversionDirector()
    raw_candidates = [_mapping(item) for item in candidates]
    evaluations = [active.evaluate_candidate(item, source_episode_id=source_episode_id) for item in raw_candidates]
    by_id = {evaluation.candidate_id: (evaluation, raw) for evaluation, raw in zip(evaluations, raw_candidates)}
    if selected_candidate_ids is None:
        ordered = sorted(evaluations, key=lambda item: (-item.rank_score, item.candidate_id))
    else:
        requested = tuple(str(item) for item in selected_candidate_ids)
        if len(requested) != len(set(requested)):
            raise ConversionDirectorError("PORTFOLIO_DUPLICATE_CANDIDATE")
        missing = tuple(item for item in requested if item not in by_id)
        if missing:
            raise ConversionDirectorError("PORTFOLIO_CANDIDATE_UNKNOWN:" + ",".join(missing))
        ordered = [by_id[item][0] for item in requested]
    selected: list[str] = []
    downselected: list[str] = []
    seen_spoiler: set[str] = set()
    seen_payoff: set[str] = set()
    cumulative_spoiler = 0.0
    cumulative_payoff = 0.0
    cumulative_limit_hit = False
    contributions: list[dict[str, Any]] = []
    for evaluation in ordered:
        raw = by_id[evaluation.candidate_id][1]
        if evaluation.status != "PASS":
            downselected.append(evaluation.candidate_id)
            continue
        spoiler_ids = _coverage_ids(raw)
        payoff_ids = _coverage_ids(raw, payoff=True)
        new_spoiler = tuple(item for item in spoiler_ids if item not in seen_spoiler)
        new_payoff = tuple(item for item in payoff_ids if item not in seen_payoff)
        spoiler_increment = float(evaluation.signals["SPOILER_COST"]) * (len(new_spoiler) / max(1, len(spoiler_ids)))
        payoff_increment = float(evaluation.signals["PAYOFF_DISCLOSURE_LEVEL"]) * (len(new_payoff) / max(1, len(payoff_ids)))
        if cumulative_spoiler + spoiler_increment > max_cumulative_spoiler_cost or cumulative_payoff + payoff_increment > max_cumulative_payoff_coverage:
            downselected.append(evaluation.candidate_id)
            cumulative_limit_hit = True
            contributions.append({"candidate_id": evaluation.candidate_id, "status": "DOWNSELECTED", "spoiler_increment": round(spoiler_increment, 6), "payoff_increment": round(payoff_increment, 6)})
            continue
        selected.append(evaluation.candidate_id)
        cumulative_spoiler += spoiler_increment
        cumulative_payoff += payoff_increment
        seen_spoiler.update(spoiler_ids)
        seen_payoff.update(payoff_ids)
        contributions.append({"candidate_id": evaluation.candidate_id, "status": "SELECTED", "spoiler_increment": round(spoiler_increment, 6), "payoff_increment": round(payoff_increment, 6)})
    portfolio_summary = cumulative_limit_hit or cumulative_payoff >= max_cumulative_payoff_coverage or cumulative_spoiler >= max_cumulative_spoiler_cost
    payload = {
        "schema_version": SCHEMA_VERSION,
        "director_version": DIRECTOR_VERSION,
        "selected_candidate_ids": selected,
        "downselected_candidate_ids": downselected,
        "CUMULATIVE_SPOILER_COST": round(min(1.0, cumulative_spoiler), 6),
        "CUMULATIVE_PAYOFF_COVERAGE": round(min(1.0, cumulative_payoff), 6),
        "PORTFOLIO_SUMMARIZES_WHOLE_EPISODE": portfolio_summary,
        "contributions": contributions,
    }
    payload["portfolio_sha256"] = _sha256_value(payload)
    payload["status"] = "DOWNSELECT_REQUIRED" if portfolio_summary else "PASS"
    return payload


def _source_segments(candidate: Mapping[str, Any], source_segments: Sequence[Mapping[str, Any]] | None) -> tuple[Mapping[str, Any], ...]:
    if source_segments is not None:
        return tuple(source_segments)
    for key in ("source_segments", "segments", "narration_segments", "beats"):
        value = candidate.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            return tuple(item for item in value if isinstance(item, Mapping))
    return ()


def build_endpoint_variants(
    candidate: Any,
    *,
    source_segments: Sequence[Mapping[str, Any]] | None = None,
    max_variants: int = 8,
) -> tuple[dict[str, Any], ...]:
    """Build only source-segment endpoint variants at explicit safe boundaries."""

    if max_variants <= 0:
        raise ConversionDirectorError("MAX_VARIANTS:POSITIVE_REQUIRED")
    raw = _mapping(candidate)
    segments = _source_segments(raw, source_segments)
    if not segments:
        return ({"status": "BLOCKED", "reason": "SOURCE_SEGMENT_BOUNDARIES_REQUIRED", "source_derived": False},)
    start = _time_number(raw.get("start_time", raw.get("start", 0.0)), "candidate.start_time")
    end = _time_number(raw.get("end_time", raw.get("end", 1.0)), "candidate.end_time")
    if end <= start:
        return ({"status": "BLOCKED", "reason": "CANDIDATE_RANGE_INVALID", "source_derived": False},)
    previous_end: float | None = None
    normalized: list[dict[str, Any]] = []
    for index, segment in enumerate(segments):
        try:
            seg_start = _time_number(segment.get("start_time", segment.get("start")), f"segment[{index}].start")
            seg_end = _time_number(segment.get("end_time", segment.get("end")), f"segment[{index}].end")
        except ConversionDirectorError:
            continue
        if seg_end <= seg_start or seg_start < start or seg_end > end:
            continue
        if previous_end is not None and not math.isclose(seg_start, previous_end, rel_tol=0.0, abs_tol=1e-6):
            continue
        text = str(segment.get("text", ""))
        if not text.strip():
            continue
        previous_end = seg_end
        normalized.append({
            "segment_id": str(segment.get("segment_id", segment.get("beat_id", f"SOURCE-{index + 1:03d}"))),
            "start": seg_start,
            "end": seg_end,
            "text": text,
            "sentence_boundary": _bool(segment.get("sentence_boundary")) is True,
            "semantic_complete": _bool(segment.get("semantic_complete")) is True,
            "open_loop_strength": segment.get("open_loop_strength", segment.get("OPEN_LOOP_STRENGTH")),
            "spoiler_cost": segment.get("spoiler_cost", segment.get("SPOILER_COST")),
            "payoff_disclosure_level": segment.get("payoff_disclosure_level", segment.get("PAYOFF_DISCLOSURE_LEVEL")),
        })
    if not normalized:
        return ({"status": "BLOCKED", "reason": "NO_VALID_SOURCE_SEGMENT_BOUNDARIES", "source_derived": False},)
    if not math.isclose(normalized[0]["start"], start, rel_tol=0.0, abs_tol=1e-6):
        return ({"status": "BLOCKED", "reason": "SOURCE_SEGMENT_START_NOT_BOUND_TO_CANDIDATE", "source_derived": False},)
    variants: list[dict[str, Any]] = []
    for end_index in range(len(normalized)):
        portion = normalized[: end_index + 1]
        last = portion[-1]
        if not last["sentence_boundary"] or not last["semantic_complete"]:
            continue
        variant_start = portion[0]["start"]
        variant_end = last["end"]
        if variant_end <= variant_start:
            continue
        variant = {
            "variant_id": f"SOURCE_ENDPOINT_{end_index + 1:03d}",
            "status": "PASS",
            "reason": "SOURCE_SEGMENT_SEMANTIC_BOUNDARY",
            "source_derived": True,
            "start": variant_start,
            "end": variant_end,
            "text": " ".join(item["text"] for item in portion),
            "source_segment_ids": [item["segment_id"] for item in portion],
            "semantic_complete": True,
            "sentence_boundary": True,
        }
        for output_key, source_key in (
            ("open_loop_strength", "open_loop_strength"),
            ("spoiler_cost", "spoiler_cost"),
            ("payoff_disclosure_level", "payoff_disclosure_level"),
        ):
            if last[source_key] is not None:
                variant[output_key] = last[source_key]
        variants.append(variant)
    if not variants:
        return ({"status": "BLOCKED", "reason": "NO_SEMANTIC_ENDPOINT_BOUNDARY", "source_derived": False},)
    return tuple(variants[-max_variants:])


def select_endpoint_variant(candidate: Any, variants: Sequence[Mapping[str, Any]] | None = None, *, director: ConversionDirector | None = None) -> dict[str, Any]:
    raw = _mapping(candidate)
    director = director or ConversionDirector()
    candidates = tuple(variants) if variants is not None else build_endpoint_variants(raw)
    candidate_start = _time_number(raw.get("start_time", raw.get("start", 0.0)), "candidate.start_time")
    candidate_end = _time_number(raw.get("end_time", raw.get("end", 1.0)), "candidate.end_time")
    eligible: list[tuple[float, float, float, float, str, Mapping[str, Any]]] = []
    for variant in candidates:
        if variant.get("status") != "PASS" or variant.get("source_derived") is not True or variant.get("semantic_complete") is not True:
            continue
        try:
            variant_start = _time_number(variant.get("start"), "variant.start")
            variant_end = _time_number(variant.get("end"), "variant.end")
        except ConversionDirectorError:
            continue
        if variant_end <= variant_start or variant_start < candidate_start or variant_end > candidate_end:
            continue
        if not str(variant.get("text", "")).strip() or not _sequence(variant.get("source_segment_ids")):
            continue
        variant_candidate = dict(raw)
        variant_candidate["start_time"] = variant.get("start")
        variant_candidate["end_time"] = variant.get("end")
        for key in ("open_loop_strength", "spoiler_cost", "payoff_disclosure_level"):
            if key in variant:
                variant_candidate[key] = variant[key]
        evaluation = director.evaluate_candidate(variant_candidate)
        if evaluation.status != "PASS":
            continue
        eligible.append((evaluation.rank_score, float(variant_candidate.get("open_loop_strength", 0.0)), -float(variant_candidate.get("spoiler_cost", 1.0)), -float(variant["end"]), str(variant.get("variant_id", "")), variant))
    if not eligible:
        return {"status": "BLOCKED", "reason": "NO_SAFE_ENDPOINT_VARIANT", "source_derived": False}
    eligible.sort(key=lambda item: (-item[0], -item[1], -item[2], -item[3], item[4]))
    selected = dict(eligible[0][5])
    selected["selection_status"] = "PASS"
    selected["selection_reason"] = "SEMANTIC_COMPLETENESS_OPEN_LOOP_LOW_SPOILER"
    return selected


__all__ = [
    "CONVERSION_GATE_NAMES",
    "CONVERSION_SIGNAL_FIELDS",
    "ConversionDirector",
    "ConversionDirectorBlocked",
    "ConversionDirectorError",
    "ConversionEvaluation",
    "DIRECTOR_VERSION",
    "SCHEMA_VERSION",
    "ShortsConversionDirector",
    "account_portfolio",
    "build_endpoint_variants",
    "evaluate_candidate",
    "score_candidate",
    "select_endpoint_variant",
]
