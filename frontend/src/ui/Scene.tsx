// 人の絵の場面を画面に出す。毎フレーム動かし、カーソルを合わせると反応する場面もある。
// 端末で「視差効果を減らす」が有効なときは、止めた絵にする。

import { useEffect, useRef } from 'react'
import { createScene, type LobbyPerson, type Scene as SceneHandle, type SceneKind } from './scenes'

interface SceneProps {
  kind: SceneKind
  /** 画面読み上げ用の説明 */
  label: string
  /** ロビーの参加者（参加した順） */
  people?: LobbyPerson[]
  className?: string
}

const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches

export function Scene({ kind, label, people, className }: SceneProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const sceneRef = useRef<SceneHandle | null>(null)
  const peopleRef = useRef(people)
  const peopleKey = JSON.stringify(people ?? [])

  // 最新の参加者を覚えておく（場面を作り直したときに使う）
  useEffect(() => {
    peopleRef.current = people
  })

  useEffect(() => {
    const svg = svgRef.current
    if (!svg) return
    svg.replaceChildren()
    const scene = createScene(kind, svg)
    sceneRef.current = scene
    if (peopleRef.current) scene.setPeople?.(peopleRef.current)

    if (reducedMotion()) {
      for (let i = 0; i < 60; i++) scene.update(0.6, 1 / 60)
      return
    }
    const startedAt = performance.now() / 1000
    let last = startedAt
    let frame = 0
    const tick = () => {
      const now = performance.now() / 1000
      scene.update(now - startedAt, Math.min(0.05, now - last))
      last = now
      frame = requestAnimationFrame(tick)
    }
    tick()
    return () => cancelAnimationFrame(frame)
  }, [kind])

  useEffect(() => {
    if (peopleRef.current) sceneRef.current?.setPeople?.(peopleRef.current)
  }, [peopleKey])

  const hover = (on: boolean) => sceneRef.current?.setHover?.(on)

  return (
    <svg
      ref={svgRef}
      className={`scene ${className ?? ''}`}
      viewBox="0 0 200 130"
      role="img"
      aria-label={label}
      onPointerEnter={() => hover(true)}
      onPointerLeave={() => hover(false)}
      onTouchStart={() => {
        hover(true)
        setTimeout(() => hover(false), 1600)
      }}
    />
  )
}
