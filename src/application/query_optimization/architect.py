from src.application.operations_common import *
from .models import QueryStrategy,QueryPlan
class QueryOptimizationArchitect:
 def build_query_plan(self,key):
  strategy=QueryStrategy(deterministic_id("query_strategy",["EXACT",key]),["EXACT_LOOKUP","FILTER"],CANONICAL_TIMESTAMP,0,canonical_version_metadata(key),{}, {})
  return QueryPlan(deterministic_id("query_plan",[key,strategy.strategy_id]),key,strategy,CANONICAL_TIMESTAMP,0,canonical_version_metadata(key),{}, {})
