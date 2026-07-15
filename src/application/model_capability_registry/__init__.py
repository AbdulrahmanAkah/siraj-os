class ModelCapabilityRegistry:
 def __init__(self):self.models={}
 def register(self,model_id,capabilities):self.models[model_id]=sorted(set(capabilities))
 def require(self,model_id,capability):
  if capability not in self.models.get(model_id,[]):raise ValueError("UNSUPPORTED_CAPABILITY")
