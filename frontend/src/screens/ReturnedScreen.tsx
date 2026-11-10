// ロビーへ戻った人の待機画面。全員そろうと自動でロビーに切り替わる。

import { Scene } from '../ui/Scene'

export function ReturnedScreen({ onNewRoom }: { onNewRoom: () => void }) {
  return (
    <main className="screen center">
      <div className="heading">
        <p className="en">WAITING</p>
        <h1>ほかの人を待っています</h1>
      </div>
      <Scene kind="start" label="ほかの人を待つ間の絵" />
      <p>全員がロビーへ戻ると、次のゲームを始められます</p>
      <p className="muted">戻らない人がいるときは、新しい部屋を作ってください</p>
      <button className="sub" onClick={onNewRoom}>
        新しい部屋を作る
      </button>
    </main>
  )
}
