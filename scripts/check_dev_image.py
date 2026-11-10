"""Gemini API（キー）で画像生成が使えるかを、時間つきで1回だけ確かめる（最大90秒で打ち切る）。

実行: uv run --python 3.12 python scripts/check_dev_image.py [--key2]
--key2: .env の GEMINI_API_KEY2 を使う（キーの値は表示しない）
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from google import genai
from google.genai import types

from common.settings import get_settings

s = get_settings()
key = s.gemini_api_key
if "--key2" in sys.argv:
    from dotenv import dotenv_values

    key = dotenv_values(Path(__file__).resolve().parent.parent / ".env").get("GEMINI_API_KEY2")
    print("使うキー: GEMINI_API_KEY2", "(設定あり)" if key else "(未設定)", flush=True)
c = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=90_000))
t = time.time()
print("画像生成を依頼:", s.model_image, flush=True)
try:
    r = c.models.generate_content(model=s.model_image, contents="a small red apple, photo, no text")
    for p in r.candidates[0].content.parts:
        if p.inline_data:
            d = p.inline_data.data
            kind = "PNG" if d[:8] == b"\x89PNG\r\n\x1a\n" else "JPEG" if d[:3] == b"\xff\xd8\xff" else "不明"
            print(f"成功 {time.time()-t:.1f}秒 / {p.inline_data.mime_type} / 中身 {kind} / {len(d)} bytes")
            break
    else:
        print(f"画像なし {time.time()-t:.1f}秒:", (r.text or "")[:200])
except Exception as e:  # noqa: BLE001
    print(f"失敗 {time.time()-t:.1f}秒: {type(e).__name__}: {str(e)[:300]}")
