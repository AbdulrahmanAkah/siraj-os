from src.application.operations_common import *
from src.application.performance_common import *
from .models import *
class TimelineOptimizationRuntime:
 def optimize_timeline(self,timeline):
  entries=sorted(timeline.entries,key=lambda x:(x.event_date or "",x.entry_id));ranges={}
  for e in entries:ranges.setdefault((e.event_date or "UNDATED")[:4],[]).append(e.entry_id)
  chunks=partition_items([e.entry_id for e in entries],2);parts=[TimelineSegment(deterministic_id("timeline_segment",x),x,i,canonical_version_metadata("timeline"),{},performance_metadata(x,"timeline_segment")) for i,x in enumerate(chunks)];perf=performance_metadata(ranges,"timeline");idx=TimelineRangeIndex(deterministic_id("timeline_range_index",ranges),ranges,canonical_version_metadata("timeline"),{},perf);return TimelineOptimizationResult(deterministic_id("timeline_optimization",[x.segment_id for x in parts]),parts,idx,"VALID")
