// 開発用の道具。3人分の並べ表示はモックと本物の両方、失敗ボタンはモックだけで使う。

import { mockTools } from '../api'

const PLAYERS = ['a', 'b', 'c']

/** ?dev=3 で3人分の画面を横に並べる */
export function DevGrid() {
  const params = new URLSearchParams(location.search)
  params.delete('dev')
  return (
    <div className="dev-grid">
      {PLAYERS.map((player) => {
        params.set('player', player)
        return (
          <iframe key={player} title={`player-${player}`} src={`/?${params}`} allow="camera" />
        )
      })}
    </div>
  )
}

/** 失敗の表示を試すためのボタン */
export function DevPanel({ roomId }: { roomId: string | null }) {
  const tools = mockTools
  if (!tools) return null
  return (
    <details className="dev-panel">
      <summary>開発用</summary>
      {roomId && (
        <>
          <button onClick={() => tools.devFail(roomId, 'ai_failed')}>AI失敗</button>
          <button onClick={() => tools.devFail(roomId, 'communication_failed')}>通信失敗</button>
          <button onClick={() => tools.devFail(roomId, 'player_dropped')}>途中離脱</button>
          <button onClick={() => tools.devFailGestureAi(roomId)}>読み取り失敗</button>
        </>
      )}
      <button
        onClick={() => {
          tools.devReset()
          localStorage.clear()
          location.reload()
        }}
      >
        全部消す
      </button>
    </details>
  )
}
