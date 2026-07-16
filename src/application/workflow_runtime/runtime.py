from src.application.operations_common import *
from .models import WorkflowExecution
class WorkflowRuntime:
 def execute_workflow(self,definition):
  ids=[x.step_id for x in definition.steps]
  return WorkflowExecution(deterministic_id("workflow_execution",[definition.workflow_id,ids]),definition.workflow_id,ids,CANONICAL_TIMESTAMP,0,canonical_version_metadata(definition.workflow_id),definition.trace_metadata,"VALID")
