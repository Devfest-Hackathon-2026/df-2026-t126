"""ジェスチャー読み取りの実験: 手の21点の座標を自作して、AIが何と読むかを見る。

本物の MediaPipe の座標が手に入るまでの代わり（手の形は、おおまかな模型）。
実行: RUNTIME_MODE=cloud ENABLE_CLOUD=true AI_MODE=real uv run --python 3.12 python scripts/gesture_lab.py [名前 ...]
名前: wave circle fist peace thumbs_up up_down（省略で全部）
"""
import asyncio
import math
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.models import GestureBatch, Hand, Landmark, Sample
from common.settings import get_settings
from worker.ai.preprocess import prepare_batches
from worker.ai.real import RealAIClient

# 手のひらをカメラに向け、指を上に伸ばした形（x:右、y:下、0〜1）。MediaPipe の21点の並び。
OPEN = [(0.50, 0.80),
        (0.45, 0.76), (0.40, 0.70), (0.36, 0.64), (0.33, 0.59),   # 親指
        (0.45, 0.62), (0.44, 0.52), (0.435, 0.46), (0.43, 0.40),  # 人さし指
        (0.50, 0.60), (0.50, 0.49), (0.50, 0.43), (0.50, 0.37),   # 中指
        (0.55, 0.62), (0.56, 0.52), (0.565, 0.46), (0.57, 0.41),  # 薬指
        (0.60, 0.66), (0.62, 0.58), (0.63, 0.53), (0.64, 0.49)]   # 小指
FINGERS = {"thumb": (1, 2, 3, 4), "index": (5, 6, 7, 8), "middle": (9, 10, 11, 12),
           "ring": (13, 14, 15, 16), "pinky": (17, 18, 19, 20)}


def pose(curled: set[str], thumb_up: bool = False) -> list[tuple[float, float]]:
    pts = list(OPEN)
    for name in curled:
        a, b, c, d = FINGERS[name]
        mx, my = pts[a]
        pts[b], pts[c], pts[d] = (mx, my - 0.04), (mx, my - 0.005), (mx, my + 0.035)
    if thumb_up:
        pts[1], pts[2], pts[3], pts[4] = (0.45, 0.76), (0.44, 0.68), (0.44, 0.60), (0.44, 0.52)
    return pts


def transform(pts, angle=0.0, dx=0.0, dy=0.0):
    wx, wy = pts[0]
    ca, sa = math.cos(angle), math.sin(angle)
    out = []
    for x, y in pts:
        rx, ry = x - wx, y - wy
        out.append((wx + rx * ca - ry * sa + dx, wy + rx * sa + ry * ca + dy))
    return out


def make(name: str, n: int = 50, step_ms: int = 100) -> list[GestureBatch]:
    rnd = random.Random(1)
    samples = []
    for i in range(n):
        t = i * step_ms / 1000
        if name == "wave":
            pts = transform(pose(set()), angle=math.radians(28) * math.sin(2 * math.pi * 2 * t))
        elif name == "circle":
            pts = transform(pose(set()), dx=0.12 * math.cos(2 * math.pi * 0.6 * t), dy=0.12 * math.sin(2 * math.pi * 0.6 * t))
        elif name == "fist":
            pts = pose({"thumb", "index", "middle", "ring", "pinky"})
        elif name == "peace":
            pts = pose({"thumb", "ring", "pinky"})
        elif name == "thumbs_up":
            pts = pose({"index", "middle", "ring", "pinky"}, thumb_up=True)
        elif name == "up_down":
            pts = transform(pose(set()), dy=0.10 * math.sin(2 * math.pi * 1.0 * t))
        else:
            raise SystemExit(f"知らない名前: {name}")
        hand = Hand(handedness="Right", landmarks=[Landmark(x=x + rnd.gauss(0, 0.002), y=y + rnd.gauss(0, 0.002), z=0.0) for x, y in pts])
        samples.append(Sample(timestamp_ms=i * step_ms, hands=[hand]))
    return [GestureBatch(gesture_session_id=name, sequence_number=0, mirrored=False, samples=samples)]


LABEL = {"wave": "手を振る（バイバイ）", "circle": "手で円を描く", "fist": "グー（握りこぶし）",
         "peace": "ピース", "thumbs_up": "いいね（親指を立てる）", "up_down": "手を上下に動かす"}


def load_settings():
    """A の安全ガード: 本物のAIを使うには、人間が明示的に RUNTIME_MODE=cloud ENABLE_CLOUD=true AI_MODE=real を付ける。"""
    import os

    os.environ.setdefault("GCP_PROJECT", "gesture-relay-game")   # A の設定の既定は demo-gesture-relay（Emulator用）
    try:
        return get_settings()
    except Exception as e:  # noqa: BLE001
        raise SystemExit(
            "設定エラー: " + str(e).splitlines()[-1] + "\n"
            "本物のAIを使うときは、次のように環境変数を付けて実行してください:\n"
            "  RUNTIME_MODE=cloud ENABLE_CLOUD=true AI_MODE=real uv run --python 3.12 python " + sys.argv[0]
        )


async def main():
    names = sys.argv[1:] or list(LABEL)
    ai = RealAIClient(load_settings())
    for n in names:
        batches = make(n)
        size = len(str(prepare_batches(batches)))
        t = time.time()
        try:
            text = await ai.read_gesture(batches)
        except Exception as e:  # noqa: BLE001
            text = f"失敗: {type(e).__name__}: {str(e)[:100]}"
        print(f"\n■ {n}（正解: {LABEL[n]}） 入力{size}文字 {time.time()-t:.1f}秒\n  AI: {text[:300]}")


if __name__ == "__main__":
    asyncio.run(main())
