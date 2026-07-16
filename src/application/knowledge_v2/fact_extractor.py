from .rule_engine import RuleEngine


class FactExtractor:

    def __init__(self):
        self.rules = RuleEngine()

    def extract(self,text,context):
        result = self.rules.extract_claims(text)
        return {"facts": result}


