// F1: 名前・同意・部屋の作成と参加

import { useState } from 'react'
import { backend } from '../api'
import { newRequestId } from '../api/backend'
import { errorMessage, withRetry } from '../lib/retry'

// 文面は仕様書 §2 のとおり
const CONSENTS = [
  'カメラを使うこと',
  '手の座標がAIに送られること（映像・画像はAIに送りません）',
  '録画が保存され、同じ部屋のプレイヤーに見られること',
  '録画は全員がロビーに戻った時点で削除されること（一定時間後にも自動で削除されます）',
]

interface EntryProps {
  onEnter: (roomId: string) => void
  /** スタート画面へ戻る */
  onBack: () => void
}

export function EntryScreen({ onEnter, onBack }: EntryProps) {
  const [name, setName] = useState('')
  const [checked, setChecked] = useState(() => CONSENTS.map(() => false))
  const [joinCode, setJoinCode] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const ready = name.trim() !== '' && checked.every(Boolean)

  async function run(action: () => Promise<{ room_id: string }>) {
    setBusy(true)
    setError('')
    try {
      onEnter((await withRetry(action)).room_id)
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  function createRoom() {
    const body = { name: name.trim(), consented: true, request_id: newRequestId() }
    void run(() => backend.createRoom(body))
  }

  function joinRoom() {
    const body = {
      name: name.trim(),
      consented: true,
      join_code: joinCode,
      request_id: newRequestId(),
    }
    void run(() => backend.joinRoom(body))
  }

  return (
    <main className="screen">
      <div className="heading">
        <p className="en">ENTRY</p>
        <h1>名前と同意</h1>
      </div>

      <label className="field">
        名前
        <input value={name} maxLength={40} autoComplete="nickname" onChange={(e) => setName(e.target.value)} />
      </label>

      <fieldset>
        <legend>次の内容に同意してください</legend>
        {CONSENTS.map((text, index) => (
          <label key={text} className="check">
            <input
              type="checkbox"
              checked={checked[index]}
              onChange={(e) =>
                setChecked(checked.map((c, i) => (i === index ? e.target.checked : c)))
              }
            />
            {text}
          </label>
        ))}
      </fieldset>

      <div className="heading">
        <p className="en">NEW ROOM</p>
        <h2>部屋を作る</h2>
      </div>
      <button disabled={!ready || busy} onClick={createRoom}>
        部屋を作る
      </button>

      <div className="heading">
        <p className="en">JOIN</p>
        <h2>部屋に参加する</h2>
      </div>
      <label className="field">
        参加コード（4桁）
        <input
          value={joinCode}
          inputMode="numeric"
          maxLength={4}
          onChange={(e) => setJoinCode(e.target.value.replace(/\D/g, ''))}
        />
      </label>
      <button className="sub" disabled={!ready || busy || joinCode.length !== 4} onClick={joinRoom}>
        部屋に参加する
      </button>

      {error && <p className="error">{error}</p>}
      <button className="text-link" onClick={onBack}>
        最初の画面へ戻る
      </button>
    </main>
  )
}
