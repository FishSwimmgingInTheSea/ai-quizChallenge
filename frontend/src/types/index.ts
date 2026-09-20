export type QuestionType = 'single' | 'multiple' | 'judge'
export type Difficulty = 'easy' | 'medium' | 'hard'
export type DifficultyRequest = Difficulty | 'mixed'
export type TaskStatus = 'pending' | 'generating' | 'done' | 'failed'

export interface Option {
  key: string
  text: string
}

export interface Question {
  id: string
  type: QuestionType
  stem: string
  options: Option[]
  answer: string[]
  explanation: string
  knowledge_point: string
  difficulty: Difficulty
}

export interface Quiz {
  quiz_id: string
  title: string
  summary: string
  source_type: string
  user_input: string
  questions: Question[]
}

export interface AnswerRecord {
  question_id: string
  selected_answers: string[]
  is_correct: boolean
  duration_ms: number
}

export interface TaskState {
  task_id: string
  status: TaskStatus
  /** 生成阶段：researching（联网检索中）/ generating（出题中）；空串为旧语义 */
  phase?: string
  /** 是否实际用上联网研究资料：null = 研究中/未知 */
  research_used?: boolean | null
  generated_count: number
  total: number
  quiz_id: string
  title: string
  summary: string
  questions: Question[]
  error: string | null
  created_at: number
}

export interface Report {
  accuracy: number
  mastered_points: string[]
  weak_points: string[]
  three_line_summary: string[]
  advice: string[]
  share_quote: string
}

export interface ApiResponse<T> {
  code: number
  message: string
  data: T
}

// ---------- 用户系统（用户系统方案设计 §6 / §8） ----------

export interface UserProfile {
  nickname: string
  avatar_url: string
  total_xp: number
}

export interface LoginResult {
  token: string
  profile: UserProfile
}

export interface UserStats {
  total_count: number
  avg_accuracy: number
  total_xp: number
}

export interface QuizRecordItem {
  record_id: number
  title: string
  question_count: number
  correct_count: number
  accuracy: number
  stars: number
  xp_earned: number
  duration_ms: number
  created_at: string
}

export interface QuizRecordsPage {
  total: number
  records: QuizRecordItem[]
}

export interface RecordSubmitResult {
  record_id: number
  correct_count: number
  accuracy: number
  stars: number
  xp_earned: number
  total_xp: number
  duplicated: boolean
}

/** 单题明细：自包含题快照 + 作答（is_correct 为服务端复算值）。 */
export interface RecordQuestionItem {
  question_index: number
  question_id: string
  type: QuestionType
  difficulty: Difficulty
  knowledge_point: string
  stem: string
  options: Option[]
  answer: string[]
  explanation: string
  selected_answers: string[]
  is_correct: boolean
  duration_ms: number
}

/** 单局记录详情：汇总 + 逐题明细 + 复盘报告（无报告时为 null）。 */
export interface RecordDetail {
  record: QuizRecordItem
  questions: RecordQuestionItem[]
  report: Report | null
}

// ---------- 知识库（kb-rag：用户私有知识库） ----------

/** 文档状态机：上传受理（解析中）/ 就绪可出题 / 解析失败。 */
export type KbDocStatus = 'processing' | 'ready' | 'failed'

export interface KbDocument {
  doc_id: number
  filename: string
  doc_type: string
  file_size: number
  char_count: number
  chunk_count: number
  status: KbDocStatus
  error: string
  created_at: string
}

export interface KbDocumentPage {
  total: number
  documents: KbDocument[]
}

export interface KbUploadResult {
  doc_id: number
  status: KbDocStatus
}
