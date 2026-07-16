from src.application.operations_common import *
from .models import ExecutionMetrics,ExecutionStatus,ExecutionReport
class ExecutionMonitoringRuntime:
 def build_execution_report(self,queue,results):
  completed=sum(x.status=="COMPLETED" for x in results);metrics=ExecutionMetrics(deterministic_id("execution_metrics",[completed,len(queue.jobs)]),completed,len(queue.jobs),CANONICAL_TIMESTAMP,0,canonical_version_metadata(queue.queue_id),{})
  status=ExecutionStatus(deterministic_id("execution_status",[completed,len(queue.jobs)]),"COMPLETED" if completed==len(queue.jobs) else "FAILED",CANONICAL_TIMESTAMP,0,canonical_version_metadata(queue.queue_id),{})
  return ExecutionReport(deterministic_id("execution_report",[metrics.metrics_id,status.status_id]),metrics,status,CANONICAL_TIMESTAMP,0,canonical_version_metadata(queue.queue_id),{},"VALID")
