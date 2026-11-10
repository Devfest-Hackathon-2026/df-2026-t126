// MediaPipe の実行ファイルとモデルを public/mediapipe に用意する。
// 大きいファイルなので Git には入れず、npm run dev と npm run build の前に自動で実行する。
// SKIP_MEDIAPIPE=1 のときは、モデルをダウンロードしない（ネットにつながらない環境でビルド・テストするため）。
// そのビルドでは手の検出が動かないので、画面やテストの確認だけに使う。

import { copyFile, mkdir, stat, writeFile } from 'node:fs/promises'
import { dirname, join } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = join(dirname(fileURLToPath(import.meta.url)), '..')
const wasmSource = join(root, 'node_modules/@mediapipe/tasks-vision/wasm')
const target = join(root, 'public/mediapipe')
const modelPath = join(target, 'hand_landmarker.task')
const modelUrl =
  'https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task'

async function exists(path) {
  return stat(path).then(
    () => true,
    () => false,
  )
}

await mkdir(join(target, 'wasm'), { recursive: true })
for (const name of ['vision_wasm_internal.js', 'vision_wasm_internal.wasm']) {
  await copyFile(join(wasmSource, name), join(target, 'wasm', name))
}

if (process.env.SKIP_MEDIAPIPE === '1') {
  console.log('SKIP_MEDIAPIPE=1 なので、手の検出モデルのダウンロードを飛ばします（手の検出は動きません）')
} else if (!(await exists(modelPath))) {
  console.log('手の検出モデルをダウンロードしています')
  const response = await fetch(modelUrl)
  if (!response.ok) throw new Error(`モデルを取得できません: ${response.status}`)
  await writeFile(modelPath, Buffer.from(await response.arrayBuffer()))
}
