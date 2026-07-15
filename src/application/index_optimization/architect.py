from src.application.operations_common import *
class IndexOptimizationArchitect:
 def build_index_policy(self):return {"policy_id":deterministic_id("index_policy",["SORTED_SEGMENTS"]),"segment_size":2,"timestamp":CANONICAL_TIMESTAMP}
