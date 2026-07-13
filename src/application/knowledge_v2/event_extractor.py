from .rule_engine import RuleEngine


class EventExtractor:

    def __init__(self):
        self.rules = RuleEngine()

    def extract(self,text,context):
        result = self.rules.extract_events(text)
        return {"events": result}


