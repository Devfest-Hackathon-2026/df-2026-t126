"""サンプル数（AIに渡す座標の数）を変えたとき、読み取りの正しさと速さがどう変わるかを、自作座標で比べる。

実行: RUNTIME_MODE=cloud ENABLE_CLOUD=true AI_MODE=real uv run --python 3.12 python scripts/gesture_ablation.py [30 60 ...]
"""
import asyncio
import functools
import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lab, ev = load("gesture_lab"), load("eval_gestures")

import worker.ai.real as real  # noqa: E402
from worker.ai.preprocess import prepare_batches  # noqa: E402


async def one(ai, name, sem):
    async with sem:
        batches = lab.make(name)
        t = time.time()
        reading = await ai.read_gesture(batches)
        dt = time.time() - t
        verdict = await ev.judge(ai, lab.LABEL[name], reading)
        return name, verdict[:1], dt, len(str(prepare_batches(batches, max_samples=real_n)))


async def main():
    global real_n
    sizes = [int(a) for a in sys.argv[1:]] or [20, 30, 60]
    ai = real.RealAIClient(ev.load_settings())
    for n in sizes:
        real_n = n
        real.prepare_batches = functools.partial(prepare_batches, max_samples=n)
        sem = asyncio.Semaphore(3)
        res = await asyncio.gather(*(one(ai, g, sem) for g in lab.LABEL), return_exceptions=True)
        ok = [r for r in res if not isinstance(r, Exception)]
        good = sum(1 for r in ok if r[1] == "○")
        print(f"\n== サンプル {n} 件 ==  ○ {good}/{len(res)}  平均 {sum(r[2] for r in ok)/max(1,len(ok)):.1f}秒  入力 約{sum(r[3] for r in ok)//max(1,len(ok))}文字")
        for r in res:
            print("  ", "失敗:" + str(r)[:80] if isinstance(r, Exception) else f"{r[0]:<10} {r[1]}  {r[2]:.1f}秒")


if __name__ == "__main__":
    asyncio.run(main())
