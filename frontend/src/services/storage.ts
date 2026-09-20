import Taro from '@tarojs/taro'

const RECENT_KEY = 'recent_quizzes'
const XP_KEY = 'total_xp'

export interface RecentQuiz {
  title: string
  count: number
  accuracy: number
  stars: number
  time: string
  /** 服务端记录 id（登录态才有）；匿名本地记录为 undefined，无法回看报告 */
  id?: number
}

export function getRecentQuizzes(): RecentQuiz[] {
  try {
    return Taro.getStorageSync(RECENT_KEY) || []
  } catch {
    return []
  }
}

export function addRecentQuiz(item: RecentQuiz): void {
  const list = getRecentQuizzes()
  list.unshift(item)
  Taro.setStorageSync(RECENT_KEY, list.slice(0, 20))
}

export function getTotalXp(): number {
  try {
    return Taro.getStorageSync(XP_KEY) || 0
  } catch {
    return 0
  }
}

export function addTotalXp(delta: number): void {
  Taro.setStorageSync(XP_KEY, getTotalXp() + delta)
}
