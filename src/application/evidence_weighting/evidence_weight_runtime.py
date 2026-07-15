import hashlib,json
from src.application.evidence_resolution.models import EvidenceResolutionResult
from src.application.source_reliability.models import ReliabilityResult
from src.application.multi_source_correlation.models import CorrelationResult
from .models import EvidenceWeight,WeightedEvidence,EvidenceWeightResult
class EvidenceWeightRuntime:
 LEVELS=("VERY_LOW","LOW","MEDIUM","HIGH","VERY_HIGH")
 def build_weight_result(self,evidence,reliability,correlation):
  if not isinstance(evidence,EvidenceResolutionResult) or not isinstance(reliability,ReliabilityResult) or not isinstance(correlation,CorrelationResult): raise ValueError("Invalid weight inputs")
  rank={x:i+1 for i,x in enumerate(self.LEVELS)}; rel=max([rank[x.reliability] for x in reliability.scores] or [1]); out=[]
  for item in evidence.resolved_evidence:
   value=rel+len(item.references)+correlation.group_count; level=self.LEVELS[min(4,max(0,value-1))]; w=EvidenceWeight(self._id([item.resolved_evidence_id,value]),item.resolved_evidence_id,value,level);out.append(WeightedEvidence(item.resolved_evidence_id,w))
  out=sorted(out,key=lambda x:x.resolved_evidence_id);return EvidenceWeightResult(self._id([x.weight.weight_id for x in out]),out,len(out))
 def validate_weights(self,r): return isinstance(r,EvidenceWeightResult) and r.weight_count==len(r.weighted_evidence)
 @staticmethod
 def _id(x): return "evidence_weight_"+hashlib.sha256(json.dumps(x).encode()).hexdigest()[:16]
