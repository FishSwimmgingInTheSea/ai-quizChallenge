import { getQuizTask } from './api'
import { POLL_INTERVAL_MS, POLL_MAX_TIMES } from './config'
import { TaskState } from '../types'

interface PollHandlers {
  onUpdate: (state: TaskState) => void
  onDone?: (state: TaskState) => void
  onError?: (err: Error) => void
}

/**
 * 轮询出题进度（方案 §9.4.3）：setTimeout 串行，避免请求叠加；带最大次数兜底。
 * 返回 stop 函数。
 */
export function startPolling(taskId: string, handlers: PollHandlers): () => void {
  let stopped = false
  let times = 0
  let timer: ReturnType<typeof setTimeout>

  const tick = async () => {
    if (stopped) return
    times += 1
    try {
      const state = await getQuizTask(taskId)
      if (stopped) return
      handlers.onUpdate(state)
      if (state.status === 'done') {
        handlers.onDone?.(state)
        return
      }
      if (state.status === 'failed') {
        handlers.onError?.(new Error(state.error || '生成失败'))
        return
      }
    } catch (e: any) {
      handlers.onError?.(e instanceof Error ? e : new Error(String(e)))
      return
    }
    if (times >= POLL_MAX_TIMES) {
      handlers.onError?.(new Error('生成超时，请重试'))
      return
    }
    timer = setTimeout(tick, POLL_INTERVAL_MS)
  }

  timer = setTimeout(tick, POLL_INTERVAL_MS)
  return () => {
    stopped = true
    clearTimeout(timer)
  }
}
