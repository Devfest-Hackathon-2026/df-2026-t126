"""お題（shared-types.md §9）。お題は「〜している〇〇」の短文（例: 走っているいぬ）。"""
import json
import random
from pathlib import Path
from typing import Protocol

from pydantic import BaseModel

_DATA = Path(__file__).resolve().parent.parent / "data" / "odai.json"


class Odai(BaseModel):
    odai_id: str
    text: str
    category: str
    difficulty: int
    subject: str | None = None   # 名詞（例: いぬ）。text = action + subject。後で組み合わせ生成に使える
    action: str | None = None    # 動作（例: 走っている）


class OdaiSource(Protocol):
    def select(self) -> Odai: ...


class FileOdaiSource:
    def __init__(self, path: Path = _DATA):
        self.items = [Odai(**d) for d in json.loads(path.read_text(encoding="utf-8"))]

    def select(self) -> Odai:
        return random.choice(self.items)
