import asyncio

import pytest
from google.genai import errors

from common.enums import ErrorCode
from common.settings import Settings
from worker.ai.base import AIError
from worker.ai.real import RealAIClient


def api_error(code: int) -> errors.APIError:
    return errors.APIError(code, {"error": {"message": "x", "status": "S"}})


@pytest.fixture
def client(monkeypatch):
    sleeps = []

    async def fake_sleep(t):
        sleeps.append(t)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    c = RealAIClient(Settings(ai_mode="mock"), rate_limit_retries=2, rate_limit_backoff_s=6.0)
    c.sleeps = sleeps
    return c


async def test_429_retries_then_succeeds(client):
    calls = {"n": 0}

    def make():
        async def run():
            calls["n"] += 1
            if calls["n"] < 3:
                raise api_error(429)
            return "ok"

        return run()

    assert await client._call(make) == "ok"
    assert calls["n"] == 3 and len(client.sleeps) == 2
    assert 4.8 <= client.sleeps[0] <= 7.2 and 9.6 <= client.sleeps[1] <= 14.4  # 6秒、12秒（±20%）


async def test_429_gives_up_as_retryable(client):
    def make():
        async def run():
            raise api_error(429)

        return run()

    with pytest.raises(AIError) as e:
        await client._call(make)
    assert e.value.retryable and e.value.code == ErrorCode.ai_failed and len(client.sleeps) == 2


async def test_other_errors_do_not_retry_inside(client):
    calls = {"n": 0}

    def make():
        async def run():
            calls["n"] += 1
            raise api_error(400)

        return run()

    with pytest.raises(AIError) as e:
        await client._call(make)
    assert calls["n"] == 1 and not e.value.retryable and client.sleeps == []


# ---- provider の切り替え（429 で尽きたとき） --------------------------------
class _Part:
    def __init__(self, data):
        self.inline_data = type("I", (), {"data": data})()


class _Resp:
    def __init__(self, data):
        self.candidates = [
            type(
                "C",
                (),
                {"finish_reason": None, "content": type("T", (), {"parts": [_Part(data)]})()},
            )()
        ]


class _Models:
    def __init__(self, behavior):
        self.behavior, self.calls = behavior, 0

    async def generate_content(self, **kw):
        self.calls += 1
        if self.behavior == "429":
            raise api_error(429)
        return _Resp(b"PNGDATA")


def _client_with(models):
    return type("G", (), {"aio": type("A", (), {"models": models})()})()


@pytest.fixture
def fb_client(monkeypatch):
    async def fake_sleep(t):
        pass

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    s = Settings(ai_mode="mock", gemini_api_key="k", provider_image="vertex")
    c = RealAIClient(s, rate_limit_retries=1)
    return c


async def test_falls_back_to_other_provider_on_429(fb_client):
    v, d = _Models("429"), _Models("ok")
    fb_client._clients = {
        "vertex:global": _client_with(v),
        "vertex:us-central1": _client_with(_Models("429")),
        "developer": _client_with(d),
    }
    assert await fb_client.generate_image("p") == b"PNGDATA"
    assert v.calls == 2 and d.calls == 1  # vertex: 1回目+再試行1回、その後 developer


async def test_no_fallback_without_key_or_when_disabled(fb_client):
    v = _Models("429")
    fb_client._clients = {
        "vertex:global": _client_with(v),
        "vertex:us-central1": _client_with(_Models("429")),
    }
    fb_client.s = Settings(ai_mode="mock", gemini_api_key=None, provider_image="vertex")
    with pytest.raises(AIError) as e:
        await fb_client.generate_image("p")
    assert e.value.retryable and v.calls == 3  # 本命2回(再試行1回) + 別モデル(global)1回
    fb_client.s = Settings(ai_mode="mock", gemini_api_key="k", provider_image="vertex")
    fb_client.fallback = False
    fb_client._clients = {"vertex:global": _client_with(_Models("429"))}
    with pytest.raises(AIError):
        await fb_client.generate_image("p")


async def test_alternate_provider_does_not_wait_when_also_429(fb_client):
    sleeps = []

    async def rec_sleep(t):
        sleeps.append(t)

    asyncio.sleep = rec_sleep  # fb_client の fixture が元に戻す
    v, d = _Models("429"), _Models("429")
    fb_client._clients = {
        "vertex:global": _client_with(v),
        "vertex:us-central1": _client_with(_Models("429")),
        "developer": _client_with(d),
    }
    with pytest.raises(AIError):
        await fb_client.generate_image("p")
    assert (
        v.calls == 3 and d.calls == 1
    )  # 切り替え先は待たずに1回だけ。Vertex は本命2回 + 別モデル1回
    assert len(sleeps) == 1  # 待ったのは Vertex の1回だけ（rate_limit_retries=1）


# ---- 画像生成の逃げ道（別モデル・別ロケーション） ---------------------------
class _ModelsByName:
    """モデル名ごとに挙動を変える偽物。呼ばれた (model) を記録する。"""

    def __init__(self, behaviors, log, name):
        self.behaviors, self.log, self.name = behaviors, log, name

    async def generate_content(self, model, **kw):
        self.log.append((self.name, model))
        b = self.behaviors.get(model, "ok")
        if b == "429":
            raise api_error(429)
        if b == "404":
            raise api_error(404)
        if b == "timeout":
            await asyncio.sleep(10_000)
        return _Resp(b"PNGDATA")


@pytest.fixture
def img_client(monkeypatch):
    async def fast_sleep(t):
        pass

    monkeypatch.setattr(asyncio, "sleep", fast_sleep)
    c = RealAIClient(
        Settings(
            ai_mode="mock",
            gemini_api_key=None,
            provider_image="vertex",
            vertex_location="global",
            model_image="gemini-3.1-flash-image",
        ),
        rate_limit_retries=0,
    )
    return c


def _wire(c, behaviors):
    log = []
    c._clients = {
        k: _client_with(_ModelsByName(behaviors, log, k))
        for k in ("vertex:global", "vertex:us-central1")
    }
    return log


async def test_image_falls_back_to_other_model_when_primary_429(img_client):
    log = _wire(img_client, {"gemini-3.1-flash-image": "429"})
    assert await img_client.generate_image("p") == b"PNGDATA"
    assert log == [
        ("vertex:global", "gemini-3.1-flash-image"),
        ("vertex:global", "gemini-2.5-flash-image"),
    ]


async def test_image_tries_next_location_then_gives_up_with_429(img_client):
    log = _wire(img_client, {"gemini-3.1-flash-image": "429", "gemini-2.5-flash-image": "429"})
    with pytest.raises(AIError) as e:
        await img_client.generate_image("p")
    assert e.value.retryable and e.value.http_code == 429
    assert ("vertex:us-central1", "gemini-2.5-flash-image") in log and len(log) == 3


async def test_image_fallback_skips_failed_404_and_continues(img_client):
    log = _wire(img_client, {"gemini-3.1-flash-image": "429"})
    img_client._clients["vertex:global"] = _client_with(
        _ModelsByName(
            {"gemini-3.1-flash-image": "429", "gemini-2.5-flash-image": "404"}, log, "vertex:global"
        )
    )
    assert await img_client.generate_image("p") == b"PNGDATA"  # us-central1 で成功
    assert log[-1] == ("vertex:us-central1", "gemini-2.5-flash-image")


async def test_image_no_fallback_for_non_overload_errors(img_client):
    log = _wire(img_client, {"gemini-3.1-flash-image": "404"})
    with pytest.raises(AIError):
        await img_client.generate_image("p")
    assert log == [("vertex:global", "gemini-3.1-flash-image")]


async def test_image_fallback_disabled(img_client):
    img_client.fallback = False
    log = _wire(img_client, {"gemini-3.1-flash-image": "429"})
    with pytest.raises(AIError):
        await img_client.generate_image("p")
    assert len(log) == 1


def test_client_cache_is_dropped_when_the_event_loop_changes(monkeypatch):
    """Worker は要求ごとに新しいイベントループで動く。前のループのクライアントを使い回すと
    "Event loop is closed" で失敗する（2026-11-09 の本番）。ループが変わったら、作り直す。"""
    import asyncio

    from worker.ai import real as real_module
    from worker.ai.real import RealAIClient

    created = []

    class FakeClient:
        def __init__(self, **kwargs):
            created.append(self)

    monkeypatch.setattr(real_module.genai, "Client", FakeClient)
    ai = RealAIClient(Settings(gcp_project="p"))

    async def get_twice():
        return ai._client("vertex"), ai._client("vertex")

    a1, a2 = asyncio.run(get_twice())
    assert a1 is a2  # 同じループの中では、使い回す
    b1, _ = asyncio.run(get_twice())
    assert b1 is not a1  # 別のループでは、作り直す
    assert len(created) == 2
