from src.application.documentary_intelligence import CANONICAL_CREATED_AT,deterministic_id,stable_unique
from src.application.documentary_assembly.models import DocumentaryPackage
from src.application.source_attribution.models import AttributionResult
from src.application.documentary_verification.models import VerificationReport
from .architect import PublicationPackagingArchitect
from .models import PublicationPackage
class PublicationPackagingRuntime:
 def build_publication_package(self,policy,package,attributions,verification):
  if not PublicationPackagingArchitect().validate_policy(policy) or not verification.is_valid:raise ValueError("Invalid Publication Packaging inputs")
  sources=stable_unique(x for r in attributions.records for x in r.source_ids); evidence=stable_unique(x for r in attributions.records for x in r.evidence_ids)
  result=PublicationPackage(deterministic_id("publication_package",[package.package_id,sources,evidence,verification.report_id]),package.package_id,{"package_id":package.package_id},list(sources),list(sources),list(evidence),"VALID",CANONICAL_CREATED_AT,0,dict(package.trace_metadata))
  if not self.validate_publication_package(result):raise ValueError("Invalid Publication Packaging result")
  return result
 def validate_publication_package(self,r):return isinstance(r,PublicationPackage) and r.validation_state=="VALID" and r.verification_summary=="VALID" and bool(r.package_id)
