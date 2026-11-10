import { ApiError } from '../api/backend'

const ATTEMPTS = 3 // 仕様書 §8 の案

export function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

export function sleepUntil(timeMs: number): Promise<void> {
  return sleep(Math.max(0, timeMs - Date.now()))
}

/**
 * 通信の失敗とサーバーの 500 番台だけ再送する。
 * 400 番台は再送しても結果が変わらないので、すぐ呼び出し元へ返す。
 * fn は毎回同じ request_id と同じ中身で送ること。
 */
export async function withRetry<T>(fn: () => Promise<T>): Promise<T> {
  for (let attempt = 1; ; attempt += 1) {
    try {
      return await fn()
    } catch (error) {
      const clientError = error instanceof ApiError && error.status < 500
      if (clientError || attempt >= ATTEMPTS) throw error
      await sleep(500 * attempt)
    }
  }
}

export function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : '通信に失敗しました'
}
