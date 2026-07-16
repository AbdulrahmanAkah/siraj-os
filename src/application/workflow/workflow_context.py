from dataclasses import dataclass, field


@dataclass
class WorkflowContext:

    topic: str

    knowledge_graph: object | None = None

    outline: object | None = None

    narrative: object | None = None

    script: object | None = None

    scene_plan: object | None = None

    scenes: object | None = None

    image_prompts: object | None = None

    voice_segments: object | None = None

    timeline: object | None = None

    metadata: dict[str, object] = field(default_factory=dict)

    def to_dict(self):

        return {

            "topic": self.topic,

            "knowledge_graph": self.knowledge_graph,

            "outline": self.outline,

            "narrative": self.narrative,

            "script": self.script,

            "scene_plan": self.scene_plan,

            "scenes": self.scenes,

            "image_prompts": self.image_prompts,

            "voice_segments": self.voice_segments,

            "timeline": self.timeline,

            "metadata": self.metadata,
        }


__all__ = ["WorkflowContext"]



