from dataclasses import dataclass
@dataclass
class DeploymentManifest: target:str; writable_directories:list[str]; network_enabled:bool=False
class DeploymentArchitect:
 def local_cli(self):return DeploymentManifest("LOCAL_CLI",["./data"],False)
