import json

from common.models import GestureBatch, Hand, Landmark, Sample
from worker.ai.preprocess import prepare_batches


def sample(t: int, x: float = 0.123456) -> Sample:
    lm = [Landmark(x=x, y=0.5, z=0.0) for _ in range(21)]
    return Sample(timestamp_ms=t, hands=[Hand(handedness="Right", landmarks=lm)])


def batch(seq: int, start: int, n: int, mirrored=False) -> GestureBatch:
    return GestureBatch(
        gesture_session_id="s",
        sequence_number=seq,
        mirrored=mirrored,
        samples=[sample(start + i * 100) for i in range(n)],
    )


def test_small_input_not_downsampled():
    out = prepare_batches([batch(0, 0, 50)])
    assert out["total_samples"] == 50 and len(out["samples"]) == 50


def test_large_input_capped_and_keeps_first_last():
    out = prepare_batches([batch(0, 0, 1000)])
    assert len(out["samples"]) == 60 and out["total_samples"] == 1000
    assert out["samples"][0]["t"] == 0 and out["samples"][-1]["t"] == 99900


def test_rounds_coordinates_and_shrinks_prompt():
    out = prepare_batches([batch(0, 0, 1000)])
    assert out["samples"][0]["hands"][0]["pts"][0][0] == 0.123
    raw = json.dumps(GestureBatch.model_dump(batch(0, 0, 1000)))
    assert len(json.dumps(out)) < len(raw) / 10


def test_duplicate_and_out_of_order_batches():
    b1, b0 = batch(1, 1000, 10), batch(0, 0, 10)
    out = prepare_batches([b1, b0, batch(1, 1000, 10)])  # 重複 + 順序逆
    assert out["total_samples"] == 20
    ts = [s["t"] for s in out["samples"]]
    assert ts == sorted(ts)


def test_empty_and_mirrored():
    assert prepare_batches([])["samples"] == []
    assert prepare_batches([batch(0, 0, 3, mirrored=True)])["mirrored"] is True
