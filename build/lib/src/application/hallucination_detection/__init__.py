class HallucinationDetectionArchitect:
 def detect(self,citations,evidence_ids):return ["UNKNOWN_SOURCE_ID" for x in citations if x not in set(evidence_ids)]
