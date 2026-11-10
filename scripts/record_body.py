"""手・体・顔の「数値だけ」を録る実験用スクリプト（映像・画像・音声は保存しない）。

実行（初回は体と顔のモデルを Google の公式の置き場所から取得: 約10MB）:
  uv run --python 3.12 --with mediapipe --with opencv-python python scripts/record_body.py [名前 ...]
保存先: .local_storage/body/<名前>.json
保存するもの:
  hands: 手の21点（今の契約と同じ）
  pose : 上半身9点（鼻・肩・肘・手首・腰）の x,y,z,見えている確率
  face : 表情の強さ（口をすぼめる・口を開ける・笑う 等）と、頭の向き（yaw,pitch,roll）。顔の形そのもの（468点）は保存しない
"""
import json
import math
import sys
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / ".local_storage" / "body"
MODELS = ROOT / ".local_storage" / "models"
URLS = {
    "hand_landmarker.task": "https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task",
    "pose_landmarker_lite.task": "https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/1/pose_landmarker_lite.task",
    "face_landmarker.task": "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
}
POSE_IDX = {"nose": 0, "l_shoulder": 11, "r_shoulder": 12, "l_elbow": 13, "r_elbow": 14,
            "l_wrist": 15, "r_wrist": 16, "l_hip": 23, "r_hip": 24}
BLEND = ("mouthPucker", "mouthFunnel", "jawOpen", "mouthSmileLeft", "mouthSmileRight",
         "eyeBlinkLeft", "eyeBlinkRight", "browInnerUp", "cheekPuff")

# 名前: (正解の説明, やり方)
SCENES = {
    "steamboat": ("蒸気船の舵を取っているネズミ（体を左に向けて舵を回し、口笛を吹く）",
                  "カメラに体の左側を向け、舵輪を回す仕草をしながら、口をすぼめて口笛を吹く"),
    "whistle": ("口笛を吹いている（手は動かさない）", "正面を向いて、口をすぼめて口笛を吹く。手は膝の上か画面の外"),
    "clap": ("拍手している", "正面を向いて、両手をパンパンと打ち合わせる"),
    "wave": ("手を振っている（バイバイ）", "正面を向いて、手を開いて左右に振る"),
}
SECONDS, STEP_MS = 5, 100
CLOCK0 = time.monotonic()


def ensure(name: str) -> str:
    p = MODELS / name
    if not p.exists():
        MODELS.mkdir(parents=True, exist_ok=True)
        print(f"モデルを取得します: {name}")
        urllib.request.urlretrieve(URLS[name], p)
    return str(p)


def head_angles(m) -> dict:
    """4x4の変換行列から、頭の向き（度）を出す。yaw=左右、pitch=上下、roll=傾き。"""
    r = [[float(m[i][j]) for j in range(3)] for i in range(3)]
    pitch = math.atan2(r[2][1], r[2][2])
    yaw = math.atan2(-r[2][0], math.hypot(r[2][1], r[2][2]))
    roll = math.atan2(r[1][0], r[0][0])
    return {k: round(math.degrees(v)) for k, v in (("yaw", yaw), ("pitch", pitch), ("roll", roll))}


def make_landmarkers():
    base = lambda n: mp_python.BaseOptions(model_asset_path=ensure(n))
    video = vision.RunningMode.VIDEO
    return (
        vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
            base_options=base("hand_landmarker.task"), running_mode=video, num_hands=2)),
        vision.PoseLandmarker.create_from_options(vision.PoseLandmarkerOptions(
            base_options=base("pose_landmarker_lite.task"), running_mode=video)),
        vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=base("face_landmarker.task"), running_mode=video,
            output_face_blendshapes=True, output_facial_transformation_matrixes=True)),
    )


def record(lms, cap, name: str) -> dict:
    hand_d, pose_d, face_d = lms
    expected, how = SCENES[name]
    print(f"\n■ {name}: {expected}\n  やり方: {how}")
    for n in (3, 2, 1):
        print(f"  {n}…", flush=True)
        t = time.time()
        while time.time() - t < 1:
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
        clock = int((time.monotonic() - CLOCK0) * 1000)      # 検出器の時刻は、録画をまたいで増え続ける
        hr, pr, fr = hand_d.detect_for_video(image, clock), pose_d.detect_for_video(image, clock), face_d.detect_for_video(image, clock)
        if now_ms - last_ms < STEP_MS:
            continue
        last_ms = now_ms
        hands = [{"handedness": c[0].category_name if c[0].category_name in ("Left", "Right") else "Right",
                  "landmarks": [{"x": p.x, "y": p.y, "z": p.z} for p in h]}
                 for h, c in zip(hr.hand_landmarks, hr.handedness)]
        pose = None
        if pr.pose_landmarks:
            L = pr.pose_landmarks[0]
            pose = {k: {"x": round(L[i].x, 3), "y": round(L[i].y, 3), "z": round(L[i].z, 3),
                        "v": round(L[i].visibility or 0, 2)} for k, i in POSE_IDX.items()}
        face = None
        if fr.face_blendshapes:
            bs = {c.category_name: round(c.score, 2) for c in fr.face_blendshapes[0]}
            face = {"blend": {k: bs.get(k, 0) for k in BLEND}}
            if fr.facial_transformation_matrixes:
                face["head"] = head_angles(fr.facial_transformation_matrixes[0])
        samples.append({"timestamp_ms": now_ms, "hands": hands, "pose": pose, "face": face})
    n = max(1, len(samples))
    print(f"  終了。サンプル {len(samples)} 件、手 {sum(1 for s in samples if s['hands'])*100//n}% 体 {sum(1 for s in samples if s['pose'])*100//n}% 顔 {sum(1 for s in samples if s['face'])*100//n}%")
    return {"label": name, "expected": expected, "samples": samples}


def main():
    names = sys.argv[1:] or list(SCENES)
    for n in names:
        if n not in SCENES:
            raise SystemExit(f"知らない名前: {n}（使えるもの: {', '.join(SCENES)}）")
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        raise SystemExit("カメラを開けません。システム設定 → プライバシーとセキュリティ → カメラ で、ターミナルを許可してください。")
    OUT.mkdir(parents=True, exist_ok=True)
    lms = make_landmarkers()
    try:
        for n in names:
            (OUT / f"{n}.json").write_text(json.dumps(record(lms, cap, n), ensure_ascii=False), encoding="utf-8")
    finally:
        cap.release()
        for d in lms:
            d.close()
    print(f"\n保存しました: {OUT}\n次: RUNTIME_MODE=cloud ENABLE_CLOUD=true AI_MODE=real uv run --python 3.12 python scripts/body_lab.py")


if __name__ == "__main__":
    main()
