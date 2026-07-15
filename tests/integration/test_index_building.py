def test_index_building_creates_all_canonical_indexes(retrieval_index):
    assert retrieval_index.index_id.startswith("retrieval_index_")
    assert retrieval_index.fingerprint_index
    assert retrieval_index.media_type_index == {"image/jpeg": sorted(retrieval_index.records_by_id)}
    assert retrieval_index.metadata_key_index == {"title": sorted(retrieval_index.records_by_id)}
    assert retrieval_index.metadata_value_index == {"Example": sorted(retrieval_index.records_by_id)}
    assert retrieval_index.entries
