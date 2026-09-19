/**
 * Token 存取（用户系统方案设计 §10.1）。
 *
 * 独立成模块避免 request.ts / auth.ts / api.ts 循环依赖：
 * request.ts -> token.ts <- auth.ts -> api.ts -> request.ts
 */
import Taro from '@tarojs/taro'

const TOKEN_KEY = 'auth_token'

export function getToken(): string {
  try {
    return Taro.getStorageSync(TOKEN_KEY) || ''
  } catch {
    return ''
  }
}

export function setToken(token: string): void {
  Taro.setStorageSync(TOKEN_KEY, token)
}

export function clearToken(): void {
  Taro.removeStorageSync(TOKEN_KEY)
}

/** 本地存在 Token 即视为登录态；权威校验交给服务端 4010 回执 */
export function isLoggedIn(): boolean {
  return !!getToken()
}
