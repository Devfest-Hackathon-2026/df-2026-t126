"""Vertex AI を ADC（gcloud ログイン）で呼べるか確かめるPoC。
実行: uv run --python 3.12 --with google-genai scripts/poc_vertex_check.py <プロジェクトIDまたは番号>
"""
import sys

from google import genai

project = sys.argv[1]
for loc in ("global", "asia-northeast1"):
    client = genai.Client(vertexai=True, project=project, location=loc)
    for model in ("gemini-3.5-flash", "gemini-3.1-flash-image"):
        try:
            if "image" in model:
                r = client.models.generate_content(model=model, contents="a small red apple, simple illustration")
                ok = any(getattr(p, "inline_data", None) for p in r.candidates[0].content.parts)
                print(f"[{loc}] {model}: OK 画像={ok}")
            else:
                r = client.models.generate_content(model=model, contents="「こんにちは」とだけ返して")
                print(f"[{loc}] {model}: OK", (r.text or "").strip()[:30])
        except Exception as e:  # noqa: BLE001
            print(f"[{loc}] {model}: 失敗", type(e).__name__, str(e)[:160].replace("\n", " "))
