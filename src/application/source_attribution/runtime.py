from src.application.documentary_intelligence import CANONICAL_CREATED_AT,deterministic_id
from src.application.documentary_assembly.models import DocumentaryPackage
from src.application.storyboard_runtime.models import Storyboard
from .architect import SourceAttributionArchitect
from .models import AttributionRecord,AttributionResult
class SourceAttributionRuntime:
 def build_attribution_result(self,policy,package,storyboard):
  if not SourceAttributionArchitect().validate_policy(policy) or package.storyboard_id!=storyboard.storyboard_id:raise ValueError("Invalid Source Attribution inputs")
  records=[AttributionRecord(deterministic_id("attribution_record",[f.frame_id,f.trace_metadata]),f.frame_id,list(f.trace_metadata.get("source_ids",[])),list(f.referenced_evidence_ids),list(f.trace_metadata.get("claim_ids",[])),CANONICAL_CREATED_AT,f.position,dict(f.trace_metadata)) for f in storyboard.frames]
  result=AttributionResult(deterministic_id("attribution_result",[package.package_id,[r.attribution_id for r in records]]),package.package_id,records,len(records),CANONICAL_CREATED_AT,0,dict(package.trace_metadata))
  if not self.validate_attribution_result(result):raise ValueError("Invalid Source Attribution result")
  return result
 def validate_attribution_result(self,r):return isinstance(r,AttributionResult) and r.record_count==len(r.records) and [x.position for x in r.records]==list(range(len(r.records))) and all(x.evidence_ids for x in r.records)
