from dataclasses import dataclass,field
@dataclass
class PluginDescriptor: plugin_id:str; version:str; capabilities:list[str]=field(default_factory=list)
class PluginRegistry:
 def __init__(self):self.plugins={}
 def register(self,descriptor):
  if descriptor.plugin_id in self.plugins:raise ValueError("DUPLICATE_PLUGIN")
  self.plugins[descriptor.plugin_id]=descriptor
 def load_order(self):return sorted(self.plugins)
