// 画面が切り替わるとき、オレンジの帯が横切り、帯で隠れている間に次の画面に変える。
// 帯が画面を覆うまでの間は、前の画面を最後の状態のまま見せておく。

import { useEffect, useState, type ReactNode } from 'react'

/** 帯が画面を覆いきるまでの時間（index.css の .wipe と合わせる） */
const COVER_MS = 380

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

interface Shown {
  key: string
  node: ReactNode
}

export function Wipe({ viewKey, children }: { viewKey: string; children: ReactNode }) {
  const [shown, setShown] = useState<Shown>({ key: viewKey, node: children })
  const [pending, setPending] = useState<string | null>(null)
  const [wipes, setWipes] = useState(0)

  // 描画中に、表示する中身を合わせる（React の「props の変化に合わせて state を直す」書き方）
  if (viewKey === shown.key) {
    if (shown.node !== children) setShown({ key: viewKey, node: children })
  } else if (reducedMotion() || shown.key === 'loading') {
    // 読み込み中からの切り替えと、動きを減らす設定のときは、帯を出さずにすぐ変える
    setShown({ key: viewKey, node: children })
  } else if (pending !== viewKey) {
    setPending(viewKey)
    setWipes((n) => n + 1)
  }

  // 画面が変わったら、いちばん上から見せる
  useEffect(() => {
    window.scrollTo(0, 0)
  }, [shown.key])

  useEffect(() => {
    if (pending === null) return
    const timer = setTimeout(() => {
      setShown({ key: pending, node: null })
      setPending(null)
    }, COVER_MS)
    return () => clearTimeout(timer)
  }, [pending])

  return (
    <>
      {viewKey === shown.key ? children : shown.node}
      {wipes > 0 && (
        <div key={wipes} className="wipe" aria-hidden="true" onAnimationEnd={() => setWipes(0)}>
          <span className="en">GESTURE RELAY</span>
        </div>
      )}
    </>
  )
}
