def test_narration_planner_generates_one_ordered_block_per_segment(
    narration_planner,
    script_structure,
):
    blocks = narration_planner.generate_blocks(script_structure)

    assert len(blocks) == len(script_structure.segments)
    assert [block.position for block in blocks] == list(range(len(blocks)))
    assert {block.segment_id for block in blocks} == {
        segment.segment_id for segment in script_structure.segments
    }
