from src.application.operations_common import *
from src.application.workflow_runtime.models import WorkflowExecution
from .models import Job,JobQueue,JobResult
class JobOrchestrationRuntime:
 def orchestrate_jobs(self,execution):
  jobs=[Job(deterministic_id("job",[step,pos]),step,"QUEUED",CANONICAL_TIMESTAMP,pos,canonical_version_metadata(step),{}) for pos,step in enumerate(execution.completed_step_ids)]
  queue=JobQueue(deterministic_id("job_queue",[x.job_id for x in jobs]),jobs,CANONICAL_TIMESTAMP,0,canonical_version_metadata(execution.execution_id),{})
  results=[JobResult(deterministic_id("job_result",[j.job_id,"COMPLETED"]),j.job_id,"COMPLETED",CANONICAL_TIMESTAMP,j.position,canonical_version_metadata(j.job_id),{}) for j in jobs]
  return queue,results
