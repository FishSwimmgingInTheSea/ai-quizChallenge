import { PropsWithChildren } from 'react'
import { useLaunch } from '@tarojs/taro'
import { restoreLoginState } from './services/auth'
import { useQuizStore } from './store/quiz'
import './app.scss'

function App({ children }: PropsWithChildren) {
  useLaunch(() => {
    // 应用启动：恢复登录态（有 Token 则验证，过期则静默换新，失败转匿名）
    restoreLoginState()
    // 拉取后端功能标志：首页配图开关按系统级有效值显隐，失败兜底为关闭
    useQuizStore.getState().fetchFeatures()
  })

  return children
}

export default App
