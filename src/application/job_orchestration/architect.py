from src.application.operations_common import *
class JobOrchestrationArchitect:
 def build_job_policy(self):return {"policy_id":deterministic_id("job_policy",["LOCAL_FIFO"]),"timestamp":CANONICAL_TIMESTAMP}
