// 画面に出す人の絵の場面。どれも viewBox 0 0 200 130 の SVG に描き、毎フレーム update を呼ぶ。
//   start  … 青い人がジェスチャー、ピンクの人が考えて揺れ、「？」が浮く（カーソルで揺れが大きくなる）
//   lobby  … 参加した人が横・上・下から合流し、手を振る
//   think  … 青い人が汗をかいて悩み、ピンクの人がペンで書く
//   laugh  … ロボットの答えを見て、3人が笑う
//   robot  … ロボットが絵を描いている（AI を待つ間）

import { COLORS, Figure, svgEl } from './figure'
import { POSES, blend, clamp01, cycle, easeInOut, lerp, swing, walk, wave, type Pose } from './pose'

export type SceneKind = 'start' | 'lobby' | 'think' | 'laugh' | 'robot'

export interface LobbyPerson {
  id: string
  name: string
  color: string
  /** 自分なら、名前を青で出す */
  self?: boolean
}

export interface Scene {
  update(t: number, dt: number): void
  setHover?(on: boolean): void
  setPeople?(people: LobbyPerson[]): void
}

// 外部のフォントは使わず、端末の書体で描く（index.css の --font-head・--font-body と同じ並び）
const JP_FONTS = "'Hiragino Sans', 'Hiragino Kaku Gothic ProN', 'Noto Sans JP', 'Noto Sans CJK JP', 'Yu Gothic', 'YuGothic', Meiryo"
const HEAD_FONT = `${JP_FONTS}, system-ui, sans-serif`
const BODY_FONT = `system-ui, -apple-system, ${JP_FONTS}, sans-serif`
const { ink: INK, blue: BLUE, pink: PINK, orange: ORANGE, soft: SOFT, paper: PAPER } = COLORS

function text(parent: Element, content: string, attrs: Record<string, string | number>) {
  const t = svgEl('text', { 'font-family': HEAD_FONT, 'font-weight': 900, 'text-anchor': 'middle', ...attrs }, parent)
  t.textContent = content
  return t
}

/** ロボット。体の部品の色を変えられるように返す */
function robot(parent: Element, color: string) {
  const g = svgEl('g', {}, parent)
  const shadow = svgEl('g', { transform: 'translate(4 4)' }, g)
  const shapes: [number, number, number, number, number][] = [
    [30, 112, 8, 12, 2],
    [44, 112, 8, 12, 2],
    [26, 74, 30, 40, 6],
    [22, 44, 38, 28, 8],
  ]
  for (const [x, y, w, h, rx] of shapes) svgEl('rect', { x, y, width: w, height: h, rx, fill: INK }, shadow)
  const body = shapes.map(([x, y, w, h, rx]) =>
    svgEl('rect', { x, y, width: w, height: h, rx, fill: color, stroke: INK, 'stroke-width': 3 }, g),
  )
  svgEl('line', { x1: 41, y1: 44, x2: 41, y2: 34, stroke: INK, 'stroke-width': 3 }, g)
  const lamp = svgEl('circle', { cx: 41, cy: 32, r: 4.5, fill: ORANGE }, g)
  svgEl('circle', { cx: 33, cy: 57, r: 3.5, fill: INK }, g)
  svgEl('circle', { cx: 49, cy: 57, r: 3.5, fill: INK }, g)
  svgEl('path', { d: 'M35 64q6 5 12 0', fill: 'none', stroke: INK, 'stroke-width': 2.5, 'stroke-linecap': 'round' }, g)
  return { g, body, lamp }
}

function startScene(svg: SVGSVGElement): Scene {
  const arcs = svgEl('path', { fill: 'none', stroke: ORANGE, 'stroke-width': 2.5, 'stroke-linecap': 'round' }, svg)
  const blue = new Figure(svg, BLUE, 0.95)
  const pink = new Figure(svg, PINK, 0.95)
  const q1 = text(svg, '？', { x: 180, y: 30, 'font-size': 30, fill: ORANGE })
  const q2 = text(svg, '？', { x: 194, y: 10, 'font-size': 15, fill: ORANGE })
  let hover = 0
  let target = 0
  let sway = 0
  let float = 0
  return {
    setHover: (on) => (target = on ? 1 : 0),
    update(t, dt) {
      hover += (target - hover) * Math.min(1, dt * 4)
      sway += (dt * Math.PI * 2) / (2.4 - 1.3 * hover)
      float += (dt * Math.PI * 2) / (1.6 - 0.8 * hover)
      blue.set(cycle(t, [POSES.gesture1, POSES.gesture2, POSES.gesture3], 0.85), 62, 124 - 1.6 * swing(t, 0.425), dt)
      const pose = blue.pose
      if (pose) {
        const [lx, ly] = blue.at(pose.a[1])
        const [rx, ry] = blue.at(pose.b[1])
        arcs.setAttribute(
          'd',
          `M${lx - 7} ${ly - 7}q-5 7 0 14M${lx - 12} ${ly - 12}q-9 12 0 24M${rx + 7} ${ry - 7}q5 7 0 14M${rx + 12} ${ry - 12}q9 12 0 24`,
        )
        arcs.setAttribute('opacity', (0.35 + 0.65 * swing(t, 0.5)).toFixed(2))
      }
      pink.set(POSES.think, 150, 124, dt, { rotation: (3 + 7 * hover) * Math.sin(sway) })
      const dy = -(4 + 6 * hover) * Math.sin(float)
      q1.setAttribute('transform', `translate(0 ${dy.toFixed(1)}) rotate(${(12 * hover * Math.sin(float * 1.3)).toFixed(1)} 180 20)`)
      q2.setAttribute('transform', `translate(0 ${(-dy * 0.7).toFixed(1)}) rotate(${(15 + 15 * hover * Math.sin(float)).toFixed(1)} 194 6)`)
    },
  }
}

type JoinMode = 'side' | 'top' | 'bottom'
const SLOT_X = [36, 100, 164]
/** 立つ高さ。下の台（y=106）の上に足が乗る */
const GROUND = 101
const JOIN_SECONDS = 5.2

interface Slot {
  id: string | null
  figure: Figure
  label: SVGTextElement
  mark: SVGTextElement
  joinAt: number | null
  mode: JoinMode
}

/** 合流のしかたは、入った順で決める。1人目（ホスト）は歩いて、2人目は上から落ちて、3人目は下から登ってくる */
const JOIN_MODES: JoinMode[] = ['side', 'top', 'bottom']

function lobbyScene(svg: SVGSVGElement): Scene {
  const world = svgEl('g', {}, svg)
  const dust = [0, 1, 2].map(() => svgEl('circle', { fill: 'none', stroke: INK, 'stroke-width': 2, opacity: 0 }, world))
  const figures = SLOT_X.map(() => new Figure(world, BLUE, 0.78))
  // 下の台。下からよじ登る人は、この台に隠れている
  svgEl('rect', { x: -20, y: 106, width: 240, height: 30, fill: SOFT }, world)
  svgEl('line', { x1: -20, y1: 106, x2: 220, y2: 106, stroke: INK, 'stroke-width': 3 }, world)
  const slots: Slot[] = SLOT_X.map((x, i) => ({
    id: null,
    figure: figures[i],
    label: svgEl('text', { x, y: 122, 'font-size': 10, 'font-weight': 700, fill: INK, 'text-anchor': 'middle', 'font-family': BODY_FONT }, world),
    mark: text(world, '！', { 'font-size': 16, fill: ORANGE, opacity: 0 }),
    joinAt: null,
    mode: 'side',
  }))
  for (const slot of slots) slot.figure.setVisible(false)
  let started = false
  let now = 0

  return {
    setPeople(people) {
      slots.forEach((slot, i) => {
        const person = people[i]
        if (!person) {
          slot.id = null
          slot.joinAt = null
          slot.figure.setVisible(false)
          slot.label.textContent = ''
          return
        }
        if (slot.id !== person.id) {
          slot.id = person.id
          // 後から来た人は合流の動きをする。最初からいた人は動かないが、
          // 自分だけは、ロビーに入った時に自分の合流が見えるようにする
          if (started || person.self) {
            // 落ちる・登るは、前の人が手を貸す動き。前の人がまだ合流の途中なら、
            // それが終わってから始める（続けて入ると、手を貸す人がいなくて歩きに戻っていた）
            const prev = slots[i - 1]
            const after = prev && prev.joinAt !== null ? prev.joinAt + JOIN_SECONDS + 0.1 : now
            slot.joinAt = Math.max(now, after)
            slot.mode = JOIN_MODES[i] ?? 'side'
          }
        }
        slot.figure.setVisible(true)
        slot.figure.setColor(person.color)
        slot.label.setAttribute('fill', person.self ? BLUE : INK)
        slot.label.textContent = person.name.length > 6 ? `${person.name.slice(0, 6)}…` : person.name
      })
      started = true
    },
    update(t, dt) {
      now = t
      const present = slots.map((s) => s.id !== null)
      const state = slots.map((_, i) => ({
        x: SLOT_X[i],
        y: GROUND - 0.6 * swing(t + i * 0.7, 2.2),
        pose: POSES.stand as Pose,
        flip: false,
        squash: 1,
        mark: 0,
      }))
      let dustAt = -1
      let shake = 0
      slots.forEach((slot, j) => {
        // 合流の順番を待っている人は、名前も出さない
        slot.label.setAttribute('opacity', slot.joinAt !== null && t < slot.joinAt ? '0' : '1')
        if (slot.joinAt === null || !present[j]) return
        const u = t - slot.joinAt
        // 前の人の合流が終わるのを待っている間は、画面の外に置く
        if (u < 0) {
          state[j].x = -999
          return
        }
        if (u > JOIN_SECONDS) {
          slot.joinAt = null
          return
        }
        const me = state[j]
        const X = SLOT_X[j]
        const helperIndex = j > 0 && present[j - 1] && slots[j - 1].joinAt === null ? j - 1 : -1
        const helper = helperIndex >= 0 ? state[helperIndex] : null
        const H0 = helperIndex >= 0 ? SLOT_X[helperIndex] : 0
        const reachX = X - 46
        const others = state.filter((_, i) => i !== j && present[i])
        const between = (a: number, b: number) => u >= a && u < b
        let waveFrom = 9
        const jump = (start: number, height: number) => {
          const k = u - start
          if (k < 0.08) return 3 * (k / 0.08)
          return -height * Math.sin(Math.PI * clamp01((k - 0.08) / 0.38)) + (k < 0.5 ? 3 * (1 - clamp01((k - 0.08) / 0.1)) : 0)
        }
        const surprise = (start: number, end: number, height: number) => {
          if (!between(start, end)) return
          for (const o of others) {
            o.pose = POSES.surprised
            o.y += jump(start, height)
            o.mark = 1
          }
        }
        me.flip = j > 0
        if (slot.mode === 'side' || !helper) {
          const walkEnd = 1.6
          if (u < walkEnd) {
            const k = u / walkEnd
            me.x = lerp(236, X, 1 - Math.pow(1 - k, 2))
            me.pose = walk(u)
            me.y = GROUND - 1.6 * Math.abs(Math.sin((u * Math.PI) / 0.35))
          } else if (u < 3.4) me.pose = wave(u)
          waveFrom = 1.7
        } else if (slot.mode === 'top') {
          me.flip = false
          if (u < 0.5) {
            me.y = -40 + (GROUND + 40) * Math.pow(u / 0.5, 2)
            me.pose = POSES.surprised
          } else if (u < 2) {
            me.pose = u < 0.62 ? blend(POSES.crouch, POSES.fallen, easeInOut((u - 0.5) / 0.12)) : POSES.fallen
            me.squash = 1 - 0.3 * Math.exp(-7 * (u - 0.5)) * Math.cos(16 * (u - 0.5))
            if (u < 1.1) dustAt = (u - 0.5) / 0.6
            if (u < 0.7) shake = 1 - (u - 0.5) / 0.2
          } else if (u < 2.3) me.pose = blend(POSES.fallen, POSES.fallenReach, easeInOut((u - 2) / 0.3))
          else if (u < 3.1) {
            me.pose = blend(POSES.fallenReach, POSES.stand, easeInOut((u - 2.3) / 0.8))
            me.y = GROUND - 2 * Math.sin(Math.PI * clamp01((u - 2.3) / 0.8))
          } else {
            me.flip = true
            if (u < 4.7) me.pose = wave(u)
          }
          surprise(0.55, 1.3, 8)
          if (between(1.3, 2)) {
            helper.x = lerp(H0, reachX, easeInOut((u - 1.3) / 0.7))
            helper.pose = walk(u)
          } else if (between(2, 2.3)) {
            helper.x = reachX
            helper.pose = blend(POSES.stand, POSES.reach, easeInOut((u - 2) / 0.3))
          } else if (between(2.3, 3.1)) {
            helper.x = reachX - 4 * easeInOut((u - 2.3) / 0.8)
            helper.pose = blend(POSES.reach, POSES.pull, easeInOut((u - 2.3) / 0.8))
          } else if (between(3.1, 3.7)) {
            helper.x = lerp(reachX - 4, H0, easeInOut((u - 3.1) / 0.6))
            helper.pose = walk(u)
          }
          waveFrom = 3.5
        } else {
          me.flip = false
          if (u < 0.5) {
            me.pose = POSES.climb
            me.y = lerp(204, 192, easeInOut(u / 0.5))
          } else if (u < 1.4) {
            me.pose = blend(POSES.climb, POSES.climbHold, easeInOut((u - 0.5) / 0.9))
            me.y = lerp(192, 160, easeInOut((u - 0.5) / 0.9)) + 2 * Math.sin(Math.PI * clamp01((u - 0.5) / 0.45))
          } else if (u < 2.4) {
            me.pose = POSES.climbHold
            me.y = 160 + 0.6 * Math.sin(u * 9)
          } else if (u < 2.7) {
            me.pose = blend(POSES.climbHold, POSES.climbReach, easeInOut((u - 2.4) / 0.3))
            me.y = 160
          } else if (u < 3.5) {
            me.pose = blend(POSES.climbReach, POSES.stand, easeInOut((u - 2.7) / 0.8))
            me.y = lerp(160, GROUND, easeInOut((u - 2.7) / 0.8))
          } else {
            me.flip = true
            if (u < 5) me.pose = wave(u)
          }
          surprise(1.3, 1.9, 7)
          const downX = X - 42
          if (between(1.9, 2.4)) {
            helper.x = lerp(H0, downX, easeInOut((u - 1.9) / 0.5))
            helper.pose = walk(u)
          } else if (between(2.4, 2.7)) {
            helper.x = downX
            helper.pose = blend(POSES.stand, POSES.reachDown, easeInOut((u - 2.4) / 0.3))
          } else if (between(2.7, 3.5)) {
            helper.x = downX - 6 * easeInOut((u - 2.7) / 0.8)
            helper.pose = blend(POSES.reachDown, POSES.pull, easeInOut((u - 2.7) / 0.8))
          } else if (between(3.5, 4)) {
            helper.x = lerp(downX - 6, H0, easeInOut((u - 3.5) / 0.5))
            helper.pose = walk(u)
          }
          waveFrom = 3.8
        }
        // 先にいた人は、合流した人に手を振り返す
        others.forEach((o, k) => {
          if (u >= waveFrom + k * 0.2 && u < waveFrom + 1 + k * 0.2) o.pose = wave(u + 0.1 * (k + 1))
        })
      })
      slots.forEach((slot, i) => {
        if (!present[i]) return
        const s = state[i]
        slot.figure.set(s.pose, s.x, s.y, dt, { flip: s.flip, squash: s.squash })
        const head = slot.figure.pose ? slot.figure.at(slot.figure.pose.h) : [s.x, s.y - 70]
        slot.mark.setAttribute('x', String(head[0] + 10))
        slot.mark.setAttribute('y', String(head[1] - 10))
        slot.mark.setAttribute('opacity', String(s.mark))
      })
      world.setAttribute('transform', shake > 0 ? `translate(${(3 * shake * Math.sin(t * 90)).toFixed(1)} ${(2 * shake * Math.cos(t * 70)).toFixed(1)})` : '')
      const landed = slots.find((s) => s.joinAt !== null && s.mode === 'top')
      const cx = landed ? SLOT_X[slots.indexOf(landed)] : 164
      dust.forEach((d, i) => {
        if (dustAt < 0) return d.setAttribute('opacity', '0')
        const e = 1 - Math.pow(1 - dustAt, 3)
        d.setAttribute('cx', String(cx + (i - 1) * (14 + 10 * e)))
        d.setAttribute('cy', String(GROUND - (i === 1 ? 6 : 0) - 4 * e))
        d.setAttribute('r', String(3 + 6 * e))
        d.setAttribute('opacity', (1 - dustAt).toFixed(2))
      })
    },
  }
}

function thinkScene(svg: SVGSVGElement): Scene {
  const blue = new Figure(svg, BLUE, 0.9)
  const drops = [0, 1].map(() => svgEl('path', { fill: BLUE }, svg))
  svgEl('circle', { cx: 74, cy: 22, r: 3, fill: PAPER, stroke: INK, 'stroke-width': 2 }, svg)
  svgEl('circle', { cx: 84, cy: 14, r: 4.5, fill: PAPER, stroke: INK, 'stroke-width': 2 }, svg)
  svgEl('ellipse', { cx: 116, cy: 14, rx: 26, ry: 12, fill: PAPER, stroke: INK, 'stroke-width': 2 }, svg)
  const scribble = svgEl('path', { d: 'M100 15q4-6 8 0t8 0t8 0t8 0', fill: 'none', stroke: INK, 'stroke-width': 2, 'stroke-linecap': 'round', 'stroke-dasharray': 60 }, svg)
  const pink = new Figure(svg, PINK, 0.9)
  const paper = svgEl('g', { transform: 'rotate(8 158 73)' }, svg)
  svgEl('rect', { x: 146, y: 58, width: 24, height: 30, rx: 2, fill: PAPER, stroke: INK, 'stroke-width': 2 }, paper)
  const lines = [66, 72, 78].map((y) => svgEl('path', { d: `M150 ${y}h14`, stroke: 'rgba(27,27,27,.5)', 'stroke-width': 2, 'stroke-dasharray': 14 }, paper))
  const pen = svgEl('line', { stroke: ORANGE, 'stroke-width': 3, 'stroke-linecap': 'round' }, svg)
  const writing = (t: number): Pose => ({
    ...POSES.think,
    h: [3 + Math.sin(t * 2), -89],
    n: [0, -76],
    p: [0, -42],
    a: [[-10, -60], [8, -58]],
    b: [[16, -62], [13 + 3 * Math.cos(t * 9), -53 + 1.5 * Math.sin(t * 18)]],
    l: POSES.stand.l,
    r: POSES.stand.r,
  })
  return {
    update(t, dt) {
      blue.set(cycle(t, [POSES.headHold1, POSES.headHold2, POSES.headHold1, POSES.headHold3], 1), 56, 124, dt, { rotation: 1.5 * Math.sin(t * 3) })
      drops.forEach((d, i) => {
        const ph = ((t + i * 0.7) % 1.4) / 1.4
        const x = 78 + 8 * i
        const y = 32 + 40 * ph * ph
        d.setAttribute('d', `M${x} ${(y - 5).toFixed(1)}q4 6 0 9q-4-3 0-9z`)
        d.setAttribute('opacity', (ph < 0.1 ? ph * 10 : 1 - ph).toFixed(2))
      })
      scribble.setAttribute('stroke-dashoffset', (60 * (1 - (t % 1.6) / 1.6)).toFixed(1))
      pink.set(writing(t), 150, 124, dt)
      if (pink.pose) {
        const [hx, hy] = pink.at(pink.pose.b[1])
        pen.setAttribute('x1', hx.toFixed(1))
        pen.setAttribute('y1', hy.toFixed(1))
        pen.setAttribute('x2', (hx + 8).toFixed(1))
        pen.setAttribute('y2', (hy - 11).toFixed(1))
      }
      const ph = ((t % 3) / 3) * 3.4
      lines.forEach((l, i) => l.setAttribute('stroke-dashoffset', (14 * (1 - clamp01(ph - i))).toFixed(1)))
    },
  }
}

function laughScene(svg: SVGSVGElement): Scene {
  const r = robot(svg, COLORS.robot)
  svgEl('path', { d: 'M56 86L66 80', stroke: INK, 'stroke-width': 6, 'stroke-linecap': 'round' }, r.g)
  const card = svgEl('g', { transform: 'rotate(-6 84 74)' }, r.g)
  svgEl('rect', { x: 62, y: 54, width: 46, height: 38, rx: 3, fill: PAPER, stroke: INK, 'stroke-width': 2.5 }, card)
  svgEl('circle', { cx: 82, cy: 80, r: 8, fill: 'none', stroke: INK, 'stroke-width': 2 }, card)
  svgEl('circle', { cx: 82, cy: 66, r: 5, fill: 'none', stroke: INK, 'stroke-width': 2 }, card)
  svgEl('path', { d: 'M87 65l6 2-6 2z', fill: ORANGE }, card)
  const people = [new Figure(svg, BLUE, 0.72), new Figure(svg, PINK, 0.72), new Figure(svg, ORANGE, 0.72)]
  const lines = people.map(() => [0, 1, 2, 3].map(() => svgEl('line', { stroke: ORANGE, 'stroke-width': 2.2, 'stroke-linecap': 'round' }, svg)))
  const haha = [0, 1].map(() => text(svg, 'ハハ', { 'font-size': 11, fill: ORANGE }))
  const ANGLES = [-140, -115, -65, -40].map((a) => (a * Math.PI) / 180)
  return {
    update(t, dt) {
      const bob = -3 * Math.sin((t * Math.PI * 2) / 1.4) - 0.8 * Math.sin((t * Math.PI * 2) / 0.7)
      r.g.setAttribute('transform', `translate(0 ${bob.toFixed(1)}) rotate(${(1.5 * Math.sin((t * Math.PI * 2) / 1.4 - 0.6)).toFixed(2)} 41 118)`)
      r.lamp.setAttribute('opacity', (0.4 + 0.6 * swing(t, 0.8)).toFixed(2))
      const o0 = swing(t, 0.55)
      const o1 = swing(t + 0.1, 0.42)
      const o2 = swing(t, 0.36)
      people[0].set(blend(POSES.laugh1, POSES.laugh2, o0), 124, 124 - 2 * o0, dt, { rotation: 6 + 3 * o0 })
      people[1].set(blend(POSES.belly1, POSES.belly2, o1), 156, 124 - 2 * o1, dt)
      people[2].set(blend(POSES.clap1, POSES.clap2, o2), 186, 124 - 1.5 * o2, dt, { rotation: 5 + 2 * o2 })
      people.forEach((f, i) => {
        if (!f.pose) return
        const [hx, hy] = f.at(f.pose.h)
        const ph = swing(t + i * 0.13, 0.32)
        lines[i].forEach((l, j) => {
          const r1 = 12 + 3 * ph
          const r2 = r1 + 5 + 2 * ph
          l.setAttribute('x1', (hx + r1 * Math.cos(ANGLES[j])).toFixed(1))
          l.setAttribute('y1', (hy + r1 * Math.sin(ANGLES[j])).toFixed(1))
          l.setAttribute('x2', (hx + r2 * Math.cos(ANGLES[j])).toFixed(1))
          l.setAttribute('y2', (hy + r2 * Math.sin(ANGLES[j])).toFixed(1))
          l.setAttribute('opacity', (0.45 + 0.55 * ph).toFixed(2))
        })
      })
      ;[0, 2].forEach((i, k) => {
        const f = people[i]
        if (!f.pose) return
        const [hx, hy] = f.at(f.pose.h)
        haha[k].setAttribute('x', (hx + (k ? 8 : -6)).toFixed(1))
        haha[k].setAttribute('y', (hy - 24 - 2 * k - 3 * swing(t + k * 0.2, 0.5)).toFixed(1))
      })
    },
  }
}

function robotScene(svg: SVGSVGElement): Scene {
  const easel = svgEl('g', {}, svg)
  svgEl('path', { d: 'M118 124L130 40M178 124L166 40', stroke: INK, 'stroke-width': 3, 'stroke-linecap': 'round' }, easel)
  svgEl('rect', { x: 112, y: 30, width: 72, height: 58, rx: 3, fill: PAPER, stroke: INK, 'stroke-width': 2.5 }, easel)
  const drawing = svgEl('path', {
    d: 'M134 72c-8 0-8-14 2-14c-6-10 12-14 14-4c10-2 12 12 2 14c4 8-10 12-14 6c-2 0-4-1-4-2z',
    fill: 'none',
    stroke: BLUE,
    'stroke-width': 2.5,
    'stroke-linecap': 'round',
    'stroke-dasharray': 120,
  }, easel)
  const r = robot(svg, COLORS.robot)
  r.g.setAttribute('transform', 'translate(30 0)')
  const arm = svgEl('g', {}, r.g)
  svgEl('path', { d: 'M56 86L76 80', stroke: INK, 'stroke-width': 6, 'stroke-linecap': 'round' }, arm)
  svgEl('path', { d: 'M76 80l8-10', stroke: ORANGE, 'stroke-width': 3, 'stroke-linecap': 'round' }, arm)
  return {
    update(t) {
      arm.setAttribute('transform', `rotate(${(14 * Math.sin(t * 12)).toFixed(1)} 56 86)`)
      r.lamp.setAttribute('opacity', (0.4 + 0.6 * swing(t, 0.6)).toFixed(2))
      drawing.setAttribute('stroke-dashoffset', (120 * (1 - ((t % 3) / 3))).toFixed(1))
    },
  }
}

export function createScene(kind: SceneKind, svg: SVGSVGElement): Scene {
  switch (kind) {
    case 'start':
      return startScene(svg)
    case 'lobby':
      return lobbyScene(svg)
    case 'think':
      return thinkScene(svg)
    case 'laugh':
      return laughScene(svg)
    case 'robot':
      return robotScene(svg)
  }
}
