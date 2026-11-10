"""著作物利用シート（運営の様式）の B 担当部分の下書きを作る。

入力: 運営の様式（xlsx）。1枚目「著作物利用シート」の列は、
      No. / 著作物の名称 / 種類 / 入手元URL / 権利者名（著作者名） / ライセンス形態 / 改変の有無
出力: docs/submission/著作物利用シート_Bの下書き.xlsx（様式のコピーに、行を入れたもの）
      2枚目「提出時チェックリスト」は、**そのまま（チェックを入れない）**。誓約は、人間が確認して、自分で入れる。

使い方:
    uv run --with openpyxl python scripts/build_copyright_sheet.py "<様式の xlsx のパス>"

根拠: ライブラリの版・ライセンスは uv.lock / package-lock.json とインストール済みのメタデータ（2026-11-10 確認）。
「要確認」と書いた欄は、人間が確かめてから、書き換える。
"""
from __future__ import annotations

import sys
from copy import copy
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "submission" / "著作物利用シート_Bの下書き.xlsx"

GCP_TERMS = "独自規約（Google Cloud 利用規約。従量課金。運営配布のクレジットを利用）"
FB_TERMS = "独自規約（Firebase 利用規約）"

# (名称, 種類, 入手元URL, 権利者, ライセンス形態, 改変)
ROWS: list[tuple[str, str, str, str, str, str]] = [
    # --- 実行に使うライブラリ（バックエンド）---
    ("FastAPI 0.162.1", "コード", "https://github.com/fastapi/fastapi", "Sebastián Ramírez", "MIT License", "なし"),
    ("Pydantic 2.14.3", "コード", "https://github.com/pydantic/pydantic", "Samuel Colvin ほか Pydantic の貢献者", "MIT License", "なし"),
    ("pydantic-settings 2.16.2", "コード", "https://github.com/pydantic/pydantic-settings", "Samuel Colvin ほか", "MIT License", "なし"),
    ("python-multipart 0.0.33", "コード", "https://github.com/Kludex/python-multipart", "Andrew Dunham ほか", "Apache License 2.0", "なし"),
    ("Uvicorn 0.54.0", "コード", "https://github.com/encode/uvicorn", "Tom Christie（Encode）ほか", "BSD 3-Clause License", "なし"),
    ("google-cloud-firestore 2.34.1", "コード", "https://github.com/googleapis/google-cloud-python/tree/main/packages/google-cloud-firestore", "Google LLC", "Apache License 2.0", "なし"),
    ("google-cloud-storage 3.17.1", "コード", "https://github.com/googleapis/google-cloud-python/tree/main/packages/google-cloud-storage", "Google LLC", "Apache License 2.0", "なし"),
    ("google-cloud-tasks 2.26.0", "コード", "https://github.com/googleapis/google-cloud-python/tree/main/packages/google-cloud-tasks", "Google LLC", "Apache License 2.0", "なし"),
    ("firebase-admin（Python）7.7.0", "コード", "https://github.com/firebase/firebase-admin-python", "Google LLC（Firebase）", "Apache License 2.0", "なし"),
    ("google-genai 3.0.0", "コード", "https://github.com/googleapis/python-genai", "Google LLC", "Apache License 2.0", "なし"),
    ("PyAV（av）18.1.0", "コード", "https://github.com/PyAV-Org/PyAV", "PyAV Contributors（WyattBlue、Jeremy Lainé ほか）", "BSD 3-Clause License", "なし"),
    ("FFmpeg と、同梱のライブラリ（PyAV の配布版に含まれる: コーデックの x264・x265・libvpx・libdav1d・SVT-AV1・Opus・LAME・OpenCORE-AMR・libwebp、通信・数学の GnuTLS・Nettle・GMP など）", "コード（PyAV に同梱）", "https://ffmpeg.org/", "FFmpeg の開発者、VideoLAN（x264）、MulticoreWare（x265）ほか", "LGPL 2.1 以降／GPL 2.0 以降（x264・x265 を含むビルドのため。2026-11-10 に、本番と同じ Linux 版 18.1.0 の同梱ライブラリを確認）。サーバー内で録画の形式・長さの検証にだけ使い、利用者には配布しない", "なし"),
    # --- 実行に使うライブラリ（フロントエンド）---
    ("React 19.3.1", "コード", "https://github.com/facebook/react", "Meta Platforms, Inc. and affiliates", "MIT License", "なし"),
    ("React DOM 19.3.1", "コード", "https://github.com/facebook/react", "Meta Platforms, Inc. and affiliates", "MIT License", "なし"),
    ("Firebase JS SDK 13.2.0", "コード", "https://github.com/firebase/firebase-js-sdk", "Google LLC（Firebase）", "Apache License 2.0", "なし"),
    ("@mediapipe/tasks-vision 1.2.2（MediaPipe Tasks Vision）", "コード", "https://www.npmjs.com/package/@mediapipe/tasks-vision", "Google LLC", "Apache License 2.0", "なし"),
    ("vision_wasm_internal.js（MediaPipe Tasks Vision の同梱物。ビルド時にコピーして、画面と一緒に配信）", "コード", "https://www.npmjs.com/package/@mediapipe/tasks-vision", "Google LLC", "Apache License 2.0（パッケージ同梱物）", "なし"),
    ("vision_wasm_internal.wasm（MediaPipe Tasks Vision の同梱物。ビルド時にコピーして、画面と一緒に配信）", "コード", "https://www.npmjs.com/package/@mediapipe/tasks-vision", "Google LLC", "Apache License 2.0（パッケージ同梱物）", "なし"),
    # --- モデル ---
    ("MediaPipe Hand Landmarker（hand_landmarker.task、float16）", "モデル（データ）", "https://ai.google.dev/edge/mediapipe/solutions/vision/hand_landmarker", "Google LLC", "Apache License 2.0", "なし"),
    # --- Google の AI（API）---
    ("Gemini 3.5 Flash（Vertex AI）", "API", "https://cloud.google.com/vertex-ai", "Google LLC", GCP_TERMS, "なし"),
    ("Gemini 3.1 Flash Image（Vertex AI）", "API", "https://cloud.google.com/vertex-ai", "Google LLC", GCP_TERMS, "なし"),
    ("Gemini 2.5 Flash Image（Vertex AI。画像生成が混んだときの予備）", "API", "https://cloud.google.com/vertex-ai", "Google LLC", GCP_TERMS, "なし"),
    ("gemini-embedding-001（Vertex AI）", "API", "https://cloud.google.com/vertex-ai", "Google LLC", GCP_TERMS, "なし"),
    # --- Google Cloud / Firebase（サービス）---
    ("Cloud Run", "API", "https://cloud.google.com/run", "Google LLC", GCP_TERMS, "なし"),
    ("Cloud Firestore", "API", "https://cloud.google.com/firestore", "Google LLC", GCP_TERMS, "なし"),
    ("Cloud Storage", "API", "https://cloud.google.com/storage", "Google LLC", GCP_TERMS, "なし"),
    ("Cloud Tasks", "API", "https://cloud.google.com/tasks", "Google LLC", GCP_TERMS, "なし"),
    ("Cloud Scheduler", "API", "https://cloud.google.com/scheduler", "Google LLC", GCP_TERMS, "なし"),
    ("Cloud Build（gcloud run deploy --source が、裏でコンテナを作るために使う）", "API", "https://cloud.google.com/build", "Google LLC", GCP_TERMS, "なし"),
    ("Artifact Registry（同上。作ったコンテナの置き場）", "API", "https://cloud.google.com/artifact-registry", "Google LLC", GCP_TERMS, "なし"),
    ("Firebase Hosting", "API", "https://firebase.google.com/products/hosting", "Google LLC（Firebase）", FB_TERMS, "なし"),
    ("Firebase Authentication（匿名ログイン）", "API", "https://firebase.google.com/products/auth", "Google LLC（Firebase）", FB_TERMS, "なし"),
    ("Python 公式 Docker イメージ python:3.11-slim（Debian ベース。Cloud Run のコンテナの土台）", "コード", "https://hub.docker.com/_/python", "Python Software Foundation ほか（Docker Official Image）。中身の Debian の各パッケージは各権利者", "PSF License（Python）、Debian の各パッケージは各ライセンス", "なし"),
    # --- アーキテクチャ図のアイコン ---
    ("Google Cloud アイコン（アーキテクチャ図）", "画像", "https://cloud.google.com/icons", "Google LLC", "Google が公開する利用条件に従う（アーキテクチャ図での利用）", "なし"),
    ("Firebase アイコン（アーキテクチャ図）", "画像", "https://firebase.google.com/brand-guidelines", "Google LLC（Firebase）", "Firebase ブランドガイドラインに従う", "なし"),
    # --- 開発用ツール（成果物には含まれない）---
    ("pytest 9.2.0（開発用）", "コード", "https://github.com/pytest-dev/pytest", "Holger Krekel ほか pytest の貢献者", "MIT License", "なし"),
    ("pytest-asyncio 1.4.1（開発用）", "コード", "https://github.com/pytest-dev/pytest-asyncio", "pytest-asyncio の貢献者", "Apache License 2.0", "なし"),
    ("httpx 0.28.1（開発用）", "コード", "https://github.com/encode/httpx", "Tom Christie（Encode）ほか", "BSD 3-Clause License", "なし"),
    ("Ruff 0.17.4（開発用）", "コード", "https://github.com/astral-sh/ruff", "Astral Software Inc.", "MIT License", "なし"),
    ("Vite 8.3.6（開発用）", "コード", "https://github.com/vitejs/vite", "Evan You ほか Vite の貢献者", "MIT License", "なし"),
    ("TypeScript 7.0.2（開発用）", "コード", "https://github.com/microsoft/TypeScript", "Microsoft Corp.", "Apache License 2.0", "なし"),
    ("@vitejs/plugin-react 6.2.1（開発用）", "コード", "https://github.com/vitejs/vite-plugin-react", "Evan You ほか", "MIT License", "なし"),
    ("@vitejs/plugin-basic-ssl 2.3.0（開発用）", "コード", "https://github.com/vitejs/vite-plugin-basic-ssl", "Evan You ほか Vite の貢献者", "MIT License", "なし"),
    ("firebase-tools 15.35.0（開発用）", "コード", "https://github.com/firebase/firebase-tools", "Google LLC（Firebase）", "MIT License", "なし"),
    ("oxlint 1.92.0（開発用）", "コード", "https://github.com/oxc-project/oxc", "Boshen と oxc の貢献者", "MIT License", "なし"),
    ("@types/node・@types/react・@types/react-dom（型定義。開発用）", "コード", "https://github.com/DefinitelyTyped/DefinitelyTyped", "DefinitelyTyped の貢献者", "MIT License", "なし"),
    ("@firebase/rules-unit-testing（Firestore ルールの試験用。tools/emulator。開発用）", "コード", "https://www.npmjs.com/package/@firebase/rules-unit-testing", "Google LLC（Firebase）", "Apache License 2.0", "なし"),
    ("setuptools（Python のパッケージ作成。ビルド用）", "コード", "https://github.com/pypa/setuptools", "Python Packaging Authority の貢献者", "MIT License", "なし"),
    ("pptxgenjs 4.0.1（プレゼンスライドの下書きを作る道具。開発用）", "コード", "https://github.com/gitbrent/PptxGenJS", "Brent Ely ほか PptxGenJS の貢献者", "MIT License", "なし"),
    ("sharp 0.35.5（人・ロボットの絵を PNG にする道具。開発用）", "コード", "https://github.com/lovell/sharp", "Lovell Fuller ほか sharp の貢献者", "Apache License 2.0", "なし"),
    # --- フォント（プレゼンスライド）---
    ("Noto Sans JP（プレゼンスライドの書体。見出し: Black、本文: Medium。Google スライドで使用）", "フォント", "https://fonts.google.com/noto/specimen/Noto+Sans+JP", "The Noto Project Authors（Google、Adobe ほか）", "SIL Open Font License 1.1", "なし"),
    # --- 自作（外部の素材を使っていないことの明記）---
    ("自作の素材: お題44件、AI へのプロンプト、画面のデザインと光る線のエフェクト（11種類）、人のミニキャラ、favicon、README の画面画像", "自作", "（リポジトリ内）", "チーム（自作）", "自作（外部の著作物を含まない）", "—"),
    ("外部の画像・音声・動画は使用していない（アプリ・デモ動画・スライドとも。アプリの書体は、利用者の端末の標準書体。プレゼンスライドの書体だけ、上の Noto Sans JP。デモ動画に、外部の BGM・効果音・素材は使っていない＝フロント担当の確認）", "—", "—", "—", "—", "—"),
]


def build(template: Path, dest: Path) -> None:
    import openpyxl

    wb = openpyxl.load_workbook(str(template))
    ws = wb["著作物利用シート"]
    style = {c.column: c for c in ws[2]}  # 例1 の行の書式を、各行に使う

    # 例（2〜4行目）を消して、実際の行を入れる
    ws.delete_rows(2, ws.max_row - 1)
    for i, row in enumerate(ROWS, start=1):
        r = i + 1
        values = (i, *row)
        for col, value in enumerate(values, start=1):
            cell = ws.cell(row=r, column=col, value=value)
            src = style.get(col)
            if src is not None:
                cell.font = copy(src.font)
                cell.border = copy(src.border)
                cell.fill = copy(src.fill)
                cell.number_format = src.number_format
                cell.alignment = copy(src.alignment)
    ws.column_dimensions["B"].width = 46
    ws.column_dimensions["D"].width = 44
    ws.column_dimensions["E"].width = 34
    ws.column_dimensions["F"].width = 42
    # 2枚目のチェック欄は、幅が狭いと Excel で「##」に見える。幅だけ広げる（値は変えない）
    wb["提出時チェックリスト"].column_dimensions["C"].width = 8
    dest.parent.mkdir(parents=True, exist_ok=True)
    wb.save(str(dest))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit("使い方: build_copyright_sheet.py <様式の xlsx>")
    build(Path(sys.argv[1]), OUT)
    print("作成:", OUT, "/", len(ROWS), "行")
