import hashlib,json
from src.application.evidence_resolution.models import EvidenceResolutionResult
from src.application.contradiction_detection.models import ContradictionResult
from .models import SourceProfile,SourceReliabilityScore,ReliabilityResult
class SourceReliabilityRuntime:
    LEVELS=("VERY_LOW","LOW","MEDIUM","HIGH","VERY_HIGH")
    def build_reliability_result(self,evidence,contradictions):
        if not isinstance(evidence,EvidenceResolutionResult) or not isinstance(contradictions,ContradictionResult): raise ValueError("Invalid reliability inputs")
        refs=[r for item in evidence.resolved_evidence for r in item.references]; sources=sorted({(r.source_type,r.source_id) for r in refs}); scores=[]
        for typ,sid in sources:
            count=sum(r.source_type==typ and r.source_id==sid for r in refs); value=len(sources)+count-contradictions.contradiction_count; level=self.LEVELS[max(0,min(4,value-1))]
            scores.append(SourceReliabilityScore(self._id([sid,level,value]),sid,level,value))
        scores=sorted(scores,key=lambda x:x.score_id); return ReliabilityResult(self._id([x.score_id for x in scores]),scores,len(scores))
    def validate_reliability(self,result): return isinstance(result,ReliabilityResult) and result.score_count==len(result.scores) and len({x.score_id for x in result.scores})==len(result.scores)
    @staticmethod
    def _id(value): return "reliability_"+hashlib.sha256(json.dumps(value).encode()).hexdigest()[:16]
