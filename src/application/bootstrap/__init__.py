from dataclasses import dataclass,field
from src.application.configuration import ApplicationConfig
@dataclass
class BootstrapResult: state:str; phases:list[str]=field(default_factory=list)
class ApplicationBootstrap:
 def start(self,config):
  if not isinstance(config,ApplicationConfig):return BootstrapResult("FAILED",["CONFIGURING"])
  return BootstrapResult("READY",["CONFIGURING","INITIALIZING","READY"])
 def shutdown(self):return BootstrapResult("STOPPED",["STOPPING","STOPPED"])
