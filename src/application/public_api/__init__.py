from dataclasses import dataclass
@dataclass
class APIResponse: version:str; status:int; body:dict
class PublicAPI:
 def handle(self,path,command):
  if not path.startswith("/v1/"):return APIResponse("v1",404,{"error":"UNKNOWN_ENDPOINT"})
  return APIResponse("v1",200,{"result":command,"trace_id":"api-local"})
