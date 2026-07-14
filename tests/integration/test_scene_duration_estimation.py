def test_scene_duration_is_derived_from_words_and_bounded(scene_planner):
    assert scene_planner.estimate_scene_duration(1) == scene_planner.MIN_SCENE_DURATION
    assert scene_planner.estimate_scene_duration(150) == scene_planner.MAX_SCENE_DURATION
    assert scene_planner.estimate_scene_duration(1000) == scene_planner.MAX_SCENE_DURATION
