// 類似度の帯のテスト。npm test で実行する。

import assert from 'node:assert/strict'
import { test } from 'node:test'
import { BAND_THRESHOLDS, similarityBand } from '../src/game/similarity.ts'

test('境界の値は、上の帯に入る', () => {
  assert.equal(similarityBand(BAND_THRESHOLDS.near), 'near')
  assert.equal(similarityBand(BAND_THRESHOLDS.close), 'close')
})

test('短文で無関係でも出やすい点（0.6〜0.7）は、遠い', () => {
  assert.equal(similarityBand(0.62), 'far')
  assert.equal(similarityBand(0.7), 'far')
})

test('1 と 0 も帯に入る', () => {
  assert.equal(similarityBand(1), 'near')
  assert.equal(similarityBand(0), 'far')
})
