import { test } from 'node:test'
import assert from 'node:assert/strict'
import { plainAiText } from '../src/game/aiText.ts'

test('太字の記号を取り除く（本物の AI の返答で見つかった形）', () => {
  assert.equal(
    plainAiText('これは、**「丸（円）」という形状**や、**「（右に）回す」という回転の動作**を表しています。'),
    'これは、「丸（円）」という形状や、「（右に）回す」という回転の動作を表しています。',
  )
})

test('行頭の見出しと箇条書きの記号を取り除く', () => {
  assert.equal(plainAiText('# 読み取り\n- 円を描く\n* 回す'), '読み取り\n円を描く\n回す')
})

test('記号のない文はそのまま', () => {
  assert.equal(plainAiText('手を大きく振っている'), '手を大きく振っている')
})
