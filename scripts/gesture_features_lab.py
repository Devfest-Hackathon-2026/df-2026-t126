"""実機録画で、「生の座標」と「指の状態を先に計算した要約」を比べる実験。

実行: RUNTIME_MODE=cloud ENABLE_CLOUD=true AI_MODE=real uv run --python 3.12 python scripts/gesture_features_lab.py
"""
import asyncio
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import worker.ai.real as real
from common.models import GestureBatch
from eval_gestures import DEFAULT_DIR, judge, load_settings
from worker.ai.preprocess import prepare_batches
from worker.ai.real import RealAIClient

FINGERS = {"親指": (4, 2), "人さし指": (8, 5), "中指": (12, 9), "くすり指": (16, 13), "小指": (20, 17)}


def finger_levels(pts):
    """各指の「のび具合」。手首から指先の距離 ÷ 手首から付け根の距離。1.6以上=のびる、1.0以下=曲がる。"""
    w = pts[0]
    d = lambda i: math.dist(pts[i][:2], w[:2])
    return {k: round(d(t) / max(d(m), 1e-6), 1) for k, (t, m) in FINGERS.items()}


def features(data: dict) -> dict:
    out = []
    for s in data["samples"]:
        hands = [{"hand": h["hand"], "wrist": h["pts"][0][:2], "fingers": finger_levels(h["pts"])} for h in s["hands"]]
        out.append({"t": s["t"], "hands": hands})
    return {"説明": "fingersは指ののび具合（1.6以上=のびる、1.0以下=曲がる）。wristは手首の位置。", "samples": out}


def make_variant(kind):
    def prep(batches, *a, **k):
        base = prepare_batches(batches, *a, **k)
        if kind == "raw":
            return base
        if kind == "features":
            return features(base)
        return {"features": features(base), "raw": base}   # both
    return prep


async def main():
    ai = RealAIClient(load_settings())
    files = sorted(DEFAULT_DIR.glob("*.json"))
    for kind in ("raw", "features", "both"):
        real.prepare_batches = make_variant(kind)
        print(f"\n######## {kind}")
        for f in files:
            d = json.loads(f.read_text(encoding="utf-8"))
            batches = [GestureBatch(**b) for b in d["batches"]]
            reading = await ai.read_gesture(batches)
            verdict = await judge(ai, d["expected"], reading)
            print(f"{f.stem}: 読み={reading[:80]!r} 判定={verdict[:40]}")


asyncio.run(main())
