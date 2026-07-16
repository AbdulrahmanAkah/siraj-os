
class ConfidenceEngine:

    def score(self,c):

        s=max(c.confidence,0.50)

        if c.kind=="PERSON":
            s=max(s,0.90)

        elif c.kind=="PLACE":
            s=max(s,0.90)

        elif c.kind=="EVENT":
            s=max(s,0.85)

        elif c.kind=="CLAIM":
            s=max(s,0.75)

        elif c.kind=="RELATIONSHIP":
            s=max(s,0.75)

        elif c.kind=="SOURCE":
            s=max(s,0.80)

        elif c.kind=="EVIDENCE":
            s=max(s,0.70)

        if c.metadata.get("has_date"):
            s+=0.05

        if c.metadata.get("has_subject"):
            s+=0.05

        if c.metadata.get("has_verb"):
            s+=0.05

        if c.metadata.get("trusted_source"):
            s+=0.05

        c.confidence=min(1.0,s)

        return c


