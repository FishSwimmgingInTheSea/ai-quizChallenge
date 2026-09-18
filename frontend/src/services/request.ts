import Taro from '@tarojs/taro'
import { API_BASE } from './config'
import { ApiResponse } from '../types'

export class ApiError extends Error {
  code: number
  constructor(code: number, message: string) {
    super(message)
    this.code = code
  }
}

interface RequestOptions {
  url: string
  method?: 'GET' | 'POST'
  data?: Record<string, any>
}

/**
 * 统一请求封装：解包 {code,message,data}，非 0 抛 ApiError。
 */
export async function request<T>({
  url,
  method = 'GET',
  data,
}: RequestOptions): Promise<T> {
  let res: Taro.request.SuccessCallbackResult<ApiResponse<T>>
  try {
    res = await Taro.request<ApiResponse<T>>({
      url: `${API_BASE}${url}`,
      method,
      data,
      header: { 'content-type': 'application/json' },
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
  if (body.code !== 0) {
    throw new ApiError(body.code, body.message || '请求失败')
  }
  return body.data
}
