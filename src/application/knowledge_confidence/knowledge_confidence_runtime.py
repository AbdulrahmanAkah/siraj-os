import hashlib,json
from src.application.evidence_weighting.models import EvidenceWeightResult
from src.application.source_reliability.models import ReliabilityResult
from src.application.contradiction_detection.models import ContradictionResult
from .models import ConfidenceRecord,ConfidenceAssessment,KnowledgeConfidenceResult
class KnowledgeConfidenceRuntime:
 LEVELS=("VERY_LOW","LOW","MEDIUM","HIGH","VERY_HIGH")
 def build_confidence_result(self,weights,reliability,contradictions):
  if not isinstance(weights,EvidenceWeightResult) or not isinstance(reliability,ReliabilityResult) or not isinstance(contradictions,ContradictionResult): raise ValueError("Invalid confidence inputs")
  penalty=1 if contradictions.contradiction_count else 0; records=[]
  for x in weights.weighted_evidence:
   level=self.LEVELS[min(4,max(0,x.weight.weight-1-penalty))]; records.append(ConfidenceRecord(self._id([x.resolved_evidence_id,level]),x.resolved_evidence_id,level))
  records=sorted(records,key=lambda x:x.confidence_id); a=ConfidenceAssessment(self._id([x.confidence_id for x in records]),records);return KnowledgeConfidenceResult(self._id([a.assessment_id]),a,len(records))
 def validate_confidence(self,r): return isinstance(r,KnowledgeConfidenceResult) and r.record_count==len(r.assessment.records)
 @staticmethod
 def _id(x): return "knowledge_confidence_"+hashlib.sha256(json.dumps(x).encode()).hexdigest()[:16]
