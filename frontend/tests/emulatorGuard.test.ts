// エミュレーターの事前確認のテスト。npm test で実行する。

import assert from 'node:assert/strict'
import { test } from 'node:test'
import { emulatorConfigProblem } from '../src/api/real/emulatorGuard.ts'

const PAGE = 'http://localhost:5173/?dev=3'

test('demo- のプロジェクトと、この端末の API なら通す', () => {
  for (const apiBaseUrl of ['http://127.0.0.1:8000', 'http://localhost:8000', 'http://[::1]:8000']) {
    assert.equal(emulatorConfigProblem({ projectId: 'demo-gesture-relay', apiBaseUrl, pageUrl: PAGE }), null)
  }
})

test('API の URL が空なら、画面と同じ場所として確かめる', () => {
  assert.equal(emulatorConfigProblem({ projectId: 'demo-x', apiBaseUrl: '', pageUrl: PAGE }), null)
  assert.notEqual(
    emulatorConfigProblem({ projectId: 'demo-x', apiBaseUrl: '', pageUrl: 'https://gesture-relay-game.web.app/' }),
    null,
  )
})

test('本物のプロジェクト ID なら止める', () => {
  for (const projectId of ['gesture-relay-game', undefined, '']) {
    const problem = emulatorConfigProblem({ projectId, apiBaseUrl: 'http://127.0.0.1:8000', pageUrl: PAGE })
    assert.match(problem ?? '', /demo-/)
  }
})

test('外の API の URL なら止める', () => {
  for (const apiBaseUrl of ['https://api-xxxx.a.run.app', 'http://192.168.0.10:8000', 'https://localhost.example.com']) {
    const problem = emulatorConfigProblem({ projectId: 'demo-x', apiBaseUrl, pageUrl: PAGE })
    assert.match(problem ?? '', /API/, apiBaseUrl)
  }
})
