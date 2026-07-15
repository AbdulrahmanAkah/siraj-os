from src.application.operations_common import *
from .models import WorkflowStep,WorkflowDefinition
class WorkflowArchitect:
 def build_workflow_definition(self,names):
  steps=[]
  for pos,name in enumerate(names):
   step_id=deterministic_id("workflow_step",[name,pos])
   steps.append(WorkflowStep(step_id,name,([] if pos==0 else [steps[-1].step_id]),CANONICAL_TIMESTAMP,pos,canonical_version_metadata(name),{}))
  return WorkflowDefinition(deterministic_id("workflow_definition",[x.name for x in steps]),steps,CANONICAL_TIMESTAMP,0,canonical_version_metadata("workflow"),{})
