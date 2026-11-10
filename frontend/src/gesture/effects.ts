// ジェスチャーのエフェクト。録画に焼き込まれるだけで、API の約束には含まない。
// どの種類も「手の中心の軌跡」を光る線として描く。線を残すか消すかは、種類とは別に選ぶ。
// 種類を増やすときは、Style（線の描き方）を書いて EFFECTS に足す。

export interface Point {
  x: number
  y: number
}

/** 手1つ分。座標はキャンバスのピクセルで、画面の見た目と同じ向き */
export interface DrawnHand {
  handedness: string
  points: Point[]
}

/** draw で使うキャンバスの機能。テストで偽物を渡せるように、使う分だけ書く */
export type EffectContext = Pick<
  CanvasRenderingContext2D,
  | 'save'
  | 'restore'
  | 'beginPath'
  | 'moveTo'
  | 'lineTo'
  | 'arc'
  | 'closePath'
  | 'stroke'
  | 'fill'
  | 'lineCap'
  | 'lineJoin'
  | 'lineWidth'
  | 'strokeStyle'
  | 'fillStyle'
  | 'globalCompositeOperation'
>

export interface Effect {
  draw(context: EffectContext, hands: DrawnHand[], now: number): void
  /** これから描く線を残すか消すかを変える。すでに描いた線はそのまま */
  setMode(mode: TrailMode): void
  /** 試し描き（録画前）。true の間は「残る」でも線を残さない */
  setPreview(preview: boolean): void
}

/** 0以上1未満の乱数。テストでは決まった値を返す関数を渡す */
export type Random = () => number

export type EffectId =
  | 'neon_blue'
  | 'neon_pink'
  | 'electric_blue'
  | 'electric_green'
  | 'fire'
  | 'smoke'
  | 'energy'
  | 'wave'
  | 'snow'
  | 'wind'
  | 'water'

/** fade は時間がたつと消える。persist は録画の最後まで残る */
export type TrailMode = 'fade' | 'persist'

export interface EffectChoice {
  id: EffectId
  mode: TrailMode
}

// ---- 手の追跡（どの種類でも共通） ----

// 手首と指の付け根。指先と違って、握っても離れても位置が安定している
const PALM_POINTS = [0, 5, 9, 13, 17]
const SMOOTHING = 0.5 // 1に近いほど手に素早く追従し、小さいほどなめらかになる
const TRAIL_MAX_GAP_MS = 500 // 速い動きで検出が抜けても、この時間までは線でつなぐ
const FADE_LIFETIME_MS = 1_000
const PERSIST_MAX_POINTS = 1_500 // 長く動かし続けても重くならないように、古い点から捨てる

interface TrailPoint extends Point {
  time: number
  /** 「残る」で描いた点。時間がたっても消えない */
  keep: boolean
  /** 軌跡の始まりからの長さ。模様の位置を固定するのに使う（古い点が消えても模様がずれない） */
  s: number
}

type Track = TrailPoint[]

function palmCenter(hand: DrawnHand): Point {
  const palm = PALM_POINTS.map((index) => hand.points[index])
  return {
    x: palm.reduce((sum, point) => sum + point.x, 0) / palm.length,
    y: palm.reduce((sum, point) => sum + point.y, 0) / palm.length,
  }
}

function distance(a: Point, b: Point): number {
  return Math.hypot(a.x - b.x, a.y - b.y)
}

/**
 * 今の手を、一番近い軌跡に結びつける。
 * 手を交差させると左右のラベルが入れ替わることがあるので、ラベルは使わない。
 * 速い動きでは点が大きく離れるが、途切れないように距離の上限は設けない。
 */
function matchTracks(tracks: Track[], centers: Point[], now: number) {
  const pairs: { center: number; track: Track; gap: number }[] = []
  centers.forEach((center, index) => {
    for (const track of tracks) {
      const last = track.at(-1)
      if (!last || now - last.time > TRAIL_MAX_GAP_MS) continue
      pairs.push({ center: index, track, gap: distance(center, last) })
    }
  })
  pairs.sort((a, b) => a.gap - b.gap)

  const matched = new Map<number, Track>()
  const used = new Set<Track>()
  for (const { center, track } of pairs) {
    if (matched.has(center) || used.has(track)) continue
    matched.set(center, track)
    used.add(track)
  }
  return matched
}

function createTracker() {
  let tracks: Track[] = []

  /** keep が true なら、今回足す点を残す */
  function update(hands: DrawnHand[], now: number, keep: boolean) {
    const centers = hands.map(palmCenter)
    const matched = matchTracks(tracks, centers, now)
    centers.forEach((center, index) => {
      const track = matched.get(index)
      const last = track?.at(-1)
      if (track && last) {
        const x = last.x + (center.x - last.x) * SMOOTHING
        const y = last.y + (center.y - last.y) * SMOOTHING
        track.push({ x, y, time: now, keep, s: last.s + Math.hypot(x - last.x, y - last.y) })
      } else {
        tracks.push([{ ...center, time: now, keep, s: 0 }])
      }
    })

    // 消える点は時間がたったら捨てる。残る点の間の点が消えたら、そこで軌跡を分ける
    const alive = (point: TrailPoint) => point.keep || now - point.time < FADE_LIFETIME_MS
    tracks = tracks.flatMap((track) => {
      const parts: Track[] = [[]]
      for (const point of track) {
        if (alive(point)) parts[parts.length - 1].push(point)
        else if (parts[parts.length - 1].length > 0) parts.push([])
      }
      return parts.filter((part) => part.length > 0)
    })

    // 残る点が多すぎるときは、古い点から捨てる
    const kept = tracks.flat().filter((point) => point.keep)
    if (kept.length > PERSIST_MAX_POINTS) {
      const times = kept.map((point) => point.time).sort((x, y) => x - y)
      const oldest = times[kept.length - PERSIST_MAX_POINTS]
      tracks = tracks
        .map((track) => track.filter((point) => !point.keep || point.time >= oldest))
        .filter((track) => track.length > 0)
    }
  }

  /** 今の軌跡。life は 1（新しい）から 0（消える直前）まで。残る点は常に 1 */
  function live(now: number): LivePoint[][] {
    return tracks.map((track) =>
      track.map((point) => ({
        x: point.x,
        y: point.y,
        s: point.s,
        life: point.keep ? 1 : Math.max(0, 1 - (now - point.time) / FADE_LIFETIME_MS),
      })),
    )
  }

  return { update, live }
}

// ---- 描くための道具 ----

interface LivePoint extends Point {
  s: number
  life: number
}

/** 等間隔に並べ直した点。nx, ny は線と直角の向き、k は模様の番号（位置で決まり、時間で変わらない） */
interface Sample extends LivePoint {
  nx: number
  ny: number
  k: number
}

type RGB = readonly [number, number, number]

const WHITE: RGB = [255, 255, 255]

const rgba = (color: RGB, alpha: number) =>
  `rgba(${color[0]}, ${color[1]}, ${color[2]}, ${Math.max(0, Math.min(1, alpha)).toFixed(3)})`

function mix(a: RGB, b: RGB, ratio: number): RGB {
  return [0, 1, 2].map((i) => Math.round(a[i] + (b[i] - a[i]) * ratio)) as unknown as RGB
}

/** 位置ごとに決まった 0以上1未満の値。同じ k なら毎フレーム同じ値になる */
function hash(k: number, slot: number): number {
  const value = Math.sin(k * 127.1 + slot * 311.7) * 43758.5453
  return value - Math.floor(value)
}

/** 線を描く。点が1つだけなら丸を描く */
function strokePath(context: EffectContext, points: Point[], width: number, color: string) {
  if (points.length === 0 || width <= 0) return
  if (points.length === 1) {
    context.fillStyle = color
    context.beginPath()
    context.arc(points[0].x, points[0].y, width / 2, 0, Math.PI * 2)
    context.fill()
    return
  }
  context.lineWidth = width
  context.strokeStyle = color
  context.beginPath()
  context.moveTo(points[0].x, points[0].y)
  for (const point of points.slice(1)) context.lineTo(point.x, point.y)
  context.stroke()
}

/**
 * 光る線。外側ほど太く薄い線を重ねて、にじんだ光に見せる。
 * shadowBlur は iPhone で重いので使わない。
 */
function glow(
  context: EffectContext,
  points: Point[],
  color: RGB,
  width: number,
  alpha = 1,
  core: RGB = mix(color, WHITE, 0.75),
) {
  strokePath(context, points, width * 5, rgba(color, 0.07 * alpha))
  strokePath(context, points, width * 2.6, rgba(color, 0.16 * alpha))
  strokePath(context, points, width * 1.4, rgba(color, 0.55 * alpha))
  strokePath(context, points, width * 0.55, rgba(core, 0.95 * alpha))
}

/**
 * 明るさがほぼ同じ区間ごとに分ける。消える軌跡は先ほど薄く細くなるので、区間ごとに描き分ける。
 * 残る軌跡は全部明るさ1なので、1本のまま描ける。
 */
function chunks<T extends { life: number }>(points: T[]): { points: T[]; life: number }[] {
  const result: { points: T[]; life: number }[] = []
  const level = (life: number) => Math.ceil(life * 6) / 6
  for (const point of points) {
    const life = level(point.life)
    const current = result.at(-1)
    if (current && current.life === life) {
      current.points.push(point)
    } else {
      // 前の区間の最後の点も入れて、区間の間に隙間ができないようにする
      const previous = current?.points.at(-1)
      result.push({ points: previous ? [previous, point] : [point], life })
    }
  }
  return result.filter((chunk) => chunk.life > 0)
}

/** 軌跡を spacing ピクセルごとの点に並べ直す。模様（炎の舌や雪の粒）を置く位置に使う */
function resample(track: LivePoint[], spacing: number): Sample[] {
  const result: Sample[] = []
  if (track.length < 2) return result
  let k = Math.ceil(track[0].s / spacing)
  for (let index = 1; index < track.length; index += 1) {
    const from = track[index - 1]
    const to = track[index]
    const length = to.s - from.s
    if (length <= 0) continue
    const nx = -(to.y - from.y) / length
    const ny = (to.x - from.x) / length
    while (k * spacing <= to.s) {
      const ratio = (k * spacing - from.s) / length
      result.push({
        x: from.x + (to.x - from.x) * ratio,
        y: from.y + (to.y - from.y) * ratio,
        s: k * spacing,
        life: from.life + (to.life - from.life) * ratio,
        nx,
        ny,
        k,
      })
      k += 1
    }
  }
  return result
}

/** 並べ直した点を、線と直角の向きに offset だけずらす */
function shifted(samples: Sample[], offset: (sample: Sample) => number): Sample[] {
  return samples.map((sample) => {
    const amount = offset(sample)
    return { ...sample, x: sample.x + sample.nx * amount, y: sample.y + sample.ny * amount }
  })
}

/** 線の描き方。track は手1つ分の軌跡 */
type Style = (context: EffectContext, track: LivePoint[], now: number, random: Random) => void

// ---- 種類ごとの描き方 ----

/** 点を順に結んだ形を塗る */
function fillPolygon(context: EffectContext, points: Point[], color: string) {
  if (points.length < 3) return
  context.fillStyle = color
  context.beginPath()
  context.moveTo(points[0].x, points[0].y)
  for (const point of points.slice(1)) context.lineTo(point.x, point.y)
  context.closePath()
  context.fill()
}

function fillCircle(context: EffectContext, center: Point, radius: number, color: string) {
  if (radius <= 0) return
  context.fillStyle = color
  context.beginPath()
  context.arc(center.x, center.y, radius, 0, Math.PI * 2)
  context.fill()
}

/** 線の進む向き（nx, ny と直角） */
const tangentOf = (sample: Sample): Point => ({ x: sample.ny, y: -sample.nx })

/**
 * 軌跡全体で「上側」になる向き。右へ動いた軌跡と左へ動いた軌跡で直角の向きが逆になるので、
 * 波の山や炎が画面の上へ出るように、軌跡ごとに向きをそろえる
 */
function upSign(samples: Sample[]): number {
  const total = samples.reduce((sum, sample) => sum + sample.ny, 0)
  return total > 0 ? -1 : 1
}

const offsetPoint = (sample: Sample, amount: number): Point => ({
  x: sample.x + sample.nx * amount,
  y: sample.y + sample.ny * amount,
})

/** ネオン。白い芯の周りが色つきで光る */
function neon(color: RGB, width: number): Style {
  return (context, track) => {
    for (const chunk of chunks(track)) {
      glow(context, chunk.points, color, width * (0.4 + 0.6 * chunk.life), chunk.life)
    }
  }
}

/** 電気。線に沿ってギザギザの電撃が走り、毎フレーム形が変わる */
function electric(color: RGB): Style {
  return (context, track, _now, random) => {
    for (const chunk of chunks(track)) {
      glow(context, chunk.points, color, 11 * chunk.life, 0.6 * chunk.life)
    }
    const samples = resample(track, 14)
    if (samples.length < 2) return
    for (let bolt = 0; bolt < 2; bolt += 1) {
      const jagged = shifted(samples, (sample) => (random() - 0.5) * 46 * sample.life)
      for (const chunk of chunks(jagged)) {
        glow(context, chunk.points, color, 6.5, chunk.life)
      }
    }
  }
}

/** 炎の舌1枚。根元が太く、先がとがり、上ほど大きく揺れる */
function flameTongue(
  context: EffectContext,
  base: Point,
  height: number,
  width: number,
  sway: number,
  wiggle: number,
  color: string,
) {
  const left: Point[] = []
  const right: Point[] = []
  const steps = 14
  for (let index = 0; index <= steps; index += 1) {
    const t = index / steps
    const y = base.y - height * t
    const half = (width / 2) * Math.pow(1 - t, 0.9) * (1 + 0.35 * Math.sin(t * Math.PI))
    // 上ほど大きく曲がり、途中でくねる
    const x = base.x + sway * t * t + Math.sin(t * Math.PI * 1.6 + wiggle) * width * 0.22 * t
    left.push({ x: x - half, y })
    right.push({ x: x + half, y })
  }
  fillPolygon(context, [...left, ...right.reverse()], color)
}

/** 炎。赤・橙・黄・白の炎の舌を重ね、メラメラと揺らす */
function fire(): Style {
  const layers: { color: RGB; size: number; alpha: number }[] = [
    { color: [215, 35, 10], size: 1, alpha: 0.7 },
    { color: [255, 110, 20], size: 0.75, alpha: 0.85 },
    { color: [255, 205, 60], size: 0.5, alpha: 0.9 },
    { color: [255, 250, 225], size: 0.25, alpha: 0.9 },
  ]
  return (context, track, now, random) => {
    // 下に、にじんだ光を敷く
    for (const chunk of chunks(track)) {
      glow(context, chunk.points, [255, 80, 15], 17 * chunk.life, 0.7 * chunk.life, [255, 190, 110])
    }
    const tongues = resample(track, 13).map((sample) => {
      // ゆっくりした揺れと速い揺れを重ね、少しだけ毎フレームばらつかせる
      const flicker =
        0.55 +
        0.25 * Math.sin(now * 0.021 + sample.k * 1.7) +
        0.2 * Math.sin(now * 0.047 + sample.k * 0.6) +
        (random() - 0.5) * 0.15
      const height = (50 + 55 * hash(sample.k, 1)) * flicker * sample.life
      return {
        base: { x: sample.x + (hash(sample.k, 3) - 0.5) * 10, y: sample.y + 10 },
        height,
        width: (42 + 18 * hash(sample.k, 2)) * sample.life,
        sway: Math.sin(now * 0.013 + sample.k * 0.8) * height * 0.4,
        wiggle: now * 0.02 + sample.k * 2.3,
        life: sample.life,
      }
    })
    context.globalCompositeOperation = 'source-over' // 色が白く飛ばないように、炎の本体は重ねて塗る
    for (const layer of layers) {
      // 舌の根元を帯でつなぎ、舌が重なったところに段ができないようにする
      for (const chunk of chunks(track)) {
        const body = chunk.points.map((point) => ({ x: point.x, y: point.y - 4 }))
        strokePath(context, body, 42 * layer.size * chunk.life, rgba(layer.color, layer.alpha * chunk.life))
      }
      for (const tongue of tongues) {
        flameTongue(
          context,
          tongue.base,
          tongue.height * layer.size,
          tongue.width * (0.35 + 0.65 * layer.size),
          tongue.sway * layer.size,
          tongue.wiggle,
          rgba(layer.color, layer.alpha * tongue.life),
        )
      }
    }
    // 火の粉
    context.globalCompositeOperation = 'lighter'
    for (const sample of resample(track, 30)) {
      const phase = (now * 0.0011 + hash(sample.k, 5)) % 1
      const spark = {
        x: sample.x + Math.sin(now * 0.004 + sample.k) * 10,
        y: sample.y - 30 - phase * 50,
      }
      fillCircle(context, spark, 2.2, rgba([255, 200, 90], (1 - phase) * sample.life))
    }
  }
}

/** 煙。ふちどりのある白い雲が、ふくらんだりしぼんだりしながら、もくもくと広がる */
function smoke(): Style {
  const fill: RGB = [250, 250, 252]
  const shade: RGB = [205, 210, 222]
  const line: RGB = [55, 60, 75]
  return (context, track, now) => {
    context.globalCompositeOperation = 'source-over'
    const samples = resample(track, 13)
    const sources: Sample[] =
      samples.length > 0 ? samples : track.map((point) => ({ ...point, nx: 0, ny: 1, k: 0 }))
    const puffs = sources.map((sample) => {
      const breathe = 0.85 + 0.2 * Math.sin(now * 0.003 + sample.k * 1.3)
      const rise = hash(sample.k, 4) * 8 + Math.sin(now * 0.002 + sample.k) * 3
      const spread = (hash(sample.k, 2) - 0.5) * 24
      return {
        x: sample.x + sample.nx * spread,
        y: sample.y + sample.ny * spread - rise,
        // 消えるときは、透けさせずに小さくしぼませる（透けると、ふちどりが中に見えるため）
        radius: (15 + 15 * hash(sample.k, 1)) * breathe * (0.3 + 0.7 * sample.life),
        alpha: Math.min(1, sample.life * 2.5),
      }
    })
    // ふちどり → 白 → かげ の順に描くと、雲の外側にだけ線が残る
    for (const puff of puffs) fillCircle(context, puff, puff.radius + 3, rgba(line, 0.85 * puff.alpha))
    for (const puff of puffs) fillCircle(context, puff, puff.radius, rgba(fill, 0.97 * puff.alpha))
    for (const puff of puffs) {
      const center = { x: puff.x + puff.radius * 0.28, y: puff.y + puff.radius * 0.32 }
      fillCircle(context, center, puff.radius * 0.5, rgba(shade, 0.55 * puff.alpha))
    }
  }
}

/** エネルギー。光る芯の周りを、うねる筋が何本も取り巻く */
function energy(color: RGB): Style {
  return (context, track, now) => {
    for (const chunk of chunks(track)) {
      glow(context, chunk.points, color, 10 * chunk.life, chunk.life)
    }
    const samples = resample(track, 8)
    for (let strand = 0; strand < 3; strand += 1) {
      const wavy = shifted(samples, (sample) => {
        const size = 9 + 13 * (0.5 + 0.5 * Math.sin(sample.k * 0.21 + strand * 1.7))
        return Math.sin(sample.k * 0.55 + now * 0.012 * (strand + 1) + strand * 2.1) * size
      })
      for (const chunk of chunks(wavy)) {
        glow(context, chunk.points, color, 3, chunk.life * 0.8)
      }
    }
  }
}

/** 波。線が波打ち、その波が先へ流れていく */
function wave(color: RGB): Style {
  return (context, track, now) => {
    for (const chunk of chunks(track)) {
      strokePath(context, chunk.points, 4, rgba(color, 0.45 * chunk.life))
    }
    const samples = resample(track, 5)
    const wavy = shifted(samples, (sample) => Math.sin(sample.s * 0.05 - now * 0.012) * 19)
    for (const chunk of chunks(wavy)) {
      glow(context, chunk.points, color, 7.5 * chunk.life, chunk.life)
    }
  }
}

/** 6本の腕の雪の結晶 */
function snowflake(context: EffectContext, center: Point, size: number, color: string) {
  context.strokeStyle = color
  context.lineWidth = 3
  context.beginPath()
  for (let arm = 0; arm < 3; arm += 1) {
    const angle = (arm * Math.PI) / 3
    const dx = Math.cos(angle) * size
    const dy = Math.sin(angle) * size
    context.moveTo(center.x - dx, center.y - dy)
    context.lineTo(center.x + dx, center.y + dy)
  }
  context.stroke()
}

/** 雪。冷たく光る線から、雪の結晶がふわふわ落ちる */
function snow(): Style {
  const color: RGB = [190, 225, 255]
  return (context, track, now) => {
    for (const chunk of chunks(track)) {
      glow(context, chunk.points, color, 10 * chunk.life, chunk.life)
    }
    for (const sample of resample(track, 20)) {
      // 1つの位置から、結晶が繰り返し落ちてくる。落ちるほど薄くなる
      const phase = (now * 0.0006 + hash(sample.k, 1)) % 1
      const center = {
        x: sample.x + Math.sin(now * 0.003 + sample.k) * 8 + (hash(sample.k, 2) - 0.5) * 22,
        y: sample.y + phase * 50 - 6,
      }
      const size = 7 + 6 * hash(sample.k, 3)
      snowflake(context, center, size, rgba(WHITE, (1 - phase) * sample.life))
    }
  }
}

/**
 * 風の刃1枚。軌跡に沿って曲がる、両端がとがった細い形。前の端ほど鋭い。
 * path は刃の芯になる点の並び、offset は軌跡からどれだけ横へずらすか
 */
function windBlade(
  context: EffectContext,
  path: Sample[],
  offset: number,
  width: number,
  color: string,
) {
  if (path.length < 3) return
  const upper: Point[] = []
  const lower: Point[] = []
  path.forEach((sample, index) => {
    const t = (index / (path.length - 1)) * 2 - 1 // -1（後ろ）〜 1（前）
    const half = (width / 2) * Math.pow(1 - t * t, 1.2) * (1 - 0.45 * t)
    // 真ん中ほど外へふくらませて、反った刃にする
    const center = offset + Math.sign(offset || 1) * (1 - t * t) * 8
    upper.push(offsetPoint(sample, center + half))
    lower.push(offsetPoint(sample, center - half))
  })
  fillPolygon(context, [...upper, ...lower.reverse()], color)
}

/** 風。とがった緑の刃が、軌跡に沿って曲がりながら、動いた向きへ流れては消える */
function wind(): Style {
  const dark: RGB = [25, 160, 85]
  const light: RGB = [205, 255, 200]
  const SPACING = 6
  return (context, track, now) => {
    context.globalCompositeOperation = 'source-over'
    const samples = resample(track, SPACING)
    for (const chunk of chunks(samples)) {
      strokePath(context, chunk.points, 5, rgba(light, 0.35 * chunk.life))
    }
    for (let start = 0; start < samples.length; start += 4) {
      const k = samples[start].k
      const phase = (now * 0.0016 + hash(k, 1)) % 1
      // 刃の長さ（点の数）。時間とともに、進む向き（新しい側）へすべっていく
      const count = Math.round((12 + 10 * hash(k, 3)) * (0.6 + 0.4 * samples[start].life))
      const from = start + Math.round(phase * 8)
      const path = samples.slice(from, from + count)
      if (path.length < 3) continue
      const life = path[Math.floor(path.length / 2)].life
      const alpha = Math.sin(Math.PI * phase) * life
      if (alpha < 0.02) continue
      const offset = (hash(k, 2) - 0.5) * 44
      const width = 13 + 7 * hash(k, 4)
      windBlade(context, path, offset, width, rgba(dark, 0.8 * alpha))
      windBlade(context, path.slice(1, -1), offset, width * 0.35, rgba(light, 0.9 * alpha))
    }
  }
}

/** 水。波打つ水の帯の上で、波頭が巻き、しぶきが飛ぶ */
function water(): Style {
  const deep: RGB = [25, 115, 215]
  const middle: RGB = [70, 175, 245]
  const light: RGB = [215, 245, 255]
  return (context, track, now) => {
    context.globalCompositeOperation = 'source-over'
    const samples = resample(track, 5)
    if (samples.length < 2) {
      for (const point of track) fillCircle(context, point, 15 * point.life, rgba(deep, 0.85 * point.life))
      return
    }
    const up = upSign(samples)
    const crest = (sample: Sample) =>
      Math.sin(sample.s * 0.07 - now * 0.009) * 6 + Math.sin(sample.s * 0.023 + now * 0.004) * 4

    // 水の帯
    for (const chunk of chunks(samples)) {
      const thickness = 22 * chunk.life
      const top = chunk.points.map((s) => offsetPoint(s, up * (thickness + crest(s))))
      const bottom = chunk.points.map((s) =>
        offsetPoint(s, up * (-thickness * 0.6 + Math.sin(s.s * 0.05 + now * 0.006) * 3)),
      )
      fillPolygon(context, [...top, ...bottom.reverse()], rgba(deep, 0.88 * chunk.life))
      const band = chunk.points.map((s) => offsetPoint(s, up * (thickness * 0.45 + crest(s) * 0.8)))
      strokePath(context, band, 9 * chunk.life, rgba(middle, 0.9 * chunk.life))
      const edge = chunk.points.map((s) => offsetPoint(s, up * (thickness - 2 + crest(s))))
      strokePath(context, edge, 3.5 * chunk.life, rgba(light, 0.9 * chunk.life))
    }

    // 波頭の巻き。帯の上から立ち上がり、前へ巻いて戻る
    for (const sample of resample(track, 70)) {
      const u = tangentOf(sample)
      const n = { x: sample.nx * up, y: sample.ny * up }
      const radius = (14 + 9 * hash(sample.k, 1)) * sample.life
      const grow = 0.6 + 0.4 * Math.sin(now * 0.006 + sample.k)
      const base = offsetPoint(sample, up * (22 * sample.life + crest(sample)))
      const center = { x: base.x + n.x * radius, y: base.y + n.y * radius }
      // 角度0が根元。前 → 上 → 後ろの順に回る
      const at = (angle: number, r: number) => ({
        x: center.x - n.x * Math.cos(angle) * r + u.x * Math.sin(angle) * r,
        y: center.y - n.y * Math.cos(angle) * r + u.y * Math.sin(angle) * r,
      })
      const end = Math.PI * 1.35 * grow
      const outer: Point[] = []
      const inner: Point[] = []
      for (let index = 0; index <= 10; index += 1) {
        const angle = (end * index) / 10
        outer.push(at(angle, radius))
        inner.push(at(angle, radius * (0.45 + 0.55 * (index / 10))))
      }
      fillPolygon(context, [...outer, ...inner.reverse()], rgba(middle, 0.92 * sample.life))
      strokePath(context, outer, 3, rgba(light, 0.9 * sample.life))

      // しぶき。巻いた先から飛び出して落ちる
      const tip = at(end, radius)
      for (let drop = 0; drop < 3; drop += 1) {
        const phase = (now * 0.0012 + hash(sample.k, 5 + drop)) % 1
        const spread = (drop - 1) * 22
        const height = phase * 34 - phase * phase * 50
        fillCircle(
          context,
          { x: tip.x + u.x * phase * spread + n.x * height, y: tip.y + u.y * phase * spread + n.y * height },
          4.5 * (1 - phase * 0.4),
          rgba(light, (1 - phase) * sample.life),
        )
      }
    }
  }
}

// ---- 一覧 ----

export const EFFECTS: { id: EffectId; label: string; style: Style }[] = [
  { id: 'neon_blue', label: 'ネオン（青）', style: neon([40, 140, 255], 15) },
  { id: 'neon_pink', label: 'ネオン（ピンク）', style: neon([255, 40, 150], 15) },
  { id: 'electric_blue', label: '電気（青）', style: electric([60, 160, 255]) },
  { id: 'electric_green', label: '電気（緑）', style: electric([120, 255, 40]) },
  { id: 'fire', label: '炎', style: fire() },
  { id: 'smoke', label: '煙', style: smoke() },
  { id: 'energy', label: 'エネルギー', style: energy([170, 70, 255]) },
  { id: 'wave', label: '波', style: wave([40, 220, 255]) },
  { id: 'snow', label: '雪', style: snow() },
  { id: 'wind', label: '風', style: wind() },
  { id: 'water', label: '水', style: water() },
]

export const TRAIL_MODES: { mode: TrailMode; label: string }[] = [
  { mode: 'fade', label: '消える' },
  { mode: 'persist', label: '残る' },
]

export const DEFAULT_CHOICE: EffectChoice = { id: 'neon_blue', mode: 'fade' }

export function isEffectId(value: unknown): value is EffectId {
  return EFFECTS.some((effect) => effect.id === value)
}

export function isTrailMode(value: unknown): value is TrailMode {
  return value === 'fade' || value === 'persist'
}

export function effectLabel(choice: EffectChoice): string {
  const effect = EFFECTS.find((item) => item.id === choice.id)
  const mode = TRAIL_MODES.find((item) => item.mode === choice.mode)
  return `${effect?.label ?? ''}・${mode?.label ?? ''}`
}

export function createEffect(
  choice: EffectChoice,
  random: Random = Math.random,
  preview = false,
): Effect {
  const style = (EFFECTS.find((effect) => effect.id === choice.id) ?? EFFECTS[0]).style
  const tracker = createTracker()
  let mode = choice.mode
  let previewing = preview

  return {
    draw(context, hands, now) {
      tracker.update(hands, now, mode === 'persist' && !previewing)
      context.save()
      context.lineCap = 'round'
      context.lineJoin = 'round'
      context.globalCompositeOperation = 'lighter' // 重なるほど明るくなり、光って見える
      for (const track of tracker.live(now)) style(context, track, now, random)
      context.restore()
    },
    setMode(next) {
      mode = next
    },
    setPreview(next) {
      previewing = next
    },
  }
}
