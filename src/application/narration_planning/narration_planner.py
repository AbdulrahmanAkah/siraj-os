from hashlib import sha256

from src.application.script_architecture.script_architect import ScriptArchitect

from .models import NarrationBlock, NarrationPlan


class NarrationPlanner:
    """Deterministically maps script structure to narration-planning blocks."""

    WORDS_PER_MINUTE = 150
    _ROLES = {
        "OPENING_HOOK": "HOOK",
        "BACKGROUND": "CONTEXT",
        "DEVELOPMENT": "EXPLANATION",
        "REVEAL": "REVELATION",
        "CLIMAX": "CLIMAX_NARRATION",
        "RESOLUTION": "RESOLUTION",
        "EPILOGUE": "LEGACY_REFLECTION",
    }
    _BASE_WORDS = {
        "OPENING_HOOK": 38,
        "BACKGROUND": 55,
        "DEVELOPMENT": 65,
        "REVEAL": 55,
        "CLIMAX": 80,
        "RESOLUTION": 55,
        "EPILOGUE": 45,
    }
    _COMPLEXITY_WORDS = {"LOW": 0, "MEDIUM": 10, "HIGH": 20}
    _HIGH_PRIORITY_ROLES = {"HOOK", "CLIMAX_NARRATION"}
    _MEDIUM_PRIORITY_ROLES = {"CONTEXT", "EXPLANATION", "REVELATION", "RESOLUTION"}

    def __init__(self, script_architect):
        if not isinstance(script_architect, ScriptArchitect):
            raise TypeError("NarrationPlanner requires a ScriptArchitect")
        self.script_architect = script_architect
        self._structures_by_id = {}

    def build_narration_plan(self, script_structure=None):
        script_structure = self._structure(script_structure)
        self._structures_by_id[script_structure.structure_id] = script_structure
        blocks = self.generate_blocks(script_structure)
        plan_key = "\x00".join(
            [script_structure.structure_id, *(block.block_id for block in blocks)]
        )
        total_words = self.estimate_word_count(script_structure, blocks)
        return NarrationPlan(
            plan_id=f"narration_plan_{sha256(plan_key.encode('utf-8')).hexdigest()[:16]}",
            script_structure_id=script_structure.structure_id,
            blocks=blocks,
            estimated_total_words=total_words,
            estimated_duration_seconds=self.estimate_duration(total_words),
        )

    def generate_blocks(self, script_structure=None):
        script_structure = self._structure(script_structure)
        roles = self.assign_roles(script_structure)
        complexity = self.script_architect.get_narrative_complexity(script_structure)
        blocks = []
        for position, segment in enumerate(
            sorted(
                script_structure.segments,
                key=lambda item: (item.position, item.segment_id),
            )
        ):
            role = roles[segment.segment_id]
            blocks.append(
                NarrationBlock(
                    block_id=self._block_id(
                        script_structure.structure_id,
                        segment.segment_id,
                        role,
                    ),
                    segment_id=segment.segment_id,
                    narration_role=role,
                    information_priority=self._priority(role),
                    estimated_word_count=self._word_count(segment, complexity),
                    position=position,
                )
            )
        return blocks

    def assign_roles(self, script_structure=None):
        script_structure = self._structure(script_structure)
        return {
            segment.segment_id: self._ROLES[segment.segment_type]
            for segment in script_structure.segments
        }

    def estimate_word_count(self, script_structure=None, blocks=None):
        script_structure = self._structure(script_structure)
        blocks = self.generate_blocks(script_structure) if blocks is None else list(blocks)
        return sum(block.estimated_word_count for block in blocks)

    def estimate_duration(self, word_count_or_plan=None):
        if isinstance(word_count_or_plan, NarrationPlan):
            word_count = word_count_or_plan.estimated_total_words
        elif word_count_or_plan is None:
            word_count = self.build_narration_plan().estimated_total_words
        else:
            word_count = word_count_or_plan
        return round(float(word_count) / self.WORDS_PER_MINUTE * 60, 2)

    def validate_plan(self, narration_plan, script_structure=None):
        if narration_plan is None or not narration_plan.blocks:
            return False
        script_structure = (
            script_structure
            or self._structures_by_id.get(narration_plan.script_structure_id)
            or self._structure(None)
        )
        blocks = narration_plan.blocks
        block_ids = [block.block_id for block in blocks]
        if len(block_ids) != len(set(block_ids)):
            return False
        if sum(block.narration_role == "HOOK" for block in blocks) != 1:
            return False
        if sum(block.narration_role == "CLIMAX_NARRATION" for block in blocks) != 1:
            return False
        if not any(
            block.narration_role in {"RESOLUTION", "LEGACY_REFLECTION"}
            for block in blocks
        ):
            return False
        if [block.position for block in blocks] != list(range(len(blocks))):
            return False
        if blocks != sorted(blocks, key=lambda item: (item.position, item.block_id)):
            return False
        segment_ids = {segment.segment_id for segment in script_structure.segments}
        block_segment_ids = [block.segment_id for block in blocks]
        return (
            all(block.estimated_word_count > 0 for block in blocks)
            and len(block_segment_ids) == len(set(block_segment_ids))
            and set(block_segment_ids) == segment_ids
        )

    def _structure(self, script_structure):
        return (
            self.script_architect.build_script_structure()
            if script_structure is None
            else script_structure
        )

    @classmethod
    def _word_count(cls, segment, complexity):
        return (
            cls._BASE_WORDS[segment.segment_type]
            + round(segment.estimated_duration * 12)
            + cls._COMPLEXITY_WORDS.get(complexity, 0)
        )

    @classmethod
    def _priority(cls, role):
        if role in cls._HIGH_PRIORITY_ROLES:
            return "HIGH"
        if role in cls._MEDIUM_PRIORITY_ROLES:
            return "MEDIUM"
        return "LOW"

    @staticmethod
    def _block_id(structure_id, segment_id, role):
        key = "\x00".join([structure_id, segment_id, role])
        return f"narration_block_{sha256(key.encode('utf-8')).hexdigest()[:16]}"


__all__ = ["NarrationPlanner"]
