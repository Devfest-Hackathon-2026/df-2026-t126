"""ジェスチャー座標を、AIに渡す前に小さくする（契約・APIは変えない）。

- 全バッチのサンプルを時間順に並べ、最大 max_samples 件に等間隔で間引く
- 座標は小数 ndigits 桁に丸める
"""
from __future__ import annotations

from common.models import GestureBatch, Sample

MAX_SAMPLES = 60
NDIGITS = 3


def _round_sample(s: Sample, nd: int) -> dict:
    return {
        "t": s.timestamp_ms,
        "hands": [
            {
                "hand": h.handedness,
                "pts": [[round(p.x, nd), round(p.y, nd), round(p.z, nd)] for p in h.landmarks],
            }
            for h in s.hands
        ],
    }


def prepare_batches(batches: list[GestureBatch], max_samples: int = MAX_SAMPLES, ndigits: int = NDIGITS) -> dict:
    """AIに渡す辞書を返す。欠番・重複は sequence_number で整える。"""
    seen: set[int] = set()
    ordered: list[GestureBatch] = []
    for b in sorted(batches, key=lambda b: b.sequence_number):
        if b.sequence_number in seen:
            continue
        seen.add(b.sequence_number)
        ordered.append(b)

    samples = sorted((s for b in ordered for s in b.samples), key=lambda s: s.timestamp_ms)
    total = len(samples)
    if total > max_samples:
        step = (total - 1) / (max_samples - 1)
        samples = [samples[round(i * step)] for i in range(max_samples)]
    return {
        "mirrored": ordered[0].mirrored if ordered else False,
        "total_samples": total,
        "samples": [_round_sample(s, ndigits) for s in samples],
    }
