"""録った座標（record_gestures.py）を、AIに読ませて、正解と合っているかを確かめる。

実行: RUNTIME_MODE=cloud ENABLE_CLOUD=true AI_MODE=real uv run --python 3.12 python scripts/eval_gestures.py [名前 ...] [--dir 保存先] [--no-judge]
判定: AIの読み取りが、正解を表しているかを、別のAI呼び出しで ○（ほぼ一致）／△（部分的）／×（違う）で判定する。
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.models import GestureBatch
from common.settings import get_settings
from worker.ai.preprocess import prepare_batches
from worker.ai.real import RealAIClient

DEFAULT_DIR = Path(__file__).resolve().parent.parent / ".local_storage" / "gestures"


def load_settings():
    os.environ.setdefault("GCP_PROJECT", "gesture-relay-game")   # A の既定は demo-gesture-relay（Emulator用）
    try:
        return get_settings()
    except Exception as e:  # noqa: BLE001
        raise SystemExit("設定エラー: " + str(e).splitlines()[-1] + "\n"
                         "RUNTIME_MODE=cloud ENABLE_CLOUD=true AI_MODE=real を付けて実行してください。")


async def judge(ai: RealAIClient, expected: str, reading: str) -> str:
    prompt = (f"正解のジェスチャー: 「{expected}」\nAIの読み取り: 「{reading}」\n"
              "AIの読み取りは、正解のジェスチャーを表していると言えますか。"
              "「○」（ほぼ一致）「△」（一部だけ合っている）「×」（違う）のどれか1文字で始めて、理由を20字以内で書いてください。")
    c = ai._client(ai.s.provider_conclude)
    r = await c.aio.models.generate_content(model=ai.s.model_conclude, contents=prompt)
    return (r.text or "").strip().replace("\n", " ")


async def main():
    args = sys.argv[1:]
    folder = Path(args[args.index("--dir") + 1]) if "--dir" in args else DEFAULT_DIR
    skip_judge = "--no-judge" in args
    names = [a for a in args if not a.startswith("--") and a != str(folder)]
    files = sorted(folder.glob("*.json"))
    if names:
        files = [f for f in files if f.stem in names]
    if not files:
        raise SystemExit(f"録画がありません: {folder}（先に record_gestures.py を実行）")
    ai = RealAIClient(load_settings())
    score = {"○": 0, "△": 0, "×": 0}
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        batches = [GestureBatch(**b) for b in d["batches"]]
        n = sum(len(b.samples) for b in batches)
        det = sum(1 for b in batches for s in b.samples if s.hands) / max(1, n)
        t = time.time()
        try:
            reading = await ai.read_gesture(batches)
        except Exception as e:  # noqa: BLE001
            reading = f"（失敗）{type(e).__name__}: {str(e)[:80]}"
        verdict = "-" if skip_judge or reading.startswith("（失敗）") else await judge(ai, d["expected"], reading)
        mark = verdict[:1] if verdict[:1] in score else "-"
        if mark in score:
            score[mark] += 1
        print(f"\n■ {d['label']}（正解: {d['expected']}） 検出率{det:.0%} 入力{len(str(prepare_batches(batches)))}文字 {time.time()-t:.1f}秒")
        print(f"  AI  : {reading[:200]}")
        print(f"  判定: {verdict[:80]}")
    print(f"\n=== 集計: ○{score['○']}  △{score['△']}  ×{score['×']}  （全{len(files)}件）===")


if __name__ == "__main__":
    asyncio.run(main())
