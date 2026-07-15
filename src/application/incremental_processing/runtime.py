from src.application.operations_common import *
from src.application.performance_common import performance_metadata
from .models import *
class IncrementalProcessingRuntime:
 def process_changes(self,changed_ids):
  ids=sorted(set(changed_ids));perf=performance_metadata(ids,"incremental");changes=ChangeSet(deterministic_id("change_set",ids),ids,canonical_version_metadata("incremental"),{},perf);plan=IncrementalPlan(deterministic_id("incremental_plan",ids),ids,canonical_version_metadata("incremental"),{},perf);return changes,plan,IncrementalResult(deterministic_id("incremental_result",ids),ids,"VALID",canonical_version_metadata("incremental"),{},perf)
