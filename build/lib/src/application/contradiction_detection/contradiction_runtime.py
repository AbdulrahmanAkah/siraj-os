import hashlib, json, re
from src.application.claim_extraction.models import ClaimExtractionResult
from .models import ContradictionCandidate, ContradictionRecord, ContradictionResult
class ContradictionRuntime:
    PATTERN = re.compile(r"^(.+?)\s*(?:=|:|is)\s*(.+?)$")
    def detect_contradictions(self, claims):
        if not isinstance(claims, ClaimExtractionResult): raise ValueError("Invalid claim result")
        values = {}
        for claim in claims.claims:
            match = self.PATTERN.match(claim.claim_text)
            if match: values.setdefault((match.group(1).strip(), "VALUE"), []).append((match.group(2).strip(), claim.claim_id))
        records=[]
        for (subject,predicate), items in values.items():
            distinct=sorted({x[0] for x in items})
            if len(distinct)>1:
                ids=sorted(x[1] for x in items); key=[subject,predicate,*distinct,*ids]
                records.append(ContradictionRecord(self._id("contradiction",key),subject,predicate,distinct,ids))
        records=sorted(records,key=lambda x:x.contradiction_id)
        return ContradictionResult(self._id("contradiction_result",[x.contradiction_id for x in records]),records,len(records))
    def validate_contradictions(self,result): return isinstance(result,ContradictionResult) and result.contradiction_count==len(result.contradictions) and len({x.contradiction_id for x in result.contradictions})==len(result.contradictions)
    @staticmethod
    def _id(prefix,value): return prefix+"_"+hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()[:16]
