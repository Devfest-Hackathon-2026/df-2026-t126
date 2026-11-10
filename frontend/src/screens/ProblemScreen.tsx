// 続けられない問題が起きたときの画面。もう一度試すと、ページを読み込み直す。
// 入っていた部屋は端末に覚えているので、読み込み直すと同じ部屋に戻る。

import type { GameProblem } from '../game/useGame'

const MESSAGES: Record<GameProblem, { title: string; detail: string }> = {
  signin: {
    title: 'ログインできませんでした',
    detail: '通信の状態を確かめて、もう一度試してください。',
  },
  connection: {
    title: 'サーバーとの接続が切れました',
    detail: 'もう一度試すと、入っていた部屋に戻ります。',
  },
}

export function ProblemScreen({ problem }: { problem: GameProblem }) {
  const { title, detail } = MESSAGES[problem]
  return (
    <main className="screen">
      <h1>{title}</h1>
      <p>{detail}</p>
      <button onClick={() => location.reload()}>もう一度試す</button>
    </main>
  )
}
