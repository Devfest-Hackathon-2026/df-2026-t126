// F4: 文章の表示、カウントダウン、録画、座標と録画の送信

import { useEffect, useRef, useState } from 'react'
import { backend } from '../api'
import { ApiError, newRequestId } from '../api/backend'
import {
  loadEffectChoice,
  prepareCapture,
  releaseCapture,
  saveEffectChoice,
  type GestureCapture,
} from '../gesture/capture'
import {
  EffectTypePicker,
  GestureRule,
  HandTips,
  PreviewNote,
  TrailModePicker,
  TYPE_LOCK_SECONDS,
} from '../gesture/EffectPicker'
import { effectLabel, type EffectChoice, type EffectId, type TrailMode } from '../gesture/effects'
import { recordCanvas } from '../gesture/recorder'
import { startBatchSender } from '../gesture/batchSender'
import { useSecondsLeft } from '../lib/hooks'
import { errorMessage, sleepUntil, withRetry } from '../lib/retry'
import { forget, recall, recallOrMake, remember as rememberInTab } from '../lib/tabMemory'

const SAMPLE_INTERVAL_MS = 100
const BATCH_INTERVAL_MS = 1_000
// 録画の終了後、残りの座標の送信を待つ上限。録画のアップロードと終了通知に、受付時間（締切＋猶予5秒）を残す
const COORDINATE_WAIT_MS = 1_000
// サーバーの上限を超えないように、録画を締切より少し早く止める
const STOP_EARLY_MS = 200
// 録画の途中で再読み込みしたときの、いちばん短い録画
const MIN_RESUMED_RECORD_MS = 1_000
// A が my-input に秒数を足すまでの仮の値（docs/frontend-requests.md §1）
const FALLBACK_RECORD_SECONDS = 8

type Phase = 'preparing' | 'countdown' | 'recording' | 'sending' | 'sent' | 'error'

const PHASE_TITLE: Record<Phase, string> = {
  preparing: '準備しています',
  countdown: '文章を読んで、エフェクトを選んでください',
  recording: '録画中',
  sending: '送信しています',
  sent: '送信しました',
  error: '送信に失敗しました',
}

function ignoreAlreadySubmitted(error: unknown): void {
  if (!(error instanceof ApiError && error.code === 'ALREADY_SUBMITTED')) throw error
}

export function GestureScreen({ roundId }: { roundId: string }) {
  const [phase, setPhase] = useState<Phase>('preparing')
  const [text, setText] = useState('')
  const [recordStartIso, setRecordStartIso] = useState<string | null>(null)
  // 帯を減らしていく長さ（ミリ秒）。録画までと、録画中
  const [countdownMs, setCountdownMs] = useState(0)
  const [recordingMs, setRecordingMs] = useState(0)
  const [error, setError] = useState('')
  const [effect, setEffect] = useState<EffectChoice>(loadEffectChoice)
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const startedRef = useRef(false)
  const captureRef = useRef<GestureCapture | null>(null)
  const effectRef = useRef(effect)

  function remember(choice: EffectChoice) {
    setEffect(choice)
    effectRef.current = choice
    saveEffectChoice(choice)
  }

  /** 種類を変えると、描いたものは消えて最初からになる */
  function chooseType(id: EffectId) {
    const choice = { ...effectRef.current, id }
    remember(choice)
    captureRef.current?.setEffect(choice)
  }

  /** 残す・消すを変えても、すでに描いた線はそのまま */
  function chooseMode(mode: TrailMode) {
    remember({ ...effectRef.current, mode })
    captureRef.current?.setTrailMode(mode)
  }

  const countdown = useSecondsLeft(recordStartIso)
  // 録画の少し前に種類を締め切り、手を構える時間にする
  const typeLocked = phase === 'countdown' && countdown !== null && countdown <= TYPE_LOCK_SECONDS

  useEffect(() => {
    // 開発時は React が useEffect を2回呼ぶので、1回だけ動かす
    if (startedRef.current) return
    startedRef.current = true

    async function run() {
      const canvas = canvasRef.current
      if (!canvas) return
      try {
        const capture = await prepareCapture()
        captureRef.current = capture
        capture.setPreview(true) // 録画が始まるまでは試し描き
        capture.setEffect(effectRef.current)
        const input = await withRetry(() => backend.getMyInput(roundId))
        if (input.input.kind === 'text') setText(input.input.text)

        // 再読み込みしても同じ送信 ID で送り直し、同じ録画の回を続ける
        // （新しい ID だと、サーバーは「もう始まっている」と断り、ゲームが止まる）
        const startKey = `gesture-start:${roundId}`
        const sequenceKey = `gesture-sequence:${roundId}`
        const startBody = { request_id: recallOrMake(startKey, newRequestId) }
        const session = await withRetry(() => backend.gestureStart(roundId, startBody))
        const sessionId = session.gesture_session_id

        const fullRecordMs = (input.record_seconds ?? FALLBACK_RECORD_SECONDS) * 1000
        const deadline = Date.parse(session.deadline_at)
        const recordStart = deadline - fullRecordMs
        // 録画の途中で再読み込みしたときは、締切までの残りだけ録画する（最低1秒。締切のあとも猶予の間は受け付ける）
        const recordMs = Math.min(fullRecordMs, Math.max(MIN_RESUMED_RECORD_MS, deadline - Date.now()))
        capture.start(canvas)
        setRecordStartIso(new Date(recordStart).toISOString())
        setCountdownMs(Math.max(0, recordStart - Date.now()))
        setRecordingMs(recordMs)
        setPhase('countdown')
        await sleepUntil(recordStart)

        // 試し描きを消して、ここから描いたものだけを録画に入れる
        capture.setPreview(false)
        capture.setEffect(effectRef.current)
        setPhase('recording')
        const stopSending = startBatchSender({
          sessionId,
          mirrored: capture.mirrored,
          read: capture.sample,
          send: (batch) => withRetry(() => backend.gestureBatch(roundId, batch)),
          sampleMs: SAMPLE_INTERVAL_MS,
          batchMs: BATCH_INTERVAL_MS,
          waitMs: COORDINATE_WAIT_MS,
          recordStartMs: recordStart,
          // 再読み込みしても、前に使った番号の続きから送る（同じ番号は、サーバーが後のものを捨てる）
          firstSequence: Number(recall(sequenceKey)) || 0,
          onSequence: (next) => rememberInTab(sequenceKey, String(next)),
        })
        const file = await recordCanvas(canvas, recordMs - STOP_EARLY_MS)
        captureRef.current = null
        releaseCapture() // 録画が終わったら、すぐカメラを止める
        await stopSending()

        setPhase('sending')
        const videoBody = { gesture_session_id: sessionId, request_id: newRequestId(), file }
        await withRetry(() => backend.gestureVideo(roundId, videoBody)).catch(
          ignoreAlreadySubmitted,
        )
        const finishBody = { gesture_session_id: sessionId, request_id: newRequestId() }
        await withRetry(() => backend.gestureFinish(roundId, finishBody)).catch(
          ignoreAlreadySubmitted,
        )
        forget(startKey)
        forget(sequenceKey)
        setPhase('sent')
      } catch (e) {
        setError(errorMessage(e))
        setPhase('error')
      } finally {
        releaseCapture()
      }
    }

    void run()
  }, [roundId])

  return (
    <main className="screen">
      <div className="heading">
        <p className="en">STEP 2</p>
        <h1>{typeLocked ? 'まもなく録画が始まります' : PHASE_TITLE[phase]}</h1>
      </div>
      {text && <p className="prompt">{text}</p>}
      {phase === 'countdown' && (
        <div className={typeLocked ? 'count sticky locked' : 'count sticky'} aria-live="polite">
          <p>
            録画まで <strong key={typeLocked ? countdown : 'wait'}>{countdown ?? '--'}</strong> 秒
            {typeLocked && <span>手を構えてください</span>}
          </p>
          <div className="count-bar">
            <i key={recordStartIso} style={{ animationDuration: `${countdownMs}ms` }} />
          </div>
        </div>
      )}
      {(phase === 'preparing' || phase === 'countdown') && (
        <>
          <EffectTypePicker value={effect.id} onChange={chooseType} disabled={typeLocked} />
          <TrailModePicker value={effect.mode} onChange={chooseMode} />
          <HandTips />
          <PreviewNote />
          <GestureRule />
        </>
      )}
      {phase === 'recording' && (
        <>
          <div className="count recording sticky">
            <p>録画中</p>
            <div className="count-bar">
              <i style={{ animationDuration: `${recordingMs}ms` }} />
            </div>
          </div>
          <p className="muted">エフェクト: {effectLabel(effect)}</p>
          <TrailModePicker value={effect.mode} onChange={chooseMode} />
        </>
      )}
      <div className="stage">
        <canvas ref={canvasRef} className="media" width={480} height={360} />
        {typeLocked && (
          <p className="stage-count" aria-hidden="true">
            <b key={countdown}>{countdown}</b>
          </p>
        )}
        {phase === 'recording' && (
          <>
            <p className="go" aria-live="assertive">
              録画開始！
            </p>
            <div className="flash" aria-hidden="true" />
          </>
        )}
      </div>
      {error && <p className="error">{error}</p>}
    </main>
  )
}
