"""Vertex の画像生成が PNG / JPEG のどちらで返すかを確認する（A の接続部は PNG 前提）。

実行: uv run --python 3.12 python scripts/check_image_format.py
"""
from google import genai

c = genai.Client(vertexai=True, project="gesture-relay-game", location="global")
r = c.models.generate_content(
    model="gemini-3.1-flash-image", contents="a small red apple, simple illustration, no text"
)
for p in r.candidates[0].content.parts:
    if p.inline_data:
        d = p.inline_data.data
        kind = "PNG" if d[:8] == b"\x89PNG\r\n\x1a\n" else "JPEG" if d[:3] == b"\xff\xd8\xff" else "不明"
        print("mime_type:", p.inline_data.mime_type, "/ 中身:", kind, "/ サイズ:", len(d), "bytes")
