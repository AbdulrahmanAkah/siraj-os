from src.application.documentary_intelligence import CANONICAL_CREATED_AT,deterministic_id
from src.application.documentary_planning_v2.models import DocumentaryPlan
from src.application.narrative_architecture_v2.models import NarrativeArchitecture
from src.application.documentary_script_runtime.models import DocumentaryScript
from src.application.scene_generation_runtime.models import ScenePlanRuntime
from src.application.storyboard_runtime.models import Storyboard
from .architect import DocumentaryAssemblyArchitect
from .models import DocumentaryPackage
class DocumentaryAssemblyRuntime:
 def build_documentary_package(self,policy,plan,narrative,script,scenes,storyboard):
  if not DocumentaryAssemblyArchitect().validate_policy(policy) or not all(getattr(x,"validation_state",None)=="VALID" for x in (plan,narrative,script,scenes,storyboard)): raise ValueError("Invalid Documentary Assembly inputs")
  if narrative.documentary_plan_id!=plan.plan_id or script.narrative_architecture_id!=narrative.architecture_id or scenes.documentary_script_id!=script.script_id or storyboard.scene_plan_id!=scenes.plan_id: raise ValueError("Broken Documentary Assembly references")
  trace=dict(storyboard.trace_metadata)
  result=DocumentaryPackage(deterministic_id("documentary_package",[plan.plan_id,narrative.architecture_id,script.script_id,scenes.plan_id,storyboard.storyboard_id,trace]),plan.plan_id,narrative.architecture_id,script.script_id,scenes.plan_id,storyboard.storyboard_id,CANONICAL_CREATED_AT,0,trace)
  if not self.validate_documentary_package(result): raise ValueError("Invalid Documentary Assembly result")
  return result
 def validate_documentary_package(self,result): return isinstance(result,DocumentaryPackage) and result.created_at==CANONICAL_CREATED_AT and result.validation_state=="VALID" and all([result.package_id,result.documentary_plan_id,result.narrative_architecture_id,result.script_id,result.scene_plan_id,result.storyboard_id])
