from src.application.documentary_intelligence import CANONICAL_CREATED_AT,canonical_trace,deterministic_id
from src.application.documentary_script_runtime.models import DocumentaryScript
from .architect import SceneGenerationArchitect
from .models import GeneratedScene,SceneGenerationPolicy,ScenePlanRuntime
class SceneGenerationRuntime:
 def build_scene_plan(self,policy,script):
  if not SceneGenerationArchitect().validate_policy(policy) or not isinstance(script,DocumentaryScript) or script.validation_state!="VALID": raise ValueError("Invalid Scene Generation inputs")
  scenes=[]
  for section in script.sections:
   trace=dict(section.trace_metadata); events=trace.get("event_ids",[]); evidence=section.paragraphs[0].evidence_ids
   scenes.append(GeneratedScene(deterministic_id("generated_scene",[section.section_id,section.role,events,evidence]),section.role,list(events),list(evidence),section.section_id,CANONICAL_CREATED_AT,section.position,trace))
  trace=canonical_trace(source_ids=(x for s in scenes for x in s.trace_metadata.get("source_ids",[])),evidence_ids=(x for s in scenes for x in s.referenced_evidence_ids),claim_ids=(x for s in scenes for x in s.trace_metadata.get("claim_ids",[])),event_ids=(x for s in scenes for x in s.referenced_event_ids),reasoning_ids=(x for s in scenes for x in s.trace_metadata.get("reasoning_ids",[])))
  result=ScenePlanRuntime(deterministic_id("scene_plan_runtime",[script.script_id,[s.scene_id for s in scenes],trace]),script.script_id,scenes,len(scenes),CANONICAL_CREATED_AT,0,trace)
  if not self.validate_scene_plan(script,result): raise ValueError("Invalid Scene Generation result")
  return result
 def validate_scene_plan(self,script,result): return isinstance(result,ScenePlanRuntime) and result.documentary_script_id==script.script_id and result.scene_count==len(result.scenes) and [s.position for s in result.scenes]==list(range(len(result.scenes))) and all(s.referenced_evidence_ids and s.narration_section_id for s in result.scenes)
