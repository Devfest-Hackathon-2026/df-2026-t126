"""プロンプト調整用: お題 → 画像 → AIの結論 → 類似度 を数件まとめて試し、画像を保存する。

実行: RUNTIME_MODE=cloud ENABLE_CLOUD=true AI_MODE=real uv run --python 3.12 python scripts/prompt_lab.py [--serial] [お題 ...]
画像は .local_storage/prompt_lab/ に出る（GitHub には上がらない）。
"""
import asyncio
import sys
from pathlib import Path

import time

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.settings import get_settings
from worker.ai.base import cosine
from worker.ai.real import RealAIClient
from worker.prompts import build_first_image_prompt

OUT = Path(__file__).resolve().parent.parent / ".local_storage" / "prompt_lab"
DEFAULT = ["いぬ", "ロケット", "ラーメン", "おばけ"]


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


async def stage(name: str, coro):
    try:
        return await coro
    except Exception as e:  # どの段階で失敗したか分かるようにする
        raise RuntimeError(f"[{name}] {type(e).__name__}: {e}") from e


async def one(ai, odai: str):
    t = time.time()
    img = await stage("画像生成", ai.generate_image(build_first_image_prompt(odai)))
    t_img = time.time() - t
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{odai}.png").write_bytes(img)
    guess = await stage("結論", ai.conclude(img))
    a, b = await stage("埋め込み", asyncio.gather(ai.embed(odai), ai.embed(guess)))
    return odai, guess, cosine(a, b), t_img


async def main():
    args = [a for a in sys.argv[1:] if a != "--serial"]
    serial = "--serial" in sys.argv[1:]   # 1件ずつ順番に（同時に投げない）
    odais = args or DEFAULT
    ai = RealAIClient(load_settings())
    if serial:
        results = []
        for o in odais:
            try:
                results.append(await one(ai, o))
            except Exception as e:  # noqa: BLE001
                results.append(e)
    else:
        results = await asyncio.gather(*(one(ai, o) for o in odais), return_exceptions=True)
    print(f"{'お題':<10}{'AIの答え':<12}{'類似度':<8}{'画像の時間'}")
    for r in results:
        if isinstance(r, Exception):
            print("失敗:", str(r)[:140])
        else:
            print(f"{r[0]:<10}{r[1]:<12}{r[2]:<8.3f}{r[3]:.1f}s")
    print("画像:", OUT.resolve())


asyncio.run(main())
