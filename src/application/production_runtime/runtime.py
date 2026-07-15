from src.application.documentary_intelligence import CANONICAL_CREATED_AT,deterministic_id
from src.application.publication_packaging.models import PublicationPackage
from src.application.export_architecture.models import ExportBundle
from src.application.documentary_verification.models import VerificationReport
from .architect import ProductionArchitect
from .models import ProductionReadyDocumentary
class ProductionRuntime:
 def build_production_ready_documentary(self,policy,publication,exports,verification):
  if not ProductionArchitect().validate_policy(policy) or not verification.is_valid or publication.validation_state!="VALID" or exports.validation_state!="VALID":raise ValueError("Invalid Production Runtime inputs")
  result=ProductionReadyDocumentary(deterministic_id("production_ready_documentary",[publication.package_id,exports.bundle_id,verification.report_id]),publication.package_id,exports.bundle_id,verification.report_id,CANONICAL_CREATED_AT,0,dict(publication.trace_metadata))
  if not self.validate_production_ready_documentary(publication,exports,verification,result):raise ValueError("Invalid Production Runtime result")
  return result
 def validate_production_ready_documentary(self,publication,exports,verification,result):return isinstance(result,ProductionReadyDocumentary) and result.validation_state=="VALID" and result.publication_package_id==publication.package_id and result.export_bundle_id==exports.bundle_id and result.verification_report_id==verification.report_id and result.created_at==CANONICAL_CREATED_AT
