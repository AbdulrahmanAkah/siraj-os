class LargeRepositoryArchitect:
 def build_large_repository_policy(self):return {"policy_id":"large_repository_policy"}
class LargeRepositoryRuntime:
 def build_synthetic_repository(self,count):return {"record-"+str(i):{"id":i} for i in range(count)}
