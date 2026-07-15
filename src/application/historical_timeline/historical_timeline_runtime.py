from hashlib import sha256
import json

from src.application.event_extraction.event_extraction_runtime import (
    EventExtractionRuntime,
)
from src.application.event_extraction.models import EventExtractionResult
from src.application.relationship_graph.models import (
    RelationshipGraph,
    RelationshipGraphResult,
)
from src.application.relationship_graph.relationship_graph_runtime import (
    RelationshipGraphRuntime,
)

from .models import (
    HistoricalTimeline,
    TimelineBuildResult,
    TimelineCandidate,
    TimelineEntry,
    TimelinePlan,
)


class HistoricalTimelineRuntime:
    """Builds a deterministic chronological timeline from extracted events."""

    def __init__(self, event_extraction_runtime, relationship_graph_runtime):
        if not isinstance(event_extraction_runtime, EventExtractionRuntime):
            raise TypeError(
                "HistoricalTimelineRuntime requires an EventExtractionRuntime"
            )
        if not isinstance(relationship_graph_runtime, RelationshipGraphRuntime):
            raise TypeError(
                "HistoricalTimelineRuntime requires a RelationshipGraphRuntime"
            )
        self.event_extraction_runtime = event_extraction_runtime
        self.relationship_graph_runtime = relationship_graph_runtime

    def build_timeline(self, plan, event_extraction_result, relationship_graph):
        self.validate_runtime_inputs_or_raise(
            plan, event_extraction_result, relationship_graph
        )
        candidates = self.create_timeline_candidates(
            plan, event_extraction_result, relationship_graph
        )
        entries = self.create_timeline_entries(candidates)
        entries = self.sort_timeline(entries)
        timeline = HistoricalTimeline(
            timeline_id=self._timeline_id(plan.plan_id, entries),
            plan_id=plan.plan_id,
            entries=entries,
            entry_count=len(entries),
        )
        result = self.build_timeline_result(timeline)
        if not self.validate_timeline(plan, event_extraction_result, relationship_graph, result):
            raise ValueError("Invalid historical timeline result")
        return result

    def create_timeline_candidates(self, plan, event_extraction_result, relationship_graph):
        graph = self._graph(relationship_graph)
        event_node_ids = {
            node.source_id
            for node in graph.nodes
            if node.node_type == "EVENT_NODE"
        }
        date_by_event_id = self._explicit_graph_dates(graph)
        candidates = []
        seen_event_ids = set()
        for event in event_extraction_result.events:
            if event.event_id in seen_event_ids:
                continue
            seen_event_ids.add(event.event_id)
            if event_node_ids and event.event_id not in event_node_ids:
                continue
            if plan.allowed_event_types and event.event_type not in plan.allowed_event_types:
                continue
            event_date = event.event_date or date_by_event_id.get(event.event_id)
            if event_date is None and not plan.include_undated_events:
                continue
            candidates.append(
                TimelineCandidate(
                    candidate_id=self._candidate_id(event.event_id, event_date),
                    event_id=event.event_id,
                    event_type=event.event_type,
                    event_title=event.event_title,
                    event_date=event_date,
                    source_claim_ids=list(event.source_claim_ids),
                    source_entity_ids=list(event.source_entity_ids),
                )
            )
        return candidates

    def create_timeline_entries(self, candidates):
        entries_by_id = {}
        for candidate in candidates:
            entry = TimelineEntry(
                entry_id=self._entry_id(candidate.event_id, candidate.event_date),
                event_id=candidate.event_id,
                event_type=candidate.event_type,
                event_title=candidate.event_title,
                event_date=candidate.event_date,
                source_claim_ids=list(candidate.source_claim_ids),
                source_entity_ids=list(candidate.source_entity_ids),
            )
            entries_by_id.setdefault(entry.entry_id, entry)
        return list(entries_by_id.values())

    def sort_timeline(self, entries):
        return sorted(
            entries,
            key=lambda entry: (
                entry.event_date is None,
                entry.event_date or "",
                entry.event_id,
            ),
        )

    def build_timeline_result(self, timeline):
        validation_state = "VALID"
        material = {
            "timeline_id": timeline.timeline_id,
            "validation_state": validation_state,
        }
        result_id = (
            "timeline_build_result_"
            f"{sha256(json.dumps(material, sort_keys=True, separators=(",", ":")).encode('utf-8')).hexdigest()[:16]}"
        )
        return TimelineBuildResult(
            result_id=result_id,
            timeline=timeline,
            validation_state=validation_state,
            entry_count=timeline.entry_count,
        )

    def validate_timeline(
        self, plan, event_extraction_result, relationship_graph, build_result
    ):
        if not self._validate_inputs(plan, event_extraction_result, relationship_graph):
            return False
        if not isinstance(build_result, TimelineBuildResult):
            return False
        timeline = build_result.timeline
        if timeline.plan_id != plan.plan_id:
            return False
        if timeline.entry_count != len(timeline.entries):
            return False
        if build_result.entry_count != timeline.entry_count:
            return False
        if build_result.validation_state not in ("VALID", "INVALID"):
            return False
        entry_ids = [entry.entry_id for entry in timeline.entries]
        event_ids = [entry.event_id for entry in timeline.entries]
        if len(entry_ids) != len(set(entry_ids)):
            return False
        if len(event_ids) != len(set(event_ids)):
            return False
        if any(
            entry.entry_id != self._entry_id(entry.event_id, entry.event_date)
            for entry in timeline.entries
        ):
            return False
        if any(
            left.event_date is not None
            and right.event_date is not None
            and (left.event_date, left.event_id) > (right.event_date, right.event_id)
            for left, right in zip(timeline.entries, timeline.entries[1:])
        ):
            return False
        graph = self._graph(relationship_graph)
        graph_event_ids = {
            node.source_id
            for node in graph.nodes
            if node.node_type == "EVENT_NODE"
        }
        if any(entry.event_id not in graph_event_ids for entry in timeline.entries):
            return False
        expected = self.sort_timeline(
            self.create_timeline_entries(
                self.create_timeline_candidates(
                    plan, event_extraction_result, relationship_graph
                )
            )
        )
        return timeline.entries == expected

    def validate_runtime_inputs_or_raise(
        self, plan, event_extraction_result, relationship_graph
    ):
        if not self._validate_inputs(plan, event_extraction_result, relationship_graph):
            raise ValueError("Invalid historical timeline inputs")

    def _validate_inputs(self, plan, event_extraction_result, relationship_graph):
        if not isinstance(plan, TimelinePlan):
            return False
        if not plan.plan_id or plan.validation_level not in ("STRICT", "STANDARD", "BASIC"):
            return False
        if not isinstance(event_extraction_result, EventExtractionResult):
            return False
        if event_extraction_result.event_count != len(event_extraction_result.events):
            return False
        graph = self._graph(relationship_graph)
        if graph is None:
            return False
        if graph.event_extraction_result_id and graph.event_extraction_result_id != event_extraction_result.result_id:
            return False
        return self._graph_has_valid_event_nodes(graph, event_extraction_result)

    @staticmethod
    def _graph(value):
        if isinstance(value, RelationshipGraphResult):
            return value.graph
        if isinstance(value, RelationshipGraph):
            return value
        return None

    @staticmethod
    def _graph_has_valid_event_nodes(graph, event_result):
        event_ids = {
            node.source_id for node in graph.nodes if node.node_type == "EVENT_NODE"
        }
        return all(event.event_id in event_ids for event in event_result.events)

    @staticmethod
    def _explicit_graph_dates(graph):
        nodes = {node.node_id: node for node in graph.nodes}
        dates = {}
        for edge in graph.edges:
            if edge.edge_type != "OCCURRED_ON":
                continue
            event_node = nodes.get(edge.source_node_id)
            date_node = nodes.get(edge.target_node_id)
            if event_node is None or date_node is None:
                continue
            if event_node.node_type == "EVENT_NODE" and date_node.node_type == "ENTITY_NODE":
                if HistoricalTimelineRuntime._is_explicit_date(date_node.source_id):
                    dates[event_node.source_id] = date_node.source_id
        return dates

    @staticmethod
    def _is_explicit_date(value):
        if not isinstance(value, str):
            return False
        parts = value.split("-")
        return (
            len(parts) in (1, 2, 3)
            and len(parts[0]) == 4
            and parts[0].isdigit()
            and all(part.isdigit() for part in parts[1:])
            and all(len(part) in (1, 2) for part in parts[1:])
        )

    @staticmethod
    def _candidate_id(event_id, event_date):
        return "timeline_candidate_" + sha256(
            json.dumps([event_id, event_date], separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]

    @staticmethod
    def _entry_id(event_id, event_date):
        return "timeline_entry_" + sha256(
            json.dumps([event_id, event_date], separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]

    @staticmethod
    def _timeline_id(plan_id, entries):
        return "historical_timeline_" + sha256(
            json.dumps(
                {"plan_id": plan_id, "entry_ids": [entry.entry_id for entry in entries]},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]


__all__ = ["HistoricalTimelineRuntime"]
