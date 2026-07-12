import re
import uuid

from src.domain.knowledge_objects.document import Document
from src.domain.knowledge_objects.paragraph import Paragraph
from src.domain.knowledge_objects.sentence import Sentence


class DocumentParser:

    _sentence_pattern = re.compile(r'(?<=[.!??])\s+')

    def parse(
        self,
        text: str,
        document_name: str = "",
        source: str = "",
        language: str = ""
    ) -> Document:

        document = Document(
            document_id=str(uuid.uuid4()),
            document_name=document_name,
            source=source,
            text=text,
            language=language,
        )

        paragraphs = []

        offset = 0

        for paragraph_index, paragraph_text in enumerate(
            [p.strip() for p in text.split("\n\n") if p.strip()]
        ):

            paragraph = Paragraph(
                index=paragraph_index,
                text=paragraph_text,
            )

            sentence_offset = offset

            raw_sentences = [
                s.strip()
                for s in self._sentence_pattern.split(paragraph_text)
                if s.strip()
            ]

            for sentence_index, sentence_text in enumerate(raw_sentences):

                start = text.find(sentence_text, sentence_offset)

                end = start + len(sentence_text)

                paragraph.sentences.append(
                    Sentence(
                        index=sentence_index,
                        text=sentence_text,
                        start_offset=start,
                        end_offset=end,
                    )
                )

                sentence_offset = end

            paragraphs.append(paragraph)

            offset += len(paragraph_text)

        document.metadata["paragraphs"] = paragraphs

        return document


