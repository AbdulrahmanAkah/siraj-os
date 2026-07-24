from pathlib import Path

from src.application.episode_production_v1.composition import _resolve_project_path


def test_episode_contract_relative_path_resolves_from_project_root(tmp_path: Path) -> None:
    assert _resolve_project_path(tmp_path, "contracts/source-package-v1.draft.json") == (tmp_path / "contracts" / "source-package-v1.draft.json").resolve()


def test_episode_contract_absolute_path_is_preserved(tmp_path: Path) -> None:
    absolute = (tmp_path / "absolute.json").resolve()
    assert _resolve_project_path(tmp_path / "other", str(absolute)) == absolute
