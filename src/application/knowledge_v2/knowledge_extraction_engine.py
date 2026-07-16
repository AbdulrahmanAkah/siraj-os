class KnowledgeExtractionEngine:

    def __init__(self, pipeline):
        self.pipeline = pipeline

    def extract(self, text):
        return self.pipeline.run(text)


