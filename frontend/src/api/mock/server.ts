// 偽物のサーバー。origin/codex/backend-a の backend_a/game.py と同じルールで動く。
// 状態は localStorage に置くので、同じブラウザのタブやフレームの間で共有される。

import { ApiError } from '../backend'
import { MOCK_ODAI } from './odai'
import type {
  ApiErrorCode,
  FailReason,
  HistoryResponse,
  HistoryStep,
  MyInputResponse,
  MyInputSource,
  PlayerDoc,
  ResultFinal,
  Role,
  RoomDoc,
  RoundDoc,
  StepDoc,
  StepType,
} from '../types'

const STORAGE_KEY = 'gesture-relay.mock.state.v1'
const GRACE_MS = 5_000

// AI の処理にかかる時間の仮の値（本物の画像生成は約11秒、とBの記録にある）
const AI_DELAY_MS: Record<'image_gen' | 'conclude' | 'similarity', number> = {
  image_gen: 3_000,
  conclude: 2_000,
  similarity: 1_000,
}


export interface GameConfig {
  text_seconds: number
  countdown_seconds: number
  record_seconds: number
  gesture_read_ms: number // 裏の読み取りにかかる時間。モック専用
}

interface MockRound {
  room_id: string
  doc: RoundDoc
  steps: StepDoc[]
  players: Record<string, Role>
  returned_uids: string[]
  outputs: Record<string, { text: string | null; asset_id: string | null }>
  odai_text: string
  config: GameConfig
  gesture: { session_id: string; finished: boolean; video_asset_id: string | null } | null
  gesture_ai_text: string | null
  ai_due_at: number | null
  gesture_due_at: number | null
  result_due_at: number | null
  result: ResultFinal | null
}

export interface MockAsset {
  round_id: string
  kind: 'image' | 'video'
  step_index: number
  content_type: string
  label: string
}

export interface MockState {
  rooms: Record<string, RoomDoc>
  players: Record<string, Record<string, PlayerDoc>>
  rounds: Record<string, MockRound>
  assets: Record<string, MockAsset>
  join_codes: Record<string, string>
  requests: Record<string, { fingerprint: string; response: unknown }>
}

function emptyState(): MockState {
  return { rooms: {}, players: {}, rounds: {}, assets: {}, join_codes: {}, requests: {} }
}

export function loadState(): MockState {
  const raw = localStorage.getItem(STORAGE_KEY)
  return raw ? (JSON.parse(raw) as MockState) : emptyState()
}

export function saveState(state: MockState): void {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(state))
}

export function resetState(): void {
  localStorage.removeItem(STORAGE_KEY)
}

function must(
  condition: unknown,
  code: ApiErrorCode,
  status = 409,
  message = '操作を受け付けられません',
): asserts condition {
  if (!condition) throw new ApiError(code, status, message)
}

function newId(): string {
  return crypto.randomUUID().replaceAll('-', '').slice(0, 20)
}

function iso(ms: number): string {
  return new Date(ms).toISOString()
}

/** request_id が同じなら前回の応答を返し、中身が違えば拒否する */
export function command<T>(
  s: MockState,
  uid: string,
  action: string,
  requestId: string,
  body: unknown,
  work: () => T,
): T {
  const key = `${uid}:${action}:${requestId}`
  const fingerprint = JSON.stringify(body)
  const previous = s.requests[key]
  if (previous) {
    must(
      previous.fingerprint === fingerprint,
      'INVALID_INPUT',
      400,
      '同じ送信IDで内容を変更できません',
    )
    return previous.response as T
  }
  const response = work()
  s.requests[key] = { fingerprint, response }
  return response
}

function roomOf(s: MockState, roomId: string, uid?: string) {
  const room = s.rooms[roomId]
  must(room, 'ROOM_NOT_FOUND', 404, '部屋が見つかりません')
  if (uid !== undefined) {
    must(s.players[roomId][uid], 'NOT_YOUR_TURN', 403, 'この部屋に参加していません')
  }
  return room
}

function roundOf(s: MockState, roundId: string, uid?: string) {
  const round = s.rounds[roundId]
  must(round, 'ROOM_NOT_FOUND', 404, 'ラウンドが見つかりません')
  if (uid !== undefined) must(round.players[uid], 'NOT_YOUR_TURN', 403, '参加者ではありません')
  return round
}

function newPlayer(name: string): PlayerDoc {
  const now = iso(Date.now())
  return { name, role: null, consented_at: now, last_seen_at: now, phase: 'lobby' }
}

export function createRoom(s: MockState, uid: string, name: string, consented: boolean) {
  must(consented, 'CONSENT_REQUIRED', 403, '同意が必要です')
  const roomId = newId()
  let code = ''
  do {
    code = String(Math.floor(Math.random() * 10_000)).padStart(4, '0')
  } while (s.join_codes[code])
  s.rooms[roomId] = {
    status: 'waiting',
    fail_reason: null,
    join_code: code,
    host_player_id: uid,
    created_at: iso(Date.now()),
    current_round_id: null,
  }
  s.players[roomId] = { [uid]: newPlayer(name) }
  s.join_codes[code] = roomId
  return { room_id: roomId, join_code: code, player_id: uid }
}

export function joinRoom(
  s: MockState,
  uid: string,
  joinCode: string,
  name: string,
  consented: boolean,
) {
  must(consented, 'CONSENT_REQUIRED', 403, '同意が必要です')
  const roomId = s.join_codes[joinCode]
  must(roomId, 'ROOM_NOT_FOUND', 404, '部屋が見つかりません')
  must(roomOf(s, roomId).status === 'waiting', 'INVALID_STATE')
  const players = s.players[roomId]
  if (!players[uid]) {
    must(Object.keys(players).length < 3, 'ROOM_FULL', 409, '部屋が満員です')
    // 全員が出て空になった部屋では、入った人がホストになる
    if (Object.keys(players).length === 0) roomOf(s, roomId).host_player_id = uid
    players[uid] = newPlayer(name)
  }
  return { room_id: roomId, player_id: uid }
}

export function selectRole(s: MockState, uid: string, roomId: string, role: Role | null) {
  must(roomOf(s, roomId, uid).status === 'waiting', 'INVALID_STATE')
  const players = s.players[roomId]
  const taken = Object.entries(players).some(([key, p]) => key !== uid && p.role === role)
  must(role === null || !taken, 'ROLE_TAKEN', 409, 'その役割は選ばれています')
  players[uid].role = role
  return { accepted: true }
}

export function startGame(s: MockState, uid: string, roomId: string, config: GameConfig) {
  const room = roomOf(s, roomId, uid)
  must(room.host_player_id === uid, 'NOT_HOST', 403, 'ホストのみ開始できます')
  must(room.status === 'waiting', 'INVALID_STATE')
  const players = s.players[roomId]
  const roles = new Set(Object.values(players).map((p) => p.role))
  must(
    Object.keys(players).length === 3 && roles.has('A') && roles.has('B') && roles.has('C'),
    'ROLES_NOT_READY',
    409,
    '3人全員が役割を選ぶと開始できます',
  )

  const roundId = newId()
  const plan: [StepType, Role | null][] = [
    ['image_gen', null],
    ['text', 'A'],
    ['gesture', 'B'],
    ['text', 'C'],
    ['image_gen', null],
    ['conclude', null],
  ]
  const steps: StepDoc[] = plan.map(([type, role], index) => ({
    step_index: index,
    type,
    actor: role ? 'player' : 'ai',
    player_id: Object.entries(players).find(([, p]) => p.role === role)?.[0] ?? null,
    role,
    status: index === 0 ? 'processing' : role ? 'waiting' : 'pending',
    started_at: index === 0 ? iso(Date.now()) : null,
    deadline_at: null,
    timed_out: false,
  }))

  deleteVideosOf(s, room.current_round_id)
  s.rounds[roundId] = {
    room_id: roomId,
    doc: {
      status: 'playing',
      current_step_index: 0,
      revision: 0,
      gesture_ai_status: 'pending',
      result_status: 'pending',
    },
    steps,
    players: Object.fromEntries(
      Object.entries(players).map(([key, p]) => [key, p.role as Role]),
    ),
    returned_uids: [],
    outputs: {},
    odai_text: MOCK_ODAI[Math.floor(Math.random() * MOCK_ODAI.length)],
    config,
    gesture: null,
    gesture_ai_text: null,
    ai_due_at: Date.now() + AI_DELAY_MS.image_gen,
    gesture_due_at: null,
    result_due_at: null,
    result: null,
  }
  room.status = 'playing'
  room.current_round_id = roundId
  room.fail_reason = null
  for (const p of Object.values(players)) {
    p.phase = 'playing'
    p.last_seen_at = iso(Date.now())
  }
  return { accepted: true, round_id: roundId }
}

function activeStep(
  s: MockState,
  uid: string,
  roundId: string,
  index: number | null,
  type: StepType,
) {
  const round = roundOf(s, roundId, uid)
  must(!round.returned_uids.includes(uid), 'NOT_YOUR_TURN', 403)
  must(round.doc.status === 'playing', 'INVALID_STATE')
  const step = round.steps[index ?? round.doc.current_step_index]
  must(
    step && step.player_id === uid && step.type === type,
    'NOT_YOUR_TURN',
    403,
    'あなたの番ではありません',
  )
  must(step.status === 'active', 'ALREADY_SUBMITTED', 409, '提出済みです')
  must(
    Date.now() <= Date.parse(step.deadline_at as string) + GRACE_MS,
    'DEADLINE_PASSED',
    409,
    '締切を過ぎました',
  )
  return { round, step }
}

function activate(round: MockRound, index: number): void {
  const step = round.steps[index]
  round.doc.current_step_index = index
  round.doc.revision += 1
  step.started_at = iso(Date.now())
  if (step.actor === 'player') {
    const { config } = round
    const seconds =
      step.type === 'gesture'
        ? config.countdown_seconds + config.record_seconds
        : config.text_seconds
    step.status = 'active'
    step.deadline_at = iso(Date.now() + seconds * 1000)
  } else {
    step.status = 'processing'
    round.ai_due_at =
      Date.now() + AI_DELAY_MS[step.type === 'conclude' ? 'conclude' : 'image_gen']
  }
}

function advance(s: MockState, round: MockRound): void {
  if (round.doc.status !== 'playing') return
  const index = round.doc.current_step_index
  const status = round.steps[index].status
  if (status !== 'done' && status !== 'timeout') return
  if (index < 5) {
    activate(round, index + 1)
  } else if (round.doc.result_status === 'pending') {
    round.doc.result_status = 'processing'
    round.doc.revision += 1
    round.result_due_at = Date.now() + AI_DELAY_MS.similarity
  } else if (round.doc.result_status === 'ready') {
    round.doc.status = 'finished'
    s.rooms[round.room_id].status = 'finished'
    for (const uid of Object.keys(round.players)) s.players[round.room_id][uid].phase = 'viewing'
  }
}

export function myInput(s: MockState, uid: string, roundId: string): MyInputResponse {
  const round = roundOf(s, roundId, uid)
  must(
    !round.returned_uids.includes(uid) && round.doc.status === 'playing',
    'NOT_YOUR_TURN',
    403,
    'あなたの番ではありません',
  )
  const index = round.doc.current_step_index
  const step = round.steps[index]
  must(
    step.status === 'active' && step.player_id === uid,
    'NOT_YOUR_TURN',
    403,
    'あなたの番ではありません',
  )
  const source = round.outputs[String(index - 1)]
  const input: MyInputSource =
    index === 2
      ? { kind: 'text', text: source?.text ?? '' }
      : { kind: index === 1 ? 'image' : 'video', asset_id: source?.asset_id ?? null }
  const response: MyInputResponse = {
    step_index: index,
    type: step.type,
    deadline_at: step.deadline_at as string,
    input,
  }
  if (step.type === 'gesture') {
    response.countdown_seconds = round.config.countdown_seconds
    response.record_seconds = round.config.record_seconds
  }
  return response
}

export function submitText(
  s: MockState,
  uid: string,
  roundId: string,
  index: number,
  text: string,
  isAuto: boolean,
) {
  must(text.length <= 2000, 'TEXT_TOO_LONG', 400, '文章が長すぎます')
  const { round, step } = activeStep(s, uid, roundId, index, 'text')
  round.outputs[String(index)] = { text, asset_id: null }
  step.status = 'done'
  step.timed_out = Date.now() >= Date.parse(step.deadline_at as string)
  step.is_auto = isAuto
  advance(s, round)
  return { accepted: true }
}

export function gestureStart(s: MockState, uid: string, roundId: string) {
  const { round, step } = activeStep(s, uid, roundId, null, 'gesture')
  must(round.gesture === null, 'ALREADY_SUBMITTED', 409, '提出済みです')
  const sessionId = newId()
  round.gesture = { session_id: sessionId, finished: false, video_asset_id: null }
  return { gesture_session_id: sessionId, deadline_at: step.deadline_at as string }
}

function checkSession(round: MockRound, sessionId: string): void {
  must(round.gesture?.session_id === sessionId, 'INVALID_STATE')
}

export function gestureBatch(s: MockState, uid: string, roundId: string, sessionId: string) {
  const { round } = activeStep(s, uid, roundId, null, 'gesture')
  checkSession(round, sessionId)
  must(!round.gesture?.finished, 'ALREADY_SUBMITTED', 409, '提出済みです')
  return { accepted: true }
}

function finishGesture(round: MockRound): void {
  const gesture = round.gesture
  if (!gesture) return
  gesture.finished = true
  if (round.gesture_due_at === null && round.doc.gesture_ai_status === 'pending') {
    round.doc.gesture_ai_status = 'processing'
    round.gesture_due_at = Date.now() + round.config.gesture_read_ms
  }
  if (gesture.video_asset_id) {
    round.outputs['2'] = { text: null, asset_id: gesture.video_asset_id }
    round.steps[2].status = 'done'
  }
}

export function gestureFinish(s: MockState, uid: string, roundId: string, sessionId: string) {
  const { round } = activeStep(s, uid, roundId, null, 'gesture')
  checkSession(round, sessionId)
  finishGesture(round)
  advance(s, round)
  return { accepted: true }
}

/** 録画の本体を保存する前の確認。本物の API の preflight と同じ */
export function checkVideoUpload(
  s: MockState,
  uid: string,
  roundId: string,
  sessionId: string,
  contentType: string,
): void {
  const { round } = activeStep(s, uid, roundId, null, 'gesture')
  checkSession(round, sessionId)
  must(!round.gesture?.video_asset_id, 'ALREADY_SUBMITTED', 409, '提出済みです')
  must(
    contentType === 'video/webm' || contentType === 'video/mp4',
    'UNSUPPORTED_MEDIA_TYPE',
    400,
    '録画の形式を確認してください',
  )
}

export function commitVideo(
  s: MockState,
  uid: string,
  roundId: string,
  sessionId: string,
  assetId: string,
  contentType: string,
) {
  const { round } = activeStep(s, uid, roundId, null, 'gesture')
  checkSession(round, sessionId)
  const gesture = round.gesture
  must(gesture, 'INVALID_STATE')
  s.assets[assetId] = {
    round_id: roundId,
    kind: 'video',
    step_index: 2,
    content_type: contentType,
    label: '録画',
  }
  gesture.video_asset_id = assetId
  if (gesture.finished) finishGesture(round)
  advance(s, round)
  return { accepted: true, asset_id: assetId }
}

function visibleUntil(round: MockRound, uid: string): number {
  must(
    !round.returned_uids.includes(uid),
    'HISTORY_LOCKED',
    403,
    '履歴は公開されていません',
  )
  if (round.doc.status === 'finished' || round.doc.status === 'failed') return 5
  for (const index of [1, 2, 3]) {
    const step = round.steps[index]
    if (step.player_id === uid && step.status === 'done') return index
  }
  return -1
}

export function history(s: MockState, uid: string, roundId: string): HistoryResponse {
  const round = roundOf(s, roundId, uid)
  const until = visibleUntil(round, uid)
  const steps: HistoryStep[] = round.steps.slice(0, until + 1).map((step) => {
    const output = round.outputs[String(step.step_index)]
    const item: HistoryStep = { ...step }
    if (output?.text !== null && output?.text !== undefined) item.text = output.text
    if (output?.asset_id) {
      if (step.step_index === 2) item.video_asset_id = output.asset_id
      else item.image_asset_id = output.asset_id
    }
    if (step.step_index === 2 && round.gesture_ai_text !== null) {
      item.gesture_ai_text = round.gesture_ai_text
    }
    return item
  })
  return {
    round_status: round.doc.status,
    visible_until_step_index: until,
    steps,
    result: until === 5 ? round.result : null,
  }
}

/** 素材を読んでよいか確認する。「公開済み履歴」か「現在の入力素材」のどちらかなら通す */
export function readableAsset(
  s: MockState,
  uid: string,
  roundId: string,
  assetId: string,
): MockAsset {
  const round = roundOf(s, roundId, uid)
  const until = visibleUntil(round, uid)
  const asset = s.assets[assetId]
  must(asset, 'ASSET_NOT_FOUND', 404, '素材が見つかりません')
  if (asset.step_index <= until) return asset
  const index = round.doc.current_step_index
  const current = round.steps[index]
  must(
    round.doc.status === 'playing' &&
      current.status === 'active' &&
      current.player_id === uid &&
      round.outputs[String(index - 1)]?.asset_id === assetId,
    'HISTORY_LOCKED',
    403,
    '素材は公開されていません',
  )
  return asset
}

function fail(s: MockState, round: MockRound, reason: FailReason): void {
  const room = s.rooms[round.room_id]
  round.doc.status = 'failed'
  room.status = 'failed'
  room.fail_reason = reason
  round.doc.revision += 1
  for (const uid of Object.keys(round.players)) {
    if (!round.returned_uids.includes(uid)) s.players[round.room_id][uid].phase = 'viewing'
  }
}

function deleteVideosOf(s: MockState, roundId: string | null): string[] {
  if (!roundId) return []
  const removed: string[] = []
  for (const [assetId, asset] of Object.entries(s.assets)) {
    if (asset.round_id === roundId && asset.kind === 'video') {
      delete s.assets[assetId]
      removed.push(assetId)
    }
  }
  return removed
}

/** 戻す処理。削除した録画の asset_id を一緒に返す */
export function leaveRoom(s: MockState, uid: string, roomId: string) {
  const room = roomOf(s, roomId, uid)
  // ロビー（待機中）では、部屋から外れる。ホストなら、参加が早い順の次の人に交代する
  if (room.status === 'waiting') {
    const players = s.players[roomId]
    delete players[uid]
    if (room.host_player_id === uid) {
      const next = Object.entries(players).sort(([, a], [, b]) =>
        a.consented_at.localeCompare(b.consented_at),
      )[0]
      if (next) room.host_player_id = next[0]
    }
    return { response: { accepted: true }, removed: [] as string[] }
  }
  must(room.current_round_id, 'INVALID_STATE')
  const round = s.rounds[room.current_round_id]
  if (round.doc.status === 'playing') fail(s, round, 'player_dropped')
  if (!round.returned_uids.includes(uid)) round.returned_uids.push(uid)
  s.players[roomId][uid].phase = 'returned'
  let removed: string[] = []
  if (round.returned_uids.length === Object.keys(round.players).length) {
    room.status = 'waiting'
    room.fail_reason = null
    for (const p of Object.values(s.players[roomId])) p.phase = 'lobby'
    removed = deleteVideosOf(s, room.current_round_id)
  }
  return { response: { accepted: true }, removed }
}

export function heartbeat(s: MockState, uid: string, roomId: string) {
  roomOf(s, roomId, uid)
  s.players[roomId][uid].last_seen_at = iso(Date.now())
  return { accepted: true }
}

function finishAiStep(s: MockState, round: MockRound): void {
  const index = round.doc.current_step_index
  const step = round.steps[index]
  if (step.type === 'image_gen') {
    const assetId = newId()
    s.assets[assetId] = {
      round_id: Object.keys(s.rounds).find((key) => s.rounds[key] === round) as string,
      kind: 'image',
      step_index: index,
      content_type: 'image/svg+xml',
      label: index === 0 ? 'AIが描いた最初の絵' : `最終の絵: ${round.outputs['3']?.text ?? ''}`,
    }
    round.outputs[String(index)] = { text: null, asset_id: assetId }
  } else {
    round.outputs[String(index)] = { text: round.odai_text, asset_id: null }
  }
  step.status = 'done'
  round.ai_due_at = null
  advance(s, round)
}

/** 時間で進む処理（AI の完了と締切）。本物の Worker と Cloud Tasks の代わり */
export function tick(s: MockState): void {
  const now = Date.now()
  for (const round of Object.values(s.rounds)) {
    if (round.gesture_due_at !== null && now >= round.gesture_due_at) {
      round.gesture_due_at = null
      round.gesture_ai_text = '両手を大きく動かして、何かの形を表しています（モックの文章）'
      round.doc.gesture_ai_status = 'done'
      if (round.result) round.result.gesture_ai_text = round.gesture_ai_text
    }
    if (round.doc.status !== 'playing') continue

    if (round.ai_due_at !== null && now >= round.ai_due_at) finishAiStep(s, round)

    if (round.result_due_at !== null && now >= round.result_due_at) {
      round.result_due_at = null
      round.result = {
        odai: round.odai_text,
        final_image_asset_id: round.outputs['4']?.asset_id ?? '',
        ai_conclusion: round.outputs['5']?.text ?? '',
        similarity: 0.82,
        gesture_ai_text: round.gesture_ai_text,
      }
      round.doc.result_status = 'ready'
      advance(s, round)
    }

    const index = round.doc.current_step_index
    const step = round.steps[index]
    const due = step.deadline_at ? Date.parse(step.deadline_at) + GRACE_MS : null
    if (step.status === 'active' && due !== null && now >= due) {
      if (index === 2 && round.gesture?.video_asset_id) {
        finishGesture(round)
        step.timed_out = true
        advance(s, round)
      } else {
        step.status = 'timeout'
        step.timed_out = true
        fail(s, round, 'communication_failed')
      }
    }
  }
}

// ---- 開発用：失敗の表示を試すための操作（モック専用） ----

export function devFail(s: MockState, roomId: string, reason: FailReason): void {
  const roundId = s.rooms[roomId]?.current_round_id
  if (!roundId) return
  const round = s.rounds[roundId]
  if (round.doc.status === 'playing') fail(s, round, reason)
}

export function devFailGestureAi(s: MockState, roomId: string): void {
  const roundId = s.rooms[roomId]?.current_round_id
  if (!roundId) return
  const round = s.rounds[roundId]
  round.gesture_due_at = null
  round.doc.gesture_ai_status = 'failed'
}
