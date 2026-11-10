// ジェスチャーの入力元。人Bの段が始まってからでは時間が足りないので、
// カメラの許可と MediaPipe の読み込みは、段の前に prepareCapture で済ませておく。

import type { Hand, Sample } from '../api/types'
import {
  createEffect,
  DEFAULT_CHOICE,
  isEffectId,
  isTrailMode,
  type EffectChoice,
  type TrailMode,
} from './effects'

export interface GestureCapture {
  /** 手の座標がカメラの向きから左右反転しているか */
  readonly mirrored: boolean
  /** キャンバスへの描画を始める */
  start(canvas: HTMLCanvasElement): void
  /** 今の手の座標を読む */
  sample(timestampMs: number): Sample
  /** エフェクトを切り替える。同じ種類でも、描いたものは消えて最初からになる */
  setEffect(choice: EffectChoice): void
  /** これから描く線を残すか消すかを変える。すでに描いた線は消えない */
  setTrailMode(mode: TrailMode): void
  /** 試し描き（録画前）。true の間は「残る」でも線を残さない */
  setPreview(preview: boolean): void
  /** カメラを止める */
  stop(): void
}

/** 録画に映すもの。camera は映像とエフェクト、skeleton は手の骨格とエフェクトだけ */
export type VideoMode = 'camera' | 'skeleton'

const params = new URLSearchParams(location.search)
const videoMode: VideoMode = params.get('video_mode') === 'skeleton' ? 'skeleton' : 'camera'

let prepared: Promise<GestureCapture> | null = null

async function load(): Promise<GestureCapture> {
  if (params.has('fake_camera')) return createFakeCapture()
  // MediaPipe は大きいので、人Bの端末でだけ読み込む
  const { createCameraCapture } = await import('./camera')
  return createCameraCapture(videoMode)
}

export function prepareCapture(): Promise<GestureCapture> {
  prepared ??= load().catch((error: unknown) => {
    prepared = null
    throw error
  })
  return prepared
}

export function releaseCapture(): void {
  const current = prepared
  prepared = null
  void current?.then((capture) => capture.stop()).catch(() => undefined)
}

const EFFECT_KEY = 'gesture-effect-choice'

/** 前回選んだエフェクト。保存できない環境では既定のものを使う */
export function loadEffectChoice(): EffectChoice {
  try {
    const saved: unknown = JSON.parse(localStorage.getItem(EFFECT_KEY) ?? 'null')
    if (saved && typeof saved === 'object' && 'id' in saved && 'mode' in saved) {
      const { id, mode } = saved
      if (isEffectId(id) && isTrailMode(mode)) return { id, mode }
    }
  } catch {
    // 保存できない環境や、壊れた値のときは既定のものを使う
  }
  return DEFAULT_CHOICE
}

export function saveEffectChoice(choice: EffectChoice): void {
  try {
    localStorage.setItem(EFFECT_KEY, JSON.stringify(choice))
  } catch {
    // 保存できなくても、今回の選択はそのまま使える
  }
}

const round4 = (value: number) => Math.round(value * 10_000) / 10_000

/** カメラの無い環境で流れを試すための仮の入力。URL に ?fake_camera を付けると使う */
function createFakeCapture(): GestureCapture {
  let timer: ReturnType<typeof setInterval> | undefined
  let preview = true
  let effect = createEffect(loadEffectChoice(), Math.random, preview)
  const startedAt = Date.now()

  function position() {
    const t = (Date.now() - startedAt) / 1000
    return { x: 0.5 + 0.3 * Math.cos(t * 2), y: 0.5 + 0.3 * Math.sin(t * 2) }
  }

  return {
    mirrored: false,
    start(canvas) {
      const context = canvas.getContext('2d')
      if (!context) return
      timer = setInterval(() => {
        const { x, y } = position()
        const point = { x: x * canvas.width, y: y * canvas.height }
        context.fillStyle = '#0f172a'
        context.fillRect(0, 0, canvas.width, canvas.height)
        context.fillStyle = '#e2e8f0'
        context.beginPath()
        context.arc(point.x, point.y, 8, 0, Math.PI * 2)
        context.fill()
        const hand = { handedness: 'Right', points: Array.from({ length: 21 }, () => point) }
        effect.draw(context, [hand], performance.now())
      }, 33)
    },
    sample(timestampMs) {
      const { x, y } = position()
      const hand: Hand = {
        handedness: 'Right',
        landmarks: Array.from({ length: 21 }, (_, index) => ({
          x: round4(x + index * 0.002),
          y: round4(y),
          z: 0,
        })),
      }
      return { timestamp_ms: timestampMs, hands: [hand] }
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
      clearInterval(timer)
    },
  }
}
