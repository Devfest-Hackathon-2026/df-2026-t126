// キャンバスの内容を録画する。エフェクト込みの録画は、このキャンバスに映像とエフェクトを描いて作る。

// iPhone でも再生できるように mp4 を優先する
const CANDIDATES = [
  { mimeType: 'video/mp4', contentType: 'video/mp4' },
  { mimeType: 'video/webm;codecs=vp9', contentType: 'video/webm' },
  { mimeType: 'video/webm;codecs=vp8', contentType: 'video/webm' },
  { mimeType: 'video/webm', contentType: 'video/webm' },
]

const VIDEO_BITS_PER_SECOND = 1_000_000 // 締切後の猶予で送り切れるように小さくする
const FRAME_RATE = 30

/**
 * 指定の時間だけ録画する。
 * サーバーは Content-Type を完全一致で確認するので、codecs を外した形式名で Blob を作る。
 */
export function recordCanvas(canvas: HTMLCanvasElement, durationMs: number): Promise<Blob> {
  const format = CANDIDATES.find((c) => MediaRecorder.isTypeSupported(c.mimeType))
  if (!format) return Promise.reject(new Error('この端末は録画に対応していません'))

  return new Promise((resolve, reject) => {
    const stream = canvas.captureStream(FRAME_RATE)
    const recorder = new MediaRecorder(stream, {
      mimeType: format.mimeType,
      videoBitsPerSecond: VIDEO_BITS_PER_SECOND,
    })
    const chunks: Blob[] = []
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data)
    }
    recorder.onerror = () => reject(new Error('録画に失敗しました'))
    recorder.onstop = () => {
      stream.getTracks().forEach((track) => track.stop())
      resolve(new Blob(chunks, { type: format.contentType }))
    }
    recorder.start()
    setTimeout(() => recorder.stop(), durationMs)
  })
}
