from dataclasses import dataclass
@dataclass
class HealthReport: status:str; checks:list[str]
class HealthArchitecture:
 def check(self,bootstrap):return HealthReport("HEALTHY" if bootstrap.state=="READY" else "UNHEALTHY",["CONFIGURATION","REGISTRY","PERSISTENCE"])
