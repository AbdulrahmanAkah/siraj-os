from src.application.operations_common import *
from .models import WorkflowStep,WorkflowDefinition
class WorkflowArchitect:
 def build_workflow_definition(self,names):
  steps=[WorkflowStep(deterministic_id("workflow_step",[name,pos]),name,([] if pos==0 else ["step_"+str(pos-1)]),CANONICAL_TIMESTAMP,pos,canonical_version_metadata(name),{}) for pos,name in enumerate(names)]
  return WorkflowDefinition(deterministic_id("workflow_definition",[x.name for x in steps]),steps,CANONICAL_TIMESTAMP,0,canonical_version_metadata("workflow"),{})
