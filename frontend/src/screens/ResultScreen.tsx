// F5: 結果・履歴・ロビーへ戻る

import { useEffect, useRef, useState } from 'react'
import { backend } from '../api'
import { newRequestId } from '../api/backend'
import type { FailReason, HistoryResponse, HistoryStep, JobStatus } from '../api/types'
import type { GameState } from '../game/useGame'
import { useAssetUrl } from '../lib/hooks'
import { errorMessage, withRetry } from '../lib/retry'
import { BAND_LABEL, similarityBand } from '../game/similarity'
import { plainAiText } from '../game/aiText'
import { Confetti, Stamp } from '../ui/Celebrate'
import { Scene } from '../ui/Scene'
import { useArrived } from '../ui/useArrived'

const FAIL_MESSAGE: Record<FailReason, string> = {
  ai_failed: 'AIがうまく動きませんでした',
  communication_failed: '通信がうまくいきませんでした',
  player_dropped: '参加者が退出しました',
}

const GESTURE_STEP_INDEX = 2

const STEP_TITLE = [
  'AIが描いた最初の絵',
  '人Aの文章',
  '人Bのジェスチャー',
  '人Cの文章',
  'AIが描いた最後の絵',
  'AIの結論',
]

/** 中断したゲームでは、まだ何も作られていない段を表示しない */
function hasContent(step: HistoryStep): boolean {
  return step.text !== undefined || Boolean(step.image_asset_id ?? step.video_asset_id)
}

function StepCard({ roundId, step, delay }: { roundId: string; step: HistoryStep; delay: number }) {
  const assetId = step.image_asset_id ?? step.video_asset_id
  const url = useAssetUrl(roundId, assetId)
  return (
    <section className="card rise" style={{ animationDelay: `${delay}s` }}>
      <h3>{STEP_TITLE[step.step_index]}</h3>
      {url && step.image_asset_id && <img className="media" src={url} alt={STEP_TITLE[step.step_index]} />}
      {url && step.video_asset_id && (
        <video className="media" src={url} controls loop muted playsInline />
      )}
      {step.text !== undefined && <p>{step.text || '（空の文章）'}</p>}
    </section>
  )
}

/** 裏の読み取りの結果。人Cの段とは別に動くので、結果画面に出た時点で未完了のこともある */
function GestureReadCard({
  status,
  text,
  delay,
}: {
  status?: JobStatus
  text?: string | null
  delay: number
}) {
  if (status !== 'processing' && status !== 'done' && status !== 'failed') return null
  const fallback = status === 'failed' ? '読み取りに失敗しました' : '読み取り中です'
  return (
    <section className="card rise" style={{ animationDelay: `${delay}s` }}>
      <h3>AIにはこう見えました</h3>
      <p>{text ? plainAiText(text) : fallback}</p>
      <p className="muted">手の動き（座標）だけを見て、AIが推測した文です。外れても、ゲームには影響しません。</p>
    </section>
  )
}

export function ResultScreen({ game }: { game: GameState }) {
  const { room, roomId, roundId, round } = game
  const [history, setHistory] = useState<HistoryResponse | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // お題とAIの答えのところまで見たら、スタンプを押す
  const finaleRef = useRef<HTMLDivElement>(null)

  // 裏の読み取りが後から終わったときも、表示を更新する
  const gestureAiStatus = round?.gesture_ai_status
  useEffect(() => {
    if (!roundId) return
    let alive = true
    withRetry(() => backend.getHistory(roundId))
      .then((response) => {
        if (alive) setHistory(response)
      })
      .catch((e: unknown) => {
        if (alive) setError(errorMessage(e))
      })
    return () => {
      alive = false
    }
  }, [roundId, gestureAiStatus])

  async function leave() {
    if (!roomId) return
    setBusy(true)
    const body = { request_id: newRequestId() }
    try {
      await withRetry(() => backend.leaveRoom(roomId, body))
    } catch (e) {
      setError(errorMessage(e))
      setBusy(false)
    }
  }

  const result = history?.result
  const visibleSteps = history?.steps.filter(hasContent) ?? []
  // 置き場所は A と B で確認中なので、どちらに入っていても表示する
  const gestureAiText =
    history?.steps[GESTURE_STEP_INDEX]?.gesture_ai_text ?? result?.gesture_ai_text
  // 伝言の流れを1段ずつめくり、最後にお題とAIの答えを並べてスタンプを押す
  const STEP_GAP = 0.45
  const before = visibleSteps.filter((step) => step.step_index <= GESTURE_STEP_INDEX)
  const after = visibleSteps.filter((step) => step.step_index > GESTURE_STEP_INDEX)
  const hasGestureRead = ['processing', 'done', 'failed'].includes(gestureAiStatus ?? '')
  const chainCount = before.length + after.length + (hasGestureRead ? 1 : 0)
  const summaryDelay = 0.3 + chainCount * STEP_GAP
  const band = result ? similarityBand(result.similarity) : null
  // 伝言の流れをめくり終えるまでは、スタンプを押さない（画面が大きく、最初から全部見えるとき用）
  const [revealDone, setRevealDone] = useState(false)
  useEffect(() => {
    if (!history) return
    const timer = setTimeout(() => setRevealDone(true), summaryDelay * 1000)
    return () => clearTimeout(timer)
  }, [history, summaryDelay])
  const arrived = useArrived(finaleRef, band !== null && revealDone)
  const STAMP_DELAY = 0.35

  return (
    <main
      className={arrived ? 'screen wide result shake' : 'screen wide result'}
      style={arrived ? { animationDelay: `${STAMP_DELAY + 0.25}s` } : undefined}
    >
      <div className="heading">
        <p className="en">RESULT</p>
        <h1>{room?.status === 'failed' ? 'ゲームを中断しました' : '結果発表'}</h1>
      </div>

      {room?.fail_reason && <p className="error fail">{FAIL_MESSAGE[room.fail_reason]}</p>}

      {/* パソコンでは、列ごとに上から読む: 最初の絵と人A／人Bのジェスチャーと AI の読み取り／人Cと最後の絵と結論。
          スマホでは列の囲みを無視して、上から順に並ぶ（.chain-col は display: contents） */}
      <div className="result-chain">
        <div className="chain-col">
          {roundId &&
            before
              .filter((step) => step.step_index < GESTURE_STEP_INDEX)
              .map((step, i) => (
                <StepCard key={step.step_index} roundId={roundId} step={step} delay={0.3 + i * STEP_GAP} />
              ))}
        </div>
        <div className="chain-col">
          {roundId &&
            before
              .filter((step) => step.step_index === GESTURE_STEP_INDEX)
              .map((step) => (
                <StepCard
                  key={step.step_index}
                  roundId={roundId}
                  step={step}
                  delay={0.3 + (before.length - 1) * STEP_GAP}
                />
              ))}
          {history && hasGestureRead && (
            <GestureReadCard status={gestureAiStatus} text={gestureAiText} delay={0.3 + before.length * STEP_GAP} />
          )}
        </div>
        <div className="chain-col">
          {roundId &&
            after.map((step, i) => (
              <StepCard
                key={step.step_index}
                roundId={roundId}
                step={step}
                delay={0.3 + (before.length + (hasGestureRead ? 1 : 0) + i) * STEP_GAP}
              />
            ))}
        </div>
      </div>

      {/* 笑う人たちは、伝言の流れをめくり終え、お題とAIの答えのところまで見たら出す */}
      <div className="result-scene">
        {arrived && <Scene kind="laugh" label="ロボットの答えを見て笑う3人" className="rise" />}
      </div>

      {result && band && (
        <div className="finale" ref={finaleRef}>
          <section className="card summary rise" style={{ animationDelay: `${summaryDelay}s` }}>
            <p>
              <small>お題</small>
              <strong>{result.odai}</strong>
            </p>
            <p>
              <small>AIの答え</small>
              <strong>{plainAiText(result.ai_conclusion)}</strong>
            </p>
          </section>
          <div className="stamp-area">
            {arrived && <Stamp label={BAND_LABEL[band]} delay={STAMP_DELAY} />}
          </div>
          {arrived && (
            <p className="muted rise" style={{ animationDelay: `${STAMP_DELAY + 0.4}s`, textAlign: 'center' }}>
              類似度 {Math.round(result.similarity * 100)}%
            </p>
          )}
          {arrived && band === 'near' && <Confetti delay={STAMP_DELAY + 0.2} />}
        </div>
      )}

      <button className="back" disabled={busy} onClick={() => void leave()}>
        ロビーへ戻る
      </button>
      {error && <p className="error">{error}</p>}
    </main>
  )
}
