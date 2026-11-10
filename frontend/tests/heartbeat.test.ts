// 生存確認のテスト。npm test で実行する。

import assert from 'node:assert/strict'
import { test } from 'node:test'
import { startHeartbeat, type Timers, type WakeSource } from '../src/game/heartbeat.ts'

/**
 * 時間を手で進められる偽物のタイマー。
 * tick は間隔の1回分。expire(ms) は、その長さで予約されたものだけを起こす（省略すると全部）。
 */
function fakeTimers() {
  const handlers = new Map<number, () => void>()
  const timeouts = new Map<number, { handler: () => void; ms: number }>()
  let next = 1
  const timers: Timers = {
    setInterval(handler) {
      handlers.set(next, handler)
      return next++
    },
    clearInterval(id) {
      handlers.delete(id as number)
    },
    setTimeout(handler, ms) {
      timeouts.set(next, { handler, ms })
      return next++
    },
    clearTimeout(id) {
      timeouts.delete(id as number)
    },
  }
  const tick = () => handlers.forEach((handler) => handler())
  const expire = (ms?: number) => {
    const due = [...timeouts].filter(([, t]) => ms === undefined || t.ms === ms)
    due.forEach(([id]) => timeouts.delete(id))
    due.forEach(([, t]) => t.handler())
  }
  const scheduled = (ms: number) => [...timeouts.values()].filter((t) => t.ms === ms).length
  return { timers, tick, expire, scheduled, active: () => handlers.size }
}

/** 「すぐ送る」きっかけを手で起こせる偽物 */
function fakeWake() {
  let beatNow: (() => void) | null = null
  const wake: WakeSource = (handler) => {
    beatNow = handler
    return () => {
      beatNow = null
    }
  }
  return { wake, fire: () => beatNow?.(), registered: () => beatNow !== null }
}

/** 終わるタイミングを手で決められる送信 */
function controlledSend() {
  const pending: (() => void)[] = []
  let calls = 0
  const send = () => {
    calls += 1
    return new Promise<void>((resolve) => pending.push(resolve))
  }
  const finishAll = async () => {
    pending.splice(0).forEach((resolve) => resolve())
    await new Promise((resolve) => setImmediate(resolve))
  }
  return { send, finishAll, calls: () => calls }
}

test('始めるとすぐ1回送り、そのあと間隔ごとに送る', async () => {
  const { timers, tick } = fakeTimers()
  const { send, finishAll, calls } = controlledSend()
  startHeartbeat(send, 5_000, { timers, wake: fakeWake().wake })
  assert.equal(calls(), 1)
  await finishAll()
  tick()
  assert.equal(calls(), 2)
})

test('前の送信が終わっていなければ、次は送らない', async () => {
  const { timers, tick } = fakeTimers()
  const { send, finishAll, calls } = controlledSend()
  startHeartbeat(send, 5_000, { timers, wake: fakeWake().wake })
  tick()
  tick()
  assert.equal(calls(), 1, '送信中に重ねて送った')
  await finishAll()
  tick()
  assert.equal(calls(), 2)
})

test('止めたあとは送らず、タイマーも解除する', async () => {
  const { timers, tick, active } = fakeTimers()
  const { send, finishAll, calls } = controlledSend()
  const stop = startHeartbeat(send, 5_000, { timers, wake: fakeWake().wake })
  stop()
  assert.equal(active(), 0)
  await finishAll()
  tick()
  assert.equal(calls(), 1)
})

test('送信に失敗しても、次の間隔でまた送る', async () => {
  const { timers, tick } = fakeTimers()
  let calls = 0
  startHeartbeat(
    () => {
      calls += 1
      return Promise.reject(new Error('通信できない'))
    },
    5_000,
    { timers, wake: fakeWake().wake },
  )
  await new Promise((resolve) => setImmediate(resolve))
  tick()
  assert.equal(calls, 2)
})

test('1回の送信が返事のないまま止まっても、待つ上限を過ぎたら次を送る', async () => {
  const { timers, tick, expire } = fakeTimers()
  const { send, calls } = controlledSend()
  startHeartbeat(send, 5_000, { timeoutMs: 4_000, timers, wake: fakeWake().wake })
  tick()
  assert.equal(calls(), 1, '上限の前に重ねて送った')
  expire()
  tick()
  assert.equal(calls(), 2, '止まった送信のせいで、生存確認が途絶えた')
})

test('待つのをあきらめた古い送信が後から終わっても、新しい送信中の印は消さない', async () => {
  const { timers, tick, expire } = fakeTimers()
  const resolvers: (() => void)[] = []
  const send = () => new Promise<void>((resolve) => resolvers.push(resolve))
  startHeartbeat(send, 5_000, { timeoutMs: 4_000, timers, wake: fakeWake().wake })
  expire()
  tick()
  assert.equal(resolvers.length, 2)
  // 1回目だけが今ごろ終わる。2回目はまだ送信中
  resolvers[0]()
  await new Promise((resolve) => setImmediate(resolve))
  tick()
  assert.equal(resolvers.length, 2, '送信中なのに重ねて送った')
  resolvers[1]()
  await new Promise((resolve) => setImmediate(resolve))
  tick()
  assert.equal(resolvers.length, 3)
})

test('画面が表に戻ったら、間隔を待たずにすぐ送る。止めたら、きっかけも解除する', async () => {
  const { timers } = fakeTimers()
  const { send, finishAll, calls } = controlledSend()
  const wake = fakeWake()
  const stop = startHeartbeat(send, 5_000, { timers, wake: wake.wake })
  await finishAll()
  wake.fire()
  assert.equal(calls(), 2)
  stop()
  assert.equal(wake.registered(), false)
})

const settle = () => new Promise((resolve) => setImmediate(resolve))

test('失敗したら1.5秒後に1回だけ送り直す。送り直しも失敗したら、次の送り直しは予約しない（連続503）', async () => {
  const { timers, tick, expire, scheduled } = fakeTimers()
  let calls = 0
  const fail = () => {
    calls += 1
    return Promise.reject(new Error('503'))
  }
  startHeartbeat(fail, 5_000, { timeoutMs: 4_500, retryMs: 1_500, timers, wake: fakeWake().wake })
  await settle()
  assert.equal(scheduled(1_500), 1)
  expire(1_500) // 送り直し
  await settle()
  assert.equal(calls, 2)
  assert.equal(scheduled(1_500), 0, '送り直しの失敗で、さらに送り直しを予約した')
  tick() // 次のふつうの送信
  await settle()
  assert.equal(calls, 3)
  assert.equal(scheduled(1_500), 1, 'ふつうの送信の失敗には、送り直しを1回予約する')
})

test('送り直しの予約があるうちに、ふつうの送信が成功したら、古い予約は残らない', async () => {
  const { timers, tick, scheduled } = fakeTimers()
  let fails = 1
  let calls = 0
  const send = () => {
    calls += 1
    return fails-- > 0 ? Promise.reject(new Error('503')) : Promise.resolve()
  }
  startHeartbeat(send, 5_000, { timeoutMs: 4_500, retryMs: 1_500, timers, wake: fakeWake().wake })
  await settle()
  assert.equal(scheduled(1_500), 1)
  tick() // 送り直しより先に、ふつうの送信が来て成功する
  await settle()
  assert.equal(calls, 2)
  assert.equal(scheduled(1_500), 0, '古い送り直しの予約が残った')
})

test('画面が戻ったときの送信も、ふつうの送信として古い予約を取り消す', async () => {
  const { timers, scheduled } = fakeTimers()
  const wake = fakeWake()
  let fails = 1
  const send = () => (fails-- > 0 ? Promise.reject(new Error('503')) : Promise.resolve())
  startHeartbeat(send, 5_000, { timeoutMs: 4_500, retryMs: 1_500, timers, wake: wake.wake })
  await settle()
  assert.equal(scheduled(1_500), 1)
  wake.fire()
  await settle()
  assert.equal(scheduled(1_500), 0)
})

test('待つのをあきらめた古い回が後から失敗しても、新しい回が始まっていれば送り直しを予約しない', async () => {
  const { timers, tick, expire, scheduled } = fakeTimers()
  const rejecters: (() => void)[] = []
  const send = () => new Promise<void>((_, reject) => rejecters.push(() => reject(new Error('timeout'))))
  startHeartbeat(send, 5_000, { timeoutMs: 4_500, retryMs: 1_500, timers, wake: fakeWake().wake })
  expire(4_500) // 1回目を待つのをあきらめる
  tick() // 2回目を送る
  assert.equal(rejecters.length, 2)
  rejecters[0]() // 1回目が今ごろ失敗する
  await settle()
  assert.equal(scheduled(1_500), 0, '古い回の失敗で、送り直しを予約した')
})
