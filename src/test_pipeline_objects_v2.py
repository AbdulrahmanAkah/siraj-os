from src.application.knowledge.extraction_pipeline import ExtractionPipeline

text = """
Battle of Badr happened in 624 CE.

Muhammad commanded Muslim Army.

Muslims defeated Quraysh.

Badr is southwest of Madinah.

Muhammad commanded Muslim Army.

Muhammad defeated Quraysh.

The Prophet returned to Madinah.
"""

pipeline = ExtractionPipeline()

graph = pipeline.run(text)

print("=" * 70)

print("NODES:", len(graph.nodes))
for n in graph.nodes:
    print(n)

print("=" * 70)

print("RELATIONSHIPS:", len(graph.relationships))
for r in graph.relationships:
    print(r)

print("=" * 70)

print("EDGES:", len(graph.edges))
for e in graph.edges:
    print(e)

print("=" * 70)

print("GRAPH AS DICT")
print(graph.to_dict())


