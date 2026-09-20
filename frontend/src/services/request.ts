import Taro from '@tarojs/taro'
import { API_BASE } from './config'
import { ApiResponse } from '../types'
import { getToken, clearToken } from './token'
import { useUserStore } from '../store/user'

export class ApiError extends Error {
  code: number
  constructor(code: number, message: string) {
    super(message)
    this.code = code
  }
}

/** 未登录 / 登录过期的统一业务码（后端方案 §5.5） */
export const UNAUTHORIZED_CODE = 4010

interface RequestOptions {
  url: string
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  data?: Record<string, any>
}

/**
 * 统一请求封装：解包 {code,message,data}，非 0 抛 ApiError。
 * 自动携带 Bearer Token；4010 时清除本地登录态后抛错，
 * 由调用方决定是否触发静默重登（用户系统方案设计 §10.2）。
 */
export async function request<T>({
  url,
  method = 'GET',
  data,
}: RequestOptions): Promise<T> {
  const header: Record<string, string> = { 'content-type': 'application/json' }
  const token = getToken()
  if (token) {
    header.Authorization = `Bearer ${token}`
  }

  let res: Taro.request.SuccessCallbackResult<ApiResponse<T>>
  try {
    res = await Taro.request<ApiResponse<T>>({
      url: `${API_BASE}${url}`,
      method,
      data,
      header,
      timeout: 35000,
    })
  } catch (e: any) {
    throw new ApiError(-1, e?.errMsg || '网络异常，请检查网络后重试')
  }

  if (res.statusCode >= 500) {
    throw new ApiError(res.statusCode, '服务器开小差了，请稍后重试')
  }

  const body = res.data
  if (!body || typeof body.code !== 'number') {
    throw new ApiError(-1, '返回数据格式异常')
  }
  if (body.code === UNAUTHORIZED_CODE) {
    // 登录态失效：清除本地 Token 与用户态，转匿名
    clearToken()
    useUserStore.getState().clear()
    throw new ApiError(UNAUTHORIZED_CODE, body.message || '登录已过期，请重新登录')
  }
  if (body.code !== 0) {
    throw new ApiError(body.code, body.message || '请求失败')
  }
  return body.data
}
