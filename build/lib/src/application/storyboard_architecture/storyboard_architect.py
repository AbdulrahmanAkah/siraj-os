from hashlib import sha256

from src.application.scene_planning.scene_planner import ScenePlanner

from .models import StoryboardArchitecture, StoryboardFrame, StoryboardSequence


class StoryboardArchitect:
    """Deterministically turns a ScenePlan into storyboard architecture."""

    MIN_FRAME_DURATION = 1

    _FRAME_TYPES = {
        "HOOK_SCENE": "ESTABLISHING",
        "CONTEXT_SCENE": "CONTEXTUAL",
        "EXPLANATION_SCENE": "DETAIL",
        "REVELATION_SCENE": "REVEAL",
        "CLIMAX_SCENE": "CLIMAX",
        "RESOLUTION_SCENE": "TRANSITION",
        "LEGACY_SCENE": "CLOSING",
    }
    _COMPOSITION_ROLES = {
        "HOOK_SCENE": "ORIENT",
        "CONTEXT_SCENE": "INFORM",
        "EXPLANATION_SCENE": "FOCUS",
        "REVELATION_SCENE": "DISCOVER",
        "CLIMAX_SCENE": "PEAK",
        "RESOLUTION_SCENE": "CONNECT",
        "LEGACY_SCENE": "REFLECT",
    }

    def __init__(self, scene_planner):
        if not isinstance(scene_planner, ScenePlanner):
            raise TypeError("StoryboardArchitect requires a ScenePlanner")
        self.scene_planner = scene_planner
        self._plans_by_id = {}

    def build_storyboard_architecture(self, scene_plan=None):
        scene_plan = self._plan(scene_plan)
        self._plans_by_id[scene_plan.plan_id] = scene_plan
        sequences = self.generate_sequences(scene_plan)
        architecture_key = "\x00".join(
            [scene_plan.plan_id, *(sequence.sequence_id for sequence in sequences)]
        )
        return StoryboardArchitecture(
            architecture_id=(
                f"storyboard_architecture_"
                f"{sha256(architecture_key.encode('utf-8')).hexdigest()[:16]}"
            ),
            scene_plan_id=scene_plan.plan_id,
            sequences=sequences,
            frame_count=sum(len(sequence.frames) for sequence in sequences),
            total_duration=sum(
                frame.duration_seconds
                for sequence in sequences
                for frame in sequence.frames
            ),
        )

    def generate_sequences(self, scene_plan=None):
        scene_plan = self._plan(scene_plan)
        frame_types = self.assign_frame_types(scene_plan)
        composition_roles = self.assign_composition_roles(scene_plan)
        sequences = []
        for scene in self._ordered_scenes(scene_plan):
            frame_type = frame_types[scene.scene_id]
            sequence_key = "\x00".join([scene_plan.plan_id, scene.scene_id])
            sequence_id = (
                f"storyboard_sequence_"
                f"{sha256(sequence_key.encode('utf-8')).hexdigest()[:16]}"
            )
            sequences.append(
                StoryboardSequence(
                    sequence_id=sequence_id,
                    scene_id=scene.scene_id,
                    frames=self._generate_scene_frames(
                        scene,
                        frame_type,
                        composition_roles[scene.scene_id],
                    ),
                )
            )
        return sequences

    def generate_frames(self, scene_plan=None):
        """Generate flat ordered frames for a ScenePlan."""
        scene_plan = self._plan(scene_plan)
        frame_types = self.assign_frame_types(scene_plan)
        composition_roles = self.assign_composition_roles(scene_plan)
        frames = []
        for scene in self._ordered_scenes(scene_plan):
            frames.extend(
                self._generate_scene_frames(
                    scene,
                    frame_types[scene.scene_id],
                    composition_roles[scene.scene_id],
                )
            )
        return frames

    def assign_frame_types(self, scene_plan=None):
        scene_plan = self._plan(scene_plan)
        return {
            scene.scene_id: self._FRAME_TYPES[scene.scene_type]
            for scene in scene_plan.scenes
        }

    def assign_composition_roles(self, scene_plan=None):
        scene_plan = self._plan(scene_plan)
        return {
            scene.scene_id: self._COMPOSITION_ROLES[scene.scene_type]
            for scene in scene_plan.scenes
        }

    def estimate_frame_duration(self, scene_or_duration):
        duration = getattr(
            scene_or_duration,
            "estimated_duration",
            scene_or_duration,
        )
        if isinstance(duration, bool):
            raise TypeError("Frame duration must be numeric")
        try:
            duration = int(duration)
        except (TypeError, ValueError) as error:
            raise TypeError("Frame duration must be numeric") from error
        return max(self.MIN_FRAME_DURATION, duration)

    def validate_storyboard(self, architecture, scene_plan=None):
        if architecture is None or not architecture.sequences:
            return False
        scene_plan = self._validation_plan(architecture, scene_plan)
        sequences = architecture.sequences
        scenes = self._ordered_scenes(scene_plan)
        scene_ids = [scene.scene_id for scene in scenes]
        sequence_scene_ids = [sequence.scene_id for sequence in sequences]
        frame_list = [
            frame for sequence in sequences for frame in sequence.frames
        ]
        frame_ids = [frame.frame_id for frame in frame_list]

        if architecture.scene_plan_id != scene_plan.plan_id:
            return False
        if architecture.frame_count != len(frame_list):
            return False
        if architecture.total_duration != sum(
            frame.duration_seconds for frame in frame_list
        ):
            return False
        if len(sequence_scene_ids) != len(set(sequence_scene_ids)):
            return False
        if len(frame_ids) != len(set(frame_ids)):
            return False
        if sequence_scene_ids != scene_ids:
            return False
        if set(sequence_scene_ids) != set(scene_ids):
            return False
        if sum(frame.frame_type == "CLIMAX" for frame in frame_list) != 1:
            return False
        if not any(frame.frame_type == "ESTABLISHING" for frame in frame_list):
            return False
        if not any(frame.frame_type == "CLOSING" for frame in frame_list):
            return False

        expected_types = self.assign_frame_types(scene_plan)
        expected_roles = self.assign_composition_roles(scene_plan)
        for sequence, scene in zip(sequences, scenes):
            if not sequence.frames:
                return False
            if any(frame.scene_id != sequence.scene_id for frame in sequence.frames):
                return False
            if [frame.position for frame in sequence.frames] != list(
                range(len(sequence.frames))
            ):
                return False
            if sequence.frames != sorted(
                sequence.frames,
                key=lambda item: (item.position, item.frame_id),
            ):
                return False
            if sum(frame.duration_seconds for frame in sequence.frames) != scene.estimated_duration:
                return False
            if any(
                not isinstance(frame.duration_seconds, int)
                or isinstance(frame.duration_seconds, bool)
                or frame.duration_seconds < self.MIN_FRAME_DURATION
                or frame.frame_type != expected_types[scene.scene_id]
                or frame.composition_role != expected_roles[scene.scene_id]
                for frame in sequence.frames
            ):
                return False
        return True

    def _plan(self, scene_plan):
        return (
            self.scene_planner.build_scene_plan()
            if scene_plan is None
            else scene_plan
        )

    def _validation_plan(self, architecture, scene_plan):
        if scene_plan is not None:
            return scene_plan
        return self._plans_by_id.get(architecture.scene_plan_id) or self._plan(None)

    @staticmethod
    def _ordered_scenes(scene_plan):
        return sorted(
            scene_plan.scenes,
            key=lambda item: (item.position, item.scene_id),
        )

    def _generate_scene_frames(self, scene, frame_type, composition_role):
        frame_key = "\x00".join([scene.scene_id, frame_type, composition_role])
        return [
            StoryboardFrame(
                frame_id=(
                    f"frame_{sha256(frame_key.encode('utf-8')).hexdigest()[:16]}"
                ),
                scene_id=scene.scene_id,
                frame_type=frame_type,
                composition_role=composition_role,
                duration_seconds=self.estimate_frame_duration(scene),
                position=0,
            )
        ]


__all__ = ["StoryboardArchitect"]
