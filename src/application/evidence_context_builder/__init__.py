from src.application.operations_common import deterministic_id,integrity_hash,stable_unique
from src.application.ai_integration import EvidenceContext
class EvidenceContextBuilder:
 def build(self,evidence_ids,budget=None):
  ids=stable_unique(evidence_ids);selected=ids if budget is None else ids[:budget];return EvidenceContext(deterministic_id("evidence_context",selected),selected,ids[len(selected):],integrity_hash(selected))
