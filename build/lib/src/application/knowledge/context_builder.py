from src.domain.knowledge_objects.document import Document
from src.domain.knowledge_objects.document_context import DocumentContext


class ContextBuilder:

    def build(self, document: Document):

        contexts = []

        paragraphs = document.metadata.get("paragraphs", [])

        for paragraph in paragraphs:

            for sentence in paragraph.sentences:

                contexts.append(
                    DocumentContext(
                        text=sentence.text,
                        document_id=document.document_id,
                        document_name=document.document_name,
                        page=0,
                        paragraph=paragraph.index,
                        sentence=sentence.index,
                    )
                )

        return contexts


