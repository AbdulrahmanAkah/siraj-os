
from .confidence_engine import ConfidenceEngine

class QualityEngine:

    def __init__(self):
        self.engine=ConfidenceEngine()

    def process(self,candidates):

        accepted=[]
        seen=set()

        for c in candidates:

            c=self.engine.score(c)

            if c.confidence<0.60:
                continue

            key=(
                c.kind,
                str(c.value).strip().lower()
            )

            if key in seen:
                continue

            seen.add(key)
            accepted.append(c)

        return accepted


