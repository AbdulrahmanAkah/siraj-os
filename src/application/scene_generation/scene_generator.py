from src.application.planning.scene_plan import ScenePlan
from src.application.scene.scene import Scene
from src.application.ports.llm_gateway import LLMGateway

class SceneGenerator:

    def __init__(self, llm: LLMGateway):
        self.llm = llm

    def generate(
        self,
        plans: list[ScenePlan],
    ) -> list[Scene]:

        scenes = []

        for plan in plans:

            narration = f"{plan.title}. {plan.objective} " + " ".join(plan.key_points)

            scenes.append(
                Scene(
                    index=plan.index,
                    title=plan.title,
                    narration=narration,
                    visual_description=plan.objective,
                )
            )

        return scenes


__all__ = ["SceneGenerator"]


