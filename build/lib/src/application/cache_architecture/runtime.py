from src.application.operations_common import *
from src.application.performance_common import *
from .models import *
class CacheArchitectureRuntime:
 def build_cache_manifest(self,values):
  entries=[CacheEntry(deterministic_id("cache_entry",[k,v]),str(k),integrity_hash(v),i,canonical_version_metadata(str(k)),{},performance_metadata([k],"cache")) for i,(k,v) in enumerate(sorted(values.items()))];region=CacheRegion(deterministic_id("cache_region",[x.entry_id for x in entries]),entries,canonical_version_metadata("cache"),{},performance_metadata(entries,"cache"));return CacheManifest(deterministic_id("cache_manifest",region.region_id),[region],"VALID"),CacheStatistics(deterministic_id("cache_statistics",len(entries)),len(entries),performance_metadata(entries,"cache"))
