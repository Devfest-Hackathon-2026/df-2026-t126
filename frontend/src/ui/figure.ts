// 人の絵を SVG に描く。太い黒の縁と、右下にずらした影を付ける（「ぷっくり」）。
// 姿勢は関節ごとのばね（PoseSpring）を通すので、急に切り替えてもなめらかに動く。

import { PoseSpring, Spring, type Point, type Pose } from './pose'

export const COLORS = {
  bg: '#EFE2D9',
  ink: '#1B1B1B',
  blue: '#1E58EE',
  pink: '#FCB4C0',
  orange: '#FF5936',
  soft: '#E3D7CE',
  paper: '#FFFFFF',
  robot: '#CDBDF0',
}

/** 役割ごとの色。人A は青、人B はピンク、人C はオレンジ */
export const ROLE_COLOR = { A: COLORS.blue, B: COLORS.pink, C: COLORS.orange } as const
/** 役割を選ぶ前の人の色 */
export const NO_ROLE_COLOR = '#B8ADA4'

const NS = 'http://www.w3.org/2000/svg'

export function svgEl<K extends keyof SVGElementTagNameMap>(
  tag: K,
  attrs: Record<string, string | number>,
  parent?: Element,
): SVGElementTagNameMap[K] {
  const e = document.createElementNS(NS, tag)
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, String(v))
  parent?.appendChild(e)
  return e
}

const fmt = (p: Point) => `${p[0].toFixed(1)} ${p[1].toFixed(1)}`

export interface FigureOptions {
  /** 足元を中心にした傾き（度） */
  rotation?: number
  /** 左右反転（左を向く） */
  flip?: boolean
  /** 縦のつぶれ（着地のときなど） */
  squash?: number
}

export class Figure {
  readonly group: SVGGElement
  private readonly paths: SVGPathElement[] = []
  private readonly heads: SVGCircleElement[] = []
  private readonly fillPath: SVGPathElement
  private readonly fillHead: SVGCircleElement
  private readonly spring = new PoseSpring()
  private readonly turn = new Spring()
  pose: Pose | null = null
  x = 0
  y = 0
  private sx = 1
  private readonly scale: number

  constructor(parent: Element, color: string, scale: number) {
    this.scale = scale
    this.group = svgEl('g', {}, parent)
    const shadow = svgEl('g', { transform: 'translate(4 4)' }, this.group)
    const stroke = (p: Element, c: string, w: number) =>
      svgEl('path', { fill: 'none', stroke: c, 'stroke-width': w, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, p)
    this.paths.push(stroke(shadow, COLORS.ink, 19))
    this.heads.push(svgEl('circle', { r: 14, fill: COLORS.ink }, shadow))
    this.paths.push(stroke(this.group, COLORS.ink, 19))
    this.heads.push(svgEl('circle', { r: 14, fill: COLORS.ink }, this.group))
    this.fillPath = stroke(this.group, color, 13)
    this.fillHead = svgEl('circle', { r: 11, fill: color }, this.group)
    this.paths.push(this.fillPath)
    this.heads.push(this.fillHead)
  }

  setColor(color: string) {
    this.fillPath.setAttribute('stroke', color)
    this.fillHead.setAttribute('fill', color)
  }

  setVisible(visible: boolean) {
    this.group.style.display = visible ? '' : 'none'
  }

  set(target: Pose, x: number, y: number, dt: number, options: FigureOptions = {}) {
    const { pose, rotation } = this.spring.step(target, options.rotation ?? 0, dt)
    let sx = this.turn.step(options.flip ? -1 : 1, dt)
    // 向きを変える途中で、線にならないようにする
    if (Math.abs(sx) < 0.15) sx = sx < 0 ? -0.15 : 0.15
    this.pose = pose
    this.x = x
    this.y = y
    this.sx = sx
    const q = pose
    const d =
      `M${fmt(q.n)}L${fmt(q.p)}` +
      `M${fmt(q.n)}L${fmt(q.a[0])}L${fmt(q.a[1])}` +
      `M${fmt(q.n)}L${fmt(q.b[0])}L${fmt(q.b[1])}` +
      `M${fmt(q.p)}L${fmt(q.l[0])}L${fmt(q.l[1])}` +
      `M${fmt(q.p)}L${fmt(q.r[0])}L${fmt(q.r[1])}`
    for (const path of this.paths) path.setAttribute('d', d)
    for (const head of this.heads) {
      head.setAttribute('cx', q.h[0].toFixed(1))
      head.setAttribute('cy', q.h[1].toFixed(1))
    }
    const s = this.scale
    this.group.setAttribute(
      'transform',
      `translate(${x.toFixed(1)} ${y.toFixed(1)}) rotate(${rotation.toFixed(2)}) scale(${(sx * s).toFixed(3)} ${(s * (options.squash ?? 1)).toFixed(3)})`,
    )
  }

  /** 姿勢の中の点を、SVG 全体の座標にする（傾きは無視する） */
  at(point: Point): Point {
    return [this.x + this.sx * this.scale * point[0], this.y + this.scale * point[1]]
  }
}
