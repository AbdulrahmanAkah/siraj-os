from dataclasses import dataclass,field
@dataclass
class ReleaseVerificationReport: status:str; gates:dict[str,bool]=field(default_factory=dict)
class ReleaseGovernance:
 def verify(self,gates):
  if any(not value for key,value in gates.items() if key.startswith("CRITICAL_")):return ReleaseVerificationReport("REJECTED",gates)
  return ReleaseVerificationReport("READY" if all(gates.values()) else "BLOCKED",gates)
