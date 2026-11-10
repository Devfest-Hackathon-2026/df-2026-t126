/** Canonical PR #3 backend verification. Production sources are never edited.
 * FRONTEND_ROOT=/path/to/checkout/frontend node tools/validate_frontend.mjs --prepare
 * firebase emulators:exec --config .tools/pr3-firebase.json ... 'node ...'
 */
import assert from 'node:assert/strict'
import { spawn, execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync, mkdirSync, openSync, closeSync, symlinkSync, existsSync } from 'node:fs'
import { createHash, randomUUID } from 'node:crypto'
import { createServer, Socket } from 'node:net'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { setTimeout as sleep } from 'node:timers/promises'
import { Worker, isMainThread, parentPort, workerData } from 'node:worker_threads'
import { stripTypeScriptTypes } from 'node:module'

const ROOT = resolve(import.meta.dirname, '..')
assert.ok(process.env.FRONTEND_ROOT, 'explicit local frontend checkout required')
const FRONTEND = resolve(process.env.FRONTEND_ROOT)
const PLAN = resolve(ROOT, '.tools/pr3-local-plan.json')
const loopback = (host) => ['127.0.0.1', 'localhost', '::1', '[::1]'].includes(host)
function guardUrl(value) {
  const url = new URL(value)
  assert.ok(loopback(url.hostname) && ['http:', 'https:'].includes(url.protocol), 'only loopback URLs allowed')
  assert.ok(!url.username && !url.password, 'credentials in URLs are forbidden')
  return url
}
async function free(port) {
  const server = createServer()
  try {
    await new Promise((done, reject) => { server.once('error', reject); server.listen(port, '127.0.0.1', done) })
    const actual = server.address().port
    await new Promise((done) => server.close(done))
    return actual
  } catch (error) {
    if (error.code === 'EADDRINUSE') return false
    throw error
  }
}

if (isMainThread && process.argv.includes('--prepare')) {
  mkdirSync(resolve(ROOT, '.tools'), { recursive: true })
  const defaults = await Promise.all([free(9099), free(8080), free(9199)])
  let ports = { auth: 9099, firestore: 8080, storage: 9199 }
  if (!defaults.every(Boolean)) {
    const alternate = await Promise.all([free(39099), free(38080), free(39199)])
    assert.ok(alternate.every(Boolean), 'dedicated test ports unavailable; do not stop another server')
    ports = { auth: 39099, firestore: 38080, storage: 39199 }
  }
  const auxiliary = await Promise.all([free(0), free(0), free(0)])
  const config = { firestore: { rules: resolve(ROOT, 'firestore.rules') }, storage: { rules: resolve(ROOT, 'storage.rules') },
    emulators: { auth: { host: '127.0.0.1', port: ports.auth },
      firestore: { host: '127.0.0.1', port: ports.firestore, websocketPort: auxiliary[0] },
      storage: { host: '127.0.0.1', port: ports.storage }, hub: { host: '127.0.0.1', port: auxiliary[1] },
      logging: { host: '127.0.0.1', port: auxiliary[2] }, ui: { enabled: false }, singleProjectMode: true } }
  writeFileSync(PLAN, JSON.stringify({ ports, defaultPortsAvailable: defaults.every(Boolean) }, null, 2))
  writeFileSync(resolve(ROOT, '.tools/pr3-firebase.json'), JSON.stringify(config, null, 2))
  console.log(JSON.stringify({ ports, defaultPortsAvailable: defaults.every(Boolean), sourcesEdited: false }))
} else if (!isMainThread) {
  // Defense in depth: SDK sockets and fetch both remain on loopback.
  const originalConnect = Socket.prototype.connect
  Socket.prototype.connect = function (...args) {
    const options = Array.isArray(args[0]) ? args[0][0] : args[0]
    const host = typeof options === 'object' ? options.host ?? options.hostname ?? 'localhost' :
      typeof args[1] === 'string' ? args[1] : 'localhost'
    assert.ok(loopback(host), 'non-loopback socket blocked by validation harness')
    return originalConnect.apply(this, args)
  }
  const actualFetch = globalThis.fetch
  const api = guardUrl(workerData.api)
  let createAttempts = 0
  const createBodies = []
  globalThis.fetch = async (input, init) => {
    const url = guardUrl(typeof input === 'string' || input instanceof URL ? String(input) : input.url)
    if (workerData.inject401 && url.origin === api.origin && url.pathname === '/api/rooms' && init?.method === 'POST') {
      createAttempts += 1
      createBodies.push(init.body)
      if (createAttempts === 1) return Response.json({ error: { code: 'UNAUTHENTICATED', message: 'test refresh' } }, { status: 401 })
    }
    return actualFetch(input, { ...init, redirect: 'error' })
  }
  globalThis.location = { href: `${api.origin}/?player=${workerData.player}`, search: `?player=${workerData.player}` }
  globalThis.__g1SnapshotErrorCode = workerData.faultMode
  const { createRealBackend } = await import(workerData.module)
  const backend = createRealBackend()
  const subscriptions = new Map()
  parentPort.on('message', async ({ id, method, args = [], report }) => {
    if (report) return
    try {
      let value
      if (method.startsWith('subscribe')) {
        const key = `${method}:${args.join(':')}`
        subscriptions.get(key)?.()
        const stop = backend[method](...args,
          (data) => parentPort.postMessage({ event: method, data }),
          (error) => parentPort.postMessage({ event: 'subscriptionError', method, code: error.code }))
        subscriptions.set(key, stop)
        value = true
      } else {
        value = await backend[method](...args)
        if (value instanceof Blob) value = { contentType: value.type, bytes: new Uint8Array(await value.arrayBuffer()) }
      }
      parentPort.postMessage({ id, value })
    } catch (error) {
      parentPort.postMessage({ id, error: { message: error.message, status: error.status, code: error.code } })
    }
  })
  parentPort.postMessage({ ready: true })
  parentPort.on('message', ({ report }) => { if (report) parentPort.postMessage({ report: { createAttempts, sameBody: createBodies.length === 2 && createBodies[0] === createBodies[1] } }) })
} else {
  assert.equal(process.env.RUN_PR3_LOCAL_VALIDATION, '1', 'explicit local test mode required')
  const plan = JSON.parse(readFileSync(PLAN, 'utf8'))
  for (const [key, expected] of [['FIREBASE_AUTH_EMULATOR_HOST', plan.ports.auth], ['FIRESTORE_EMULATOR_HOST', plan.ports.firestore], ['FIREBASE_STORAGE_EMULATOR_HOST', plan.ports.storage]]) {
    assert.equal(process.env[key], `127.0.0.1:${expected}`, `wrong isolated emulator: ${key}`)
  }
  const python = process.env.G1_PYTHON
  assert.ok(python, 'local Python path required')
  const port = await free(0)
  const api = `http://127.0.0.1:${port}`
  guardUrl(api)
  const safeEnv = { ...process.env, RUNTIME_MODE: 'emulator', ENABLE_CLOUD: 'false', AI_MODE: 'mock',
    PROJECT_ID: 'demo-gesture-relay', BUCKET_NAME: 'demo-gesture-relay.appspot.com', PYTHONDONTWRITEBYTECODE: '1',
    CORS_ORIGINS: '["http://127.0.0.1:5173"]' }
  for (const key of ['GOOGLE_APPLICATION_CREDENTIALS','FIREBASE_TOKEN','GEMINI_API_KEY','GOOGLE_API_KEY','GCLOUD_ACCESS_TOKEN','GOOGLE_OAUTH_ACCESS_TOKEN','CLOUDSDK_AUTH_ACCESS_TOKEN']) delete safeEnv[key]
  delete safeEnv.STORAGE_EMULATOR_HOST
  const countdown = Number(process.env.G1_COUNTDOWN_SECONDS ?? 3)
  assert.ok(Number.isInteger(countdown) && countdown >= 0 && countdown <= 60, 'invalid test countdown')
  execFileSync(python, ['-c', `from google.auth.credentials import AnonymousCredentials; from google.cloud import firestore; firestore.Client(project="demo-gesture-relay", credentials=AnonymousCredentials()).document("config/game").set({"text_seconds":60,"countdown_seconds":${countdown},"record_seconds":5})`], { cwd: ROOT, env: safeEnv })

  const canonical = resolve(FRONTEND, 'src/api/real/realBackend.ts')
  const source = readFileSync(canonical, 'utf8')
  const hash = createHash('sha256').update(source).digest('hex')
  const env = { VITE_API_BASE_URL: api, VITE_FIREBASE_EMULATOR: 'true', VITE_FIREBASE_API_KEY: 'demo-key',
    VITE_FIREBASE_PROJECT_ID: 'demo-gesture-relay', VITE_FIREBASE_AUTH_DOMAIN: 'localhost', VITE_FIREBASE_APP_ID: 'demo-app' }
  assert.equal(env.VITE_FIREBASE_PROJECT_ID.startsWith('demo-'), true)
  let transformed = source.replace('import.meta.env', JSON.stringify(env))
    .replace("from '../backend'", "from './backend.mjs'")
    .replace("from './emulatorGuard'", "from './emulatorGuard.mjs'")
  if (!plan.defaultPortsAvailable) transformed = transformed.replace("'http://127.0.0.1:9099'", `'http://127.0.0.1:${plan.ports.auth}'`)
    .replace("'127.0.0.1', 8080", `'127.0.0.1', ${plan.ports.firestore}`)
  const generatedDir = resolve(ROOT, '.tools/pr3-client', hash.slice(0, 12))
  mkdirSync(generatedDir, { recursive: true })
  const dependencies = resolve(generatedDir, 'node_modules')
  if (!existsSync(dependencies)) symlinkSync(resolve(FRONTEND, 'node_modules'), dependencies, 'dir')
  for (const [input, output] of [['api/backend.ts', 'backend.mjs'], ['api/real/emulatorGuard.ts', 'emulatorGuard.mjs'], ['game/heartbeat.ts', 'heartbeat.mjs']]) {
    writeFileSync(resolve(generatedDir, output), stripTypeScriptTypes(readFileSync(resolve(FRONTEND, 'src', input), 'utf8'), { mode: 'strip' }))
  }
  const generated = resolve(generatedDir, 'realBackend.mjs')
  writeFileSync(generated, stripTypeScriptTypes(transformed, { mode: 'strip', sourceUrl: canonical }))
  const faultModule = resolve(generatedDir, 'fault-realBackend.mjs')
  writeFileSync(faultModule, stripTypeScriptTypes(transformed.replace("from 'firebase/firestore'", "from './fault-firestore.mjs'"), { mode: 'strip' }))
  writeFileSync(resolve(generatedDir, 'fault-firestore.mjs'), `export * from 'firebase/firestore';
export function onSnapshot(reference, onNext, onError) {
  queueMicrotask(() => onError(Object.assign(new Error('injected snapshot failure'), { code: globalThis.__g1SnapshotErrorCode })));
  return () => {};
}\n`)
  const viewSource = readFileSync(resolve(FRONTEND, 'src/game/useGame.ts'), 'utf8')
  const viewCode = viewSource.slice(viewSource.indexOf('export interface GameState'), viewSource.indexOf('export type CameraStatus'))
  assert.ok(viewCode.includes('export function deriveView'))
  const viewModule = resolve(generatedDir, 'view.mjs')
  writeFileSync(viewModule, stripTypeScriptTypes(viewCode, { mode: 'strip', sourceUrl: 'canonical-useGame-extract.ts' }))
  const { deriveView } = await import(pathToFileURL(viewModule).href)
  const { startHeartbeat } = await import(pathToFileURL(resolve(generatedDir, 'heartbeat.mjs')).href)
  const output = openSync(resolve(ROOT, '.tools/pr3-api.log'), 'w')
  const server = spawn(python, ['-m', 'uvicorn', 'api.local:build_local_app', '--factory', '--host', '127.0.0.1', '--port', String(port), '--no-access-log'],
    { cwd: ROOT, env: safeEnv, stdio: ['ignore', output, output] })
  const clients = []
  const faultClients = []
  let heartbeat
  let heartbeatFailure
  const counts = new Map()
  function client(player, inject401, faultMode) {
    const worker = new Worker(import.meta.filename, { workerData: { module: pathToFileURL(faultMode ? faultModule : generated).href, api, player, inject401, faultMode } })
    const pending = new Map()
    const observed = { room: null, players: {}, round: null, steps: [], errors: [], events: [] }
    let n = 0
    let readyResolve, readyReject
    const ready = new Promise((done, reject) => { readyResolve = done; readyReject = reject })
    worker.on('error', readyReject)
    worker.on('message', (message) => {
      if (message.ready) readyResolve()
      else if (message.event === 'subscriptionError') observed.errors.push(message)
      else if (message.event) { observed.events.push(message); observed[{ subscribeRoom: 'room', subscribePlayers: 'players', subscribeRound: 'round', subscribeSteps: 'steps' }[message.event]] = message.data }
      else if (message.report) pending.get('report')?.resolve(message.report)
      else {
        const request = pending.get(message.id)
        pending.delete(message.id)
        if (message.error) request?.reject(Object.assign(new Error(message.error.message), message.error))
        else request?.resolve(message.value)
      }
    })
    return { worker, observed, ready,
      call: async (method, ...args) => { await ready; counts.set(method, (counts.get(method) ?? 0) + 1)
        return new Promise((resolve, reject) => { const id = ++n; pending.set(id, { resolve, reject }); worker.postMessage({ id, method, args }) }) },
      report: () => new Promise((resolve, reject) => { pending.set('report', { resolve, reject }); worker.postMessage({ report: true }) }) }
  }
  async function until(read, label) {
    const deadline = Date.now() + 30_000
    while (Date.now() < deadline) { if (heartbeatFailure) throw heartbeatFailure; if (read()) return; await sleep(50) }
    throw new Error(`Timed out ${label}: ${JSON.stringify(clients.map((c) => c.observed.round))}`)
  }
  try {
    const deadline = Date.now() + 20_000
    while (true) {
      try { if ((await fetch(api + '/health', { redirect: 'error' })).ok) break } catch { /* starting */ }
      assert.ok(server.exitCode === null && Date.now() < deadline, 'local API startup failed')
      await sleep(100)
    }
    clients.push(...[0, 1, 2].map((i) => client(String(i), i === 0)))
    const ids = await Promise.all(clients.map((c) => c.call('signIn')))
    assert.equal(new Set(ids).size, 3)
    const room = await clients[0].call('createRoom', { name: 'A', consented: true, request_id: randomUUID() })
    assert.equal(room.player_id, ids[0])
    for (const i of [1, 2]) await clients[i].call('joinRoom', { name: 'ABC'[i], consented: true, request_id: randomUUID(), join_code: room.join_code })
    for (const [i, c] of clients.entries()) {
      await c.call('subscribeRoom', room.room_id)
      await c.call('subscribePlayers', room.room_id)
      await c.call('selectRole', room.room_id, { role: ['A', 'B', 'C'][i], request_id: randomUUID() })
    }
    const views = () => clients.map((c, i) => deriveView({ uid: ids[i], roomId: room.room_id,
      problem: null, room: c.observed.room, players: c.observed.players, round: c.observed.round, steps: c.observed.steps }))
    await until(() => clients.every((c) => c.observed.room && Object.keys(c.observed.players).length === 3), 'lobby subscriptions')
    assert.equal(typeof clients[0].observed.room.created_at, 'string')
    assert.deepEqual(views(), ['lobby', 'lobby', 'lobby'])
    const start = await clients[0].call('startGame', room.room_id, { request_id: randomUUID() })
    for (const c of clients) { await c.call('subscribeRound', room.room_id, start.round_id); await c.call('subscribeSteps', room.room_id, start.round_id) }
    heartbeat = startHeartbeat(() => Promise.all(clients.map((c) => c.call('heartbeat', room.room_id)))
      .catch((error) => { heartbeatFailure = error; throw error }), 5000)
    // Use the canonical helper, while React effect lifecycle remains unverified.
    await until(() => (counts.get('heartbeat') ?? 0) >= 6, 'periodic HTTP heartbeat')
    await until(() => JSON.stringify(views()) === '["text","waiting","waiting"]', 'A text view')
    const input = await clients[0].call('getMyInput', start.round_id)
    const image = await clients[0].call('getAsset', start.round_id, input.input.asset_id)
    assert.equal(image.contentType, 'image/png'); assert.equal(image.bytes[0], 0x89)
    await clients[0].call('submitText', start.round_id, 1, { text: '犬', is_auto: false, request_id: randomUUID() })
    await until(() => JSON.stringify(views()) === '["waiting","gesture","waiting"]', 'B gesture view')
    const timing = await clients[1].call('getMyInput', start.round_id)
    assert.equal(timing.countdown_seconds, countdown); assert.equal(timing.record_seconds, 5)
    const session = await clients[1].call('gestureStart', start.round_id, { request_id: randomUUID() })
    await clients[1].call('gestureBatch', start.round_id, { gesture_session_id: session.gesture_session_id, sequence_number: 0,
      mirrored: false, samples: [{ timestamp_ms: 0, hands: [] }] })
    await clients[1].call('gestureFinish', start.round_id, { gesture_session_id: session.gesture_session_id, request_id: randomUUID() })
    await assert.rejects(clients[2].call('getMyInput', start.round_id), (error) => error.status === 403)
    const recording = execFileSync(python, ['-c', 'import sys; from tests.conftest import video_bytes; sys.stdout.buffer.write(video_bytes())'], { cwd: ROOT, env: safeEnv })
    const video = await clients[1].call('gestureVideo', start.round_id, { gesture_session_id: session.gesture_session_id,
      request_id: randomUUID(), file: new Blob([recording], { type: 'video/mp4' }) })
    await until(() => JSON.stringify(views()) === '["waiting","waiting","text"]', 'C text view')
    assert.equal((await clients[2].call('getAsset', start.round_id, video.asset_id)).contentType, 'video/mp4')
    await clients[2].call('submitText', start.round_id, 3, { text: '犬', is_auto: false, request_id: randomUUID() })
    await until(() => views().every((v) => v === 'result'), 'result views')
    for (const c of clients) {
      const history = await c.call('getHistory', start.round_id)
      assert.equal(history.steps.length, 6); assert.ok(history.result.ai_conclusion)
      assert.deepEqual(c.observed.steps.map((s) => s.step_index), [0, 1, 2, 3, 4, 5])
      await c.call('leaveRoom', room.room_id, { request_id: randomUUID() })
      await assert.rejects(c.call('getHistory', start.round_id), (error) => error.status === 403)
    }
    await until(() => views().every((v) => v === 'lobby'), 'return lobby views')
    heartbeat?.(); heartbeat = undefined
    const replay = await clients[0].report()
    assert.deepEqual(replay, { createAttempts: 2, sameBody: true })
    const methods = ['createRoom','joinRoom','selectRole','startGame','getMyInput','submitText','gestureStart','gestureBatch','gestureVideo','gestureFinish','getHistory','getAsset','leaveRoom','heartbeat']
    assert.ok(methods.every((m) => counts.get(m) > 0))
    for (const code of ['unavailable', 'permission-denied']) {
      const c = client(`fault-${code}`, false, code)
      faultClients.push(c)
      await c.call('subscribeRoom', 'fault-room')
      await c.call('subscribePlayers', 'fault-room')
      await c.call('subscribeRound', 'fault-room', 'fault-round')
      await c.call('subscribeSteps', 'fault-room', 'fault-round')
      if (code === 'unavailable') {
        await until(() => c.observed.errors.length === 4, 'four injected subscription errors')
        assert.ok(c.observed.errors.every((e) => e.code === code))
      } else {
        await until(() => c.observed.events.length === 2, 'gone room and round events')
        assert.ok(c.observed.events.every((event) => event.data === null))
        assert.equal(c.observed.errors.length, 0)
      }
    }
    for (const problem of ['signin', 'connection']) assert.equal(deriveView({ problem }), 'problem')
    assert.equal(readFileSync(canonical, 'utf8'), source)
    const result = { status: 'PASS', canonicalSha256: hash, ports: plan.ports, defaultPortsAvailable: plan.defaultPortsAvailable,
      apiMethods: Object.fromEntries(methods.map((m) => [m, counts.get(m)])), subscriptions: 4, anonymousUsers: 3,
      forced401Replay: replay, screenStates: ['lobby','text','gesture','result','returned-to-lobby'], sourcesEdited: false,
      heartbeatHelper: 'canonical startHeartbeat', injectedSubscriptionCases: 8, problemViewStates: 2,
      countdownSeconds: countdown, backendRevision: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: ROOT, encoding: 'utf8' }).trim(),
      frontendRevision: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: FRONTEND, encoding: 'utf8' }).trim(),
      browserDom: 'unverified', cameraAndPhysicalDevices: 'unverified' }
    writeFileSync(resolve(ROOT, '.tools/pr3-local-result.json'), JSON.stringify(result, null, 2))
    console.log(JSON.stringify(result))
  } finally {
    heartbeat?.()
    await Promise.all([...clients, ...faultClients].map((c) => c.worker.terminate()))
    server.kill('SIGTERM')
    await new Promise((done) => { if (server.exitCode !== null) done(); else server.once('exit', done) })
    closeSync(output)
  }
}
