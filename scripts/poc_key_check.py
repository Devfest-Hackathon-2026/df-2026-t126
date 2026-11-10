"""キーが Gemini API / Vertex AI の両方で使えるかを確かめるPoC（キーは表示しない）。

実行: uv run --python 3.12 --with google-genai --with python-dotenv scripts/poc_key_check.py
"""
import os

from dotenv import load_dotenv
from google import genai

load_dotenv()
KEY = os.environ["GEMINI_API_KEY"]


def check(name: str, client: genai.Client) -> None:
    print(f"\n=== {name} ===")
    try:
        names = [m.name for m in client.models.list()]
        picked = [n for n in names if "gemini" in n or "embedding" in n or "image" in n]
        print(f"モデル一覧: {len(names)}件 / 該当例:")
        for n in picked[:40]:
            print("  ", n)
    except Exception as e:  # noqa: BLE001
        print("モデル一覧 失敗:", type(e).__name__, str(e)[:200].replace(KEY, "***"))

    for model in ("gemini-3.5-flash", "gemini-3.8-flash"):
        try:
            r = client.models.generate_content(model=model, contents="「こんにちは」とだけ返して")
            print(f"生成 OK ({model}):", (r.text or "").strip()[:40])
            return
        except Exception as e:  # noqa: BLE001
            print(f"生成 失敗 ({model}):", type(e).__name__, str(e)[:200].replace(KEY, "***"))


check("Gemini API (developer)", genai.Client(api_key=KEY))
check("Vertex AI (api_key)", genai.Client(vertexai=True, api_key=KEY))
