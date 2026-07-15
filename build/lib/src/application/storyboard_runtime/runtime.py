from src.application.documentary_intelligence import CANONICAL_CREATED_AT,canonical_trace,deterministic_id
from src.application.scene_generation_runtime.models import ScenePlanRuntime
from .architect import StoryboardArchitectRuntime
from .models import Storyboard,StoryboardFrame,StoryboardPolicy
class StoryboardRuntime:
 def build_storyboard(self,policy,scene_plan):
  if not StoryboardArchitectRuntime().validate_policy(policy) or not isinstance(scene_plan,ScenePlanRuntime) or scene_plan.validation_state!="VALID": raise ValueError("Invalid Storyboard Runtime inputs")
  frames=[StoryboardFrame(deterministic_id("storyboard_frame",[s.scene_id,s.scene_purpose,s.referenced_evidence_ids]),s.scene_id,s.scene_purpose,list(s.referenced_evidence_ids),CANONICAL_CREATED_AT,s.position,dict(s.trace_metadata)) for s in scene_plan.scenes]
  trace=canonical_trace(source_ids=(x for f in frames for x in f.trace_metadata.get("source_ids",[])),evidence_ids=(x for f in frames for x in f.referenced_evidence_ids),claim_ids=(x for f in frames for x in f.trace_metadata.get("claim_ids",[])),event_ids=(x for f in frames for x in f.trace_metadata.get("event_ids",[])),reasoning_ids=(x for f in frames for x in f.trace_metadata.get("reasoning_ids",[])))
  result=Storyboard(deterministic_id("storyboard",[scene_plan.plan_id,[f.frame_id for f in frames],trace]),scene_plan.plan_id,frames,len(frames),CANONICAL_CREATED_AT,0,trace)
  if not self.validate_storyboard(scene_plan,result): raise ValueError("Invalid Storyboard Runtime result")
  return result
 def validate_storyboard(self,scene_plan,result): return isinstance(result,Storyboard) and result.scene_plan_id==scene_plan.plan_id and result.frame_count==len(result.frames) and [f.position for f in result.frames]==list(range(len(result.frames))) and len({f.scene_id for f in result.frames})==scene_plan.scene_count and all(f.referenced_evidence_ids for f in result.frames)
