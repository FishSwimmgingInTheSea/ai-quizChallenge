/**
 * 后端 API 基地址。
 * 实际值由 config/index.ts 在编译期按环境注入（defineConstants）：
 * - 本地开发：http://localhost:8000/api/v1（微信开发者工具需勾选「不校验合法域名」）
 * - 正式环境：https://你的线上域名/api/v1（已备案的 HTTPS 域名）
 * 下方默认值仅作为编译期未注入时的兜底。
 */
export const API_BASE =
  process.env.TARO_APP_API || 'http://localhost:8000/api/v1'

/** 服务端根地址（API_BASE 去掉 /api/v1），用于拼接 /static 等静态资源路径 */
export const SERVER_BASE = API_BASE.replace(/\/api\/v1\/?$/, '')

/** 服务端相对路径（如 /static/avatars/...）转绝对 URL；空值原样返回 */
export function toAbsoluteUrl(path: string): string {
  if (!path) return ''
  if (/^https?:\/\//.test(path)) return path
  return `${SERVER_BASE}${path}`
}

/** 轮询间隔与上限（方案 §9.4.3 前端设计） */
export const POLL_INTERVAL_MS = 1500
export const POLL_MAX_TIMES = 40 // 40 * 1.5s = 60s 兜底超时
