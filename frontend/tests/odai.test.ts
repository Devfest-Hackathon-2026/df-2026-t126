// モックのお題が、本物のお題（data/odai.json）とそろっているかのテスト。npm test で実行する。

import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { test } from 'node:test'
import { MOCK_ODAI } from '../src/api/mock/odai.ts'

const real = JSON.parse(readFileSync(new URL('../../data/odai.json', import.meta.url), 'utf8')) as {
  text: string
}[]

test('モックのお題は、data/odai.json と同じ文を同じ順で持つ', () => {
  assert.deepEqual(
    MOCK_ODAI,
    real.map((odai) => odai.text),
  )
})
