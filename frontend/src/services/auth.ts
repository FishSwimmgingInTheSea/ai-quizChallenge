/**
 * 登录编排：wx.login code -> 后端换 Token（用户系统方案设计 §10.1 / §10.3）。
 */
import Taro from '@tarojs/taro'
import { getProfile, login as loginApi } from './api'
import { clearToken, getToken, setToken } from './token'
import { useUserStore } from '../store/user'
import { UserProfile } from '../types'

/** 封装 Taro.login，仅拿 code。 */
function wxLoginCode(): Promise<string> {
  return new Promise((resolve, reject) => {
    Taro.login({
      success: (res) => {
        if (res.code) resolve(res.code)
        else reject(new Error('获取微信登录凭证失败，请重试'))
      },
      fail: () => reject(new Error('微信登录失败，请重试')),
    })
  })
}

/** 主动登录（登录页按钮）：成功后写 Token + user store。 */
export async function login(): Promise<UserProfile> {
  const code = await wxLoginCode()
  const result = await loginApi({ code })
  setToken(result.token)
  useUserStore.getState().setAuth(result.profile)
  return result.profile
}

/** 静默重登（Token 过期后自动换新，用户无感）；失败保持匿名，返回 null。 */
export async function silentRelogin(): Promise<UserProfile | null> {
  try {
    return await login()
  } catch {
    clearToken()
    useUserStore.getState().clear()
    return null
  }
}

/**
 * 启动恢复登录态（用户系统方案设计 §10.3）：
 * 本地有 Token -> 拉 profile 验证；4010 -> 静默重登一次；仍失败 -> 匿名。
 */
export async function restoreLoginState(): Promise<void> {
  if (!getToken()) {
    useUserStore.getState().clear()
    return
  }
  try {
    const profile = await getProfile()
    useUserStore.getState().setAuth(profile)
  } catch (e: any) {
    if (e?.code === 4010) {
      await silentRelogin()
      return
    }
    // 网络异常等：保留本地 Token 与匿名展示，下次请求再验证
  }
}
