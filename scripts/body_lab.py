"""手だけ vs 手＋体＋顔 で、AIの読み取りがどう変わるかを比べる実験。

実行: RUNTIME_MODE=cloud ENABLE_CLOUD=true AI_MODE=real uv run --python 3.12 python scripts/body_lab.py [名前 ...]
"""
import asyncio
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from common.models import GestureBatch
from eval_gestures import judge, load_settings
from worker.ai.preprocess import prepare_batches
from worker.ai.real import RealAIClient

OUT = Path(__file__).resolve().parent.parent / ".local_storage" / "body"
BODY_NOTE = (
    "\n\n追加の情報: 各サンプルには、手のほかに次もあります。"
    "pose=上半身の点（x,yは0〜1、zは奥行き。l_/r_は撮影された人の左右。v=見えている確率）。"
    "face.blend=表情の強さ（0〜1。mouthPucker=口をすぼめる、jawOpen=口を開ける、mouthSmile=笑う）。"
    "face.head=頭の向き（度。yaw=左右の向き、pitch=上下、roll=傾き）。"
    "body_yaw=体の向き（度。0=正面、正の値=カメラに対して体の左側を向ける、負=右側）。"
    "手の動きだけでなく、体の向き・上半身の動き・口の形も含めて、何を身振りで伝えようとしているか読み取ってください。"
)


def body_yaw(pose):
    """両肩の奥行きの差と横幅から、体の向き（度）を出す。"""
    if not pose:
        return None
    l, r = pose["l_shoulder"], pose["r_shoulder"]
    return round(math.degrees(math.atan2(r["z"] - l["z"], max(abs(l["x"] - r["x"]), 1e-3))))


def thin(samples, n=40):
    if len(samples) <= n:
        return samples
    step = (len(samples) - 1) / (n - 1)
    return [samples[round(i * step)] for i in range(n)]


def body_payload(d, face=True):
    out = []
    for s in thin(d["samples"]):
        item = {"t": s["timestamp_ms"],
                "hands": [{"hand": h["handedness"], "pts": [[round(p["x"], 3), round(p["y"], 3), round(p["z"], 3)] for p in h["landmarks"]]} for h in s["hands"]]}
        if s["pose"]:
            item["pose"] = {k: [v["x"], v["y"], v["z"], v["v"]] for k, v in s["pose"].items()}
            item["body_yaw"] = body_yaw(s["pose"])
        if face and s["face"]:
            item["face"] = s["face"]
        out.append(item)
    return json.dumps({"samples": out}, ensure_ascii=False, separators=(",", ":"))


async def read(ai, prompt):
    from worker.prompts import PROMPTS  # noqa: F401
    c = ai._client(ai.s.provider_read)
    r = await ai._call(lambda: c.aio.models.generate_content(model=ai.s.model_read, contents=prompt))
    return (r.text or "").strip()


async def main():
    from worker.prompts import PROMPTS
    ai = RealAIClient(load_settings())
    names = sys.argv[1:]
    files = [f for f in sorted(OUT.glob("*.json")) if not names or f.stem in names]
    if not files:
        raise SystemExit("録画がありません。先に record_body.py を実行してください。")
    for f in files:
        d = json.loads(f.read_text(encoding="utf-8"))
        hands_only = GestureBatch(gesture_session_id=f.stem, sequence_number=0, mirrored=False,
                                  samples=[{"timestamp_ms": s["timestamp_ms"], "hands": s["hands"]} for s in d["samples"]])
        hdata = json.dumps(prepare_batches([hands_only]), ensure_ascii=False, separators=(",", ":"))
        bdata = body_payload(d)
        n = len(d["samples"])
        print(f"\n■ {f.stem}（正解: {d['expected']}） 体{sum(1 for s in d['samples'] if s['pose'])*100//n}% 顔{sum(1 for s in d['samples'] if s['face'])*100//n}% 手{sum(1 for s in d['samples'] if s['hands'])*100//n}%")
        for label, prompt in (("手だけ", f"{PROMPTS.gesture_read}\n\n{hdata}"),
                              ("手+体", f"{PROMPTS.gesture_read}{BODY_NOTE}\n\n{body_payload(d, face=False)}"),
                              ("手+体+顔", f"{PROMPTS.gesture_read}{BODY_NOTE}\n\n{bdata}")):
            try:
                reading = await read(ai, prompt)
                verdict = await judge(ai, d["expected"], reading)
            except Exception as e:  # noqa: BLE001
                reading, verdict = f"（失敗）{type(e).__name__}: {str(e)[:80]}", "-"
            print(f"  [{label}] 入力{len(prompt)}文字\n    AI  : {reading[:220]}\n    判定: {verdict[:80]}")


asyncio.run(main())
