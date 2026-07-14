from hashlib import sha256
from math import ceil

from src.application.narration_planning.narration_planner import NarrationPlanner

from .models import Scene, ScenePlan


class ScenePlanner:
    """Deterministically turns a NarrationPlan into a visual ScenePlan."""

    WORDS_PER_MINUTE = 150
    MIN_SCENE_DURATION = 2
    MAX_SCENE_DURATION = 30

    _SCENE_TYPES = {
        "HOOK": "HOOK_SCENE",
        "CONTEXT": "CONTEXT_SCENE",
        "EXPLANATION": "EXPLANATION_SCENE",
        "REVELATION": "REVELATION_SCENE",
        "CLIMAX_NARRATION": "CLIMAX_SCENE",
        "RESOLUTION": "RESOLUTION_SCENE",
        "LEGACY_REFLECTION": "LEGACY_SCENE",
    }
    _VISUAL_ROLES = {
        "HOOK": "ATTENTION",
        "CONTEXT": "ORIENTATION",
        "EXPLANATION": "EXPLANATION",
        "REVELATION": "DISCOVERY",
        "CLIMAX_NARRATION": "PEAK",
        "RESOLUTION": "AFTERMATH",
        "LEGACY_REFLECTION": "REFLECTION",
    }
    _ENDING_SCENE_TYPES = {"RESOLUTION_SCENE", "LEGACY_SCENE"}

    def __init__(self, narration_planner):
        if not isinstance(narration_planner, NarrationPlanner):
            raise TypeError("ScenePlanner requires a NarrationPlanner")
        self.narration_planner = narration_planner
        self._plans_by_id = {}

    def build_scene_plan(self, narration_plan=None):
        narration_plan = self._plan(narration_plan)
        self._plans_by_id[narration_plan.plan_id] = narration_plan
        scenes = self.generate_scenes(narration_plan)
        plan_key = "\x00".join(
            [narration_plan.plan_id, *(scene.scene_id for scene in scenes)]
        )
        return ScenePlan(
            plan_id=f"scene_plan_{sha256(plan_key.encode('utf-8')).hexdigest()[:16]}",
            narration_plan_id=narration_plan.plan_id,
            scenes=scenes,
            total_duration=sum(scene.estimated_duration for scene in scenes),
            scene_count=len(scenes),
        )

    def generate_scenes(self, narration_plan=None):
        narration_plan = self._plan(narration_plan)
        scene_types = self.assign_scene_types(narration_plan)
        visual_roles = self.assign_visual_roles(narration_plan)
        scenes = []
        for position, block in enumerate(self._ordered_blocks(narration_plan)):
            scene_type = scene_types[block.block_id]
            scenes.append(
                Scene(
                    scene_id=self._scene_id(
                        narration_plan.plan_id,
                        block.block_id,
                        scene_type,
                    ),
                    block_id=block.block_id,
                    scene_type=scene_type,
                    visual_role=visual_roles[block.block_id],
                    estimated_duration=self.estimate_scene_duration(block),
                    position=position,
                )
            )
        return scenes

    def assign_scene_types(self, narration_plan=None):
        narration_plan = self._plan(narration_plan)
        return {
            block.block_id: self._SCENE_TYPES[block.narration_role]
            for block in narration_plan.blocks
        }

    def assign_visual_roles(self, narration_plan=None):
        narration_plan = self._plan(narration_plan)
        return {
            block.block_id: self._VISUAL_ROLES[block.narration_role]
            for block in narration_plan.blocks
        }

    def estimate_scene_duration(self, word_count_or_block):
        word_count = getattr(
            word_count_or_block,
            "estimated_word_count",
            word_count_or_block,
        )
        if isinstance(word_count, bool):
            raise TypeError("Scene word count must be numeric")
        try:
            word_count = int(word_count)
        except (TypeError, ValueError) as error:
            raise TypeError("Scene word count must be numeric") from error
        if word_count < 0:
            raise ValueError("Scene word count cannot be negative")
        raw_duration = ceil(word_count / self.WORDS_PER_MINUTE * 60)
        return max(self.MIN_SCENE_DURATION, min(self.MAX_SCENE_DURATION, raw_duration))

    def validate_scene_plan(self, scene_plan, narration_plan=None):
        if scene_plan is None or not scene_plan.scenes:
            return False
        narration_plan = self._validation_plan(scene_plan, narration_plan)
        scenes = scene_plan.scenes
        scene_ids = [scene.scene_id for scene in scenes]
        block_ids = [scene.block_id for scene in scenes]
        narration_blocks = self._ordered_blocks(narration_plan)
        narration_block_ids = [block.block_id for block in narration_blocks]

        if scene_plan.narration_plan_id != narration_plan.plan_id:
            return False
        if scene_plan.scene_count != len(scenes):
            return False
        if scene_plan.total_duration != sum(scene.estimated_duration for scene in scenes):
            return False
        if len(scene_ids) != len(set(scene_ids)):
            return False
        if len(block_ids) != len(set(block_ids)):
            return False
        if block_ids != narration_block_ids:
            return False
        if [scene.position for scene in scenes] != list(range(len(scenes))):
            return False
        if scenes != sorted(scenes, key=lambda item: (item.position, item.scene_id)):
            return False
        if sum(scene.scene_type == "HOOK_SCENE" for scene in scenes) != 1:
            return False
        if sum(scene.scene_type == "CLIMAX_SCENE" for scene in scenes) != 1:
            return False
        if not any(scene.scene_type in self._ENDING_SCENE_TYPES for scene in scenes):
            return False

        expected_types = self.assign_scene_types(narration_plan)
        expected_roles = self.assign_visual_roles(narration_plan)
        return all(
            isinstance(scene.estimated_duration, int)
            and not isinstance(scene.estimated_duration, bool)
            and self.MIN_SCENE_DURATION <= scene.estimated_duration <= self.MAX_SCENE_DURATION
            and scene.scene_type == expected_types[scene.block_id]
            and scene.visual_role == expected_roles[scene.block_id]
            for scene in scenes
        )

    def _plan(self, narration_plan):
        return (
            self.narration_planner.build_narration_plan()
            if narration_plan is None
            else narration_plan
        )

    def _validation_plan(self, scene_plan, narration_plan):
        if narration_plan is not None:
            return narration_plan
        return self._plans_by_id.get(scene_plan.narration_plan_id) or self._plan(None)

    @staticmethod
    def _ordered_blocks(narration_plan):
        return sorted(
            narration_plan.blocks,
            key=lambda item: (item.position, item.block_id),
        )

    @staticmethod
    def _scene_id(narration_plan_id, block_id, scene_type):
        key = "\x00".join([narration_plan_id, block_id, scene_type])
        return f"scene_{sha256(key.encode('utf-8')).hexdigest()[:16]}"


__all__ = ["ScenePlanner"]
