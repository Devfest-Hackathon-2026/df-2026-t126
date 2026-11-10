// 生存確認（仕様書 §3-10）を一定の間隔で送る。
// 通信が遅くても送信が重ならないように、前の送信が終わるまで次は送らない。
// ただし、1回の送信が返事のないまま止まっても生存確認が途絶えないように、
// timeoutMs を過ぎたら、その送信は待たずに次を送れるようにする。
// 画面が表に戻ったときと、通信がつながり直したときは、間隔を待たずにすぐ送る。
// 送信に失敗したら（サーバーが混んで 503 など）、間隔を待たずに retryMs 後に1回だけ送り直す。
// 送り直しは、ふつうの送信1回につき最大1回。送り直しが失敗しても、次の送り直しは予約しない。
// ふつうの送信を始めるときは、残っている送り直しの予約を取り消す（古い予約を残さない）。
// 止めたあとは、新しい送信をしない（送信中のものは、そのまま終わらせる）。

export interface Timers {
  setInterval(handler: () => void, ms: number): unknown
  clearInterval(id: unknown): void
  setTimeout(handler: () => void, ms: number): unknown
  clearTimeout(id: unknown): void
}

/** 「すぐ送る」きっかけを登録し、解除する関数を返す */
export type WakeSource = (beatNow: () => void) => () => void

const browserTimers: Timers = {
  setInterval: (handler, ms) => setInterval(handler, ms),
  clearInterval: (id) => clearInterval(id as ReturnType<typeof setInterval>),
  setTimeout: (handler, ms) => setTimeout(handler, ms),
  clearTimeout: (id) => clearTimeout(id as ReturnType<typeof setTimeout>),
}

/** 画面が表に戻ったとき・通信がつながり直したとき */
const browserWake: WakeSource = (beatNow) => {
  const onVisible = () => {
    if (document.visibilityState === 'visible') beatNow()
  }
  document.addEventListener('visibilitychange', onVisible)
  window.addEventListener('online', beatNow)
  return () => {
    document.removeEventListener('visibilitychange', onVisible)
    window.removeEventListener('online', beatNow)
  }
}

export interface HeartbeatOptions {
  /** 1回の送信を待つ上限（ミリ秒）。過ぎたら次を送れるようにする */
  timeoutMs?: number
  /** 失敗したとき、次の間隔を待たずに送り直すまでの時間（ミリ秒）。0 なら送り直さない */
  retryMs?: number
  timers?: Timers
  wake?: WakeSource
}

/** すぐに1回送り、そのあと intervalMs ごとに送る。戻り値の関数で止める */
export function startHeartbeat(
  send: () => Promise<unknown>,
  intervalMs: number,
  { timeoutMs = intervalMs, retryMs = 0, timers = browserTimers, wake = browserWake }: HeartbeatOptions = {},
): () => void {
  let stopped = false
  // 送信中の回の番号。0 なら送信中ではない
  let inFlight = 0
  let count = 0
  let retry: unknown = null

  const cancelRetry = () => {
    if (retry !== null) timers.clearTimeout(retry)
    retry = null
  }

  /** isRetry: 失敗のあとの送り直しなら true（送り直しは、さらに送り直さない） */
  const beat = (isRetry = false) => {
    if (stopped || inFlight) return
    if (!isRetry) cancelRetry()
    const id = ++count
    inFlight = id
    const release = () => {
      // 待つのをあきらめたあとに古い回が終わっても、新しい回の印は消さない
      if (inFlight === id) inFlight = 0
    }
    const timer = timers.setTimeout(release, timeoutMs)
    // 失敗しても次の間隔でまた送る。途絶えたかどうかの判定はサーバーが行う
    send()
      .catch(() => {
        // 送り直しの失敗・止めたあと・もっと新しい回が始まっているときは、予約しない
        if (isRetry || retryMs <= 0 || stopped || id !== count) return
        retry = timers.setTimeout(() => {
          retry = null
          beat(true)
        }, retryMs)
      })
      .finally(() => {
        timers.clearTimeout(timer)
        release()
      })
  }

  beat()
  const id = timers.setInterval(() => beat(), intervalMs)
  const stopWake = wake(() => beat())
  return () => {
    stopped = true
    timers.clearInterval(id)
    cancelRetry()
    stopWake()
  }
}
