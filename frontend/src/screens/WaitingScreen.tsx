// F2: 自分の番ではないときの進行表示

import type { GameState } from '../game/useGame'
import { useSecondsLeft } from '../lib/hooks'
import { Scene } from '../ui/Scene'
import type { SceneKind } from '../ui/scenes'

function describe(game: GameState): string {
  const { round, steps, players } = game
  if (!round) return ''
  const step = steps[round.current_step_index]
  if (!step) return ''
  if (round.result_status === 'processing' || round.result_status === 'ready') {
    return 'AIが結果をまとめています'
  }
  if (step.actor === 'ai') {
    const messages: Record<number, string> = {
      0: 'AIがお題の絵を描いています',
      4: 'AIが最後の絵を描いています',
      5: 'AIがお題を推測しています',
    }
    return messages[step.step_index] ?? 'AIが処理しています'
  }
  const name = step.player_id ? (players[step.player_id]?.name ?? '') : ''
  const action = step.type === 'gesture' ? 'ジェスチャーをしています' : '文章を書いています'
  return `${name}さん（人${step.role}）が${action}`
}

/** いま進んでいる段に合わせた絵。AI の段はロボット、ジェスチャーの段は身ぶり、文章の段は悩む人 */
function sceneFor(game: GameState): SceneKind {
  const { round, steps } = game
  const step = round ? steps[round.current_step_index] : undefined
  if (!step || step.actor === 'ai' || round?.result_status === 'processing') return 'robot'
  return step.type === 'gesture' ? 'start' : 'think'
}

export function WaitingScreen({ game }: { game: GameState }) {
  const { round, steps } = game
  const step = round ? steps[round.current_step_index] : undefined
  const secondsLeft = useSecondsLeft(step?.status === 'active' ? step.deadline_at : null)

  const scene = sceneFor(game)
  return (
    <main className="screen">
      <div className="heading">
        <p className="en">WAITING</p>
        <h1>待機中</h1>
      </div>
      <Scene key={scene} kind={scene} label="待っている間の絵" />
      <p className="prompt">
        {describe(game)}
        {scene === 'robot' && <span aria-hidden="true"> …</span>}
      </p>
      {secondsLeft !== null && <p className="timer">残り {secondsLeft} 秒</p>}
      {round && (
        <p className="muted">
          段 {round.current_step_index + 1} / {steps.length}
        </p>
      )}
      {round?.gesture_ai_status === 'failed' && (
        <p className="error">AIのジェスチャー読み取りに失敗しました（ゲームは続きます）</p>
      )}
      <p className="muted">画面を消さずに、このままお待ちください</p>
    </main>
  )
}
