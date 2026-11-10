// F3: 素材の表示、文章の提出、締切時の自動送信

import { useCallback, useEffect, useRef, useState } from 'react'
import { backend } from '../api'
import { ApiError, newRequestId } from '../api/backend'
import { forget, recall, remember } from '../lib/tabMemory'
import type { MyInputResponse } from '../api/types'
import { useAssetUrl, useSecondsLeft } from '../lib/hooks'
import { errorMessage, sleepUntil, withRetry } from '../lib/retry'
import { Scene } from '../ui/Scene'

type SendState = 'editing' | 'sending' | 'sent'

export function TextScreen({ roundId, stepIndex }: { roundId: string; stepIndex: number }) {
  const [input, setInput] = useState<MyInputResponse | null>(null)
  // 書きかけの文は、再読み込みしても戻せるように、このタブに覚えておく
  const draftKey = `draft:${roundId}:${stepIndex}`
  const [text, setText] = useState(() => recall(draftKey) ?? '')
  const [sendState, setSendState] = useState<SendState>('editing')
  const [error, setError] = useState('')

  // 締切のタイマーから最新の値を読むために、ref にも持っておく
  const textRef = useRef(text)
  const sendStateRef = useRef<SendState>('editing')

  const secondsLeft = useSecondsLeft(input?.deadline_at)
  const assetId =
    input && input.input.kind !== 'text' ? input.input.asset_id : null
  const assetUrl = useAssetUrl(roundId, assetId)

  const send = useCallback(
    async (isAuto: boolean) => {
      if (sendStateRef.current !== 'editing') return
      sendStateRef.current = 'sending'
      setSendState('sending')
      setError('')
      // 再送は同じ request_id と同じ中身で送る
      const body = { text: textRef.current, request_id: newRequestId(), is_auto: isAuto }
      try {
        await withRetry(() => backend.submitText(roundId, stepIndex, body))
        forget(draftKey)
        sendStateRef.current = 'sent'
        setSendState('sent')
      } catch (e) {
        if (e instanceof ApiError && e.code === 'ALREADY_SUBMITTED') {
          forget(draftKey)
          sendStateRef.current = 'sent'
          setSendState('sent')
          return
        }
        sendStateRef.current = 'editing'
        setSendState('editing')
        setError(errorMessage(e))
      }
    },
    [roundId, stepIndex, draftKey],
  )

  useEffect(() => {
    let alive = true
    withRetry(() => backend.getMyInput(roundId))
      .then((response) => {
        if (!alive) return
        setInput(response)
        // 締切ちょうどに、できているところまでを自動で送る
        void sleepUntil(Date.parse(response.deadline_at)).then(() => {
          if (alive) void send(true)
        })
      })
      .catch((e: unknown) => {
        if (alive) setError(errorMessage(e))
      })
    return () => {
      alive = false
    }
  }, [roundId, send])

  if (sendState === 'sent') {
    return (
      <main className="screen">
        <div className="heading">
          <p className="en">SENT</p>
          <h1>送信しました</h1>
        </div>
        <Scene kind="robot" label="次の段を待つ間の絵" />
        <p>次の段へ進むのを待っています</p>
      </main>
    )
  }

  const isVideo = input?.input.kind === 'video'
  return (
    <main className="screen wide">
      <div className="heading">
        <p className="en">{isVideo ? 'STEP 3' : 'STEP 1'}</p>
        <h1>{isVideo ? '録画を文章にしよう' : '絵を文章にしよう'}</h1>
      </div>
      <div className="split">
        <div>
          {assetUrl && input?.input.kind === 'image' && (
            <img className="media" src={assetUrl} alt="AIが生成した絵" />
          )}
          {assetUrl && isVideo && (
            <video className="media" src={assetUrl} controls autoPlay loop muted playsInline />
          )}
          {input && !assetUrl && <p className="card">読み込み中です</p>}
        </div>
        <div>
          <p className="timer">残り {secondsLeft ?? '--'} 秒</p>
          <Scene kind="think" label="悩みながら文章にする人" />
          <textarea
            rows={4}
            maxLength={2000}
            value={text}
            placeholder={isVideo ? '見た動きを、短い文にしよう' : '見た絵を、短い文にしよう'}
            disabled={sendState !== 'editing'}
            onChange={(e) => {
              textRef.current = e.target.value
              setText(e.target.value)
              remember(draftKey, e.target.value)
            }}
          />
          <button disabled={sendState !== 'editing'} onClick={() => void send(false)}>
            送る
          </button>
          {error && <p className="error">{error}</p>}
        </div>
      </div>
    </main>
  )
}
