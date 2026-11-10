// 窓口（Backend）のモック実装。画面からは本物と同じように使える。

import { ApiError, type Backend, type Unsubscribe } from '../backend'
import type { FailReason } from '../types'
import { deleteBlob, getBlob, putBlob } from './blobStore'
import * as server from './server'

const LATENCY_MS = 120
const CHANNEL = 'gesture-relay.mock'
const UID_KEY = 'gesture-relay.mock.uid'

export interface MockBackend extends Backend {
  devFail(roomId: string, reason: FailReason): void
  devFailGestureAi(roomId: string): void
  devReset(): void
}

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms))
}

/** ?player=a があれば固定の ID、なければタブごとの ID を使う */
function resolveUid(): string {
  const player = new URLSearchParams(location.search).get('player')
  if (player) return `mock-${player}`
  const saved = sessionStorage.getItem(UID_KEY)
  if (saved) return saved
  const created = `mock-${crypto.randomUUID().slice(0, 8)}`
  sessionStorage.setItem(UID_KEY, created)
  return created
}

/** 開始時の秒数。?text_seconds=8 のように URL で上書きして、締切の動作を短時間で試せる */
function readConfig(): server.GameConfig {
  const params = new URLSearchParams(location.search)
  const read = (key: string, fallback: number) => Number(params.get(key)) || fallback
  return {
    text_seconds: read('text_seconds', 60),
    countdown_seconds: read('countdown_seconds', 15),
    record_seconds: read('record_seconds', 8),
    gesture_read_ms: read('gesture_read_ms', 4_000),
  }
}

function placeholderImage(label: string): Blob {
  const safe = label.replace(/[&<>"]/g, (c) => `&#${c.charCodeAt(0)};`).slice(0, 40)
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512">
  <rect width="512" height="512" fill="#dbeafe"/>
  <circle cx="256" cy="210" r="90" fill="#60a5fa"/>
  <text x="256" y="400" font-size="22" text-anchor="middle" fill="#1e3a8a">${safe}</text>
</svg>`
  return new Blob([svg], { type: 'image/svg+xml' })
}

export function createMockBackend(): MockBackend {
  const uid = resolveUid()
  const listeners = new Set<() => void>()
  const channel = new BroadcastChannel(CHANNEL)
  const notify = () => listeners.forEach((listener) => listener())
  channel.onmessage = notify

  function transact<T>(work: (s: server.MockState) => T): T {
    const state = server.loadState()
    const before = JSON.stringify(state)
    const result = work(state)
    if (JSON.stringify(state) !== before) {
      server.saveState(state)
      channel.postMessage('changed')
      notify()
    }
    return result
  }

  async function call<T>(work: (s: server.MockState) => T): Promise<T> {
    await delay(LATENCY_MS)
    return transact(work)
  }

  setInterval(() => transact(server.tick), 500)

  function watch<T>(read: (s: server.MockState) => T, onChange: (value: T) => void): Unsubscribe {
    let last: string | undefined
    const check = () => {
      const value = read(server.loadState())
      const next = JSON.stringify(value)
      if (next !== last) {
        last = next
        onChange(value)
      }
    }
    listeners.add(check)
    queueMicrotask(check)
    return () => listeners.delete(check)
  }

  return {
    signIn: async () => uid,

    createRoom: (body) =>
      call((s) =>
        server.command(s, uid, 'create', body.request_id, body, () =>
          server.createRoom(s, uid, body.name, body.consented),
        ),
      ),
    joinRoom: (body) =>
      call((s) =>
        server.command(s, uid, 'join', body.request_id, body, () =>
          server.joinRoom(s, uid, body.join_code, body.name, body.consented),
        ),
      ),
    selectRole: (roomId, body) =>
      call((s) =>
        server.command(s, uid, `role/${roomId}`, body.request_id, body, () =>
          server.selectRole(s, uid, roomId, body.role),
        ),
      ),
    startGame: (roomId, body) =>
      call((s) =>
        server.command(s, uid, `start/${roomId}`, body.request_id, body, () =>
          server.startGame(s, uid, roomId, readConfig()),
        ),
      ),

    getMyInput: (roundId) => call((s) => server.myInput(s, uid, roundId)),
    submitText: (roundId, stepIndex, body) =>
      call((s) =>
        server.command(s, uid, `submit/${roundId}/${stepIndex}`, body.request_id, body, () =>
          server.submitText(s, uid, roundId, stepIndex, body.text, body.is_auto),
        ),
      ),

    gestureStart: (roundId, body) =>
      call((s) =>
        server.command(s, uid, `gesture/start/${roundId}`, body.request_id, body, () =>
          server.gestureStart(s, uid, roundId),
        ),
      ),
    gestureBatch: (roundId, body) =>
      call((s) => server.gestureBatch(s, uid, roundId, body.gesture_session_id)),
    gestureVideo: async (roundId, body) => {
      await delay(LATENCY_MS)
      const contentType = body.file.type
      transact((s) =>
        server.checkVideoUpload(s, uid, roundId, body.gesture_session_id, contentType),
      )
      const assetId = crypto.randomUUID().replaceAll('-', '')
      await putBlob(assetId, body.file)
      return transact((s) =>
        server.commitVideo(s, uid, roundId, body.gesture_session_id, assetId, contentType),
      )
    },
    gestureFinish: (roundId, body) =>
      call((s) =>
        server.command(s, uid, `gesture/finish/${roundId}`, body.request_id, body, () =>
          server.gestureFinish(s, uid, roundId, body.gesture_session_id),
        ),
      ),

    getHistory: (roundId) => call((s) => server.history(s, uid, roundId)),
    getAsset: async (roundId, assetId) => {
      const asset = await call((s) => server.readableAsset(s, uid, roundId, assetId))
      if (asset.kind === 'image') return placeholderImage(asset.label)
      const blob = await getBlob(assetId)
      if (!blob) throw new ApiError('ASSET_NOT_FOUND', 404, '素材が見つかりません')
      return blob
    },
    leaveRoom: async (roomId, body) => {
      const { response, removed } = await call((s) =>
        server.command(s, uid, `leave/${roomId}`, body.request_id, body, () =>
          server.leaveRoom(s, uid, roomId),
        ),
      )
      await Promise.all(removed.map(deleteBlob))
      return response
    },
    heartbeat: (roomId) => call((s) => server.heartbeat(s, uid, roomId)),

    subscribeRoom: (roomId, onChange) => watch((s) => s.rooms[roomId] ?? null, onChange),
    subscribePlayers: (roomId, onChange) => watch((s) => s.players[roomId] ?? {}, onChange),
    subscribeRound: (_roomId, roundId, onChange) =>
      watch((s) => s.rounds[roundId]?.doc ?? null, onChange),
    subscribeSteps: (_roomId, roundId, onChange) =>
      watch((s) => s.rounds[roundId]?.steps ?? [], onChange),

    devFail: (roomId, reason) => transact((s) => server.devFail(s, roomId, reason)),
    devFailGestureAi: (roomId) => transact((s) => server.devFailGestureAi(s, roomId)),
    devReset: () => {
      server.resetState()
      channel.postMessage('changed')
      notify()
    },
  }
}
