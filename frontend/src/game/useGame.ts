// サーバーの公開状態を購読して、画面に渡す。画面の切り替えはこの状態だけを根拠にする。

import { useCallback, useEffect, useState } from 'react'
import { backend } from '../api'
import type { PlayerDoc, RoomDoc, RoundDoc, StepDoc } from '../api/types'
import { prepareCapture, releaseCapture } from '../gesture/capture'
import { useWakeLock } from '../lib/hooks'
import { startHeartbeat } from './heartbeat'

const HEARTBEAT_MS = 5_000 // 仕様書 §3-10 の案
// 1回の送信が止まっても、次の回を送れるようにする上限（本物のサーバーは4秒で通信を打ち切る）
const HEARTBEAT_TIMEOUT_MS = 4_500
// 失敗したとき（サーバーが混んで 503 など）、次の間隔を待たずに送り直すまでの時間
const HEARTBEAT_RETRY_MS = 1_500
const GESTURE_STEP_INDEX = 2

const roomKey = (uid: string) => `gesture-relay.room.${uid}`

/** 続けられない問題。signin はログインの失敗、connection は購読（サーバーとの接続）の失敗 */
export type GameProblem = 'signin' | 'connection'

export interface GameState {
  problem: GameProblem | null
  uid: string | null
  roomId: string | null
  room: RoomDoc | null
  players: Record<string, PlayerDoc>
  roundId: string | null
  round: RoundDoc | null
  steps: StepDoc[]
}

export type View =
  | 'problem'
  | 'loading'
  | 'entry'
  | 'lobby'
  | 'waiting'
  | 'text'
  | 'gesture'
  | 'result'
  | 'returned'

export function deriveView(game: GameState): View {
  const { problem, uid, roomId, room, players, round, steps } = game
  if (problem) return 'problem'
  if (!uid) return 'loading'
  if (!roomId) return 'entry'
  const me = players[uid]
  if (!room || !me) return 'loading'
  if (me.phase === 'returned') return 'returned'
  if (room.status === 'waiting') return 'lobby'
  if (!round || steps.length === 0) return 'loading'
  if (room.status === 'finished' || room.status === 'failed') return 'result'
  const step = steps[round.current_step_index]
  if (step?.status === 'active' && step.player_id === uid) {
    return step.type === 'gesture' ? 'gesture' : 'text'
  }
  return 'waiting'
}

export type CameraStatus = 'idle' | 'preparing' | 'ready' | 'failed'

/** カメラの許可と MediaPipe の読み込みを、人Bの段が始まる前に済ませる */
function useCameraWarmup(enabled: boolean) {
  const [outcome, setOutcome] = useState<'ready' | 'failed' | null>(null)
  const [attempt, setAttempt] = useState(0)

  useEffect(() => {
    if (!enabled) {
      releaseCapture()
      return
    }
    let alive = true
    prepareCapture()
      .then(() => {
        if (alive) setOutcome('ready')
      })
      .catch(() => {
        if (alive) setOutcome('failed')
      })
    return () => {
      alive = false
      setOutcome(null)
    }
  }, [enabled, attempt])

  const status: CameraStatus = enabled ? (outcome ?? 'preparing') : 'idle'
  return { status, retry: () => setAttempt((value) => value + 1) }
}

export function useGame() {
  const [uid, setUid] = useState<string | null>(null)
  const [roomId, setRoomId] = useState<string | null>(null)
  const [room, setRoom] = useState<RoomDoc | null>(null)
  const [players, setPlayers] = useState<Record<string, PlayerDoc>>({})
  const [round, setRound] = useState<RoundDoc | null>(null)
  const [steps, setSteps] = useState<StepDoc[]>([])

  const [problem, setProblem] = useState<GameProblem | null>(null)
  // 購読の失敗は、どの購読でも同じ画面にする。Firestore は失敗した購読を再開しないため
  const onSubscribeError = useCallback(() => setProblem('connection'), [])

  useEffect(() => {
    let alive = true
    backend
      .signIn()
      .then((id) => {
        if (!alive) return
        setUid(id)
        setRoomId(localStorage.getItem(roomKey(id)))
      })
      .catch(() => {
        if (alive) setProblem('signin')
      })
    return () => {
      alive = false
    }
  }, [])

  const enterRoom = useCallback(
    (id: string | null) => {
      if (uid) {
        if (id) localStorage.setItem(roomKey(uid), id)
        else localStorage.removeItem(roomKey(uid))
      }
      setRoomId(id)
    },
    [uid],
  )

  useEffect(() => {
    if (!roomId) return
    const stopRoom = backend.subscribeRoom(
      roomId,
      (doc) => {
        if (doc) setRoom(doc)
        else enterRoom(null) // 部屋が消えていたら入室前に戻る
      },
      onSubscribeError,
    )
    const stopPlayers = backend.subscribePlayers(roomId, setPlayers, onSubscribeError)
    return () => {
      stopRoom()
      stopPlayers()
      setRoom(null)
      setPlayers({})
    }
  }, [roomId, enterRoom, onSubscribeError])

  const roundId = room?.current_round_id ?? null
  useEffect(() => {
    if (!roomId || !roundId) return
    const stopRound = backend.subscribeRound(roomId, roundId, setRound, onSubscribeError)
    const stopSteps = backend.subscribeSteps(roomId, roundId, setSteps, onSubscribeError)
    return () => {
      stopRound()
      stopSteps()
      setRound(null)
      setSteps([])
    }
  }, [roomId, roundId, onSubscribeError])

  const playing = room?.status === 'playing'
  useEffect(() => {
    if (!roomId || !playing) return
    return startHeartbeat(() => backend.heartbeat(roomId), HEARTBEAT_MS, {
      timeoutMs: HEARTBEAT_TIMEOUT_MS,
      retryMs: HEARTBEAT_RETRY_MS,
    })
  }, [roomId, playing])
  // ロビーで待っている間も画面が消えないようにする（消えたまま始まると、すぐ退出あつかいになる）
  useWakeLock(roomId !== null && (room?.status === 'waiting' || playing))

  const isGesturePlayer = uid !== null && players[uid]?.role === 'B'
  const beforeGesture =
    room?.status === 'waiting' ||
    (playing && (round?.current_step_index ?? 0) <= GESTURE_STEP_INDEX)
  const camera = useCameraWarmup(isGesturePlayer && beforeGesture)

  const state: GameState = { problem, uid, roomId, room, players, roundId, round, steps }
  return { state, enterRoom, camera }
}
