from src.application.operations_common import *
from src.application.performance_common import *
from .models import *
class GraphOptimizationRuntime:
 def optimize_graph(self,graph):
  nodes=sorted(n.node_id for n in graph.nodes);chunks=partition_items(nodes,2);parts=[GraphPartition(deterministic_id("graph_partition",x),x,i,canonical_version_metadata("graph"),{},performance_metadata(x,"graph_partition")) for i,x in enumerate(chunks)];perf=performance_metadata(nodes,"graph");plan=GraphTraversalPlan(deterministic_id("graph_traversal",nodes),nodes,0,canonical_version_metadata("graph"),{},perf);stats=GraphStatistics(deterministic_id("graph_statistics",[len(nodes),len(graph.edges)]),len(nodes),len(graph.edges),perf);return GraphOptimizationResult(deterministic_id("graph_optimization",nodes),parts,plan,stats,"VALID")
