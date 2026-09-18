import { request } from './request'
import {
  AnswerRecord,
  DifficultyRequest,
  Question,
  Quiz,
  Report,
  TaskState,
} from '../types'

/** 提交出题任务，返回 task_id。 */
export function submitQuizTask(params: {
  user_input: string
  question_count?: number
  difficulty?: DifficultyRequest
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
