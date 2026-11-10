// 類似度を、画面で見せる帯（近い・おしい・遠い）に分ける。
// 短文のお題は、無関係でも点が高め（目安 0.6〜0.7）に出るため、点数そのものより帯で見せる（docs/shared-types.md の推奨）。
// 境界は仮の値。本物の AI で実測してから決め直す。

export type SimilarityBand = 'near' | 'close' | 'far'

export const BAND_THRESHOLDS = { near: 0.85, close: 0.75 }

export const BAND_LABEL: Record<SimilarityBand, string> = {
  near: '近い！',
  close: 'おしい！',
  far: '遠い…',
}

export function similarityBand(similarity: number): SimilarityBand {
  if (similarity >= BAND_THRESHOLDS.near) return 'near'
  if (similarity >= BAND_THRESHOLDS.close) return 'close'
  return 'far'
}
