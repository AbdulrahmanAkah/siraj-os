from src.application.documentary_intelligence import CANONICAL_CREATED_AT, canonical_trace, deterministic_id
from src.application.narrative_architecture_v2.models import NarrativeArchitecture
from .architect import DocumentaryScriptArchitect
from .models import DocumentaryScript, DocumentaryScriptPolicy, ScriptParagraph, ScriptSection
class DocumentaryScriptRuntime:
    def build_documentary_script(self, policy, narrative):
        if not DocumentaryScriptArchitect().validate_policy(policy) or not isinstance(narrative, NarrativeArchitecture) or narrative.validation_state != "VALID": raise ValueError("Invalid Documentary Script inputs")
        sections=[]
        for beat in narrative.beats:
            trace=dict(beat.trace_metadata)
            paragraph=ScriptParagraph(deterministic_id("script_paragraph", [beat.beat_id, beat.role, beat.evidence_ids]), beat.role, list(beat.evidence_ids), CANONICAL_CREATED_AT, 0, trace)
            sections.append(ScriptSection(deterministic_id("script_section", [beat.beat_id, paragraph.paragraph_id]), beat.beat_id, beat.role, [paragraph], CANONICAL_CREATED_AT, beat.position, trace))
        trace=canonical_trace(source_ids=(x for s in sections for x in s.trace_metadata.get("source_ids", [])), evidence_ids=(x for s in sections for x in s.paragraphs[0].evidence_ids), claim_ids=(x for s in sections for x in s.trace_metadata.get("claim_ids", [])), event_ids=(x for s in sections for x in s.trace_metadata.get("event_ids", [])), reasoning_ids=(x for s in sections for x in s.trace_metadata.get("reasoning_ids", [])))
        result=DocumentaryScript(deterministic_id("documentary_script", [narrative.architecture_id, [s.section_id for s in sections], trace]), narrative.architecture_id, sections, len(sections), CANONICAL_CREATED_AT, 0, trace)
        if not self.validate_documentary_script(narrative,result): raise ValueError("Invalid Documentary Script result")
        return result
    def validate_documentary_script(self,narrative,result): return isinstance(result,DocumentaryScript) and result.narrative_architecture_id==narrative.architecture_id and result.section_count==len(result.sections) and [s.position for s in result.sections]==list(range(len(result.sections))) and all(len(s.paragraphs)==1 and s.paragraphs[0].evidence_ids for s in result.sections)
