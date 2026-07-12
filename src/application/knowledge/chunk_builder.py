
from src.application.models.chunk import Chunk
from src.application.models.document import Document

class ChunkBuilder:

    def __init__(self,chunk_size=900):
        self.chunk_size=chunk_size

    def build(self,document:Document):

        chunks=[]

        current=""

        start=0

        index=0

        for paragraph in document.paragraphs:

            if len(current)+len(paragraph)<self.chunk_size:
                current+=paragraph+"\n"
                continue

            end=start+len(current)

            chunks.append(
                Chunk(index=index,text=current.strip(),start=start,end=end)
            )

            index+=1
            start=end
            current=paragraph+"\n"

        if current:
            chunks.append(
                Chunk(
                    index=index,
                    text=current.strip(),
                    start=start,
                    end=start+len(current)
                )
            )

        return chunks


