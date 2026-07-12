
from src.application.knowledge.document_parser import DocumentParser
from src.application.knowledge.chunk_builder import ChunkBuilder

text="""
Battle of Badr

The Battle of Badr happened in 624 CE.

Muslims defeated the Quraysh.

Muhammad commanded Muslim Army.

Badr is southwest of Madinah.
"""

parser=DocumentParser()
doc=parser.parse(text)

builder=ChunkBuilder(120)
chunks=builder.build(doc)

print("="*60)
print("TITLE:",doc.title)
print("PARAGRAPHS:",len(doc.paragraphs))
print("CHUNKS:",len(chunks))
for c in chunks:
    print("-"*40)
    print(c.index)
    print(c.text)


