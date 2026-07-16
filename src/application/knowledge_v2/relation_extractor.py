from .rule_engine import RuleEngine


class RelationExtractor:

    def __init__(self):
        self.rules = RuleEngine()

    def extract(self,text,context):
        result = self.rules.extract_relationships(text)
        return {"relations": result}


