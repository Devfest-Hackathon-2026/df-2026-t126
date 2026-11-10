// 画面が使う「窓口」。画面はこの形だけを知っていて、相手がモックか本物かを知らない。
// 結合のときは実装を差し替えるだけで済み、画面のコードは変えなくてよい。

import type {
  AcceptedResponse,
  ApiErrorCode,
  CreateRoomRequest,
  CreateRoomResponse,
  GestureBatch,
  GestureFinishRequest,
  GestureStartResponse,
  GestureVideoRequest,
  GestureVideoResponse,
  HistoryResponse,
  JoinRoomRequest,
  JoinRoomResponse,
  MyInputResponse,
  PlainRequest,
  PlayerDoc,
  RoomDoc,
  RoundDoc,
  SelectRoleRequest,
  StartGameResponse,
  StepDoc,
  SubmitTextRequest,
} from './types'

/** 購読をやめるときに呼ぶ関数 */
export type Unsubscribe = () => void

/**
 * 購読が続けられなくなったときに呼ぶ関数（通信が切れた、など）。
 * 部屋の外になった・部屋が消えたときは、エラーではなく onChange(null) で知らせる
 */
export type OnSubscribeError = (error: Error) => void

export interface Backend {
  /** 匿名ログインして、自分の uid を返す */
  signIn(): Promise<string>

  // #1〜#4 部屋
  createRoom(body: CreateRoomRequest): Promise<CreateRoomResponse>
  joinRoom(body: JoinRoomRequest): Promise<JoinRoomResponse>
  selectRole(roomId: string, body: SelectRoleRequest): Promise<AcceptedResponse>
  startGame(roomId: string, body: PlainRequest): Promise<StartGameResponse>

  // #5〜#6 文章
  getMyInput(roundId: string): Promise<MyInputResponse>
  submitText(
    roundId: string,
    stepIndex: number,
    body: SubmitTextRequest,
  ): Promise<AcceptedResponse>

  // #7〜#10 ジェスチャー
  gestureStart(roundId: string, body: PlainRequest): Promise<GestureStartResponse>
  gestureBatch(roundId: string, body: GestureBatch): Promise<AcceptedResponse>
  gestureVideo(roundId: string, body: GestureVideoRequest): Promise<GestureVideoResponse>
  gestureFinish(roundId: string, body: GestureFinishRequest): Promise<AcceptedResponse>

  // #11〜#14 履歴・素材・退室・生存確認
  getHistory(roundId: string): Promise<HistoryResponse>
  /** 素材の本体を返す。<img src> に URL を直接入れられないため Blob で受け取る */
  getAsset(roundId: string, assetId: string): Promise<Blob>
  leaveRoom(roomId: string, body: PlainRequest): Promise<AcceptedResponse>
  heartbeat(roomId: string): Promise<AcceptedResponse>

  // Firestore の公開状態の購読。登録した直後に現在の値でも1回呼ばれる
  subscribeRoom(
    roomId: string,
    onChange: (room: RoomDoc | null) => void,
    onError?: OnSubscribeError,
  ): Unsubscribe
  subscribePlayers(
    roomId: string,
    onChange: (players: Record<string, PlayerDoc>) => void,
    onError?: OnSubscribeError,
  ): Unsubscribe
  subscribeRound(
    roomId: string,
    roundId: string,
    onChange: (round: RoundDoc | null) => void,
    onError?: OnSubscribeError,
  ): Unsubscribe
  subscribeSteps(
    roomId: string,
    roundId: string,
    onChange: (steps: StepDoc[]) => void,
    onError?: OnSubscribeError,
  ): Unsubscribe
}

/** サーバーが返す共通のエラー。message は画面にそのまま出せる日本語 */
export class ApiError extends Error {
  readonly code: ApiErrorCode
  readonly status: number

  constructor(code: ApiErrorCode, status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.code = code
    this.status = status
  }
}

/** 二重送信を防ぐ ID。再送するときは同じ ID と同じ中身で送る（中身を変えると 400 になる） */
export function newRequestId(): string {
  return crypto.randomUUID()
}
