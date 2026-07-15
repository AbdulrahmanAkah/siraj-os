from src.application.operations_common import *
from src.application.performance_common import performance_metadata
from .models import QueryStatistics,QueryResultProfile
class QueryOptimizationRuntime:
 def execute_query_plan(self,plan,manifest):
  matches=[plan.query_key] if plan.query_key in manifest.index.entries else []
  perf=performance_metadata(matches,"query");stats=QueryStatistics(deterministic_id("query_statistics",[plan.query_key,len(matches)]),1,len(matches),CANONICAL_TIMESTAMP,0,canonical_version_metadata(plan.plan_id),{},perf)
  return QueryResultProfile(deterministic_id("query_profile",[plan.plan_id,matches]),plan.plan_id,matches,stats,CANONICAL_TIMESTAMP,0,canonical_version_metadata(plan.plan_id),{},perf,"VALID")
