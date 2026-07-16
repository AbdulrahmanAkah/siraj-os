from src.application.documentary_intelligence import CANONICAL_CREATED_AT,deterministic_id
from src.application.documentary_assembly.models import DocumentaryPackage
from src.application.scene_generation_runtime.models import ScenePlanRuntime
from src.application.storyboard_runtime.models import Storyboard
from .architect import VisualEvidenceArchitect
from .models import VisualEvidenceLink,VisualEvidenceMap
class VisualEvidenceRuntime:
 def build_visual_evidence_map(self,policy,package,scenes,storyboard):
  if not VisualEvidenceArchitect().validate_policy(policy) or package.scene_plan_id!=scenes.plan_id or package.storyboard_id!=storyboard.storyboard_id: raise ValueError("Invalid Visual Evidence inputs")
  links=[]; pos=0; frame_by_scene={f.scene_id:f for f in storyboard.frames}
  for scene in scenes.scenes:
   frame=frame_by_scene[scene.scene_id]; trace=dict(scene.trace_metadata)
   for event_id in scene.referenced_event_ids:
    links.append(VisualEvidenceLink(deterministic_id("visual_evidence_link",["EVENT_VISUALIZED_BY",event_id,frame.frame_id]),"EVENT_VISUALIZED_BY",event_id,frame.frame_id,list(scene.referenced_evidence_ids),CANONICAL_CREATED_AT,pos,trace));pos+=1
   for claim_id in trace.get("claim_ids",[]):
    links.append(VisualEvidenceLink(deterministic_id("visual_evidence_link",["CLAIM_SUPPORTED_BY_VISUAL",claim_id,frame.frame_id]),"CLAIM_SUPPORTED_BY_VISUAL",claim_id,frame.frame_id,list(scene.referenced_evidence_ids),CANONICAL_CREATED_AT,pos,trace));pos+=1
   for entity_id in trace.get("source_ids",[]):
    links.append(VisualEvidenceLink(deterministic_id("visual_evidence_link",["ENTITY_APPEARS_IN_VISUAL",entity_id,frame.frame_id]),"ENTITY_APPEARS_IN_VISUAL",entity_id,frame.frame_id,list(scene.referenced_evidence_ids),CANONICAL_CREATED_AT,pos,trace));pos+=1
  result=VisualEvidenceMap(deterministic_id("visual_evidence_map",[package.package_id,[x.link_id for x in links]]),package.package_id,links,len(links),CANONICAL_CREATED_AT,0,dict(package.trace_metadata))
  if not self.validate_visual_evidence_map(result):raise ValueError("Invalid Visual Evidence result")
  return result
 def validate_visual_evidence_map(self,r):return isinstance(r,VisualEvidenceMap) and r.link_count==len(r.links) and [x.position for x in r.links]==list(range(len(r.links))) and all(x.relation_type in VisualEvidenceArchitect.TYPES and x.evidence_ids for x in r.links)
