import json

from src.application.llm.providers.manual_gateway import ManualGateway
from src.application.workflow.documentary_workflow import DocumentaryWorkflow


def test_supported_workflow_generates_serializable_documentary_artifacts(tmp_path):
    source_file = tmp_path / "bom_source.txt"
    source_file.write_text(
        "\ufeffMuhammad traveled to Makkah in 610.",
        encoding="utf-8",
    )

    context = DocumentaryWorkflow(ManualGateway()).run(
        "Muhammad",
        [str(source_file)],
    )

    graph = context.knowledge_graph
    assert graph is not None

    persons = [node for node in graph.nodes if node.type == "PERSON"]
    assert len(persons) == 1
    assert persons[0].id == "muhammad"

    assert not any(
        node.type == "ENTITY"
        and str(node.data.get("name", "")).strip().lower() == "muhammad"
        for node in graph.nodes
    )

    assert any(
        edge.source == "muhammad"
        and edge.relation == "traveled_to"
        and edge.target == "makkah"
        and edge.metadata.get("date") == "610"
        for edge in graph.edges
    )

    assert context.outline is not None
    assert context.narrative is not None
    assert context.script is not None
    assert context.scenes
    assert context.image_prompts

    serialized = json.dumps(
        context,
        default=lambda value: value.__dict__,
        ensure_ascii=False,
    )
    assert '"knowledge_graph"' in serialized
    assert '"muhammad"' in serialized
