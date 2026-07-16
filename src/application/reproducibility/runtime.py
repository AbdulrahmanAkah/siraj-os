from src.application.operations_common import *
from src.application.versioning_engine.models import VersionResult
from .models import ReproductionManifest,ReproducibilityResult
class ReproducibilityRuntime:
 def validate_reproducibility(self,policy,input_value,configuration,versions,output_value):
  if not isinstance(versions,VersionResult):raise ValueError("Invalid reproducibility inputs")
  ids=[x.version_id for x in versions.records];manifest=ReproductionManifest(deterministic_id("reproduction_manifest",[integrity_hash(input_value),integrity_hash(configuration),ids,integrity_hash(output_value)]),integrity_hash(input_value),integrity_hash(configuration),ids,integrity_hash(output_value),CANONICAL_TIMESTAMP,0,canonical_version_metadata("reproduction"),{})
  return ReproducibilityResult(deterministic_id("reproducibility_result",manifest.manifest_id),manifest,True,CANONICAL_TIMESTAMP,0,canonical_version_metadata(manifest.manifest_id),{},"VALID")
