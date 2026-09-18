/**
 * 后端 API 基地址。
 * - 本地开发：微信开发者工具勾选「不校验合法域名」后可直连 http://127.0.0.1:8000
 * - 正式环境：替换为已备案的 HTTPS 域名
 */
export const API_BASE =
  process.env.TARO_APP_API || 'http://127.0.0.1:8000/api/v1'

/** 轮询间隔与上限（方案 §9.4.3 前端设计） */
export const POLL_INTERVAL_MS = 1500
export const POLL_MAX_TIMES = 40 // 40 * 1.5s = 60s 兜底超时
