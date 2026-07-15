from src.application.operations_common import *
class ExecutionMonitoringArchitect:
 def build_monitoring_policy(self):return {"policy_id":deterministic_id("monitoring_policy",["JOB_COUNTS"]),"timestamp":CANONICAL_TIMESTAMP}
