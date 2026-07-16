from src.application.operations_common import *
from src.application.performance_common import performance_metadata
from .models import *
class MemoryOptimizationRuntime:
 def profile_memory(self,value):
  size=len(canonical_payload(value));perf=performance_metadata([size],"memory");profile=MemoryProfile(deterministic_id("memory_profile",size),size,canonical_version_metadata("memory"),{},perf);snap=MemorySnapshot(deterministic_id("memory_snapshot",profile.profile_id),profile,canonical_version_metadata("memory"),{},perf);return MemoryOptimizationResult(deterministic_id("memory_result",snap.snapshot_id),snap,"VALID",canonical_version_metadata("memory"),{},perf)
