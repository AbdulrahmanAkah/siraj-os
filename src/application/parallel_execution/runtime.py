from src.application.operations_common import *
from src.application.performance_common import *
from .models import *
class ParallelExecutionRuntime:
 def build_parallel_plan(self,item_ids):
  chunks=partition_items(sorted(item_ids),2);parts=[ExecutionPartition(deterministic_id("execution_partition",x),x,i,canonical_version_metadata("parallel"),{},performance_metadata(x,"parallel")) for i,x in enumerate(chunks)];plan=ParallelPlan(deterministic_id("parallel_plan",[x.partition_id for x in parts]),parts,canonical_version_metadata("parallel"),{},performance_metadata(item_ids,"parallel"));shards=[ExecutionShard(deterministic_id("execution_shard",x.partition_id),x.partition_id,list(x.item_ids),x.position,canonical_version_metadata(x.partition_id),{},x.performance_metadata) for x in parts];return plan,shards
