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
