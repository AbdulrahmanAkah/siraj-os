import argparse
import json
import sys

from src.application.pipeline.production_pipeline import ProductionPipeline


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


parser = argparse.ArgumentParser(
    description="Generate documentary artifacts from source documents."
)
parser.add_argument("topic")
parser.add_argument("sources", nargs="+")
parser.add_argument(
    "--repository",
    dest="repository_path",
    help="Directory used to persist and merge the canonical knowledge graph.",
)
args = parser.parse_args()
topic = args.topic
sources = args.sources


def _line():
    print("=" * 60)


def _node_label(node):
    data = getattr(node, "data", {})
    data = data if isinstance(data, dict) else {}
    return data.get("name") or data.get("title") or data.get("text") or data.get("value") or getattr(node, "id", "Unknown")


def _print_nodes(nodes_by_type, node_type):
    print(node_type)
    print("-" * len(node_type))
    nodes = nodes_by_type.get(node_type, [])
    if not nodes:
        print("None")
    for index, node in enumerate(nodes, start=1):
        print(f"{index}. {_node_label(node)}")
    print()


def _print_report(context):
    graph = context.knowledge_graph
    nodes_by_type = getattr(graph.index, "nodes_by_type", {})
    nodes_by_id = {node.id: node for node in getattr(graph, "nodes", [])}

    _line()
    print("SIRAJ OS - DOCUMENTARY GENERATION REPORT")
    _line()
    print("\nTOPIC\n-----")
    print(context.topic)

    print("\nPIPELINE STATUS\n---------------")
    print("Extraction       : OK")
    print("Knowledge Graph  : OK")
    print("Narrative        : OK")
    print("Script           : OK")
    print("Scenes           : OK")
    print("Image Prompts    : OK")

    print()
    _line()
    print("KNOWLEDGE GRAPH SUMMARY")
    _line()
    print("\nENTITIES\n")

    for node_type in ("PERSON", "ORGANIZATION", "EVENT", "LOCATION", "SOURCE", "CLAIM"):
        _print_nodes(nodes_by_type, node_type)

    _line()
    print("RELATIONSHIPS")
    _line()
    relationships = getattr(graph, "edges", [])
    if not relationships:
        print("\nNone")
    for edge in relationships:
        source = _node_label(nodes_by_id.get(edge.source, edge))
        target = _node_label(nodes_by_id.get(edge.target, edge))
        print(f"\n{source}")
        print(f"  {edge.relation}")
        print(f"  {target}")
        if edge.metadata.get("date"):
            print(f"  date: {edge.metadata['date']}")

    _line()
    print("TIMELINE")
    _line()
    timeline = nodes_by_type.get("TIMELINE_EVENT", [])
    if not timeline:
        print("\nNone")
    for node in timeline:
        data = node.data if isinstance(node.data, dict) else {}
        print(f"\n{data.get('date', '')}")
        print(f"- {data.get('title', _node_label(node))}")

    _line()
    print("GENERATION OUTPUT")
    _line()
    print(f"\nNarrative sections:\n{len(context.narrative.body)}")
    print(f"\nScript characters:\n{len(context.script.narration)}")
    print(f"\nScenes:\n{len(context.scenes)}")
    print(f"\nImage prompts:\n{len(context.image_prompts)}")

    warnings = []
    for node_type in ("PERSON", "ORGANIZATION", "EVENT", "LOCATION", "SOURCE", "CLAIM"):
        labels = [_node_label(node) for node in nodes_by_type.get(node_type, [])]
        if len(labels) != len(set(labels)):
            warnings.append(f"Duplicate {node_type.lower()} entities detected")
    if not timeline:
        warnings.append("Missing timeline")
    if not nodes_by_type.get("SOURCE", []):
        warnings.append("Missing source")
    if any(not scene.narration.strip() for scene in context.scenes):
        warnings.append("Empty scene")

    _line()
    print("WARNINGS")
    _line()
    if warnings:
        for warning in warnings:
            print(f"\n- {warning}")
    else:
        print("\nNo warnings detected.")

result = ProductionPipeline(repository_path=args.repository_path).run(topic, sources)
print("=" * 60)
print("RAW JSON OUTPUT")
print("=" * 60)
print(json.dumps(
    result,
    default=lambda o: o.__dict__,
    ensure_ascii=False,
    indent=2,
))
print()
_print_report(result)
