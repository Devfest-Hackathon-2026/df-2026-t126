// AI が返す文には、Markdown の記号（**太字** や 行頭の「- 」「# 」）が混じることがある。
// 画面では Markdown を解釈しないので、記号だけを取り除いて、ふつうの文として見せる。

export function plainAiText(text: string): string {
  return text
    .replace(/\*\*(.+?)\*\*/gs, '$1')
    .replace(/__(.+?)__/gs, '$1')
    .replace(/^\s{0,3}#{1,6}\s+/gm, '')
    .replace(/^\s*[-*]\s+/gm, '')
    .trim()
}
