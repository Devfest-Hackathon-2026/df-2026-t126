// エフェクトを選ぶボタンの並び。人Bの録画前と、実機確認のページで使う

import { EffectPreview } from './EffectPreview'
import { EFFECTS, TRAIL_MODES, type EffectId, type TrailMode } from './effects'

/** 録画が始まる何秒前に、エフェクトの種類を締め切るか。最後の数秒は手を構える時間にする */
export const TYPE_LOCK_SECONDS = 3

interface TypePickerProps {
  value: EffectId
  onChange: (id: EffectId) => void
  disabled?: boolean
}

/** エフェクトの種類。録画の少し前に締め切る */
export function EffectTypePicker({ value, onChange, disabled = false }: TypePickerProps) {
  return (
    <div className="effects types" role="group" aria-label="エフェクトの種類">
      {EFFECTS.map((effect) => (
        <button
          key={effect.id}
          className={effect.id === value ? 'selected' : undefined}
          aria-pressed={effect.id === value}
          disabled={disabled}
          onClick={() => onChange(effect.id)}
        >
          {effect.label}
          <EffectPreview id={effect.id} />
        </button>
      ))}
    </div>
  )
}

interface ModePickerProps {
  value: TrailMode
  onChange: (mode: TrailMode) => void
  disabled?: boolean
}

/** 軌跡を残すか消すか。録画中も切り替えられ、切り替える前に描いた線はそのまま */
export function TrailModePicker({ value, onChange, disabled = false }: ModePickerProps) {
  return (
    <div className="effects modes" role="group" aria-label="軌跡を残すか">
      {TRAIL_MODES.map((item) => (
        <button
          key={item.mode}
          className={item.mode === value ? 'selected' : undefined}
          aria-pressed={item.mode === value}
          disabled={disabled}
          onClick={() => onChange(item.mode)}
        >
          軌跡が{item.label}
        </button>
      ))}
    </div>
  )
}

/** 空中に文字を書いて答えを伝えないための注意書き */
export function GestureRule() {
  return <p className="muted">文字を書くのは禁止です。矢印などの記号は使えます。</p>
}

/** 録画前の試し描きの説明 */
export function PreviewNote() {
  return <p className="muted">録画が始まるまでは試し描きです。「残る」でも線は消えます。</p>
}

/** 手がうまく映るための案内。読み取りが外れる一番の原因は、手の検出が途切れること（B の実機確認） */
export function HandTips() {
  return (
    <ul className="tips">
      <li>明るい場所で、手を1つだけ映す</li>
      <li>カメラから、腕1本分くらい離れる</li>
      <li>手がカメラの外に出ないようにする</li>
    </ul>
  )
}
