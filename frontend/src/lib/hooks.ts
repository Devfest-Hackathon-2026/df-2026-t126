import { useEffect, useState } from 'react'
import { backend } from '../api'

/** 締切までの残り秒数を返す。締切がなければ null */
export function useSecondsLeft(deadlineIso: string | null | undefined): number | null {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 250)
    return () => clearInterval(timer)
  }, [])
  if (!deadlineIso) return null
  return Math.max(0, Math.ceil((Date.parse(deadlineIso) - now) / 1000))
}

/** 素材を取得して、<img> や <video> に渡せる URL を返す */
export function useAssetUrl(roundId: string, assetId: string | null | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null)
  useEffect(() => {
    if (!assetId) return
    let alive = true
    let created: string | null = null
    backend
      .getAsset(roundId, assetId)
      .then((blob) => {
        if (!alive) return
        created = URL.createObjectURL(blob)
        setUrl(created)
      })
      .catch(() => {
        if (alive) setUrl(null)
      })
    return () => {
      alive = false
      if (created) URL.revokeObjectURL(created)
    }
  }, [roundId, assetId])
  return url
}

/**
 * 部屋にいる間、画面が消えないようにする。対応していない端末では何もしない。
 * 画面が消えたり裏に回ったりすると、ページの動きが止まって生存確認が途絶え、退出あつかいになるため。
 * 端末が勝手に解除したとき・画面が表に戻ったとき・画面を触ったときに、取り直す
 * （Safari などは、画面を触った直後でないと取れないことがあるため）。
 */
export function useWakeLock(enabled: boolean): void {
  useEffect(() => {
    if (!enabled || !('wakeLock' in navigator)) return
    let lock: WakeLockSentinel | null = null
    let requesting = false
    let alive = true
    const acquire = () => {
      if (!alive || requesting || (lock && !lock.released)) return
      if (document.visibilityState !== 'visible') return
      requesting = true
      navigator.wakeLock
        .request('screen')
        .then((sentinel) => {
          if (!alive) {
            void sentinel.release()
            return
          }
          lock = sentinel
          // 端末が解除したら（省電力など）、表に出ているうちに取り直す
          sentinel.addEventListener('release', () => {
            if (lock === sentinel) lock = null
            acquire()
          })
        })
        .catch(() => undefined)
        .finally(() => {
          requesting = false
        })
    }
    acquire()
    document.addEventListener('visibilitychange', acquire)
    window.addEventListener('pointerdown', acquire)
    return () => {
      alive = false
      document.removeEventListener('visibilitychange', acquire)
      window.removeEventListener('pointerdown', acquire)
      void lock?.release()
    }
  }, [enabled])
}
