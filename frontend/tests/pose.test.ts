// 人の絵の動かし方のテスト。npm test で実行する。

import assert from 'node:assert/strict'
import { test } from 'node:test'
import { POSES, PoseSpring, blend, fromVec, toVec, type Point, type Pose } from '../src/ui/pose.ts'

const dist = (a: Point, b: Point) => Math.hypot(a[0] - b[0], a[1] - b[1])
const upperArm = (q: Pose) => dist(q.n, q.b[0])
const close = (a: number, b: number, tolerance = 1e-6) => Math.abs(a - b) < tolerance

test('角度で表して戻すと、元の姿勢になる', () => {
  for (const pose of Object.values(POSES)) {
    const back = fromVec(toVec(pose, 3)).pose
    for (const key of ['h', 'n', 'p'] as const) {
      assert.ok(close(back[key][0], pose[key][0]) && close(back[key][1], pose[key][1]))
    }
    for (const limb of ['a', 'b', 'l', 'r'] as const) {
      for (const j of [0, 1]) {
        assert.ok(dist(back[limb][j], pose[limb][j]) < 1e-6, `${limb}${j} がずれた`)
      }
    }
  }
})

test('2つの姿勢の間でも、腕の長さが保たれる', () => {
  const from = POSES.stand
  const to = POSES.gesture2
  const start = upperArm(from)
  const end = upperArm(to)
  for (const t of [0.25, 0.5, 0.75]) {
    const middle = upperArm(blend(from, to, t))
    // 位置をそのまま混ぜると縮むが、角度で混ぜると長さは両端の間に収まる
    assert.ok(middle >= Math.min(start, end) - 1e-6 && middle <= Math.max(start, end) + 1e-6)
  }
})

test('ばねは、目標の姿勢に追いつく', () => {
  const spring = new PoseSpring()
  spring.step(POSES.stand, 0, 1 / 60)
  let last = POSES.stand
  for (let i = 0; i < 120; i++) last = spring.step(POSES.wave, 0, 1 / 60).pose
  assert.ok(dist(last.b[1], POSES.wave.b[1]) < 0.5, '2秒たっても追いつかない')
})

test('ばねは、最初の姿勢をそのまま返す', () => {
  const spring = new PoseSpring()
  const first = spring.step(POSES.think, 5, 1 / 60)
  assert.ok(dist(first.pose.h, POSES.think.h) < 1e-6)
  assert.ok(close(first.rotation, 5))
})
