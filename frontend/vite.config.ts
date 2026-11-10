import basicSsl from '@vitejs/plugin-basic-ssl'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // iPhone のカメラは HTTPS でないと動かないので、実機確認のときだけ --mode https で起動する
  const https = mode === 'https'
  return {
    plugins: https ? [react(), basicSsl()] : [react()],
    server: { host: https },
  }
})
