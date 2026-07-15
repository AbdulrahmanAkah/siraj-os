from src.application.documentary_intelligence import CANONICAL_CREATED_AT,deterministic_id
from src.application.publication_packaging.models import PublicationPackage
from .architect import ExportArchitect
from .models import ExportManifest,ExportJob,ExportBundle
class ExportArchitectureRuntime:
 def build_export_bundle(self,policy,publication):
  if not ExportArchitect().validate_policy(policy) or publication.validation_state!="VALID":raise ValueError("Invalid Export Architecture inputs")
  artifacts=["METADATA","CREDITS","SOURCES","EVIDENCE_APPENDIX","VERIFICATION_SUMMARY"]
  manifest=ExportManifest(deterministic_id("export_manifest",[publication.package_id,artifacts]),publication.package_id,artifacts,CANONICAL_CREATED_AT,0,dict(publication.trace_metadata))
  job=ExportJob(deterministic_id("export_job",[manifest.manifest_id,"ARCHITECTURE_ONLY"]),manifest.manifest_id,"ARCHITECTURE_ONLY",CANONICAL_CREATED_AT,0,dict(publication.trace_metadata))
  result=ExportBundle(deterministic_id("export_bundle",[manifest.manifest_id,job.job_id]),manifest,[job],CANONICAL_CREATED_AT,0,dict(publication.trace_metadata))
  if not self.validate_export_bundle(publication,result):raise ValueError("Invalid Export Architecture result")
  return result
 def validate_export_bundle(self,publication,result):return isinstance(result,ExportBundle) and result.validation_state=="VALID" and result.manifest.publication_package_id==publication.package_id and len(result.jobs)==1 and result.jobs[0].manifest_id==result.manifest.manifest_id and result.jobs[0].job_type=="ARCHITECTURE_ONLY"
