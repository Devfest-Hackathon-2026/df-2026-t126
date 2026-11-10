// 画面が使う窓口の実体を決める場所。VITE_BACKEND=real で本物、それ以外はモックを使う。
// 使わない方は読み込まないので、本番のファイルにモックや Firebase の余分なコードが入らない。

import type { Backend } from './backend'
import type { MockBackend } from './mock/mockBackend'

export const isMock = import.meta.env.VITE_BACKEND !== 'real'

const loaded: Backend = isMock
  ? (await import('./mock/mockBackend')).createMockBackend()
  : (await import('./real/realBackend')).createRealBackend()

export const backend: Backend = loaded

/** モックだけにある開発用の操作。本物のときは null */
export const mockTools: MockBackend | null = isMock ? (loaded as MockBackend) : null
