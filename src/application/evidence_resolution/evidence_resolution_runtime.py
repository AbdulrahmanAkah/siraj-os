from dataclasses import dataclass
from hashlib import sha256
import json

from src.application.claim_extraction.models import ClaimExtractionResult
from src.application.entity_extraction.models import EntityExtractionResult
from src.application.event_extraction.models import EventExtractionResult
from src.application.historical_timeline.models import HistoricalTimeline, TimelineBuildResult
from src.application.relationship_graph.models import RelationshipGraph, RelationshipGraphResult

from .evidence_resolution_architect import EvidenceResolutionArchitect
from .models import (
    EvidenceBundle,
    EvidenceReference,
    EvidenceResolutionPlan,
    EvidenceResolutionResult,
    ResolvedEvidence,
)


@dataclass(frozen=True)
class _CollectedEvidence:
    evidence_id: str
    evidence_text: str
    source_type: str
    source_id: str
    source_content: str


class EvidenceResolutionRuntime:
    """Collects and resolves exact, traceable evidence without inference."""

    SOURCE_TYPES = EvidenceResolutionArchitect.SOURCE_TYPES

    def build_resolution_result(
        self,
        plan,
        claim_result,
        entity_result,
        event_result,
        relationship_graph,
        historical_timeline,
    ):
        self.validate_runtime_inputs_or_raise(
            plan,
            claim_result,
            entity_result,
            event_result,
            relationship_graph,
            historical_timeline,
        )
        collected = self.collect_evidence(
            plan,
            claim_result,
            entity_result,
            event_result,
            relationship_graph,
            historical_timeline,
        )
        resolved = self.resolve_duplicates(collected)
        bundles = self.build_bundles(resolved)
        result = EvidenceResolutionResult(
            result_id=self._result_id(resolved, "VALID"),
            plan_id=plan.plan_id,
            resolved_evidence=resolved,
            bundles=bundles,
            evidence_count=len(resolved),
            bundle_count=len(bundles),
            validation_state="VALID",
        )
        if not self.validate_resolution(
            plan,
            claim_result,
            entity_result,
            event_result,
            relationship_graph,
            historical_timeline,
            result,
        ):
            raise ValueError("Invalid evidence resolution result")
        return result

    def collect_evidence(
        self,
        plan,
        claim_result,
        entity_result,
        event_result,
        relationship_graph,
        historical_timeline,
    ):
        collected = []
        if "CLAIM" in plan.allowed_source_types:
            for claim in claim_result.claims:
                for evidence in claim.evidence:
                    collected.append(
                        _CollectedEvidence(
                            evidence_id=evidence.evidence_id,
                            evidence_text=evidence.supporting_text,
                            source_type="CLAIM",
                            source_id=claim.claim_id,
                            source_content="|".join([evidence.record_id, evidence.fingerprint]),
                        )
                    )
        if "ENTITY" in plan.allowed_source_types:
            for entity in entity_result.entities:
                for evidence in entity.evidence:
                    collected.append(
                        _CollectedEvidence(
                            evidence_id=evidence.evidence_id,
                            evidence_text=evidence.supporting_text,
                            source_type="ENTITY",
                            source_id=entity.entity_id,
                            source_content=evidence.claim_id,
                        )
                    )
        if "EVENT" in plan.allowed_source_types:
            for event in event_result.events:
                for evidence in event.evidence:
                    collected.append(
                        _CollectedEvidence(
                            evidence_id=evidence.evidence_id,
                            evidence_text=evidence.supporting_text,
                            source_type="EVENT",
                            source_id=event.event_id,
                            source_content=json.dumps(
                                {
                                    "claim_ids": sorted(evidence.claim_ids),
                                    "entity_ids": sorted(evidence.entity_ids),
                                },
                                sort_keys=True,
                                separators=(",", ":"),
                            ),
                        )
                    )
        graph = self._graph(relationship_graph)
        if "GRAPH_EDGE" in plan.allowed_source_types:
            for edge in graph.edges:
                text = f"{edge.edge_type}: {edge.source_node_id} -> {edge.target_node_id}"
                collected.append(
                    _CollectedEvidence(
                        evidence_id=edge.edge_id,
                        evidence_text=text,
                        source_type="GRAPH_EDGE",
                        source_id=edge.edge_id,
                        source_content=text,
                    )
                )
        timeline = self._timeline(historical_timeline)
        if "TIMELINE_ENTRY" in plan.allowed_source_types:
            for entry in timeline.entries:
                content = json.dumps(
                    {
                        "event_id": entry.event_id,
                        "event_date": entry.event_date,
                        "source_claim_ids": sorted(entry.source_claim_ids),
                        "source_entity_ids": sorted(entry.source_entity_ids),
                    },
                    sort_keys=True,
                    separators=(",", ":"),
                )
                collected.append(
                    _CollectedEvidence(
                        evidence_id=entry.entry_id,
                        evidence_text=entry.event_title,
                        source_type="TIMELINE_ENTRY",
                        source_id=entry.entry_id,
                        source_content=content,
                    )
                )
        return sorted(
            collected,
            key=lambda item: (
                item.evidence_text,
                item.source_content,
                item.source_type,
                item.source_id,
                item.evidence_id,
            ),
        )

    def resolve_duplicates(self, collected_evidence):
        groups = {}
        for evidence in collected_evidence:
            groups.setdefault((evidence.evidence_text, evidence.source_content), []).append(evidence)
        resolved = []
        for (text, _), group in groups.items():
            references = sorted(
                {
                    self._reference(
                        evidence.evidence_id,
                        evidence.source_type,
                        evidence.source_id,
                    ).reference_id: self._reference(
                        evidence.evidence_id,
                        evidence.source_type,
                        evidence.source_id,
                    )
                    for evidence in group
                }.values(),
                key=lambda reference: reference.reference_id,
            )
            source_types = sorted({reference.source_type for reference in references})
            resolved.append(
                ResolvedEvidence(
                    resolved_evidence_id=self._resolved_id(text, references),
                    evidence_text=text,
                    references=references,
                    source_types=source_types,
                )
            )
        return sorted(resolved, key=lambda item: item.resolved_evidence_id)

    def build_bundles(self, resolved_evidence):
        grouped = {}
        for evidence in resolved_evidence:
            key = tuple(evidence.source_types)
            grouped.setdefault(key, []).append(evidence)
        bundles = []
        for evidence_group in grouped.values():
            evidence_ids = sorted(item.resolved_evidence_id for item in evidence_group)
            references = sorted(
                [reference for item in evidence_group for reference in item.references],
                key=lambda reference: reference.reference_id,
            )
            bundles.append(
                EvidenceBundle(
                    bundle_id=self._bundle_id(evidence_ids),
                    evidence_ids=evidence_ids,
                    source_references=references,
                )
            )
        return sorted(bundles, key=lambda bundle: bundle.bundle_id)

    def validate_resolution(
        self,
        plan,
        claim_result,
        entity_result,
        event_result,
        relationship_graph,
        historical_timeline,
        result,
    ):
        if not self._valid_inputs(
            plan,
            claim_result,
            entity_result,
            event_result,
            relationship_graph,
            historical_timeline,
        ) or not isinstance(result, EvidenceResolutionResult):
            return False
        if result.plan_id != plan.plan_id or result.validation_state != "VALID":
            return False
        if result.evidence_count != len(result.resolved_evidence):
            return False
        if result.bundle_count != len(result.bundles):
            return False
        resolved_ids = [item.resolved_evidence_id for item in result.resolved_evidence]
        if resolved_ids != sorted(resolved_ids) or len(resolved_ids) != len(set(resolved_ids)):
            return False
        valid_sources = self._valid_sources(
            claim_result, entity_result, event_result, relationship_graph, historical_timeline
        )
        references = [reference for item in result.resolved_evidence for reference in item.references]
        reference_ids = [reference.reference_id for reference in references]
        if len(reference_ids) != len(set(reference_ids)):
            return False
        if any(
            reference.source_type not in plan.allowed_source_types
            or (reference.source_type, reference.source_id) not in valid_sources
            or reference.reference_id
            != self._reference_id(reference.evidence_id, reference.source_type, reference.source_id)
            for reference in references
        ):
            return False
        if any(
            item.source_types != sorted(set(reference.source_type for reference in item.references))
            or item.resolved_evidence_id != self._resolved_id(item.evidence_text, item.references)
            for item in result.resolved_evidence
        ):
            return False
        expected_bundles = self.build_bundles(result.resolved_evidence)
        if result.bundles != expected_bundles:
            return False
        return result.result_id == self._result_id(result.resolved_evidence, result.validation_state)

    def validate_runtime_inputs_or_raise(self, *inputs):
        if not self._valid_inputs(*inputs):
            raise ValueError("Invalid evidence resolution inputs")

    def _valid_inputs(
        self, plan, claim_result, entity_result, event_result, relationship_graph, historical_timeline
    ):
        return (
            isinstance(plan, EvidenceResolutionPlan)
            and bool(plan.plan_id)
            and bool(plan.allowed_source_types)
            and all(item in self.SOURCE_TYPES for item in plan.allowed_source_types)
            and isinstance(claim_result, ClaimExtractionResult)
            and claim_result.claim_count == len(claim_result.claims)
            and isinstance(entity_result, EntityExtractionResult)
            and entity_result.entity_count == len(entity_result.entities)
            and isinstance(event_result, EventExtractionResult)
            and event_result.event_count == len(event_result.events)
            and self._graph(relationship_graph) is not None
            and self._timeline(historical_timeline) is not None
        )

    @staticmethod
    def _graph(value):
        if isinstance(value, RelationshipGraphResult):
            return value.graph
        return value if isinstance(value, RelationshipGraph) else None

    @staticmethod
    def _timeline(value):
        if isinstance(value, TimelineBuildResult):
            return value.timeline
        return value if isinstance(value, HistoricalTimeline) else None

    def _valid_sources(self, claim_result, entity_result, event_result, graph, timeline):
        graph = self._graph(graph)
        timeline = self._timeline(timeline)
        return (
            {("CLAIM", item.claim_id) for item in claim_result.claims}
            | {("ENTITY", item.entity_id) for item in entity_result.entities}
            | {("EVENT", item.event_id) for item in event_result.events}
            | {("GRAPH_EDGE", item.edge_id) for item in graph.edges}
            | {("TIMELINE_ENTRY", item.entry_id) for item in timeline.entries}
        )

    @staticmethod
    def _reference(evidence_id, source_type, source_id):
        return EvidenceReference(
            reference_id=EvidenceResolutionRuntime._reference_id(
                evidence_id, source_type, source_id
            ),
            evidence_id=evidence_id,
            source_type=source_type,
            source_id=source_id,
        )

    @staticmethod
    def _reference_id(evidence_id, source_type, source_id):
        return "evidence_reference_" + sha256(
            json.dumps([evidence_id, source_type, source_id], separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]

    @staticmethod
    def _resolved_id(evidence_text, references):
        return "resolved_evidence_" + sha256(
            json.dumps(
                {
                    "evidence_text": evidence_text,
                    "references": [reference.reference_id for reference in references],
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]

    @staticmethod
    def _bundle_id(evidence_ids):
        return "evidence_bundle_" + sha256(
            json.dumps(evidence_ids, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]

    @staticmethod
    def _result_id(resolved_evidence, validation_state):
        return "evidence_resolution_result_" + sha256(
            json.dumps(
                {
                    "resolved_evidence_ids": [item.resolved_evidence_id for item in resolved_evidence],
                    "validation_state": validation_state,
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]


__all__ = ["EvidenceResolutionRuntime"]
