from dataclasses import dataclass,field
from src.application.operations_common import deterministic_id
@dataclass
class BenchmarkMetric: metric_id:str; name:str; units:int
@dataclass
class BenchmarkRun: run_id:str; operation:str; metrics:list[BenchmarkMetric]=field(default_factory=list)
@dataclass
class BenchmarkReport: report_id:str; runs:list[BenchmarkRun]=field(default_factory=list); validation_state:str="VALID"
class BenchmarkingArchitect:
 def build_benchmark_policy(self):return {"policy_id":"benchmark_policy"}
class BenchmarkingRuntime:
 def benchmark(self,operations):
  runs=[BenchmarkRun(deterministic_id("benchmark_run",[n,v]),n,[BenchmarkMetric(deterministic_id("benchmark_metric",[n,v]),n,v)]) for n,v in sorted(operations.items())];return BenchmarkReport(deterministic_id("benchmark_report",[x.run_id for x in runs]),runs,"VALID")
