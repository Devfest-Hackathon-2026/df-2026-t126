"""Mac のカメラで手の動きを録り、MediaPipe の座標（21点）を、AIに渡す形式で保存する。

実行（初回は、手の検出モデル hand_landmarker.task（約7.5MB）を Google の公式の置き場所から取得する）:
  uv run --python 3.12 --with mediapipe --with opencv-python python scripts/record_gestures.py [名前 ...]
名前を省略すると全部。1つ5秒、始まる前に3秒のカウントダウン。保存先: .local_storage/gestures/<名前>.json
カメラの許可を聞かれたら、ターミナル（または VS Code など実行したアプリ）に、許可してください。

座標は、フロントと同じ方式（MediaPipe Tasks の HandLandmarker、カメラの生の向き、mirrored=false）。
"""
import json
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

from common.models import GestureBatch, Hand, Landmark, Sample

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".local_storage" / "gestures"
MODEL = ROOT / ".local_storage" / "models" / "hand_landmarker.task"
MODEL_URL = "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task"

# 名前: (正解の説明, やり方)
GESTURES = {
    "wave": ("手を振る（バイバイ）", "手を開いて、左右に振る"),
    "circle": ("手で円を描く", "手を開いたまま、空中でゆっくり円を描く"),
    "fist": ("グー（握りこぶし）", "指を全部握って、静止"),
    "open": ("パー（手を広げる）", "指を全部広げて、静止"),
    "peace": ("ピース", "人さし指と中指だけを立てる"),
    "thumbs_up": ("いいね（親指を立てる）", "親指だけを立てる"),
    "point": ("指さし", "人さし指だけを立てて、前を指す"),
    "beckon": ("手招き（おいで）", "手のひらを下に向け、指をパタパタ曲げ伸ばし"),
    "clap": ("拍手", "両手を、パンパンと打ち合わせる"),
    "ok": ("OKサイン", "親指と人さし指で輪を作る"),
    "up_down": ("手を上下に動かす", "手を開いて、上下に動かす"),
}
SECONDS, STEP_MS = 5, 100


def ensure_model() -> Path:
    if not MODEL.exists():
        MODEL.parent.mkdir(parents=True, exist_ok=True)
        print(f"手の検出モデルを取得します（約7.5MB）: {MODEL_URL}")
        urllib.request.urlretrieve(MODEL_URL, MODEL)
    return MODEL


CLOCK0 = time.monotonic()


def record(detector, cap, name: str) -> dict:
    expected, how = GESTURES[name]
    print(f"\n■ {name}: {expected}\n  やり方: {how}")
    for n in (3, 2, 1):
        print(f"  {n}…", flush=True)
        t = time.time()
        while time.time() - t < 1:      # カウントダウン中も、カメラの映像を読み捨てる
            cap.read()
    print("  ★ 開始（5秒）", flush=True)
    samples, last_ms, start = [], -STEP_MS, time.monotonic()
    while True:
        now_ms = int((time.monotonic() - start) * 1000)
        if now_ms >= SECONDS * 1000:
            break
        ok, frame = cap.read()
        if not ok:
            continue
        image = mp.Image(image_format=mp.ImageFormat.SRGB, data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        result = detector.detect_for_video(image, int((time.monotonic() - CLOCK0) * 1000))  # 検出器の時刻は、録画をまたいで増え続ける必要がある
        if now_ms - last_ms < STEP_MS:
            continue
        last_ms = now_ms
        hands = []
        for lms, cls in zip(result.hand_landmarks, result.handedness):
            hands.append(Hand(handedness=cls[0].category_name if cls[0].category_name in ("Left", "Right") else "Right",
                              landmarks=[Landmark(x=p.x, y=p.y, z=p.z) for p in lms]))
        samples.append(Sample(timestamp_ms=now_ms, hands=hands))
    detected = sum(1 for s in samples if s.hands)
    print(f"  終了。サンプル {len(samples)} 件、手を検出できた割合 {detected / max(1, len(samples)):.0%}")
    batch = GestureBatch(gesture_session_id=name, sequence_number=0, mirrored=False, samples=samples)
    return {"label": name, "expected": expected, "batches": [batch.model_dump()]}


def main():
    names = sys.argv[1:] or list(GESTURES)
    for n in names:
        if n not in GESTURES:
            raise SystemExit(f"知らない名前: {n}（使えるもの: {', '.join(GESTURES)}）")
    options = vision.HandLandmarkerOptions(
        base_options=mp_python.BaseOptions(model_asset_path=str(ensure_model())),
        running_mode=vision.RunningMode.VIDEO, num_hands=2)
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise SystemExit("カメラを開けません。システム設定 → プライバシーとセキュリティ → カメラ で、ターミナルを許可してください。")
    OUT.mkdir(parents=True, exist_ok=True)
    with vision.HandLandmarker.create_from_options(options) as detector:
        for n in names:
            data = record(detector, cap, n)
            (OUT / f"{n}.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    cap.release()
    print(f"\n保存しました: {OUT}\n次: RUNTIME_MODE=cloud ENABLE_CLOUD=true AI_MODE=real uv run --python 3.12 python scripts/eval_gestures.py")


if __name__ == "__main__":
    main()
