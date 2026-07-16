from src.application.operations_common import canonical_payload,integrity_hash
def performance_metadata(items,operation):
 return {"operation":operation,"item_count":len(items),"input_hash":integrity_hash(items),"estimated_units":len(canonical_payload(items))}
def partition_items(items,segment_size):
 ordered=list(items)
 return [ordered[index:index+segment_size] for index in range(0,len(ordered),segment_size)]
