import hashlib, json
from src.application.claim_extraction.models import ClaimExtractionResult
from src.application.entity_extraction.models import EntityExtractionResult
from src.application.event_extraction.models import EventExtractionResult
from .models import CorrelationCandidate, CorrelationGroup, CorrelationPlan, CorrelationResult

class MultiSourceCorrelationRuntime:
    def collect_candidates(self, plan, claims, entities, events):
        records = []
        if "CLAIM" in plan.allowed_correlation_types:
            records += [("CLAIM", claim.claim_text, claim.claim_id) for claim in claims.claims]
        if "ENTITY" in plan.allowed_correlation_types:
            records += [("ENTITY", f"{entity.entity_name}\x00{entity.entity_type}", entity.entity_id) for entity in entities.entities]
        if "EVENT" in plan.allowed_correlation_types:
            records += [("EVENT", f"{event.event_title}\x00{event.event_type}\x00{event.event_date}", event.event_id) for event in events.events]
        grouped = {}
        for kind, key, source_id in records: grouped.setdefault((kind, key), []).append(source_id)
        return [CorrelationCandidate(self._id("correlation_candidate", [kind, key, *sorted(ids)]), kind, key, sorted(ids)) for (kind, key), ids in grouped.items() if len(set(ids)) > 1]
    def build_correlation_result(self, plan, claims, entities, events):
        if not self._inputs(plan, claims, entities, events): raise ValueError("Invalid correlation inputs")
        candidates = self.collect_candidates(plan, claims, entities, events)
        groups = sorted([CorrelationGroup(self._id("correlation_group", [item.correlation_type, item.correlation_key, *item.source_ids]), item.correlation_type, item.correlation_key, item.source_ids) for item in candidates], key=lambda item: item.group_id)
        result = CorrelationResult(self._id("correlation_result", [plan.plan_id, *[item.group_id for item in groups], "VALID"]), plan.plan_id, groups, len(groups), "VALID")
        if not self.validate_correlation(plan, claims, entities, events, result): raise ValueError("Invalid correlation result")
        return result
    def validate_correlation(self, plan, claims, entities, events, result):
        return self._inputs(plan, claims, entities, events) and isinstance(result, CorrelationResult) and result.plan_id == plan.plan_id and result.group_count == len(result.groups) and result.validation_state == "VALID" and [x.group_id for x in result.groups] == sorted(x.group_id for x in result.groups) and len({x.group_id for x in result.groups}) == len(result.groups) and all(len(x.source_ids) > 1 and x.source_ids == sorted(set(x.source_ids)) for x in result.groups)
    @staticmethod
    def _inputs(plan, claims, entities, events): return isinstance(plan, CorrelationPlan) and isinstance(claims, ClaimExtractionResult) and isinstance(entities, EntityExtractionResult) and isinstance(events, EventExtractionResult) and claims.claim_count == len(claims.claims) and entities.entity_count == len(entities.entities) and events.event_count == len(events.events)
    @staticmethod
    def _id(prefix, values): return prefix + "_" + hashlib.sha256(json.dumps(values, separators=(",", ":")).encode()).hexdigest()[:16]
