// 実機確認のページ（?poc で開く）。ゲームを通さずに、カメラ、手の検出、軌跡、録画を1台で確かめる。

import { useEffect, useRef, useState } from 'react'
import type { Sample } from '../api/types'
import { loadEffectChoice, prepareCapture, saveEffectChoice } from '../gesture/capture'
import {
  EffectTypePicker,
  GestureRule,
  PreviewNote,
  TrailModePicker,
  TYPE_LOCK_SECONDS,
} from '../gesture/EffectPicker'
import type { EffectChoice, EffectId, TrailMode } from '../gesture/effects'
import { recordCanvas } from '../gesture/recorder'

// ゲームと同じ長さで録る（録画8秒、締切より0.2秒早く止める）。?record_seconds=5 のように変えられる
const RECORD_SECONDS = Number(new URLSearchParams(location.search).get('record_seconds')) || 8
const RECORD_MS = RECORD_SECONDS * 1000 - 200
const SAMPLE_INTERVAL_MS = 100

const wait = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

interface PocResult {
  url: string
  extension: string
  contentType: string
  sizeKb: number
  sampleCount: number
  handRate: number
  coordinateKb: number
}

function report(error: unknown): string {
  return error instanceof Error ? `${error.name}: ${error.message}` : String(error)
}

export function GesturePoc() {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const startedRef = useRef(false)
  const [status, setStatus] = useState('読み込み中です（初回は時間がかかります）')
  const [ready, setReady] = useState(false)
  const [handCount, setHandCount] = useState(0)
  const [recording, setRecording] = useState(false)
  const [counting, setCounting] = useState<number | null>(null)
  const [duration, setDuration] = useState<number | null>(null)
  const [result, setResult] = useState<PocResult | null>(null)
  const [effect, setEffect] = useState<EffectChoice>(loadEffectChoice)

  const effectRef = useRef(effect)

  function remember(choice: EffectChoice) {
    setEffect(choice)
    effectRef.current = choice
    saveEffectChoice(choice)
  }

  function chooseType(id: EffectId) {
    const choice = { ...effectRef.current, id }
    remember(choice)
    void prepareCapture().then((capture) => capture.setEffect(choice))
  }

  function chooseMode(mode: TrailMode) {
    remember({ ...effectRef.current, mode })
    void prepareCapture().then((capture) => capture.setTrailMode(mode))
  }

  useEffect(() => {
    if (startedRef.current) return
    startedRef.current = true
    const startedAt = performance.now()
    prepareCapture()
      .then((capture) => {
        if (canvasRef.current) capture.start(canvasRef.current)
        setStatus(`準備完了（${((performance.now() - startedAt) / 1000).toFixed(1)}秒）`)
        setReady(true)
      })
      .catch((error: unknown) => setStatus(`失敗: ${report(error)}`))
  }, [])

  // 手を見失っているのか、エフェクトの見え方の問題なのかを切り分けるために、今の検出数を出す
  useEffect(() => {
    if (!ready) return
    const timer = setInterval(() => {
      void prepareCapture().then((capture) => setHandCount(capture.sample(0).hands.length))
    }, 200)
    return () => clearInterval(timer)
  }, [ready])

  async function record() {
    const canvas = canvasRef.current
    if (!canvas) return
    setRecording(true)
    setResult(null)
    setDuration(null)
    try {
      const capture = await prepareCapture()
      // ゲームと同じく、録画の前に手を構える時間を取る。この間は試し描き
      for (let left = TYPE_LOCK_SECONDS; left > 0; left -= 1) {
        setCounting(left)
        await wait(1_000)
      }
      setCounting(null)
      capture.setPreview(false)
      capture.setEffect(effectRef.current) // 試し描きを消して、ここから録画する
      const samples: Sample[] = []
      const startedAt = Date.now()
      const sampling = setInterval(
        () => samples.push(capture.sample(Date.now() - startedAt)),
        SAMPLE_INTERVAL_MS,
      )
      const blob = await recordCanvas(canvas, RECORD_MS)
      clearInterval(sampling)
      capture.setPreview(true)
      capture.setEffect(effectRef.current)
      setResult({
        url: URL.createObjectURL(blob),
        extension: blob.type === 'video/mp4' ? 'mp4' : 'webm',
        contentType: blob.type,
        sizeKb: Math.round(blob.size / 1024),
        sampleCount: samples.length,
        handRate: samples.filter((s) => s.hands.length > 0).length / (samples.length || 1),
        coordinateKb: Math.round(JSON.stringify(samples).length / 1024),
      })
    } catch (error) {
      setStatus(`録画に失敗: ${report(error)}`)
    }
    setCounting(null)
    setRecording(false)
  }

  return (
    <main className="screen">
      <h1>カメラと録画の確認</h1>
      <p>{status}</p>
      {ready && <p className="timer">今の検出: 手 {handCount} つ</p>}
      <EffectTypePicker value={effect.id} onChange={chooseType} disabled={!ready || recording} />
      <TrailModePicker value={effect.mode} onChange={chooseMode} disabled={!ready} />
      <PreviewNote />
      <GestureRule />
      {counting !== null && (
        <p className="big-count" aria-live="assertive">
          {counting}
          <span>手を構えてください</span>
        </p>
      )}
      <canvas ref={canvasRef} className="media" width={480} height={360} />
      <button disabled={!ready || recording} onClick={() => void record()}>
        {counting !== null ? '準備中です' : recording ? '録画中です' : `約${RECORD_SECONDS}秒録画する`}
      </button>

      {result && (
        <section className="card">
          <h3>結果</h3>
          <video
            className="media"
            src={result.url}
            controls
            loop
            muted
            playsInline
            onLoadedMetadata={(e) => setDuration(e.currentTarget.duration)}
          />
          <ul>
            <li>形式: {result.contentType}</li>
            <li>サイズ: {result.sizeKb} KB</li>
            <li>再生時間: {duration === null ? '不明' : `${duration.toFixed(2)} 秒`}</li>
            <li>座標の件数: {result.sampleCount} 件</li>
            <li>手が映っていた割合: {Math.round(result.handRate * 100)}%</li>
            <li>座標データの大きさ: {result.coordinateKb} KB</li>
          </ul>
          <a href={result.url} download={`sample.${result.extension}`}>
            録画を保存する（Aの確認用）
          </a>
        </section>
      )}
    </main>
  )
}
