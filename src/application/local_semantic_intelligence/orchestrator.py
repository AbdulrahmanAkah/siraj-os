"""Resumable, stage-oriented local semantic extraction orchestration."""

from __future__ import annotations

from dataclasses import asdict
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Callable

from src.application.operations_common import (
    CANONICAL_TIMESTAMP,
    deterministic_id,
    integrity_hash,
)

from .models import SEMANTIC_SCHEMA_VERSION, STAGES, SemanticSegmentInput
from .provider import SemanticExtractionProvider
from .validation import canonicalize_literal_spans, validate_semantic_outputs


def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ) + "\n"


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = handle.name
        with handle:
            handle.write(canonical_json(payload))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        handle = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            delete=False,
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        temporary = handle.name
        with handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary:
            Path(temporary).unlink(missing_ok=True)


class LocalSemanticOrchestrator:
    """Processes exactly one segment at a time and checkpoints every stage."""

    def __init__(
        self,
        provider: SemanticExtractionProvider,
        output_root: str | Path,
    ):
        self.provider = provider
        self.output_root = Path(output_root).resolve()

    def _segment_root(self, segment: SemanticSegmentInput) -> Path:
        return self.output_root / "segments" / segment.audit_segment_id

    def _checkpoint(
        self,
        segment: SemanticSegmentInput,
        stage: str,
        input_payload: dict[str, Any],
        execute: Callable[[], dict[str, Any]],
        *,
        execution_status: str = "LLM_CALL_EXECUTED",
        normalise_payload: Callable[[dict[str, Any]], tuple[dict[str, Any], list[str]]] | None = None,
    ) -> dict[str, Any]:
        path = self._segment_root(segment) / f"{STAGES.index(stage) + 1:02d}-{stage.lower()}.json"
        input_hash = integrity_hash(
            {
                "stage": stage,
                "schema_version": SEMANTIC_SCHEMA_VERSION,
                "provider": asdict(self.provider.identity),
                "input": input_payload,
            }
        )
        if path.is_file():
            cached = json.loads(path.read_text(encoding="utf-8-sig"))
            if (
                cached.get("status") in {"COMPLETED", "SKIPPED"}
                and cached.get("input_hash") == input_hash
            ):
                return {**cached, "cache_hit": True}
        started = time.perf_counter_ns()
        try:
            payload = execute()
            status = "COMPLETED"
            reason_codes = list(payload.pop("_reason_codes", []))
            if normalise_payload is not None:
                payload, derived_codes = normalise_payload(payload)
                reason_codes.extend(derived_codes)
        except BaseException as error:
            payload = {}
            status = "FAILED"
            reason_codes = [str(error).splitlines()[0][:160]]
        elapsed_ms = round(
            (time.perf_counter_ns() - started) / 1_000_000,
            3,
        )
        metadata = payload.get("provider_metadata", {})
        tokens = metadata.get("tokens", payload.get("usage", {}))
        timings = metadata.get("provider_timings_ns", {})
        result = {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "stage": stage,
            "status": status,
            "input_hash": input_hash,
            "output_hash": integrity_hash(payload),
            "payload": payload,
            "reason_codes": sorted(set(reason_codes)),
            "cache_hit": False,
            "execution_status": execution_status,
            "latency_ms": elapsed_ms,
            "tokens": {
                str(key): int(value or 0)
                for key, value in sorted(tokens.items())
                if isinstance(value, (int, float))
            },
            "provider_timings_ns": {
                str(key): int(value or 0)
                for key, value in sorted(timings.items())
                if isinstance(value, (int, float))
            },
            "created_at": CANONICAL_TIMESTAMP,
            "provider": asdict(self.provider.identity),
        }
        atomic_write_json(path, result)
        if status == "FAILED":
            raise RuntimeError(f"SEMANTIC_STAGE_FAILED:{stage}:{reason_codes[0]}")
        return result

    def _skip(
        self,
        segment: SemanticSegmentInput,
        stage: str,
        reason: str,
        prior_hash: str,
    ) -> dict[str, Any]:
        path = self._segment_root(segment) / f"{STAGES.index(stage) + 1:02d}-{stage.lower()}.json"
        payload = {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "stage": stage,
            "status": "SKIPPED",
            "input_hash": prior_hash,
            "output_hash": integrity_hash({}),
            "payload": {},
            "reason_codes": [reason],
            "cache_hit": False,
            "execution_status": "NOT_REQUIRED",
            "latency_ms": 0.0,
            "tokens": {},
            "provider_timings_ns": {},
            "created_at": CANONICAL_TIMESTAMP,
            "provider": asdict(self.provider.identity),
        }
        atomic_write_json(path, payload)
        return payload

    def _reused_from_combined(
        self,
        segment: SemanticSegmentInput,
        stage: str,
        payload: dict[str, Any],
        combined: dict[str, Any],
    ) -> dict[str, Any]:
        path = self._segment_root(segment) / f"{STAGES.index(stage) + 1:02d}-{stage.lower()}.json"
        result = {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "stage": stage,
            "status": "COMPLETED",
            "input_hash": integrity_hash(combined),
            "output_hash": integrity_hash(payload),
            "payload": payload,
            "reason_codes": ["REUSED_FROM_SIMPLE_HISTORICAL_COMBINED_CALL"],
            "cache_hit": False,
            "execution_status": "REUSED_FROM_COMBINED_CALL",
            "latency_ms": 0.0,
            "tokens": {},
            "provider_timings_ns": {},
            "created_at": CANONICAL_TIMESTAMP,
            "provider": asdict(self.provider.identity),
        }
        atomic_write_json(path, result)
        return result

    @staticmethod
    def _route(structure: dict[str, Any]) -> str:
        segment_type = str(structure.get("segment_type", "UNKNOWN"))
        subtypes = set(map(str, structure.get("subtypes", [])))
        if segment_type == "NON_HISTORICAL":
            return "SHORT_CIRCUIT_NON_HISTORICAL"
        if structure.get("isnad_ranges") or "ISNAD" in subtypes:
            return "ISNAD"
        if structure.get("poetry_ranges") or segment_type == "POETRY":
            return "POETRY"
        if segment_type in {"BIOGRAPHY", "RIJAL"}:
            return "BIOGRAPHY"
        return "HISTORICAL_NARRATIVE"

    @staticmethod
    def _execution_plan(segment: SemanticSegmentInput) -> str:
        reasons = set(segment.selection_reasons)
        current = segment.current_extraction
        if "NEGATIVE_CONTROL" in reasons or "NEGATIVE_CONTROL_NO_CURRENT_SIGNAL" in reasons:
            return "NEGATIVE_OR_NON_HISTORICAL"
        if current.get("isnad_chains") or "ISNAD" in reasons:
            return "ISNAD"
        if "POETRY_OR_SIRA" in reasons or "POETRY_OR_SHORT_LINE_STRUCTURE" in reasons:
            return "POETRY_SIRA"
        signal_count = sum(
            bool(current.get(key))
            for key in ("entities", "events", "relations", "claims", "temporal_mentions")
        )
        if signal_count >= 4 or len(segment.original_text) > 3000:
            return "COMPLEX"
        return "SIMPLE_HISTORICAL"

    def run_segment(
        self,
        segment: SemanticSegmentInput,
    ) -> dict[str, Any]:
        base = {
            "audit_segment_id": segment.audit_segment_id,
            "source_id": segment.source_id,
            "locator": segment.locator,
            "original_text": segment.original_text,
            "schema_version": SEMANTIC_SCHEMA_VERSION,
        }
        execution_plan = self._execution_plan(segment)
        atomic_write_json(
            self._segment_root(segment) / "adaptive-execution-plan.json",
            {
                "schema_version": SEMANTIC_SCHEMA_VERSION,
                "audit_segment_id": segment.audit_segment_id,
                "execution_plan": execution_plan,
                "selection_reasons": sorted(segment.selection_reasons),
                "one_model_request_at_a_time": True,
            },
        )
        stage_results: list[dict[str, Any]] = []
        if execution_plan == "SIMPLE_HISTORICAL":
            combined_request = {
                **base,
                "execution_plan": execution_plan,
                "prior_stage_outputs": {},
            }
            combined_result = self._checkpoint(
                segment,
                "STRUCTURAL_ANALYSIS",
                combined_request,
                lambda: self.provider.extract_combined(combined_request),
                normalise_payload=lambda value: canonicalize_literal_spans(
                    value,
                    segment.original_text,
                ),
            )
            stage_results.append(combined_result)
            combined = combined_result["payload"]
            structure_payload = {"structure": combined.get("structure", {})}
            route = self._route(structure_payload["structure"])
            prior: dict[str, Any] = {"structure": structure_payload}
            mentions = self._reused_from_combined(
                segment,
                "MENTION_EXTRACTION",
                {"entities": list(combined.get("entities", []))},
                combined,
            )
            events = self._reused_from_combined(
                segment,
                "EVENT_RELATION_EXTRACTION",
                {
                    "events": list(combined.get("events", [])),
                    "relations": list(combined.get("relations", [])),
                    "institutions": list(combined.get("institutions", [])),
                },
                combined,
            )
            claims = self._reused_from_combined(
                segment,
                "CLAIM_ATTRIBUTION",
                {
                    "claims": list(combined.get("claims", [])),
                    "isnads": list(combined.get("isnads", [])),
                    "temporals": list(combined.get("temporals", [])),
                },
                combined,
            )
            stage_results.extend((mentions, events, claims))
            prior.update(
                {
                    "mentions": mentions["payload"],
                    "events_relations": events["payload"],
                    "claims_attribution": claims["payload"],
                }
            )
        else:
            structure_request = {**base, "execution_plan": execution_plan}
            structure_result = self._checkpoint(
                segment,
                "STRUCTURAL_ANALYSIS",
                structure_request,
                lambda: self.provider.classify_structure(structure_request),
                normalise_payload=lambda value: canonicalize_literal_spans(
                    value,
                    segment.original_text,
                ),
            )
            stage_results.append(structure_result)
            structure_payload = structure_result["payload"]
            structure = structure_payload.get("structure", structure_payload)
            route = self._route(structure)
            prior = {"structure": structure_payload}

        if route == "SHORT_CIRCUIT_NON_HISTORICAL" or execution_plan == "NEGATIVE_OR_NON_HISTORICAL":
            prior_hash = integrity_hash(prior)
            for stage in (
                "MENTION_EXTRACTION",
                "EVENT_RELATION_EXTRACTION",
                "CLAIM_ATTRIBUTION",
            ):
                stage_results.append(
                    self._skip(segment, stage, route, prior_hash)
                )
            prior.update(
                {
                    "mentions": {"items": [], "entities": []},
                    "events_relations": {
                        "items": [],
                        "events": [],
                        "relations": [],
                        "institutions": [],
                    },
                    "claims_attribution": {
                        "items": [],
                        "claims": [],
                        "isnads": [],
                        "temporals": [],
                    },
                }
            )
        elif execution_plan == "SIMPLE_HISTORICAL":
            # Mentions, events, relations, claims, and structure already came
            # from the one bounded combined model request above.
            pass
        elif execution_plan == "ISNAD":
            request = {**base, "route": route, "execution_plan": execution_plan, "prior_stage_outputs": prior}
            isnad = self._checkpoint(
                segment,
                "CLAIM_ATTRIBUTION",
                request,
                lambda: self.provider.extract_isnad(request),
                normalise_payload=lambda value: canonicalize_literal_spans(
                    value,
                    segment.original_text,
                ),
            )
            mentions = self._skip(segment, "MENTION_EXTRACTION", "ISNAD_SPECIALIZED_EXTRACTION", integrity_hash(prior))
            events = self._skip(segment, "EVENT_RELATION_EXTRACTION", "ISNAD_SPECIALIZED_EXTRACTION", integrity_hash(prior))
            stage_results.extend((mentions, events, isnad))
            prior.update(
                {
                    "mentions": {"entities": []},
                    "events_relations": {"events": [], "relations": [], "institutions": []},
                    "claims_attribution": isnad["payload"],
                }
            )
        elif execution_plan == "POETRY_SIRA":
            request = {**base, "route": route, "execution_plan": execution_plan, "prior_stage_outputs": prior}
            poetry = self._checkpoint(
                segment,
                "MENTION_EXTRACTION",
                request,
                lambda: self.provider.extract_poetry_sira(request),
                normalise_payload=lambda value: canonicalize_literal_spans(
                    value,
                    segment.original_text,
                ),
            )
            payload = poetry["payload"]
            events = self._reused_from_combined(segment, "EVENT_RELATION_EXTRACTION", {"events": list(payload.get("events", [])), "relations": list(payload.get("relations", [])), "institutions": list(payload.get("institutions", []))}, payload)
            claims = self._reused_from_combined(segment, "CLAIM_ATTRIBUTION", {"claims": list(payload.get("claims", [])), "isnads": list(payload.get("isnads", [])), "temporals": list(payload.get("temporals", []))}, payload)
            stage_results.extend((poetry, events, claims))
            prior.update({"mentions": {"entities": list(payload.get("entities", []))}, "events_relations": events["payload"], "claims_attribution": claims["payload"]})
        else:
            request = {**base, "route": route, "execution_plan": execution_plan, "prior_stage_outputs": prior}
            mentions = self._checkpoint(
                segment,
                "MENTION_EXTRACTION",
                request,
                lambda: self.provider.extract_mentions(request),
                normalise_payload=lambda value: canonicalize_literal_spans(
                    value,
                    segment.original_text,
                ),
            )
            stage_results.append(mentions)
            prior["mentions"] = mentions["payload"]
            request = {**base, "route": route, "execution_plan": execution_plan, "prior_stage_outputs": prior}
            events = self._checkpoint(
                segment,
                "EVENT_RELATION_EXTRACTION",
                request,
                lambda: self.provider.extract_events_relations(request),
                normalise_payload=lambda value: canonicalize_literal_spans(
                    value,
                    segment.original_text,
                ),
            )
            stage_results.append(events)
            prior["events_relations"] = events["payload"]
            request = {**base, "route": route, "execution_plan": execution_plan, "prior_stage_outputs": prior}
            claims = self._checkpoint(
                segment,
                "CLAIM_ATTRIBUTION",
                request,
                lambda: self.provider.extract_claims_attribution(request),
                normalise_payload=lambda value: canonicalize_literal_spans(
                    value,
                    segment.original_text,
                ),
            )
            stage_results.append(claims)
            prior["claims_attribution"] = claims["payload"]

        validation_input = {
            **base,
            "semantic_outputs_hash": integrity_hash(prior),
        }
        validation = self._checkpoint(
            segment,
            "DETERMINISTIC_EVIDENCE_VALIDATION",
            validation_input,
            lambda: validate_semantic_outputs(
                segment.original_text,
                segment.source_id,
                segment.locator,
                prior,
            ),
            execution_status="DETERMINISTIC_ONLY",
        )
        stage_results.append(validation)
        prior["validation"] = validation["payload"]

        critic_request = {**base, "route": route, "execution_plan": execution_plan, "prior_stage_outputs": prior}
        validation_codes = {
            str(issue.get("code", ""))
            for issue in validation["payload"].get("issues", [])
            if isinstance(issue, dict)
        }
        if validation["payload"].get("warning_count", 0) or any(
            "CONTRADICTION" in code for code in validation_codes
        ):
            critic = self._checkpoint(
                segment,
                "CRITICAL_REVIEW",
                critic_request,
                lambda: self.provider.critique_extraction(critic_request),
            )
        else:
            critic = self._skip(segment, "CRITICAL_REVIEW", "NO_VALIDATION_WARNING_OR_CONTRADICTION", integrity_hash(prior))
        stage_results.append(critic)
        prior["critic"] = critic["payload"]

        reconciliation = self._checkpoint(
            segment,
            "RECONCILIATION",
            {
                "semantic_hash": integrity_hash(prior),
                "baseline_hash": integrity_hash(segment.current_extraction),
            },
            lambda: self._reconcile(segment, prior),
        )
        stage_results.append(reconciliation)
        prior["reconciliation"] = reconciliation["payload"]

        learning = self._checkpoint(
            segment,
            "LEARNING_REPORT",
            {
                "reconciliation_hash": reconciliation["output_hash"],
                "reviewer_notes_hash": integrity_hash(segment.reviewer_notes),
            },
            lambda: self._learning_report(segment, prior),
        )
        stage_results.append(learning)
        run_id = deterministic_id(
            "semantic_segment_run",
            [
                segment.audit_segment_id,
                self.provider.identity,
                [stage_results[0]["output_hash"], learning["output_hash"]],
            ],
        )
        summary = {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "run_id": run_id,
            "audit_segment_id": segment.audit_segment_id,
            "source_id": segment.source_id,
            "locator": segment.locator,
            "route": route,
            "execution_plan": execution_plan,
            "status": "COMPLETED",
            "provider": asdict(self.provider.identity),
            "baseline_hash": integrity_hash(segment.current_extraction),
            "original_text_hash": integrity_hash(segment.original_text),
            "stage_count": len(STAGES),
            "reconciliation_counts": reconciliation["payload"]["counts"],
            "cache_hits": sum(bool(item.get("cache_hit")) for item in stage_results),
            "total_stage_latency_ms": round(
                sum(float(item.get("latency_ms", 0)) for item in stage_results),
                3,
            ),
            "tokens": {
                key: sum(
                    int(item.get("tokens", {}).get(key, 0))
                    for item in stage_results
                )
                for key in sorted(
                    {
                        key
                        for item in stage_results
                        for key in item.get("tokens", {})
                    }
                )
            },
            "model_load_time_ms": round(
                sum(
                    int(item.get("provider_timings_ns", {}).get("load", 0))
                    for item in stage_results
                )
                / 1_000_000,
                3,
            ),
            "graph_written": False,
        }
        atomic_write_json(self._segment_root(segment) / "run-summary.json", summary)
        return summary

    @staticmethod
    def _model_items(outputs: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
        items: list[tuple[str, dict[str, Any]]] = []
        for payload_key, collection_keys in (
            ("mentions", ("entities",)),
            ("events_relations", ("events", "relations", "institutions")),
            ("claims_attribution", ("claims", "isnads", "temporals")),
        ):
            payload = outputs.get(payload_key, {})
            for collection in collection_keys:
                for item in payload.get(collection, []):
                    if isinstance(item, dict):
                        items.append((collection, item))
        return items

    @classmethod
    def _reconcile(
        cls,
        segment: SemanticSegmentInput,
        outputs: dict[str, Any],
    ) -> dict[str, Any]:
        issues = outputs["validation"].get("issues", [])
        issue_subjects = {
            str(item.get("subject_id", "")): item
            for item in issues
        }
        reconciled = []
        for collection, item in cls._model_items(outputs):
            identifier = str(
                item.get("mention_id")
                or item.get("event_id")
                or item.get("relation_id")
                or item.get("record_id")
                or item.get("claim_id")
                or item.get("isnad_id")
                or item.get("temporal_id")
                or ""
            )
            issue = issue_subjects.get(identifier)
            uncertainty = str(item.get("uncertainty", "")).upper()
            if issue and issue.get("severity") in {"ERROR", "CRITICAL"}:
                status = "REJECTED_UNSUPPORTED"
                reasons = [str(issue["code"])]
            elif issue:
                status = "ACCEPTED_WITH_WARNING"
                reasons = [str(issue["code"])]
            elif uncertainty in {"HIGH", "UNRESOLVED", "UNKNOWN"}:
                status = "HUMAN_REVIEW_REQUIRED"
                reasons = ["MODEL_UNCERTAINTY_REQUIRES_REVIEW"]
            else:
                status = "ACCEPTED_HIGH_CONFIDENCE"
                reasons = ["EXACT_EVIDENCE_AND_REFERENCES_VALID"]
            reconciled.append(
                {
                    "item_id": identifier,
                    "item_type": collection,
                    "status": status,
                    "reason_codes": reasons,
                }
            )
        baseline_ids = sorted(
            {
                str(item.get(key, ""))
                for collection, key in (
                    ("entities", "mention_id"),
                    ("events", "event_mention_id"),
                    ("relations", "relation_id"),
                    ("claims", "claim_id"),
                    ("temporal_mentions", "temporal_id"),
                    ("isnad_chains", "chain_id"),
                )
                for item in segment.current_extraction.get(collection, [])
                if item.get(key)
            }
        )
        counts = {
            status: sum(item["status"] == status for item in reconciled)
            for status in (
                "ACCEPTED_HIGH_CONFIDENCE",
                "ACCEPTED_WITH_WARNING",
                "HUMAN_REVIEW_REQUIRED",
                "REJECTED_UNSUPPORTED",
            )
        }
        return {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "items": sorted(reconciled, key=lambda item: item["item_id"]),
            "counts": counts,
            "baseline_ids": baseline_ids,
            "baseline_is_candidate_only": True,
            "knowledge_graph_write_allowed": False,
        }

    @staticmethod
    def _learning_report(
        segment: SemanticSegmentInput,
        outputs: dict[str, Any],
    ) -> dict[str, Any]:
        baseline_counts = {
            key: len(segment.current_extraction.get(key, []))
            for key in (
                "entities",
                "events",
                "relations",
                "claims",
                "temporal_mentions",
                "isnad_chains",
            )
        }
        validation_codes = sorted(
            {
                str(item["code"])
                for item in outputs["validation"].get("issues", [])
            }
        )
        return {
            "schema_version": SEMANTIC_SCHEMA_VERSION,
            "baseline_error_categories": (
                ["HUMAN_REVIEWER_NOTE_PRESENT"]
                if segment.reviewer_notes.strip()
                else ["NO_HUMAN_DIAGNOSTIC_NOTE"]
            ),
            "model_error_categories": validation_codes,
            "deterministic_fixes_proposed": [
                "Preserve exact evidence validation as a hard gate.",
                "Use reviewed failures as future regression fixtures.",
            ],
            "semantic_issues_must_remain_model_based": [
                "contextual role disambiguation",
                "authorial versus quoted attribution",
                "institution and office semantics",
            ],
            "ontology_gaps": [],
            "prompt_schema_gaps": validation_codes,
            "suggested_regression_cases": [
                segment.audit_segment_id
            ] if validation_codes or segment.reviewer_notes else [],
            "baseline_counts": baseline_counts,
            "reviewer_notes_used_as_labels": False,
            "automatic_rule_or_code_modification": False,
        }


__all__ = [
    "LocalSemanticOrchestrator",
    "atomic_write_json",
    "atomic_write_text",
    "canonical_json",
]
