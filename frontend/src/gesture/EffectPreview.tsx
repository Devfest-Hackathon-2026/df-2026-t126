// エフェクトのボタンに入れる、小さな見本。8の字に動く点に、そのエフェクトを付けて描く。
// 初めての人でも、全部を試さずに見た目が分かるようにする。
// 見本はいくつも並ぶので、1つの繰り返し（requestAnimationFrame）でまとめて、1秒に約30回だけ描く。

import { useEffect, useRef } from 'react'
import { createEffect, type Effect, type EffectId } from './effects'

/** エフェクトから見た、仮のキャンバスの大きさ（本物の録画と同じくらいの太さに見せるため） */
const VIEW_W = 400
const VIEW_H = 180
const SCALE = 0.5
const FRAME_MS = 33

interface Preview {
  canvas: HTMLCanvasElement
  effect: Effect
}

const previews = new Set<Preview>()
let loop = 0
let lastDraw = 0

function drawAll(now: number) {
  loop = requestAnimationFrame(drawAll)
  if (now - lastDraw < FRAME_MS) return
  lastDraw = now
  const t = now / 1000
  // 8の字。横に大きく、縦に小さく動く
  const x = VIEW_W / 2 + (VIEW_W * 0.36) * Math.sin(t * 1.6)
  const y = VIEW_H / 2 + (VIEW_H * 0.28) * Math.sin(t * 3.2)
  const hand = { handedness: 'Right', points: Array.from({ length: 21 }, () => ({ x, y })) }
  for (const { canvas, effect } of previews) {
    const context = canvas.getContext('2d')
    if (!context) continue
    context.setTransform(1, 0, 0, 1, 0, 0)
    context.fillStyle = '#121826'
    context.fillRect(0, 0, canvas.width, canvas.height)
    context.setTransform(SCALE, 0, 0, SCALE, 0, 0)
    effect.draw(context, [hand], now)
  }
}

export function EffectPreview({ id }: { id: EffectId }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    // 録画前と同じく、線は少しずつ消える
    const preview = { canvas, effect: createEffect({ id, mode: 'fade' }, Math.random, true) }
    previews.add(preview)
    if (previews.size === 1) loop = requestAnimationFrame(drawAll)
    return () => {
      previews.delete(preview)
      if (previews.size === 0) cancelAnimationFrame(loop)
    }
  }, [id])

  return (
    <canvas
      ref={canvasRef}
      className="effect-preview"
      width={VIEW_W * SCALE}
      height={VIEW_H * SCALE}
      aria-hidden="true"
    />
  )
}
