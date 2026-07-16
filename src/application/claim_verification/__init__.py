class ClaimVerificationEngine:
 def verify(self,claim_ids,known_claim_ids):return ["SUPPORTED" if x in set(known_claim_ids) else "UNVERIFIABLE" for x in claim_ids]
