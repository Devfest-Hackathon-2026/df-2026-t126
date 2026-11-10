// 人Bの手の座標を一定の間隔で読み、まとめてサーバーへ送る。
// - サーバーが同時に受けられる数が少ない（混むと 503）ので、送信は1つずつにする。
//   前の送信が終わっていなければ、座標をためておき、終わってから次のまとまりとして送る。
// - 1回に送る大きさは、API の上限（gesture_batch_max_bytes = 250,000 バイト）より小さく切る。
//   ためた座標が多いときは、いくつかのまとまりに分けて、順に送る。
// - 録画の終了後は、座標の送信を waitMs までしか待たない。録画のアップロードと終了通知に
//   受付時間（締切＋猶予）を残すため。座標は途中までで構わない（サーバーもそう扱う）。

import type { GestureBatch, Sample } from '../api/types'

/** 1回の送信の大きさの上限（バイト）。API の上限 250,000 に余裕を持たせる */
export const MAX_BATCH_BYTES = 200_000

/**
 * 数を、Python の repr(float(v)) と同じ書き方にする。
 * API は座標を float に直してから json.dumps で大きさを測るので（0 → 0.0、1e-7 → 1e-07 など）、
 * 送るときの JSON（JavaScript の書き方）より大きくなることがある。
 */
export function pythonFloat(v: number): string {
  if (Object.is(v, -0)) return '-0.0'
  // 最短で元に戻せる桁（JavaScript も Python も同じ桁を選ぶ）
  const [mantissa, expText] = v.toExponential().split('e')
  const exp = Number(expText)
  const negative = mantissa.startsWith('-')
  const digits = mantissa.replace('-', '').replace('.', '')
  let body: string
  if (exp < -4 || exp >= 16) {
    // 指数の書き方。Python は指数を2桁以上で書く
    const head = digits.length > 1 ? `${digits[0]}.${digits.slice(1)}` : digits
    const e = Math.abs(exp).toString().padStart(2, '0')
    body = `${head}e${exp < 0 ? '-' : '+'}${e}`
  } else if (exp < 0) {
    body = `0.${'0'.repeat(-exp - 1)}${digits}`
  } else if (digits.length <= exp + 1) {
    body = `${digits}${'0'.repeat(exp + 1 - digits.length)}.0`
  } else {
    body = `${digits.slice(0, exp + 1)}.${digits.slice(exp + 1)}`
  }
  return negative ? `-${body}` : body
}

const encoder = new TextEncoder()

/** 座標1つを、API が測るときと同じ大きさ（バイト）で数える */
function sampleBytes(sample: Sample): number {
  let size = encoder.encode(JSON.stringify(sample)).length
  for (const hand of sample.hands) {
    for (const point of hand.landmarks) {
      for (const v of [point.x, point.y, point.z]) size += pythonFloat(v).length - JSON.stringify(v).length
    }
  }
  return size
}

/** まとまり全体を、API が測るときと同じ大きさ（バイト）で数える */
export function serverBytes(batch: GestureBatch): number {
  const empty = encoder.encode(JSON.stringify({ ...batch, samples: [] })).length
  return empty + batch.samples.reduce((n, s, i) => n + sampleBytes(s) + (i > 0 ? 1 : 0), 0)
}

/**
 * ためた座標の先頭から、1回で送れるだけ取り出す。
 * 1つの座標だけで上限を超えることはない（両手でも数 KB）が、念のため最低1つは取り出す。
 */
export function takeBatch(
  pending: Sample[],
  base: Omit<GestureBatch, 'samples'>,
  maxBytes = MAX_BATCH_BYTES,
): GestureBatch {
  // API が測るときと同じ数え方で、空の samples の分と、座標どうしの区切りの「,」の分を足して数える
  let size = serverBytes({ ...base, samples: [] })
  let count = 0
  while (count < pending.length) {
    const next = sampleBytes(pending[count]) + (count > 0 ? 1 : 0)
    if (count > 0 && size + next > maxBytes) break
    size += next
    count += 1
  }
  return { ...base, samples: pending.splice(0, count) }
}

export interface SenderTimers {
  setInterval(handler: () => void, ms: number): unknown
  clearInterval(id: unknown): void
  /** ms 後に終わる Promise */
  sleep(ms: number): Promise<void>
}

const browserTimers: SenderTimers = {
  setInterval: (handler, ms) => setInterval(handler, ms),
  clearInterval: (id) => clearInterval(id as ReturnType<typeof setInterval>),
  sleep: (ms) => new Promise((resolve) => setTimeout(resolve, ms)),
}

export interface SenderOptions {
  sessionId: string
  mirrored: boolean
  /** 座標を1つ読む（録画開始からの経過ミリ秒を渡す） */
  read: (timestampMs: number) => Sample
  /** 1つのまとまりを送る（再送はこの中で行う） */
  send: (batch: GestureBatch) => Promise<unknown>
  sampleMs: number
  batchMs: number
  /** 止めたあと、残りの座標の送信を待つ上限（ミリ秒） */
  waitMs: number
  maxBytes?: number
  /** 最初のまとまりの番号（再読み込みのあとは、前の番号と重ならないようにする） */
  firstSequence?: number
  /** 番号を1つ使うたびに、次の番号を知らせる（再読み込みしても続きの番号から送るため） */
  onSequence?: (next: number) => void
  timers?: SenderTimers
  now?: () => number
  /** 再読み込み前後で共通の録画開始時刻（Unix時刻のミリ秒） */
  recordStartMs?: number
}

/** 送り始める。戻り値の関数で止める（残りを送るが、waitMs を過ぎたら待たずに終わる） */
export function startBatchSender({
  sessionId,
  mirrored,
  read,
  send,
  sampleMs,
  batchMs,
  waitMs,
  maxBytes = MAX_BATCH_BYTES,
  firstSequence = 0,
  onSequence = () => undefined,
  timers = browserTimers,
  now = Date.now,
  recordStartMs = now(),
}: SenderOptions): () => Promise<void> {
  const pending: Sample[] = []
  let sequence = firstSequence
  let stopped = false
  // 今の送信（終わるまで次を送らない）
  let inFlight: Promise<void> | null = null

  const flush = () => {
    if (inFlight || pending.length === 0) return
    const batch = takeBatch(pending, { gesture_session_id: sessionId, sequence_number: sequence, mirrored }, maxBytes)
    sequence += 1
    onSequence(sequence)
    // 座標は途中までで構わないので、失敗しても次へ進む
    inFlight = send(batch)
      .catch(() => undefined)
      .then(() => {
        inFlight = null
        // 上限で分けた残りがあれば、続けて送る（止めたあとは、止める側が送る）
        if (!stopped && pending.length > 0) flush()
      })
  }

  const sampling = timers.setInterval(
    () => pending.push(read(Math.max(0, now() - recordStartMs))),
    sampleMs,
  )
  const batching = timers.setInterval(flush, batchMs)

  return async () => {
    stopped = true
    timers.clearInterval(sampling)
    timers.clearInterval(batching)
    let gaveUp = false
    const drain = async () => {
      // あきらめたあとは、新しいまとまりを送らない（録画の送信と取り合わないため）
      while (!gaveUp && (inFlight || pending.length > 0)) {
        if (inFlight) await inFlight
        else flush()
      }
    }
    // 残りを送り切るか、waitMs を過ぎるか、早いほうで終わる
    await Promise.race([
      drain(),
      timers.sleep(waitMs).then(() => {
        gaveUp = true
      }),
    ])
  }
}
