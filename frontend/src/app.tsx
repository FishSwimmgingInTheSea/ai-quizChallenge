import { PropsWithChildren } from 'react'
import { useLaunch } from '@tarojs/taro'
import { restoreLoginState } from './services/auth'
import './app.scss'

function App({ children }: PropsWithChildren) {
  useLaunch(() => {
    // 应用启动：恢复登录态（有 Token 则验证，过期则静默换新，失败转匿名）
    restoreLoginState()
  })

  return children
}

export default App
