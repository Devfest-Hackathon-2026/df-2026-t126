// ページを再読み込みしても、このタブの中だけ残しておきたい値（sessionStorage）。
// 再読み込みのあと、同じ送信 ID で送り直したり、書きかけの文を戻したりするために使う。
// 使えない環境（プライベートブラウズの制限など）では、何もしない（覚えていないものとして動く）。

export function remember(key: string, value: string): void {
  try {
    sessionStorage.setItem(key, value)
  } catch {
    // 覚えられなくても、ゲームは続けられる
  }
}

export function recall(key: string): string | null {
  try {
    return sessionStorage.getItem(key)
  } catch {
    return null
  }
}

export function forget(key: string): void {
  try {
    sessionStorage.removeItem(key)
  } catch {
    // 何もしない
  }
}

/** key に覚えた値を返す。なければ make() で作って覚える */
export function recallOrMake(key: string, make: () => string): string {
  const saved = recall(key)
  if (saved) return saved
  const value = make()
  remember(key, value)
  return value
}
