// API と Firestore の形を定義する。項目名は仕様書と一字一句同じにする。
// 綴りがずれるとエラーにならず値が空になるので、ここだけは snake_case のまま書く。
// 根拠: docs/specification.md、docs/shared-types.md §1・§6、origin/codex/backend-a の実装

// ---- 状態の値（shared-types §1） ----

export type RoomStatus = 'waiting' | 'playing' | 'finished' | 'failed'
export type RoundStatus = 'playing' | 'finished' | 'failed'
export type FailReason = 'ai_failed' | 'communication_failed' | 'player_dropped'
export type PlayerPhase = 'lobby' | 'playing' | 'viewing' | 'returned'
export type Role = 'A' | 'B' | 'C'
export type StepActor = 'player' | 'ai'
export type StepType = 'image_gen' | 'text' | 'gesture' | 'conclude'
export type PlayerStepStatus = 'waiting' | 'active' | 'done' | 'timeout'
export type JobStatus = 'pending' | 'processing' | 'done' | 'failed'
export type StepStatus = PlayerStepStatus | JobStatus
export type ResultStatus = 'pending' | 'processing' | 'ready' | 'failed'

// ---- Firestore の公開状態（読むだけ） ----
// 時刻は窓口の実装が ISO 8601 の文字列に揃えてから渡す。

export interface RoomDoc {
  status: RoomStatus
  fail_reason: FailReason | null
  join_code: string
  host_player_id: string
  created_at: string
  current_round_id: string | null
}

export interface PlayerDoc {
  name: string
  role: Role | null
  consented_at: string
  last_seen_at: string
  phase: PlayerPhase
}

export interface RoundDoc {
  status: RoundStatus
  current_step_index: number
  revision: number
  gesture_ai_status: JobStatus
  result_status: ResultStatus
}

export interface StepDoc {
  step_index: number
  type: StepType
  actor: StepActor
  player_id: string | null
  role: Role | null
  status: StepStatus
  started_at: string | null
  deadline_at: string | null
  timed_out: boolean
  is_auto?: boolean
}

// ---- API の入出力（仕様書 §3） ----

export interface CreateRoomRequest {
  name: string
  consented: boolean
  request_id: string
}

export interface CreateRoomResponse {
  room_id: string
  join_code: string
  player_id: string
}

export interface JoinRoomRequest extends CreateRoomRequest {
  join_code: string
}

export interface JoinRoomResponse {
  room_id: string
  player_id: string
}

export interface SelectRoleRequest {
  role: Role | null
  request_id: string
}

export interface PlainRequest {
  request_id: string
}

export interface AcceptedResponse {
  accepted: boolean
}

export interface StartGameResponse extends AcceptedResponse {
  round_id: string
}

export type MyInputSource =
  | { kind: 'image'; asset_id: string | null }
  | { kind: 'video'; asset_id: string | null }
  | { kind: 'text'; text: string }

export interface MyInputResponse {
  step_index: number
  type: StepType
  deadline_at: string
  input: MyInputSource
  // ジェスチャーの段だけ返す。A に追加を依頼中（docs/frontend-requests.md §1）。
  countdown_seconds?: number
  record_seconds?: number
}

export interface SubmitTextRequest {
  text: string
  request_id: string
  is_auto: boolean
}

export interface GestureStartResponse {
  gesture_session_id: string
  deadline_at: string
}

export interface GestureFinishRequest {
  gesture_session_id: string
  request_id: string
}

export interface GestureVideoRequest {
  gesture_session_id: string
  request_id: string
  file: Blob
}

export interface GestureVideoResponse extends AcceptedResponse {
  asset_id: string
}

// ---- 座標（shared-types §6） ----

export interface Landmark {
  x: number
  y: number
  z: number
}

export interface Hand {
  handedness: 'Left' | 'Right'
  landmarks: Landmark[] // 検出した手ごとに21点
}

export interface Sample {
  timestamp_ms: number
  hands: Hand[] // 手が映っていなければ空
}

export interface GestureBatch {
  gesture_session_id: string
  sequence_number: number
  mirrored: boolean
  samples: Sample[]
}

// ---- 履歴と結果（仕様書 §3-7） ----

export interface HistoryStep extends StepDoc {
  text?: string
  image_asset_id?: string
  video_asset_id?: string
  gesture_ai_text?: string
}

export interface ResultFinal {
  odai: string
  final_image_asset_id: string
  ai_conclusion: string
  similarity: number
  gesture_ai_text: string | null
}

export interface HistoryResponse {
  round_status: RoundStatus
  visible_until_step_index: number // まだ何も見られないときは -1
  steps: HistoryStep[]
  result: ResultFinal | null
}

// ---- エラー（仕様書 §1） ----

export type ApiErrorCode =
  | 'INVALID_INPUT'
  | 'TEXT_TOO_LONG'
  | 'PAYLOAD_TOO_LARGE'
  | 'UNSUPPORTED_MEDIA_TYPE'
  | 'UNAUTHENTICATED'
  | 'NOT_YOUR_TURN'
  | 'NOT_HOST'
  | 'CONSENT_REQUIRED'
  | 'HISTORY_LOCKED'
  | 'ROOM_NOT_FOUND'
  | 'ASSET_NOT_FOUND'
  | 'ALREADY_SUBMITTED'
  | 'DEADLINE_PASSED'
  | 'ROLE_TAKEN'
  | 'ROOM_FULL'
  | 'ROLES_NOT_READY'
  | 'INVALID_STATE'
  | 'TOO_MANY_ATTEMPTS'
  | 'AI_FAILED'
  | 'INTERNAL'
