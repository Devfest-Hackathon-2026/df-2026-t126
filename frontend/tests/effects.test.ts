// エフェクトのテスト。npm test で実行する。

import assert from 'node:assert/strict'
import { test } from 'node:test'
import {
  createEffect,
  EFFECTS,
  TRAIL_MODES,
  type DrawnHand,
  type EffectChoice,
  type EffectContext,
  type Random,
} from '../src/gesture/effects.ts'

interface Line {
  length: number
  endX: number
  endY: number
}

interface Dot {
  x: number
  y: number
}

/** 引かれた線と丸を記録する偽物のキャンバス */
function createRecorder() {
  const lines: Line[] = []
  const dots: Dot[] = []
  let from = { x: 0, y: 0 }
  const context = {
    save() {},
    restore() {},
    beginPath() {},
    stroke() {},
    fill() {},
    closePath() {},
    moveTo(x: number, y: number) {
      from = { x, y }
    },
    lineTo(x: number, y: number) {
      lines.push({ length: Math.hypot(x - from.x, y - from.y), endX: x, endY: y })
      from = { x, y }
    },
    arc(x: number, y: number) {
      dots.push({ x, y })
    },
  } as unknown as EffectContext
  return { context, lines, dots }
}

/** 手のひらの点がすべて同じ位置にある手を作る */
function handAt(x: number, y: number, handedness: string): DrawnHand {
  return { handedness, points: Array.from({ length: 21 }, () => ({ x, y })) }
}

/** 決まった順に値を返す乱数。テストの結果を毎回同じにする */
function fixedRandom(): Random {
  let value = 0.37
  return () => {
    value = ((value * 9301 + 49297) % 233280) / 233280
    return value
  }
}

const NEON_FADE: EffectChoice = { id: 'neon_blue', mode: 'fade' }
const longest = (lines: Line[]) => Math.max(0, ...lines.map((line) => line.length))
const ALL_CHOICES: EffectChoice[] = EFFECTS.flatMap(({ id }) =>
  TRAIL_MODES.map(({ mode }) => ({ id, mode })),
)

// ---- 手の追跡（どの種類でも共通） ----

test('手を動かすと軌跡が引かれる', () => {
  const { context, lines } = createRecorder()
  const effect = createEffect(NEON_FADE)
  for (let frame = 0; frame < 10; frame += 1) {
    effect.draw(context, [handAt(100 + frame * 10, 200, 'Right')], frame * 50)
  }
  assert.ok(lines.length > 0)
})

test('手を交差させて左右のラベルが入れ替わっても、線が反対の手へ飛ばない', () => {
  const { context, lines } = createRecorder()
  const effect = createEffect(NEON_FADE)
  for (let frame = 0; frame <= 40; frame += 1) {
    const offset = frame * 10
    // 右へ動く手と左へ動く手が、途中ですれ違う。すれ違う前後でラベルが毎回入れ替わる
    const swapped = frame % 2 === 0
    effect.draw(
      context,
      [
        handAt(120 + offset, 200, swapped ? 'Left' : 'Right'),
        handAt(520 - offset, 240, swapped ? 'Right' : 'Left'),
      ],
      frame * 50,
    )
  }
  assert.ok(longest(lines) < 100, `最も長い線: ${longest(lines)}`)
})

test('速い動きで点が大きく離れても、線でつなぐ', () => {
  const { context, lines } = createRecorder()
  const effect = createEffect(NEON_FADE)
  effect.draw(context, [handAt(50, 100, 'Right')], 0)
  effect.draw(context, [handAt(550, 400, 'Right')], 50)
  assert.ok(longest(lines) > 200, `最も長い線: ${longest(lines)}`)
})

test('速い動きで検出が一瞬抜けても、途切れない', () => {
  const { context, lines } = createRecorder()
  const effect = createEffect(NEON_FADE)
  effect.draw(context, [handAt(100, 100, 'Right')], 0)
  effect.draw(context, [], 100)
  effect.draw(context, [], 200)
  lines.length = 0
  effect.draw(context, [handAt(300, 100, 'Right')], 300)
  assert.ok(lines.length > 0)
})

test('片方の手だけ速く動いても、もう片方の手とは結ばない', () => {
  const { context, lines } = createRecorder()
  const effect = createEffect(NEON_FADE)
  effect.draw(context, [handAt(100, 200, 'Left'), handAt(400, 200, 'Right')], 0)
  effect.draw(context, [handAt(100, 200, 'Left'), handAt(600, 200, 'Right')], 50)
  assert.ok(longest(lines) < 150, `最も長い線: ${longest(lines)}`)
})

test('しばらく手を見失ったあとは、前の線につなげない', () => {
  const { context, lines } = createRecorder()
  const effect = createEffect(NEON_FADE)
  effect.draw(context, [handAt(100, 100, 'Right')], 0)
  effect.draw(context, [handAt(120, 100, 'Right')], 50)
  lines.length = 0
  effect.draw(context, [handAt(130, 100, 'Right')], 700)
  // 古い線は消えるまで描かれ続けるが、新しい手の位置へ向かう線は引かれない
  assert.ok(lines.every((line) => line.endX !== 130))
})

// ---- 種類と、残す・消す ----

test('どの種類も、残す・消すのどちらでも、手を動かすと何かを描き、手が無くても止まらない', () => {
  for (const choice of ALL_CHOICES) {
    const { context, lines, dots } = createRecorder()
    const effect = createEffect(choice, fixedRandom())
    for (let frame = 0; frame < 15; frame += 1) {
      effect.draw(context, [handAt(100 + frame * 20, 200, 'Right')], frame * 33)
    }
    effect.draw(context, [], 600)
    assert.ok(lines.length + dots.length > 0, `${choice.id}・${choice.mode} が何も描いていない`)
  }
})

test('「残る」は、どの種類でも時間がたっても線を描き続ける', () => {
  for (const { id } of EFFECTS) {
    const { context, lines, dots } = createRecorder()
    const effect = createEffect({ id, mode: 'persist' }, fixedRandom())
    for (let frame = 0; frame < 10; frame += 1) {
      effect.draw(context, [handAt(100 + frame * 20, 200, 'Right')], frame * 33)
    }
    lines.length = 0
    dots.length = 0
    effect.draw(context, [], 5_000)
    assert.ok(lines.length + dots.length > 0, `${id} が残っていない`)
  }
})

test('「消える」は、どの種類でも時間がたつと何も描かない', () => {
  for (const { id } of EFFECTS) {
    const { context, lines, dots } = createRecorder()
    const effect = createEffect({ id, mode: 'fade' }, fixedRandom())
    for (let frame = 0; frame < 10; frame += 1) {
      effect.draw(context, [handAt(100 + frame * 20, 200, 'Right')], frame * 33)
    }
    lines.length = 0
    dots.length = 0
    effect.draw(context, [], 5_000)
    assert.equal(lines.length + dots.length, 0, `${id} が消えていない`)
  }
})

test('「残る」で長く動かし続けても、描く量が増え続けない', () => {
  const { context, lines } = createRecorder()
  const effect = createEffect({ id: 'neon_blue', mode: 'persist' })
  const count = (frame: number) => {
    lines.length = 0
    const angle = frame * 0.2
    effect.draw(context, [handAt(300 + Math.cos(angle) * 200, 200 + Math.sin(angle) * 150, 'R')], frame * 33)
    return lines.length
  }
  for (let frame = 0; frame < 2_000; frame += 1) count(frame)
  const atLimit = count(2_000)
  for (let frame = 2_001; frame < 3_000; frame += 1) count(frame)
  assert.ok(count(3_000) <= atLimit + 8, '古い点が捨てられていない')
})

test('炎の舌は、線より上へ伸びる', () => {
  const { context, lines } = createRecorder()
  const effect = createEffect({ id: 'fire', mode: 'persist' })
  for (let frame = 0; frame < 10; frame += 1) {
    effect.draw(context, [handAt(100 + frame * 20, 300, 'Right')], frame * 33)
  }
  assert.ok(lines.some((line) => line.endY < 290))
})

test('雪は、線より下へ落ちる結晶を描く', () => {
  const { context, lines } = createRecorder()
  const effect = createEffect({ id: 'snow', mode: 'persist' })
  for (let frame = 0; frame < 20; frame += 1) {
    effect.draw(context, [handAt(100 + frame * 20, 300, 'Right')], frame * 33)
  }
  const lowest = Math.max(...lines.map((line) => line.endY))
  assert.ok(lowest > 315, `一番下: ${lowest}`)
})

test('水の波頭と、炎の舌は、左へ動いても右へ動いても上側に出る', () => {
  for (const id of ['water', 'fire'] as const) {
    for (const direction of [1, -1]) {
      const { context, lines } = createRecorder()
      const effect = createEffect({ id, mode: 'persist' })
      for (let frame = 0; frame < 25; frame += 1) {
        effect.draw(context, [handAt(320 + direction * (frame * 10 - 120), 300, 'Right')], frame * 33)
      }
      const highest = Math.min(...lines.map((line) => line.endY))
      assert.ok(highest < 280, `${id}（向き ${direction}）の一番上: ${highest}`)
    }
  }
})

// ---- 残す・消すの切り替えと、試し描き ----

/** 右へ動かしながら描き、引いた線の終わりの x を返す */
function drawRight(effect: ReturnType<typeof createEffect>, context: EffectContext, from: number, to: number) {
  for (let frame = from; frame < to; frame += 1) {
    effect.draw(context, [handAt(100 + frame * 20, 200, 'Right')], frame * 33)
  }
}

test('「残る」で描いたあとに「消える」へ変えても、残るで描いた線は残る', () => {
  const { context, lines } = createRecorder()
  const effect = createEffect({ id: 'neon_blue', mode: 'persist' })
  drawRight(effect, context, 0, 10) // x = 100〜280 を「残る」で描く
  effect.setMode('fade')
  drawRight(effect, context, 10, 20) // x = 300〜480 を「消える」で描く
  lines.length = 0
  effect.draw(context, [], 5_000)
  assert.ok(lines.length > 0, '残るで描いた線が消えた')
  assert.ok(lines.every((line) => line.endX < 300), '消えるで描いた線が残っている')
})

test('「消える」で描いたあとに「残る」へ変えると、変えたあとの線だけが残る', () => {
  const { context, lines } = createRecorder()
  const effect = createEffect({ id: 'neon_blue', mode: 'fade' })
  drawRight(effect, context, 0, 10)
  effect.setMode('persist')
  drawRight(effect, context, 10, 20)
  lines.length = 0
  effect.draw(context, [], 5_000)
  assert.ok(lines.length > 0)
  assert.ok(lines.every((line) => line.endX >= 280), '消えるで描いた線が残っている')
})

test('試し描きの間は、「残る」でも線を残さない', () => {
  const { context, lines } = createRecorder()
  const effect = createEffect({ id: 'neon_blue', mode: 'persist' }, Math.random, true)
  drawRight(effect, context, 0, 10)
  lines.length = 0
  effect.draw(context, [], 5_000)
  assert.equal(lines.length, 0)
  // 試し描きを終えると、そこから描いた線は残る
  effect.setPreview(false)
  drawRight(effect, context, 200, 210)
  lines.length = 0
  effect.draw(context, [], 20_000)
  assert.ok(lines.length > 0)
})
