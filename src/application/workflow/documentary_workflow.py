from src.application.knowledge_v2.pipeline import KnowledgeExtractionPipeline
from src.application.artifacts.artifact import Artifact, ArtifactType
from src.application.artifacts.artifact_store import ArtifactStore

from src.application.workflow.workflow_context import WorkflowContext

from src.application.knowledge.knowledge_repository import KnowledgeRepository
from src.application.knowledge.character_engine import CharacterEngine
from src.application.knowledge.relationship_engine import RelationshipEngine
from src.application.knowledge.timeline_engine import TimelineEngine

from src.application.documentary.knowledge_outline_builder import KnowledgeOutlineBuilder
from src.application.narrative.narrative_builder import NarrativeBuilder
from src.application.script.script_generator import ScriptGenerator

from src.application.planning.scene_plan import ScenePlanner
from src.application.scene_generation.scene_generator import SceneGenerator
from src.application.image.image_prompt_generator import ImagePromptGenerator

from src.application.knowledge.citation_engine import CitationEngine
from src.application.knowledge.source_ranking_engine import SourceRankingEngine
from src.application.knowledge.fact_verification_engine import FactVerificationEngine


class DocumentaryWorkflow:

    def __init__(self, gateway):

        self.repository = KnowledgeRepository(gateway)

        self.outline_builder = KnowledgeOutlineBuilder()

        self.narrative_builder = NarrativeBuilder()

        self.script_generator = ScriptGenerator()

        self.scene_planner = ScenePlanner()

        self.scene_generator = SceneGenerator(gateway)

        self.image_generator = ImagePromptGenerator()

        self.citation_engine = CitationEngine()
        self.source_ranking_engine = SourceRankingEngine()
        self.fact_verification_engine = FactVerificationEngine()

        self.character_engine=CharacterEngine()
        self.relationship_engine=RelationshipEngine()
        self.timeline_engine=TimelineEngine()

        self.store = ArtifactStore()

    def run(
        self,
        topic: str,
        sources: list[str],
    ):

        ctx = WorkflowContext(topic)

        graph = None

        for source in sources:

            graph = self.repository.ingest_file(source)

        ctx.knowledge_graph = graph

        ctx.metadata["character_profiles"]=self.character_engine.build(graph)
        ctx.metadata["relationship_summary"]=self.relationship_engine.build(graph)

        ctx.timeline=self.timeline_engine.build(graph)

        ctx.metadata["timeline"]=ctx.timeline

        self.store.put(
            Artifact(
                ArtifactType.KNOWLEDGE_GRAPH,
                graph,
            )
        )

        ctx.outline = self.outline_builder.build(
            graph,
            topic,
        )

        self.store.put(
            Artifact(
                ArtifactType.OUTLINE,
                ctx.outline,
            )
        )

        ctx.narrative = self.narrative_builder.build(
            graph,
            ctx.outline,
        )

        ctx.script = self.script_generator.build(
            ctx.outline,
            ctx.narrative,
        )

        self.store.put(
            Artifact(
                ArtifactType.SCRIPT,
                ctx.script,
            )
        )

        ctx.scene_plan = self.scene_planner.plan(
            graph,
            ctx.outline,
        )

        self.store.put(
            Artifact(
                ArtifactType.SCENE_PLAN,
                ctx.scene_plan,
            )
        )

        ctx.scenes = self.scene_generator.generate(
            ctx.scene_plan
        )

        self.store.put(
            Artifact(
                ArtifactType.SCENES,
                ctx.scenes,
            )
        )

        ctx.image_prompts = self.image_generator.generate(
            ctx.scenes
        )

        self.store.put(
            Artifact(
                ArtifactType.IMAGE_PROMPTS,
                ctx.image_prompts,
            )
        )

        ctx.metadata["citations"]=self.citation_engine.build(graph)

        ctx.metadata["ranked_sources"]=self.source_ranking_engine.rank(graph)

        ctx.metadata["verified_claims"]=self.fact_verification_engine.verify(graph)

        return ctx


__all__=["DocumentaryWorkflow"]









