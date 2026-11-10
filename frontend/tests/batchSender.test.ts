// 人Bの座標の送信のテスト。npm test で実行する。

import assert from 'node:assert/strict'
import { test } from 'node:test'
import type { GestureBatch, Sample } from '../src/api/types.ts'
import {
  MAX_BATCH_BYTES,
  pythonFloat,
  serverBytes,
  startBatchSender,
  takeBatch,
  type SenderTimers,
} from '../src/gesture/batchSender.ts'

const API_LIMIT_BYTES = 250_000

/** 両手が映っている座標（小数の桁が多い、いちばん大きくなる形） */
function twoHandSample(timestamp: number): Sample {
  const hand = (handedness: 'Left' | 'Right') => ({
    handedness,
    landmarks: Array.from({ length: 21 }, (_, i) => ({
      x: 0.123456789012345 + i / 1000,
      y: 0.987654321098765 - i / 1000,
      z: -0.0123456789012345 * i,
    })),
  })
  return { timestamp_ms: timestamp, hands: [hand('Left'), hand('Right')] }
}

/** 手で進められる偽物のタイマー。sleep は wake() で終わらせる */
function fakeTimers() {
  const intervals = new Map<number, { handler: () => void; ms: number }>()
  const sleepers: (() => void)[] = []
  let next = 1
  const timers: SenderTimers = {
    setInterval(handler, ms) {
      intervals.set(next, { handler, ms })
      return next++
    },
    clearInterval(id) {
      intervals.delete(id as number)
    },
    sleep: () => new Promise<void>((resolve) => sleepers.push(resolve)),
  }
  const run = (ms: number, times = 1) => {
    for (let i = 0; i < times; i += 1) intervals.forEach((t) => t.ms === ms && t.handler())
  }
  const wakeAll = () => sleepers.splice(0).forEach((resolve) => resolve())
  return { timers, run, wakeAll }
}

const settle = () => new Promise((resolve) => setImmediate(resolve))

test('両手・30秒分（300件）たまっても、各送信は API の上限 250,000 バイトに収まるよう分ける', () => {
  const pending = Array.from({ length: 300 }, (_, i) => twoHandSample(i * 100))
  const base = { gesture_session_id: 'gs_1', sequence_number: 0, mirrored: true }
  const batches: GestureBatch[] = []
  while (pending.length > 0) batches.push(takeBatch(pending, { ...base, sequence_number: batches.length }))
  assert.ok(batches.length > 1, '分けられていない')
  assert.equal(batches.reduce((n, b) => n + b.samples.length, 0), 300, '座標が欠けた')
  for (const batch of batches) {
    const size = serverBytes(batch)
    assert.ok(size <= MAX_BATCH_BYTES, `上限を超えた: ${size}`)
    assert.ok(size <= API_LIMIT_BYTES)
  }
})

test('送信が遅いあいだは座標をためて、終わってから上限内に分けて順に送る（同時には1つだけ）', async () => {
  const { timers, run } = fakeTimers()
  const sent: GestureBatch[] = []
  const finishers: (() => void)[] = []
  let concurrent = 0
  let maxConcurrent = 0
  startBatchSender({
    sessionId: 'gs_1',
    mirrored: false,
    read: (t) => twoHandSample(t),
    send: (batch) => {
      sent.push(batch)
      concurrent += 1
      maxConcurrent = Math.max(maxConcurrent, concurrent)
      return new Promise<void>((resolve) =>
        finishers.push(() => {
          concurrent -= 1
          resolve()
        }),
      )
    },
    sampleMs: 100,
    batchMs: 1_000,
    waitMs: 1_000,
    timers,
    now: () => 0,
  })
  run(100, 10)
  run(1_000) // 1つ目を送る。返事は来ない
  run(100, 300) // 30秒分ためる
  run(1_000, 30) // 送信中なので、次は送らない
  assert.equal(sent.length, 1)
  // 返事が来るたびに、たまった分を上限内で続けて送る
  for (let i = 0; i < 10 && finishers.length > 0; i += 1) {
    finishers.shift()?.()
    await settle()
  }
  assert.equal(maxConcurrent, 1, '同時に2つ以上送った')
  assert.equal(sent.reduce((n, b) => n + b.samples.length, 0), 310, '座標が欠けた')
  assert.deepEqual(
    sent.map((b) => b.sequence_number),
    sent.map((_, i) => i),
  )
  for (const batch of sent) assert.ok(serverBytes(batch) <= API_LIMIT_BYTES)
})

test('止めたあと、座標の送信が返らなくても、待つ上限で終わる（録画の送信へ進める）', async () => {
  const { timers, run, wakeAll } = fakeTimers()
  const stop = startBatchSender({
    sessionId: 'gs_1',
    mirrored: false,
    read: (t) => twoHandSample(t),
    send: () => new Promise<void>(() => undefined), // 返事が来ない
    sampleMs: 100,
    batchMs: 1_000,
    waitMs: 1_000,
    timers,
    now: () => 0,
  })
  run(100, 10)
  run(1_000)
  let done = false
  const stopping = stop().then(() => {
    done = true
  })
  await settle()
  assert.equal(done, false, '上限の前に終わった')
  wakeAll() // 待つ上限（1秒）が来た
  await stopping
  assert.equal(done, true)
})

test('止めたあと、遅い送信が上限のあとに終わっても、残りの座標は送らない（録画の送信と取り合わない）', async () => {
  const { timers, run, wakeAll } = fakeTimers()
  const sent: GestureBatch[] = []
  const finishers: (() => void)[] = []
  const stop = startBatchSender({
    sessionId: 'gs_1',
    mirrored: false,
    read: (t) => twoHandSample(t),
    send: (batch) => {
      sent.push(batch)
      return new Promise<void>((resolve) => finishers.push(resolve))
    },
    sampleMs: 100,
    batchMs: 1_000,
    waitMs: 1_000,
    timers,
    now: () => 0,
  })
  run(100, 10)
  run(1_000) // 1つ目を送る（遅い）
  run(100, 5) // 残りがたまる
  const stopping = stop()
  wakeAll() // 上限が来た
  await stopping
  finishers.shift()?.() // 1つ目が今ごろ終わる
  await settle()
  assert.equal(sent.length, 1, '上限のあとに、残りを送った')
})

test('止めたあと、送信が早く終われば、残りを送り切ってから終わる', async () => {
  const { timers, run } = fakeTimers()
  const sent: GestureBatch[] = []
  const stop = startBatchSender({
    sessionId: 'gs_1',
    mirrored: false,
    read: (t) => twoHandSample(t),
    send: async (batch) => {
      sent.push(batch)
    },
    sampleMs: 100,
    batchMs: 1_000,
    waitMs: 1_000,
    timers,
    now: () => 0,
  })
  run(100, 10)
  run(1_000)
  run(100, 5)
  await stop()
  assert.equal(sent.reduce((n, b) => n + b.samples.length, 0), 15)
})

test('数の書き方を、Python の repr(float(v)) と同じにする（API の大きさの測り方）', () => {
  // python3 -c "print(repr(float(v)))" で確かめた値
  const cases: [number, string][] = [
    [0, '0.0'],
    [1, '1.0'],
    [-0, '-0.0'],
    [0.5, '0.5'],
    [0.123456789012345, '0.123456789012345'],
    [1e-7, '1e-07'],
    [1.5e-7, '1.5e-07'],
    [0.00001, '1e-05'],
    [0.0001, '0.0001'],
    [0.001, '0.001'],
    [123456789, '123456789.0'],
    [1e16, '1e+16'],
    [1.2345e16, '1.2345e+16'],
    [1e21, '1e+21'],
    [-3, '-3.0'],
    [2.5e-5, '2.5e-05'],
    [0.1 + 0.2, '0.30000000000000004'],
    [1 / 3, '0.3333333333333333'],
  ]
  for (const [v, expected] of cases) assert.equal(pythonFloat(v), expected, `${v}`)
})

test('座標が整数（0 や 1）ばかりでも、API が測る大きさで 250,000 バイト以内に分ける', () => {
  const integerSample = (t: number): Sample => {
    const hand = (handedness: 'Left' | 'Right') => ({
      handedness,
      landmarks: Array.from({ length: 21 }, (_, i) => ({ x: i % 2, y: 0, z: 0 })),
    })
    return { timestamp_ms: t, hands: [hand('Left'), hand('Right')] }
  }
  const pending = Array.from({ length: 1000 }, (_, i) => integerSample(i * 33))
  const base = { gesture_session_id: 'gs_1', sequence_number: 0, mirrored: false }
  const batches: GestureBatch[] = []
  while (pending.length > 0) batches.push(takeBatch(pending, { ...base, sequence_number: batches.length }))
  assert.equal(batches.reduce((n, b) => n + b.samples.length, 0), 1000)
  for (const batch of batches) {
    const sent = new TextEncoder().encode(JSON.stringify(batch)).length
    const measured = serverBytes(batch)
    assert.ok(measured > sent, 'API の数え方（0 → 0.0）のほうが大きくなるはず')
    assert.ok(measured <= MAX_BATCH_BYTES, `上限を超えた: ${measured}`)
  }
})

test('録画中に2回再読み込みしても、座標の番号と時刻は続きから始まる', async () => {
  const recordStartMs = 10_000
  let now = recordStartMs
  let saved = 0
  const sent: GestureBatch[] = []

  const run = async () => {
    const { timers, run: tick } = fakeTimers()
    startBatchSender({
      sessionId: 'gs_1',
      mirrored: false,
      read: (t) => twoHandSample(t),
      send: async (batch) => {
        sent.push(batch)
      },
      sampleMs: 100,
      batchMs: 1_000,
      waitMs: 1_000,
      firstSequence: saved,
      onSequence: (next) => {
        saved = next
      },
      timers,
      now: () => now,
      recordStartMs,
    })
    for (let i = 0; i < 10; i += 1) {
      now += 100
      tick(100)
    }
    tick(1_000)
    await settle()
    // ページの再読み込みと再開の間は座標を取らない。
    now += 1_000
  }

  await run()
  await run()
  await run()
  assert.deepEqual(sent.map((batch) => batch.sequence_number), [0, 1, 2])
  assert.deepEqual(
    sent.map((batch) => batch.samples.map((sample) => sample.timestamp_ms)),
    [0, 2_000, 4_000].map((offset) => Array.from({ length: 10 }, (_, i) => offset + (i + 1) * 100)),
  )
})
