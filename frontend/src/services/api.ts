import { request } from './request'
import { API_BASE } from './config'
import Taro from '@tarojs/taro'
import { getToken } from './token'
import {
  AnswerRecord,
  DifficultyRequest,
  KbDocumentPage,
  KbUploadResult,
  LoginResult,
  Question,
  Quiz,
  QuizRecordItem,
  QuizRecordsPage,
  RecordDetail,
  RecordSubmitResult,
  Report,
  TaskState,
  UserProfile,
  UserStats,
} from '../types'

/** 提交出题任务，返回 task_id；kb_doc_ids 为选中的知识库文档（登录有效）。 */
export function submitQuizTask(params: {
  user_input: string
  question_count?: number
  difficulty?: DifficultyRequest
  kb_doc_ids?: number[]
}): Promise<{ task_id: string; status: string }> {
  return request({
    url: '/quiz/generate',
    method: 'POST',
    data: {
      question_count: 5,
      difficulty: 'mixed',
      ...params,
    },
  })
}

/** 轮询出题进度。 */
export function getQuizTask(taskId: string): Promise<TaskState> {
  return request({ url: `/quiz/task/${taskId}`, method: 'GET' })
}

/** 同步一次性生成题库（调试用）。 */
export function generateQuizSync(params: {
  user_input: string
  question_count?: number
  difficulty?: DifficultyRequest
}): Promise<Quiz> {
  return request({ url: '/quiz/generate/sync', method: 'POST', data: params })
}

/** 生成复盘报告。 */
export function generateReport(params: {
  quiz_id: string
  topic: string
  questions: Question[]
  answer_records: AnswerRecord[]
}): Promise<Report> {
  return request({ url: '/report/generate', method: 'POST', data: params })
}

// ---------- 用户系统（用户系统方案设计 §9.1） ----------

/** 微信登录：code 换 Token + 资料。 */
export function login(params: { code: string }): Promise<LoginResult> {
  return request({ url: '/auth/login', method: 'POST', data: params })
}

/** 获取当前用户资料（必需登录）。 */
export function getProfile(): Promise<UserProfile> {
  return request({ url: '/user/profile', method: 'GET' })
}

/** 修改昵称 / 头像（至少传一项）。 */
export function updateProfile(params: {
  nickname?: string
  avatar_url?: string
}): Promise<UserProfile> {
  return request({ url: '/user/profile', method: 'PUT', data: params })
}

/** 上传头像文件，返回可引用的 avatar_url。 */
export async function uploadAvatar(
  filePath: string,
): Promise<{ avatar_url: string }> {
  const token = getToken()
  const header: Record<string, string> = {}
  if (token) {
    header.Authorization = `Bearer ${token}`
  }
  const res = await Taro.uploadFile({
    url: `${API_BASE}/user/avatar`,
    filePath,
    name: 'file',
    header,
  })
  if (res.statusCode >= 500) {
    throw new Error('服务器开小差了，请稍后重试')
  }
  let body: { code: number; message?: string; data?: { avatar_url: string } }
  try {
    body = JSON.parse(res.data)
  } catch {
    throw new Error('上传失败，请重试')
  }
  if (body.code !== 0 || !body.data?.avatar_url) {
    throw new Error(body.message || '上传失败，请重试')
  }
  return body.data
}

/** 通关结算写入（幂等，服务端复算权威成绩）；report 为用户实际看到的报告，随事务落库。 */
export function submitQuizRecord(params: {
  client_record_id: string
  title: string
  duration_ms: number
  questions: Question[]
  answer_records: AnswerRecord[]
  report?: Report
}): Promise<RecordSubmitResult> {
  return request({ url: '/quiz/records', method: 'POST', data: params })
}

/** 单局记录详情：汇总 + 逐题明细 + 复盘报告（仅本人可读）。 */
export function getQuizRecordDetail(recordId: number): Promise<RecordDetail> {
  return request({ url: `/quiz/records/${recordId}`, method: 'GET' })
}

/** 闯关历史列表（倒序，limit/offset 分页）。 */
export function getQuizRecords(params: {
  limit?: number
  offset?: number
}): Promise<QuizRecordsPage> {
  return request({
    url: `/quiz/records?limit=${params.limit ?? 10}&offset=${params.offset ?? 0}`,
    method: 'GET',
  })
}

/** 基础统计：闯关次数 / 平均正确率 / 累计 XP。 */
export function getUserStats(): Promise<UserStats> {
  return request({ url: '/user/stats', method: 'GET' })
}

// ---------- 知识库（kb-rag：用户私有知识库） ----------

/** 知识库文档列表（登录，created_at 倒序，limit/offset 分页）。 */
export function getKbDocuments(params: {
  limit?: number
  offset?: number
} = {}): Promise<KbDocumentPage> {
  return request({
    url: `/kb/documents?limit=${params.limit ?? 20}&offset=${params.offset ?? 0}`,
    method: 'GET',
  })
}

/** 上传知识库文档（pdf / docx / md / txt，≤10MB），受理后后台解析向量化。 */
export async function uploadKbDocument(
  filePath: string,
): Promise<KbUploadResult> {
  const token = getToken()
  const header: Record<string, string> = {}
  if (token) {
    header.Authorization = `Bearer ${token}`
  }
  const res = await Taro.uploadFile({
    url: `${API_BASE}/kb/documents`,
    filePath,
    name: 'file',
    header,
  })
  if (res.statusCode >= 500) {
    throw new Error('服务器开小差了，请稍后重试')
  }
  let body: { code: number; message?: string; data?: KbUploadResult }
  try {
    body = JSON.parse(res.data)
  } catch {
    throw new Error('上传失败，请重试')
  }
  if (body.code !== 0 || !body.data?.doc_id) {
    throw new Error(body.message || '上传失败，请重试')
  }
  return body.data
}

/** 删除知识库文档（向量 + 原始文件 + 记录一并清理）。 */
export function deleteKbDocument(docId: number): Promise<null> {
  return request({ url: `/kb/documents/${docId}`, method: 'DELETE' })
}

/** 服务端历史记录 -> 页面展示视图（首页/我的共用，对齐本地 RecentQuiz 结构，方案 §8.1）。 */
export function recordToRecentView(r: QuizRecordItem) {
  return {
    title: r.title,
    count: r.question_count,
    accuracy: r.accuracy,
    stars: r.stars,
    time: r.created_at ? r.created_at.slice(5, 16) : '',
  }
}

export type { QuizRecordItem }
