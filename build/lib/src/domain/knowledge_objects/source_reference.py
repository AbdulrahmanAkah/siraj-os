from dataclasses import dataclass

@dataclass
class SourceReference:
    document_id:str=""
    document_name:str=""
    page:int=0
    paragraph:int=0
    sentence:int=0
    start_offset:int=0
    end_offset:int=0
    extractor:str=""


