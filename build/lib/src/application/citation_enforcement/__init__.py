class CitationEnforcementEngine:
 def enforce(self,citations,evidence_ids):return "VALID" if citations and set(citations)<=set(evidence_ids) else "MISSING"
