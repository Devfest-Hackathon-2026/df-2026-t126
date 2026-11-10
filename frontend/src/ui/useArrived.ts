// 要素が画面に入ったかどうか。一度入ったら true のまま（見せ場の演出を、見ている時に1回だけ出すため）。

import { useEffect, useState, type RefObject } from 'react'

export function useArrived(ref: RefObject<Element | null>, ready: boolean): boolean {
  const [arrived, setArrived] = useState(false)

  useEffect(() => {
    const element = ref.current
    if (!ready || arrived || !element) return
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) setArrived(true)
      },
      { threshold: 0.6 },
    )
    observer.observe(element)
    return () => observer.disconnect()
  }, [ref, ready, arrived])

  return arrived
}
