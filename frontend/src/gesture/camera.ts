// カメラと MediaPipe の入力元。映像は端末の中だけで処理し、AI へ送るのは手の座標だけ。

import { FilesetResolver, HandLandmarker } from '@mediapipe/tasks-vision'
import type { Hand, Sample } from '../api/types'
import { loadEffectChoice, type GestureCapture, type VideoMode } from './capture'
import { createEffect, type DrawnHand } from './effects'

const MAX_SIDE = 640 // 録画のファイルを小さくするために、長い辺をこの大きさに抑える
const DETECT_INTERVAL_MS = 33 // 間隔が空くと、速い手を追えずに見失いやすい

const round4 = (value: number) => Math.round(value * 10_000) / 10_000

async function createLandmarker(): Promise<HandLandmarker> {
  const fileset = await FilesetResolver.forVisionTasks('/mediapipe/wasm')
  const create = (delegate: 'GPU' | 'CPU') =>
    HandLandmarker.createFromOptions(fileset, {
      baseOptions: { modelAssetPath: '/mediapipe/hand_landmarker.task', delegate },
      runningMode: 'VIDEO',
      numHands: 2,
    })
  return create('GPU').catch(() => create('CPU'))
}

async function openCamera(): Promise<HTMLVideoElement> {
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: false,
    video: { facingMode: 'user', width: { ideal: 640 }, height: { ideal: 480 } },
  })
  const video = document.createElement('video')
  video.muted = true
  video.playsInline = true
  video.srcObject = stream
  // iPhone は画面に無い video の再生を止めることがあるので、見えない形で置いておく
  video.style.cssText = 'position:fixed;width:1px;height:1px;opacity:0;pointer-events:none'
  document.body.append(video)
  await video.play()
  return video
}

function closeCamera(video: HTMLVideoElement): void {
  const stream = video.srcObject as MediaStream | null
  stream?.getTracks().forEach((track) => track.stop())
  video.remove()
}

function evenSize(value: number): number {
  return Math.max(2, Math.floor(value / 2) * 2) // 動画の形式によっては奇数の大きさを扱えない
}

export async function createCameraCapture(videoMode: VideoMode): Promise<GestureCapture> {
  const video = await openCamera()
  let landmarker: HandLandmarker
  try {
    landmarker = await createLandmarker()
  } catch (error) {
    closeCamera(video)
    throw error
  }

  let preview = true // 録画が始まるまでは試し描き
  let effect = createEffect(loadEffectChoice(), Math.random, preview)
  let hands: Hand[] = []
  let frame = 0
  let lastDetectAt = 0

  function detect(now: number): void {
    if (now - lastDetectAt < DETECT_INTERVAL_MS || video.readyState < 2) return
    lastDetectAt = now
    const result = landmarker.detectForVideo(video, now)
    hands = result.landmarks.map((landmarks, index) => ({
      handedness: result.handedness[index][0].categoryName === 'Left' ? 'Left' : 'Right',
      landmarks: landmarks.map(({ x, y, z }) => ({ x: round4(x), y: round4(y), z: round4(z) })),
    }))
  }

  function draw(context: CanvasRenderingContext2D, now: number): void {
    const { width, height } = context.canvas
    if (videoMode === 'camera') {
      // 鏡のように見えるよう、表示だけ左右を反転する。送る座標は反転しない
      context.save()
      context.translate(width, 0)
      context.scale(-1, 1)
      context.drawImage(video, 0, 0, width, height)
      context.restore()
    } else {
      context.fillStyle = '#0f172a'
      context.fillRect(0, 0, width, height)
    }

    const drawn: DrawnHand[] = hands.map((hand) => ({
      handedness: hand.handedness,
      points: hand.landmarks.map(({ x, y }) => ({ x: (1 - x) * width, y: y * height })),
    }))
    if (videoMode === 'skeleton') {
      context.strokeStyle = '#e2e8f0'
      context.lineWidth = 3
      for (const { points } of drawn) {
        for (const { start, end } of HandLandmarker.HAND_CONNECTIONS) {
          context.beginPath()
          context.moveTo(points[start].x, points[start].y)
          context.lineTo(points[end].x, points[end].y)
          context.stroke()
        }
      }
    }
    effect.draw(context, drawn, now)
  }

  return {
    mirrored: false,
    start(canvas) {
      const scale = Math.min(1, MAX_SIDE / Math.max(video.videoWidth, video.videoHeight))
      canvas.width = evenSize(video.videoWidth * scale)
      canvas.height = evenSize(video.videoHeight * scale)
      const context = canvas.getContext('2d')
      if (!context) return
      const loop = (now: number) => {
        detect(now)
        draw(context, now)
        frame = requestAnimationFrame(loop)
      }
      cancelAnimationFrame(frame)
      frame = requestAnimationFrame(loop)
    },
    sample(timestampMs): Sample {
      return { timestamp_ms: timestampMs, hands }
    },
    setEffect(choice) {
      effect = createEffect(choice, Math.random, preview)
    },
    setTrailMode(mode) {
      effect.setMode(mode)
    },
    setPreview(next) {
      preview = next
      effect.setPreview(next)
    },
    stop() {
      cancelAnimationFrame(frame)
      closeCamera(video)
      landmarker.close()
    },
  }
}
