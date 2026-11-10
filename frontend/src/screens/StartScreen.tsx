// 最初の画面。「はじめる」で、名前と同意の画面へ進む。

import { Scene } from '../ui/Scene'

export function StartScreen({ onStart }: { onStart: () => void }) {
  return (
    <main className="start">
      <div className="start-left">
        <div className="start-title">
          <p className="en rise">GESTURE RELAY</p>
          <p className="sub-title rise" style={{ animationDelay: '0.1s' }}>
            ジェスチャー
          </p>
          <h1 className="big">
            <span className="slam">
              伝<em>言</em>
            </span>
          </h1>
        </div>
        <p className="start-lead">
          3人で遊ぶ伝言ゲーム。
          <br />
          手の動きだけで、お題を伝えよう。
        </p>
      </div>
      <div className="start-right">
        <Scene kind="start" label="ジェスチャーをする人と、首をかしげる人" />
        <div className="start-steps">
          <div>
            <span className="dot" style={{ background: 'var(--blue)' }} /> <span className="en">STEP 1</span>
            <b>人A：絵を文章に</b>
          </div>
          <div>
            <span className="dot" style={{ background: 'var(--pink)' }} /> <span className="en">STEP 2</span>
            <b>人B：身ぶりで伝える</b>
          </div>
          <div>
            <span className="dot" style={{ background: 'var(--orange)' }} /> <span className="en">STEP 3</span>
            <b>人C：録画を文章に</b>
          </div>
        </div>
      </div>
      <div className="start-actions">
        <button onClick={onStart}>はじめる</button>
      </div>
    </main>
  )
}
