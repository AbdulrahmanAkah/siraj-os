
from src.application.knowledge.document_parser import DocumentParser
from src.application.knowledge.chunk_builder import ChunkBuilder
from src.application.knowledge.extraction_pipeline import ExtractionPipeline

text="""
Battle of Badr happened in 624 CE.

Muhammad commanded Muslim Army.

Muslims defeated Quraysh.

Badr is southwest of Madinah.
"""

doc=DocumentParser().parse(text)

chunks=ChunkBuilder().build(doc)

pipeline=ExtractionPipeline()

results=pipeline.run(chunks)

print("="*70)

for r in results:
    print(r)

print("="*70)
print("TOTAL:",len(results))


