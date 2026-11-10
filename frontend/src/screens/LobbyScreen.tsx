// F1: ロビー（役割の選択とホストの開始操作）

import { useState } from 'react'
import { backend } from '../api'
import { newRequestId } from '../api/backend'
import type { Role } from '../api/types'
import type { CameraStatus, GameState } from '../game/useGame'
import { errorMessage, withRetry, sleep } from '../lib/retry'
import { NO_ROLE_COLOR, ROLE_COLOR } from '../ui/figure'
import { Scene } from '../ui/Scene'

const ROLES: { role: Role; description: string }[] = [
  { role: 'A', description: '絵を見て文章にする' },
  { role: 'B', description: '文章を見てジェスチャーする' },
  { role: 'C', description: '録画を見て文章にする' },
]

const CAMERA_MESSAGE: Record<Exclude<CameraStatus, 'idle' | 'failed'>, string> = {
  preparing: 'カメラと手の検出を準備しています',
  ready: 'カメラの準備ができました',
}

interface LobbyProps {
  game: GameState
  cameraStatus: CameraStatus
  onRetryCamera: () => void
  /** 部屋を出て、最初の画面に戻る */
  onLeaveRoom: () => void
}

/** 「部屋を出る」で、サーバーへの通知を待つ上限 */
const LEAVE_WAIT_MS = 3_000

export function LobbyScreen({ game, cameraStatus, onRetryCamera, onLeaveRoom }: LobbyProps) {
  const { uid, roomId, room, players } = game
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  if (!uid || !roomId || !room) return null
  const me = players[uid]
  const isHost = room.host_player_id === uid
  // 参加した順に並べる（人の絵の立ち位置になる）
  const everyone = Object.entries(players).sort(([, a], [, b]) =>
    a.consented_at.localeCompare(b.consented_at),
  )
  const people = everyone.map(([id, p]) => ({
    id,
    name: p.name,
    self: id === uid,
    color: p.role ? ROLE_COLOR[p.role] : NO_ROLE_COLOR,
  }))
  const ready = everyone.length === 3 && everyone.every(([, p]) => p.role !== null)

  async function run(action: () => Promise<unknown>) {
    setBusy(true)
    setError('')
    try {
      await withRetry(action)
    } catch (e) {
      setError(errorMessage(e))
    }
    setBusy(false)
  }

  function chooseRole(role: Role) {
    const body = { role: me.role === role ? null : role, request_id: newRequestId() }
    void run(() => backend.selectRole(roomId as string, body))
  }

  function start() {
    const body = { request_id: newRequestId() }
    void run(() => backend.startGame(roomId as string, body))
  }

  // 部屋を出る。サーバーへの通知が失敗しても、画面は抜けられるようにする（出られなくなるのを避ける）
  async function leaveRoom() {
    setBusy(true)
    try {
      // 通信が固まっても押したままにならないよう、3秒で待つのをやめて抜ける
      await Promise.race([backend.leaveRoom(roomId as string, { request_id: newRequestId() }), sleep(LEAVE_WAIT_MS)])
    } catch {
      // 通知できなくても、この端末は部屋を離れる
    }
    onLeaveRoom()
  }

  return (
    <main className="screen wide">
      <div className="heading">
        <p className="en">LOBBY</p>
        <h1>ロビー</h1>
      </div>
      <div className="split">
        <div>
          <section className="card">
            <p className="en">ROOM CODE</p>
            <p className="muted">参加コード</p>
            <p className="code">{room.join_code}</p>
            <p>
              {everyone.length < 3
                ? `このコードを、あと${3 - everyone.length}人に伝えよう`
                : '3人そろいました'}
            </p>
          </section>
          <div className="people">
            <Scene kind="lobby" label={`参加者 ${everyone.length}人`} people={people} />
          </div>
          <p className="muted">
            参加者 {everyone.length}/3
            {everyone.some(([id]) => id === room.host_player_id) &&
              `（ホスト: ${players[room.host_player_id]?.name ?? ''}）`}
          </p>
          {/* 画面が消えるとページが止まり、生存確認が途絶えて退出あつかいになるため */}
          <p className="keep-awake">
            ゲームが終わるまで、このページを開いたままにしてください。画面が消えたり、ほかのアプリに切り替えたりすると、退出したことになり、ゲームが止まります。
          </p>
        </div>

        <div>
          <div className="heading">
            <p className="en">ROLE</p>
            <h2>役割を選ぶ</h2>
          </div>
          <div className="roles">
            {ROLES.map(({ role, description }) => {
              const owner = everyone.find(([, p]) => p.role === role)
              const mine = owner?.[0] === uid
              return (
                <button
                  key={role}
                  className={mine ? 'sub selected' : 'sub'}
                  disabled={busy || (owner !== undefined && !mine)}
                  onClick={() => chooseRole(role)}
                >
                  <span className="dot" style={{ background: ROLE_COLOR[role] }} />
                  人{role}：{description}
                  {owner && <small>{owner[1].name}</small>}
                </button>
              )
            })}
          </div>

          {(cameraStatus === 'preparing' || cameraStatus === 'ready') && (
            <p className="muted">{CAMERA_MESSAGE[cameraStatus]}</p>
          )}
          {cameraStatus === 'failed' && (
            <>
              <p className="error">カメラを使えません。ブラウザの設定でカメラを許可してください</p>
              <button className="sub" onClick={onRetryCamera}>
                カメラをもう一度確認する
              </button>
            </>
          )}

          {isHost ? (
            <button disabled={busy || !ready} onClick={start}>
              ゲームを始める
            </button>
          ) : (
            <p className="muted">
              ホストの開始を待っています。来ないときは、部屋を出て、新しく始められます
            </p>
          )}
          <button className="sub" disabled={busy} onClick={() => void leaveRoom()}>
            部屋を出る
          </button>

          {error && <p className="error">{error}</p>}
        </div>
      </div>
    </main>
  )
}
