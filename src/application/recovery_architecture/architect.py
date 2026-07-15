from src.application.operations_common import *
class RecoveryArchitect:
 def build_recovery_policy(self):return {"policy_id":deterministic_id("recovery_policy",["RESTORE_SNAPSHOT"]),"timestamp":CANONICAL_TIMESTAMP}
