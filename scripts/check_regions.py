"""Vertex の画像生成が、どのロケーションで使えるかを1回ずつ確かめる（各90秒で打ち切る）。

実行: uv run --python 3.12 python scripts/check_regions.py [ロケーション ...]
"""
import sys
import time

from google import genai
from google.genai import types

import os

MODEL = os.environ.get("MODEL", "gemini-3.1-flash-image")
DEFAULT = ["global", "us-central1", "us-east4", "europe-west4", "asia-northeast1", "asia-southeast1"]

for loc in sys.argv[1:] or DEFAULT:
    c = genai.Client(vertexai=True, project="gesture-relay-game", location=loc,
                     http_options=types.HttpOptions(timeout=90_000))
    t = time.time()
    try:
        r = c.models.generate_content(model=MODEL, contents="a small red apple, photo, no text")
        ok = any(p.inline_data for p in r.candidates[0].content.parts)
        print(f"{loc:<18} {'✅ 画像あり' if ok else '⚠ 画像なし'} {time.time()-t:.1f}秒", flush=True)
    except Exception as e:  # noqa: BLE001
        print(f"{loc:<18} ❌ {time.time()-t:.1f}秒 {type(e).__name__}: {str(e)[:110]}", flush=True)
