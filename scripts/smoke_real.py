"""本物のAIで、画像生成→結論→類似度→ジェスチャー読み取りを1回ずつ通す（時間も測る）。"""
import asyncio, time
from common.models import GestureBatch, Hand, Landmark, Sample
from common.settings import get_settings
from worker.ai.base import cosine
from worker.ai.real import RealAIClient
from worker.prompts import build_first_image_prompt


async def timed(name, coro):
    t = time.time(); r = await coro
    print(f"{name}: {time.time()-t:.1f}s"); return r


async def main():
    ai = RealAIClient(get_settings())
    img = await timed("画像生成", ai.generate_image(build_first_image_prompt("いぬ")))
    print("  画像サイズ", len(img), "bytes")
    ans = await timed("結論", ai.conclude(img)); print("  結論:", ans)
    a, b = await asyncio.gather(ai.embed("いぬ"), ai.embed(ans))
    print("  類似度:", round(cosine(a, b), 3))
    # 手を左右に振る偽データ
    samples = [Sample(timestamp_ms=i*100, hands=[Hand(handedness="Right",
               landmarks=[Landmark(x=0.4+0.1*(i%2), y=0.5, z=0) for _ in range(21)])]) for i in range(10)]
    g = await timed("ジェスチャー", ai.read_gesture([GestureBatch(gesture_session_id="s", sequence_number=0, mirrored=False, samples=samples)]))
    print("  読み取り:", g[:80])

asyncio.run(main())
