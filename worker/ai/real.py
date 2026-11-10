"""本物のAI（Gemini API / Vertex AI）。処理ごとに provider を選べる。

429（上限超過）への備え:
1. 呼び出しの中で、待って再試行する（6秒、12秒）
2. それでも 429 なら、もう一方の provider（Vertex ⇔ Gemini API）に切り替えて1回試す
   （Gemini API は gemini_api_key があるときだけ）
3. 画像生成だけは、さらに別モデル・別ロケーションの Vertex に順に切り替える
   （429 のとき、または応答が遅くてタイムアウトしたとき。2026-11-08 の実測で動作確認済みの組だけ）
"""
from __future__ import annotations

import asyncio
import contextvars
import json
import logging
import random

from google import genai
from google.genai import errors, types

from common.enums import ErrorCode
from common.models import GestureBatch
from common.settings import Settings
from worker.ai.base import AIError
from worker.ai.preprocess import prepare_batches
from worker.prompts import PROMPTS

log = logging.getLogger(__name__)

# Settings（A と共有する契約）は増やさず、ここで持つ。
RATE_LIMIT_RETRIES = 2
RATE_LIMIT_BACKOFF_S = 6.0

# 画像生成の逃げ道（モデル, ロケーション）。実測（scripts/check_regions.py）で、画像が返ることを確認した組。
# gemini-3.1-flash-image は global のみ。gemini-2.5-flash-image は global と us-central1 で約6秒。
IMAGE_FALLBACKS = [("gemini-2.5-flash-image", "global"), ("gemini-2.5-flash-image", "us-central1")]

# 文章を作る呼び出しは、あまり考えさせず、出力も短く打ち切る（費用の抑制。2026-11 の実測で、考える分の出力が費用の最大要因だった）
TEXT_CONFIG = types.GenerateContentConfig(
    thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
    max_output_tokens=1024,
)

# 切り替え先の provider では、待って再試行しない（切り替え先も 429 のとき、無駄に待たないため）
_RETRIES_OVERRIDE: contextvars.ContextVar[int | None] = contextvars.ContextVar("retries_override", default=None)


class RealAIClient:
    def __init__(self, s: Settings, *, rate_limit_retries: int = RATE_LIMIT_RETRIES,
                 rate_limit_backoff_s: float = RATE_LIMIT_BACKOFF_S, fallback: bool = True):
        self.s = s
        self.rate_limit_retries = rate_limit_retries
        self.rate_limit_backoff_s = rate_limit_backoff_s
        self.fallback = fallback
        self._clients: dict[str, genai.Client] = {}
        self._clients_loop: asyncio.AbstractEventLoop | None = None

    def _client(self, provider: str, location: str | None = None) -> genai.Client:
        # Worker は、1回の要求ごとに新しいイベントループで動く（api/worker_app.py の asyncio.run）。
        # 以前のループに結びついた genai のクライアントを使い回すと、"Event loop is closed" で失敗する
        # （2026-11-09 の本番で、最初の呼び出しの約半分が失敗し、3回とも失敗するとゲームが中断した）。
        # ループが変わったら、キャッシュを捨てて、作り直す。
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if self._clients_loop is not None and loop is not self._clients_loop:
            self._clients.clear()
        self._clients_loop = loop
        loc = location or self.s.vertex_location
        key = f"{provider}:{loc}" if provider == "vertex" else provider
        if key not in self._clients:
            if provider == "vertex":
                c = genai.Client(vertexai=True, project=self.s.gcp_project, location=loc)
            else:
                c = genai.Client(api_key=self.s.gemini_api_key)
            self._clients[key] = c
        return self._clients[key]

    def _alternate(self, provider: str) -> str | None:
        if not self.fallback:
            return None
        if provider == "vertex":
            return "developer" if getattr(self.s, "gemini_api_key", None) else None
        return "vertex"

    async def _call(self, make):
        """make は、呼ぶたびに新しいコルーチンを返す関数。429 のときだけ、待って再試行する。"""
        attempt = 0
        override = _RETRIES_OVERRIDE.get()
        limit = self.rate_limit_retries if override is None else override
        while True:
            try:
                return await asyncio.wait_for(make(), timeout=self.s.ai_timeout_s)
            except asyncio.TimeoutError as e:
                log.warning("AI call timed out (%.0fs)", self.s.ai_timeout_s)
                raise AIError(ErrorCode.ai_timeout, "AIの応答がタイムアウト", True) from e
            except errors.APIError as e:
                code = getattr(e, "code", 0) or 0
                # 失敗の原因を残す（再試行で成功すると、Firestore 側の記録が消えるため。2026-11-09 の調査用）
                log.warning("AI API error code=%s status=%s message=%s", code, getattr(e, "status", ""),
                            (getattr(e, "message", "") or "")[:200])
                if code == 429 and attempt < limit:
                    wait = self.rate_limit_backoff_s * (2 ** attempt) * random.uniform(0.8, 1.2)
                    attempt += 1
                    await asyncio.sleep(wait)
                    continue
                retryable = code in (408, 429) or code >= 500
                detail = f"{getattr(e, 'status', '') or ''}: {(getattr(e, 'message', '') or '')[:100]}".strip(": ")
                err = AIError(ErrorCode.ai_failed, f"AI APIエラー {code} {detail}".strip(), retryable)
                err.http_code = code
                raise err from e

    async def _run(self, provider: str, do):
        """do(provider) を実行。429 で尽きたら、もう一方の provider で1回だけ試す。"""
        try:
            return await do(provider)
        except AIError as e:
            alt = self._alternate(provider)
            if getattr(e, "http_code", None) == 429 and alt:
                token = _RETRIES_OVERRIDE.set(0)
                try:
                    return await do(alt)
                finally:
                    _RETRIES_OVERRIDE.reset(token)
            raise

    async def generate_image(self, prompt: str) -> bytes:
        async def attempt(provider: str, model: str, location: str | None = None) -> bytes:
            c = self._client(provider, location)
            r = await self._call(lambda: c.aio.models.generate_content(model=model, contents=prompt))
            for cand in r.candidates or []:
                if cand.finish_reason and "SAFETY" in str(cand.finish_reason):
                    raise AIError(ErrorCode.ai_blocked, "安全フィルタで拒否", False)
                for part in (cand.content.parts if cand.content else []):
                    if part.inline_data and part.inline_data.data:
                        return part.inline_data.data
            raise AIError(ErrorCode.ai_bad_output, "画像が返らなかった", True)

        first: AIError
        try:
            return await self._run(self.s.provider_image, lambda provider: attempt(provider, self.s.model_image))
        except AIError as e:
            first = e
            overloaded = getattr(e, "http_code", None) == 429 or e.code == ErrorCode.ai_timeout
            if not (overloaded and self.fallback):
                raise
        # 混雑（429）か遅延（タイムアウト）のとき、別モデル・別ロケーションの Vertex を順に試す（待たない）
        token = _RETRIES_OVERRIDE.set(0)
        try:
            for model, location in IMAGE_FALLBACKS:
                if model == self.s.model_image and location == self.s.vertex_location:
                    continue
                try:
                    return await attempt("vertex", model, location)
                except AIError:
                    continue
        finally:
            _RETRIES_OVERRIDE.reset(token)
        raise first

    async def read_gesture(self, batches: list[GestureBatch]) -> str:
        data = json.dumps(prepare_batches(batches), ensure_ascii=False, separators=(",", ":"))

        async def do(provider: str) -> str:
            c = self._client(provider)
            r = await self._call(lambda: c.aio.models.generate_content(
                model=self.s.model_read, contents=f"{PROMPTS.gesture_read}\n\n{data}", config=TEXT_CONFIG))
            if not r.text:
                raise AIError(ErrorCode.ai_bad_output, "文章が返らなかった", True)
            return r.text.strip()

        return await self._run(self.s.provider_read, do)

    async def conclude(self, image: bytes) -> str:
        part = types.Part.from_bytes(data=image, mime_type="image/png")

        async def do(provider: str) -> str:
            c = self._client(provider)
            r = await self._call(lambda: c.aio.models.generate_content(
                model=self.s.model_conclude, contents=[PROMPTS.conclude, part], config=TEXT_CONFIG))
            if not r.text:
                raise AIError(ErrorCode.ai_bad_output, "結論が返らなかった", True)
            return r.text.strip()

        return await self._run(self.s.provider_conclude, do)

    async def embed(self, text: str) -> list[float]:
        async def do(provider: str) -> list[float]:
            c = self._client(provider)
            r = await self._call(lambda: c.aio.models.embed_content(model=self.s.model_embed, contents=text))
            if not r.embeddings:
                raise AIError(ErrorCode.ai_bad_output, "埋め込みが返らなかった", True)
            return list(r.embeddings[0].values)

        return await self._run(self.s.provider_embed, do)
