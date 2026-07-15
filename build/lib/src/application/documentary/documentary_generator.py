from src.domain.knowledge_graph.knowledge_graph import KnowledgeGraph

from src.application.models.outline import DocumentaryOutline


class DocumentaryGenerator:

    def generate(
        self,
        graph: KnowledgeGraph,
        topic: str,
    ) -> DocumentaryOutline:

        people = [
            n.data.get("name","")
            for n in graph.get_nodes_by_type("PERSON")
        ]

        events = [
            n.data.get("name","")
            for n in graph.get_nodes_by_type("EVENT")
        ]

        timeline = [
            n.data.get("title","")
            for n in graph.get_nodes_by_type("TIMELINE_EVENT")
        ]

        claims = [
            n.data.get("text","")
            for n in graph.get_nodes_by_type("CLAIM")
        ]

        sections=[]

        if people:
            sections.append("Ø§Ù„Ø´Ø®ØµÙŠØ§Øª")

        if events:
            sections.append("Ø§Ù„Ø£Ø­Ø¯Ø§Ø«")

        if timeline:
            sections.append("Ø§Ù„ØªØ³Ù„Ø³Ù„ Ø§Ù„Ø²Ù…Ù†ÙŠ")

        if claims:
            sections.append("Ø§Ù„Ø­Ù‚Ø§Ø¦Ù‚ ÙˆØ§Ù„Ø§Ø³ØªÙ†ØªØ§Ø¬Ø§Øª")

        return DocumentaryOutline(
            title=topic,
            introduction=f"Ù…Ù‚Ø¯Ù…Ø© Ø¹Ù† {topic}",
            sections=sections,
            conclusion=f"Ø®Ø§ØªÙ…Ø© Ø¹Ù† {topic}",
        )


__all__=["DocumentaryGenerator"]


