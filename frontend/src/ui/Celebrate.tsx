// 結果発表の演出。ギザギザのスタンプと、紙吹雪。

import { useMemo } from 'react'

const BURST_POINTS = (() => {
  const points: string[] = []
  for (let i = 0; i < 36; i++) {
    const r = i % 2 ? 44 : 55
    const a = (Math.PI * i) / 18 - Math.PI / 2
    points.push(`${(56 + r * Math.cos(a)).toFixed(1)},${(56 + r * Math.sin(a)).toFixed(1)}`)
  }
  return points.join(' ')
})()

/** 大きく落ちてきて押されるスタンプ。delay 秒後に押す */
export function Stamp({ label, delay }: { label: string; delay: number }) {
  return (
    <div className="stamp" style={{ animationDelay: `${delay}s` }} role="status">
      <svg viewBox="0 0 112 112" aria-hidden="true">
        <polygon points={BURST_POINTS} fill="var(--orange)" />
      </svg>
      <span>{label}</span>
    </div>
  )
}

const CONFETTI_COLORS = ['var(--blue)', 'var(--pink)', 'var(--orange)', 'var(--ink)']

/** 0〜1 のばらつき。毎回同じ値になるので、描き直しても紙吹雪が飛ばない */
const scatter = (i: number, k: number) => {
  const x = Math.sin(i * 12.9898 + k * 78.233) * 43758.5453
  return x - Math.floor(x)
}

/** 配色の4色で降る紙吹雪。delay 秒後に降り始める */
export function Confetti({ delay }: { delay: number }) {
  const pieces = useMemo(
    () =>
      Array.from({ length: 48 }, (_, i) => ({
        left: scatter(i, 1) * 100,
        size: 6 + scatter(i, 2) * 6,
        delay: delay + scatter(i, 3) * 0.9,
        duration: 1.8 + scatter(i, 4) * 1.4,
        color: CONFETTI_COLORS[i % CONFETTI_COLORS.length],
      })),
    [delay],
  )
  return (
    <div className="confetti" aria-hidden="true">
      {pieces.map((p, i) => (
        <i
          key={i}
          style={{
            left: `${p.left}%`,
            width: p.size,
            height: p.size * 1.6,
            background: p.color,
            animationDelay: `${p.delay}s`,
            animationDuration: `${p.duration}s`,
          }}
        />
      ))}
    </div>
  )
}
