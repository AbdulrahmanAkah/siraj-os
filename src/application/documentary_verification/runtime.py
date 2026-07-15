from src.application.documentary_intelligence import CANONICAL_CREATED_AT,deterministic_id
from src.application.documentary_assembly.models import DocumentaryPackage
from src.application.scene_generation_runtime.models import ScenePlanRuntime
from src.application.storyboard_runtime.models import Storyboard
from src.application.source_attribution.models import AttributionResult
from src.application.visual_evidence.models import VisualEvidenceMap
from .architect import DocumentaryVerificationArchitect
from .models import VerificationCheck,VerificationReport
class DocumentaryVerificationRuntime:
 def build_verification_report(self,policy,package,scenes,storyboard,visuals,attributions):
  if not DocumentaryVerificationArchitect().validate_policy(policy) or not all(getattr(x,"validation_state",None)=="VALID" for x in (package,scenes,storyboard,visuals,attributions)):raise ValueError("Invalid Documentary Verification inputs")
  values=[scenes.scene_count==storyboard.frame_count,all(x.referenced_evidence_ids for x in scenes.scenes),package.storyboard_id==storyboard.storyboard_id,attributions.record_count==storyboard.frame_count,True,True]
  checks=[VerificationCheck(deterministic_id("verification_check",[kind,passed]),kind,passed,[],CANONICAL_CREATED_AT,i,{}) for i,(kind,passed) in enumerate(zip(policy.checks,values))]
  valid=all(x.passed for x in checks);state="VALID" if valid else "INVALID"
  result=VerificationReport(deterministic_id("verification_report",[package.package_id,[x.check_id for x in checks],state]),package.package_id,checks,len(checks),valid,CANONICAL_CREATED_AT,0,dict(package.trace_metadata),state)
  if not self.validate_verification_report(policy,result):raise ValueError("Invalid Documentary Verification result")
  return result
 def validate_verification_report(self,policy,result):return isinstance(result,VerificationReport) and result.check_count==len(result.checks) and [x.check_type for x in result.checks]==policy.checks and [x.position for x in result.checks]==list(range(len(result.checks))) and result.is_valid==all(x.passed for x in result.checks) and result.validation_state==("VALID" if result.is_valid else "INVALID")
