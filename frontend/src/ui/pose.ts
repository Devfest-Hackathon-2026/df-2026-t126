// 人の絵（ぷっくりした棒人間）の姿勢と、その動かし方。
// 姿勢は関節の位置で持ち、足元を原点、上をマイナスにする（体の高さはおよそ110）。
// 姿勢の間をつなぐときは、関節の角度でつなぐ（腕や脚の長さが途中で縮まない）。

export type Point = [number, number]
type Limb = [Point, Point] // [ひじ・ひざ, 手・足]

export interface Pose {
  /** 頭の中心 */
  h: Point
  /** 首（肩の高さ） */
  n: Point
  /** 腰 */
  p: Point
  /** 左腕・右腕・左脚・右脚 */
  a: Limb
  b: Limb
  l: Limb
  r: Limb
}

const pose = (h: Point, n: Point, p: Point, a: Limb, b: Limb, l: Limb, r: Limb): Pose => ({
  h,
  n,
  p,
  a,
  b,
  l,
  r,
})

const LEFT_LEG: Limb = [
  [-6, -22],
  [-8, 0],
]
const RIGHT_LEG: Limb = [
  [6, -22],
  [8, 0],
]

export const POSES = {
  stand: pose([0, -90], [0, -76], [0, -42], [[-10, -60], [-12, -44]], [[10, -60], [12, -44]], LEFT_LEG, RIGHT_LEG),
  gesture1: pose([0, -90], [0, -76], [2, -42], [[-18, -90], [-8, -110]], [[20, -72], [38, -84]], [[-12, -22], [-20, 0]], [[14, -22], [20, 0]]),
  gesture2: pose([0, -90], [0, -76], [-2, -42], [[-20, -72], [-38, -84]], [[18, -90], [8, -110]], [[-14, -22], [-20, 0]], [[12, -22], [20, 0]]),
  gesture3: pose([0, -91], [0, -77], [0, -42], [[-24, -90], [-6, -108]], [[24, -90], [6, -108]], [[-12, -22], [-18, 0]], [[12, -22], [18, 0]]),
  think: pose([5, -89], [0, -76], [0, -42], [[-12, -58], [2, -52]], [[14, -62], [8, -82]], LEFT_LEG, RIGHT_LEG),
  wave: pose([0, -90], [0, -76], [0, -42], [[-10, -60], [-12, -44]], [[18, -82], [24, -102]], LEFT_LEG, RIGHT_LEG),
  walkA: pose([0, -90], [0, -76], [0, -42], [[-8, -60], [-15, -47]], [[8, -60], [15, -47]], [[-5, -21], [-13, 0]], [[5, -21], [13, 0]]),
  walkB: pose([0, -90], [0, -76], [0, -42], [[8, -60], [15, -47]], [[-8, -60], [-15, -47]], [[5, -21], [13, 0]], [[-5, -21], [-13, 0]]),
  surprised: pose([0, -93], [0, -79], [0, -44], [[-18, -84], [-26, -100]], [[18, -84], [26, -100]], [[-10, -22], [-14, 0]], [[10, -22], [14, 0]]),
  crouch: pose([0, -82], [0, -68], [0, -36], [[-12, -54], [-14, -40]], [[12, -54], [14, -40]], [[-10, -18], [-8, 0]], [[10, -18], [8, 0]]),
  fallen: pose([-8, -60], [-6, -47], [0, -14], [[-16, -30], [-20, -12]], [[4, -32], [-6, -14]], [[14, -18], [30, -4]], [[12, -14], [28, 0]]),
  fallenReach: pose([-8, -61], [-6, -47], [0, -14], [[-18, -52], [-30, -64]], [[4, -32], [-6, -14]], [[14, -18], [30, -4]], [[12, -14], [28, 0]]),
  reach: pose([4, -88], [2, -75], [0, -42], [[-10, -60], [-14, -46]], [[18, -66], [34, -58]], LEFT_LEG, RIGHT_LEG),
  reachDown: pose([16, -74], [10, -64], [0, -40], [[-2, -50], [-6, -36]], [[22, -48], [34, -30]], [[-6, -20], [-8, 0]], [[6, -20], [8, 0]]),
  pull: pose([-6, -88], [-4, -75], [2, -42], [[-14, -60], [-18, -48]], [[14, -64], [30, -60]], [[-10, -22], [-14, 0]], [[8, -22], [12, 0]]),
  climb: pose([0, -90], [0, -76], [0, -42], [[-12, -96], [-16, -112]], [[12, -96], [16, -112]], LEFT_LEG, RIGHT_LEG),
  climbHold: pose([0, -90], [0, -76], [0, -42], [[-24, -82], [-14, -68]], [[24, -82], [14, -68]], [[-6, -22], [-10, -2]], [[6, -22], [10, -2]]),
  climbReach: pose([-2, -90], [0, -76], [0, -42], [[-20, -90], [-30, -100]], [[24, -82], [14, -68]], [[-6, -22], [-10, -2]], [[6, -22], [10, -2]]),
  headHold1: pose([0, -88], [0, -75], [0, -42], [[-18, -84], [-8, -98]], [[18, -84], [8, -98]], LEFT_LEG, RIGHT_LEG),
  headHold2: pose([3, -88], [1, -75], [0, -42], [[-18, -82], [-6, -96]], [[20, -78], [12, -92]], LEFT_LEG, RIGHT_LEG),
  headHold3: pose([5, -89], [0, -76], [0, -42], [[-12, -58], [4, -56]], [[14, -62], [6, -80]], LEFT_LEG, RIGHT_LEG),
  laugh1: pose([-8, -88], [-4, -75], [2, -42], [[-20, -90], [-26, -106]], [[12, -92], [22, -108]], [[-8, -22], [-12, 0]], [[10, -22], [14, 0]]),
  laugh2: pose([-9, -90], [-5, -76], [2, -42], [[-18, -94], [-20, -112]], [[14, -95], [18, -112]], [[-8, -22], [-12, 0]], [[10, -22], [14, 0]]),
  belly1: pose([12, -80], [7, -68], [0, -40], [[2, -54], [12, -46]], [[16, -56], [18, -46]], [[-4, -20], [-8, 0]], [[6, -20], [10, 0]]),
  belly2: pose([14, -76], [9, -65], [0, -40], [[4, -52], [13, -44]], [[17, -53], [19, -43]], [[-4, -20], [-8, 0]], [[6, -20], [10, 0]]),
  clap1: pose([-4, -89], [-2, -76], [1, -42], [[-12, -62], [2, -72]], [[14, -62], [4, -74]], LEFT_LEG, RIGHT_LEG),
  clap2: pose([-5, -89], [-3, -76], [1, -42], [[-16, -62], [-8, -74]], [[18, -62], [14, -76]], LEFT_LEG, RIGHT_LEG),
} satisfies Record<string, Pose>

export type PoseName = keyof typeof POSES

// ---- 数の道具 ----

const TAU = Math.PI * 2
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t
export const clamp01 = (t: number) => Math.max(0, Math.min(1, t))
/** 始めと終わりがゆっくりになる */
export function easeInOut(t: number): number {
  const x = clamp01(t)
  return x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2
}
/** 0〜1 をなめらかに行き来する。period は1往復の秒数 */
export const swing = (t: number, period: number) => (Math.sin((t * TAU) / period) + 1) / 2
/** 角度の差を -π〜π に収める（遠回りしないため） */
const wrapAngle = (d: number) => ((((d + Math.PI) % TAU) + TAU) % TAU) - Math.PI

// ---- 角度での表し方 ----
// [首x, 首y, 腰x, 腰y, 頭の角度, 頭の距離, 腕・脚ごとに(上の角度, 上の長さ, 下の角度, 下の長さ) ×4, 傾き]

const LIMBS = ['a', 'b', 'l', 'r'] as const
const ANGLE_INDEX = new Set([4, 6, 8, 10, 12, 14, 16, 18, 20])
const ROTATION_INDEX = 22

type Vec = number[]

const segment = (from: Point, to: Point): [number, number] => [
  Math.atan2(to[1] - from[1], to[0] - from[0]),
  Math.hypot(to[0] - from[0], to[1] - from[1]),
]
const polar = (origin: Point, angle: number, length: number): Point => [
  origin[0] + length * Math.cos(angle),
  origin[1] + length * Math.sin(angle),
]
const base = (q: Pose, limb: (typeof LIMBS)[number]) => (limb === 'a' || limb === 'b' ? q.n : q.p)

export function toVec(q: Pose, rotation = 0): Vec {
  const v = [...q.n, ...q.p, ...segment(q.n, q.h)]
  for (const k of LIMBS) {
    v.push(...segment(base(q, k), q[k][0]), ...segment(q[k][0], q[k][1]))
  }
  v.push(rotation)
  return v
}

export function fromVec(v: Vec): { pose: Pose; rotation: number } {
  const n: Point = [v[0], v[1]]
  const p: Point = [v[2], v[3]]
  const limbs = {} as Record<(typeof LIMBS)[number], Limb>
  let i = 6
  for (const k of LIMBS) {
    const origin = k === 'a' || k === 'b' ? n : p
    const joint = polar(origin, v[i], v[i + 1])
    limbs[k] = [joint, polar(joint, v[i + 2], v[i + 3])]
    i += 4
  }
  return { pose: { n, p, h: polar(n, v[4], v[5]), ...limbs }, rotation: v[ROTATION_INDEX] }
}

/** 2つの姿勢の間。腕や脚は角度でつなぐので、長さが保たれる */
export function blend(a: Pose, b: Pose, t: number): Pose {
  const va = toVec(a)
  const vb = toVec(b)
  return fromVec(va.map((x, i) => (ANGLE_INDEX.has(i) ? x + wrapAngle(vb[i] - x) * t : lerp(x, vb[i], t)))).pose
}

/** 並べた姿勢を順に巡る。1つあたり per 秒 */
export function cycle(t: number, poses: Pose[], per: number): Pose {
  const s = t / per
  const i = Math.floor(s) % poses.length
  return blend(poses[i], poses[(i + 1) % poses.length], easeInOut(s % 1))
}

/** 歩く。脚は前後に交互、腕は脚と逆に振る */
export const walk = (t: number) => blend(POSES.walkA, POSES.walkB, swing(t, 0.7))

/** 手を振る。ひじが揺れ、前腕が少し遅れてついてくる */
export function wave(t: number): Pose {
  const v = toVec(POSES.wave)
  const phase = (t * TAU) / 0.6
  v[10] += 0.2 * Math.sin(phase)
  v[12] += 0.5 * Math.sin(phase - 0.8)
  v[4] += 0.06 * Math.sin(phase - 1.2)
  return fromVec(v).pose
}

/**
 * 関節ごとのばね。目標の姿勢に、少し弾みながら追いつく。
 * 姿勢がいきなり切り替わっても、なめらかにつながる。
 */
export class PoseSpring {
  private x: Vec | null = null
  private v: Vec = []
  private readonly stiffness: number
  private readonly damping: number
  constructor(stiffness = 16, damping = 0.7) {
    this.stiffness = stiffness
    this.damping = damping
  }

  step(target: Pose, rotation: number, dt: number): { pose: Pose; rotation: number } {
    const goal = toVec(target, rotation)
    if (!this.x) {
      this.x = goal
      this.v = goal.map(() => 0)
      return fromVec(this.x)
    }
    const x = this.x
    const w = this.stiffness
    const z = this.damping
    const steps = Math.max(1, Math.ceil(dt / 0.008))
    const h = dt / steps
    for (let s = 0; s < steps; s++) {
      for (let i = 0; i < goal.length; i++) {
        const g = ANGLE_INDEX.has(i) ? x[i] + wrapAngle(goal[i] - x[i]) : goal[i]
        const accel = w * w * (g - x[i]) - 2 * z * w * this.v[i]
        this.v[i] += accel * h
        x[i] += this.v[i] * h
      }
    }
    return fromVec(x)
  }
}

/** 1つの数のばね（向きを変えるときの横幅などに使う） */
export class Spring {
  private x: number | null = null
  private v = 0
  private readonly stiffness: number
  private readonly damping: number
  constructor(stiffness = 14, damping = 0.8) {
    this.stiffness = stiffness
    this.damping = damping
  }

  step(goal: number, dt: number): number {
    if (this.x === null) {
      this.x = goal
      return goal
    }
    const steps = Math.max(1, Math.ceil(dt / 0.008))
    const h = dt / steps
    for (let s = 0; s < steps; s++) {
      const accel = this.stiffness ** 2 * (goal - this.x) - 2 * this.damping * this.stiffness * this.v
      this.v += accel * h
      this.x += this.v * h
    }
    return this.x
  }
}
