// 窓口（Backend）の本物の実装。API は fetch、公開状態は Firestore の購読で受け取る。
// 書き込みはすべて API を通す。端末は Firestore を読むだけ（仕様書 §4）。

import { initializeApp } from 'firebase/app'
import {
  browserLocalPersistence,
  connectAuthEmulator,
  inMemoryPersistence,
  initializeAuth,
  signInAnonymously,
} from 'firebase/auth'
import {
  collection,
  connectFirestoreEmulator,
  doc,
  getFirestore,
  onSnapshot,
  Timestamp,
  type FirestoreError,
} from 'firebase/firestore'
import { ApiError, type Backend } from '../backend'
import type { ApiErrorCode, PlayerDoc, RoomDoc, RoundDoc, StepDoc } from '../types'
import { emulatorConfigProblem } from './emulatorGuard'

const env = import.meta.env
const API_BASE_URL: string = env.VITE_API_BASE_URL ?? ''
const USE_EMULATOR = env.VITE_FIREBASE_EMULATOR === 'true'
/** 生存確認の1回を待つ上限。間隔（5秒）より短くして、次の回までに打ち切る */
const HEARTBEAT_TIMEOUT_MS = 4_000

/** Firestore の Timestamp を ISO 8601 の文字列にそろえる（画面は文字列だけを扱う） */
function normalize(value: unknown): unknown {
  if (value instanceof Timestamp) return value.toDate().toISOString()
  if (Array.isArray(value)) return value.map(normalize)
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, normalize(item)]))
  }
  return value
}

/** 部屋の外の人や、消えた部屋への購読は、部屋が無いものとして扱う */
function isGone(error: FirestoreError): boolean {
  return error.code === 'permission-denied' || error.code === 'not-found'
}

export function createRealBackend(): Backend {
  if (USE_EMULATOR) {
    // 本物の Firebase や API に触れる前に止める
    const problem = emulatorConfigProblem({
      projectId: env.VITE_FIREBASE_PROJECT_ID,
      apiBaseUrl: API_BASE_URL,
      pageUrl: location.href,
    })
    if (problem) throw new Error(problem)
  }
  const app = initializeApp({
    apiKey: env.VITE_FIREBASE_API_KEY,
    authDomain: env.VITE_FIREBASE_AUTH_DOMAIN,
    projectId: env.VITE_FIREBASE_PROJECT_ID,
    appId: env.VITE_FIREBASE_APP_ID,
  })
  // ?player= があるときはタブごとに別の人としてログインする（1台で3人を試すため）
  const separatePlayers = new URLSearchParams(location.search).has('player')
  const auth = initializeAuth(app, {
    persistence: separatePlayers ? inMemoryPersistence : browserLocalPersistence,
  })
  const db = getFirestore(app)
  if (USE_EMULATOR) {
    connectAuthEmulator(auth, 'http://127.0.0.1:9099', { disableWarnings: true })
    connectFirestoreEmulator(db, '127.0.0.1', 8080)
  }

  async function token(refresh = false): Promise<string> {
    const user = auth.currentUser
    if (!user) throw new ApiError('UNAUTHENTICATED', 401, 'ログインが必要です')
    return user.getIdToken(refresh)
  }

  async function toApiError(response: Response): Promise<ApiError> {
    try {
      const body = (await response.json()) as { error?: { code: ApiErrorCode; message: string } }
      if (body.error) return new ApiError(body.error.code, response.status, body.error.message)
    } catch {
      // 本文が JSON でないときは下の共通メッセージにする
    }
    return new ApiError('INTERNAL', response.status, '処理に失敗しました')
  }

  /** ID トークンを付けて API を呼ぶ。期限切れなら1回だけトークンを更新して送り直す */
  async function send(path: string, init: RequestInit = {}): Promise<Response> {
    for (const refresh of [false, true]) {
      const headers = new Headers(init.headers)
      headers.set('Authorization', `Bearer ${await token(refresh)}`)
      const response = await fetch(`${API_BASE_URL}${path}`, { ...init, headers })
      if (response.ok) return response
      if (response.status !== 401 || refresh) throw await toApiError(response)
    }
    throw new ApiError('UNAUTHENTICATED', 401, 'ログインが必要です')
  }

  async function getJson<T>(path: string): Promise<T> {
    return (await (await send(path)).json()) as T
  }

  async function postJson<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
    const init: RequestInit = { method: 'POST', signal }
    if (body !== undefined) {
      init.headers = { 'Content-Type': 'application/json' }
      init.body = JSON.stringify(body)
    }
    return (await (await send(path, init)).json()) as T
  }

  return {
    async signIn() {
      await auth.authStateReady()
      const user = auth.currentUser ?? (await signInAnonymously(auth)).user
      return user.uid
    },

    createRoom: (body) => postJson('/api/rooms', body),
    joinRoom: (body) => postJson('/api/rooms/join', body),
    selectRole: (roomId, body) => postJson(`/api/rooms/${roomId}/role`, body),
    startGame: (roomId, body) => postJson(`/api/rooms/${roomId}/start`, body),

    getMyInput: (roundId) => getJson(`/api/rounds/${roundId}/my-input`),
    submitText: (roundId, stepIndex, body) =>
      postJson(`/api/rounds/${roundId}/steps/${stepIndex}/submit`, body),

    gestureStart: (roundId, body) => postJson(`/api/rounds/${roundId}/gesture/start`, body),
    gestureBatch: (roundId, body) => postJson(`/api/rounds/${roundId}/gesture/batches`, body),
    async gestureVideo(roundId, body) {
      // Content-Type の境界はブラウザに作らせるので、ヘッダーは付けない
      const form = new FormData()
      form.append('gesture_session_id', body.gesture_session_id)
      form.append('request_id', body.request_id)
      const extension = body.file.type === 'video/mp4' ? 'mp4' : 'webm'
      form.append('file', body.file, `gesture.${extension}`)
      const response = await send(`/api/rounds/${roundId}/gesture/video`, {
        method: 'POST',
        body: form,
      })
      return response.json()
    },
    gestureFinish: (roundId, body) => postJson(`/api/rounds/${roundId}/gesture/finish`, body),

    getHistory: (roundId) => getJson(`/api/rounds/${roundId}/history`),
    getAsset: async (roundId, assetId) =>
      (await send(`/api/rounds/${roundId}/assets/${assetId}`)).blob(),
    leaveRoom: (roomId, body) => postJson(`/api/rooms/${roomId}/leave`, body),
    // 返事のないまま止まった通信を残さないよう、生存確認は4秒で打ち切る（次の回が送り直す）
    heartbeat: (roomId) =>
      postJson(`/api/rooms/${roomId}/heartbeat`, undefined, AbortSignal.timeout(HEARTBEAT_TIMEOUT_MS)),

    subscribeRoom: (roomId, onChange, onError) =>
      onSnapshot(
        doc(db, 'rooms', roomId),
        (snapshot) => onChange(snapshot.exists() ? (normalize(snapshot.data()) as RoomDoc) : null),
        (error) => (isGone(error) ? onChange(null) : onError?.(error)),
      ),
    subscribePlayers: (roomId, onChange, onError) =>
      onSnapshot(
        collection(db, 'rooms', roomId, 'players'),
        (snapshot) =>
          onChange(
            Object.fromEntries(
              snapshot.docs.map((item) => [item.id, normalize(item.data()) as PlayerDoc]),
            ),
          ),
        // 部屋の外になったときは、部屋の購読が onChange(null) で知らせるので、ここでは何もしない
        (error) => {
          if (!isGone(error)) onError?.(error)
        },
      ),
    subscribeRound: (roomId, roundId, onChange, onError) =>
      onSnapshot(
        doc(db, 'rooms', roomId, 'rounds', roundId),
        (snapshot) => onChange(snapshot.exists() ? (normalize(snapshot.data()) as RoundDoc) : null),
        (error) => (isGone(error) ? onChange(null) : onError?.(error)),
      ),
    subscribeSteps: (roomId, roundId, onChange, onError) =>
      onSnapshot(
        collection(db, 'rooms', roomId, 'rounds', roundId, 'steps'),
        (snapshot) =>
          onChange(
            snapshot.docs
              .map((item) => normalize(item.data()) as StepDoc)
              .sort((a, b) => a.step_index - b.step_index),
          ),
        (error) => {
          if (!isGone(error)) onError?.(error)
        },
      ),
  }
}
