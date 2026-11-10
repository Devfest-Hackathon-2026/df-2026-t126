// エミュレーターで試すつもりが、本物の Firebase や API につながってしまうのを防ぐ。
// Firebase を初期化する前に、設定がエミュレーター用になっているかを確かめる。

const LOOPBACK_HOSTS = new Set(['localhost', '127.0.0.1', '[::1]', '::1'])

function isLoopback(hostname: string): boolean {
  return LOOPBACK_HOSTS.has(hostname) || hostname.endsWith('.localhost')
}

export interface EmulatorConfig {
  /** Firebase のプロジェクト ID */
  projectId: string | undefined
  /** API の URL。空なら、画面と同じ場所（pageUrl）へ送る */
  apiBaseUrl: string
  /** 今開いている画面の URL */
  pageUrl: string
}

/** エミュレーター用の設定でなければ、その理由を返す。問題がなければ null */
export function emulatorConfigProblem(config: EmulatorConfig): string | null {
  if (!config.projectId?.startsWith('demo-')) {
    return `エミュレーターでは、Firebase のプロジェクト ID を demo- で始めてください（今: ${config.projectId ?? '未設定'}）`
  }
  let apiUrl: URL
  try {
    apiUrl = new URL(config.apiBaseUrl || '/', config.pageUrl)
  } catch {
    return `API の URL が読めません（今: ${config.apiBaseUrl}）`
  }
  if (!isLoopback(apiUrl.hostname)) {
    return `エミュレーターでは、API の URL をこの端末（localhost や 127.0.0.1）にしてください（今: ${apiUrl.origin}）`
  }
  return null
}
