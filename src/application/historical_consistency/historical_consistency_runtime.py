import hashlib, json
from src.application.event_extraction.models import EventExtractionResult
from src.application.relationship_graph.models import RelationshipGraph
from src.application.historical_timeline.models import HistoricalTimeline
from .models import ConsistencyCheck, ConsistencyReport, ConsistencyResult
class HistoricalConsistencyRuntime:
    def build_consistency_result(self, event_result, graph, timeline):
        if not isinstance(event_result, EventExtractionResult) or not isinstance(graph, RelationshipGraph) or not isinstance(timeline, HistoricalTimeline): raise ValueError("Invalid consistency inputs")
        node_ids = {node.node_id for node in graph.nodes}
        expected = sorted(timeline.entries, key=lambda x: (x.event_date is None, x.event_date or "", x.event_id))
        checks = [("BROKEN_GRAPH_REFERENCES", all(edge.source_node_id in node_ids and edge.target_node_id in node_ids for edge in graph.edges)), ("DUPLICATE_TIMELINE_EVENTS", len({x.event_id for x in timeline.entries}) == len(timeline.entries)), ("INVALID_EVENT_ORDERING", timeline.entries == expected), ("IMPOSSIBLE_CHRONOLOGY", all(x.event_id in {event.event_id for event in event_result.events} for x in timeline.entries))]
        check_models = [ConsistencyCheck(self._id(kind, state), kind, state, "PASS" if state else "FAIL") for kind, state in checks]
        report = ConsistencyReport(self._id("consistency_report", [x.check_id for x in check_models]), check_models)
        return ConsistencyResult(self._id("consistency_result", [report.report_id, all(x.is_consistent for x in check_models)]), report, all(x.is_consistent for x in check_models), len(check_models))
    def validate_consistency(self, result): return isinstance(result, ConsistencyResult) and result.check_count == len(result.report.checks) and result.consistent == all(x.is_consistent for x in result.report.checks) and len({x.check_id for x in result.report.checks}) == result.check_count
    @staticmethod
    def _id(prefix, value): return prefix.lower() + "_" + hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()[:16]
