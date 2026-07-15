from src.application.documentary_intelligence import CANONICAL_CREATED_AT, canonical_trace, deterministic_id, stable_unique
from src.application.documentary_planning_v2.models import DocumentaryPlan
from .architect import NarrativeArchitectureArchitectV2
from .models import NarrativeArchitecture, NarrativeBeat, NarrativeArchitecturePolicy

class NarrativeArchitectureRuntimeV2:
    ROLE_MAP = {"OPENING":"OPENING", "CONTEXT":"CONTEXT", "DEVELOPMENT":"ESCALATION", "TURNING_POINT":"TURNING_POINT", "OUTCOME":"RESOLUTION"}
    def build_narrative_architecture(self, policy, plan):
        if not isinstance(plan, DocumentaryPlan) or plan.validation_state != "VALID" or not NarrativeArchitectureArchitectV2().validate_policy(policy):
            raise ValueError("Invalid Narrative Architecture v2 inputs")
        beats=[]
        for chapter in plan.major_chapters:
            role=self.ROLE_MAP[chapter.chapter_role]
            trace=canonical_trace(source_ids=chapter.trace_metadata.get("source_ids", []), evidence_ids=chapter.evidence_ids, claim_ids=chapter.trace_metadata.get("claim_ids", []), event_ids=chapter.event_ids, reasoning_ids=chapter.trace_metadata.get("reasoning_ids", []))
            beats.append(NarrativeBeat(deterministic_id("narrative_beat_v2", [chapter.chapter_id, role, trace, chapter.position]), chapter.chapter_id, role, list(chapter.event_ids), list(chapter.evidence_ids), CANONICAL_CREATED_AT, chapter.position, trace))
        trace=canonical_trace(source_ids=(x for b in beats for x in b.trace_metadata["source_ids"]), evidence_ids=(x for b in beats for x in b.evidence_ids), claim_ids=(x for b in beats for x in b.trace_metadata["claim_ids"]), event_ids=(x for b in beats for x in b.event_ids), reasoning_ids=(x for b in beats for x in b.trace_metadata["reasoning_ids"]))
        result=NarrativeArchitecture(deterministic_id("narrative_architecture_v2", [plan.plan_id, [b.beat_id for b in beats], trace]), plan.plan_id, beats, len(beats), CANONICAL_CREATED_AT, 0, trace)
        if not self.validate_narrative_architecture(policy, plan, result): raise ValueError("Invalid Narrative Architecture v2 result")
        return result
    def validate_narrative_architecture(self, policy, plan, result):
        return isinstance(result, NarrativeArchitecture) and result.documentary_plan_id == plan.plan_id and result.beat_count == len(result.beats) and [b.position for b in result.beats] == list(range(len(result.beats))) and len({b.beat_id for b in result.beats}) == len(result.beats) and all(b.role in policy.roles and b.evidence_ids and b.created_at == CANONICAL_CREATED_AT for b in result.beats)
