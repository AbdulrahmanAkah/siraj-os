
from src.application.knowledge.document_parser import DocumentParser
from src.application.knowledge.chunk_builder import ChunkBuilder
from src.application.knowledge.extraction_pipeline import ExtractionPipeline

text="""
Battle of Badr

Muhammad commanded Muslim Army.

Muslims defeated Quraysh.

Badr is southwest of Madinah.
"""

doc=DocumentParser().parse(text)

chunks=ChunkBuilder(120).build(doc)

pipeline=ExtractionPipeline()

results=pipeline.run(chunks)

print("="*60)
print("Chunks:",len(chunks))
print("Results:",len(results))

for r in results[:10]:
    print(r)


