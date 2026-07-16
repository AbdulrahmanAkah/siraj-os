import json
from pathlib import Path


class JsonStorage:

    def __init__(self, base_path="data"):
        self.base_path = Path(base_path)
        self.base_path.mkdir(
            parents=True,
            exist_ok=True
        )


    def save(self, name, data):

        path = self.base_path / f"{name}.json"

        with open(
            path,
            "w",
            encoding="utf-8"
        ) as f:
            json.dump(
                data,
                f,
                indent=4,
                ensure_ascii=False
            )

        return path


    def load(self, name):

        path = self.base_path / f"{name}.json"

        if not path.exists():
            return None

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)
