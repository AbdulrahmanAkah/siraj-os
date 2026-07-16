from src.application.documentary_intelligence import CANONICAL_CREATED_AT,canonical_trace,deterministic_id
from .models import PublicationPackagingPolicy
class PublicationPackagingArchitect:
 def build_publication_policy(self):return PublicationPackagingPolicy(deterministic_id("publication_policy",["METADATA","CREDITS","SOURCES","EVIDENCE_APPENDIX","VERIFICATION"]),CANONICAL_CREATED_AT,0,canonical_trace())
 def validate_policy(self,p):return isinstance(p,PublicationPackagingPolicy) and p.created_at==CANONICAL_CREATED_AT
