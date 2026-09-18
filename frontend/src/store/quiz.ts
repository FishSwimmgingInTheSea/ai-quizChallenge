import { create } from 'zustand'
import {
  AnswerRecord,
  DifficultyRequest,
  Question,
  Report,
  TaskState,
} from '../types'

const XP_PER_CORRECT = 10

export interface QuizState {
  // 输入
  userInput: string
  difficulty: DifficultyRequest

  // 任务
  taskId: string
  quizId: string
  title: string
  summary: string
  status: TaskState['status'] | 'idle'
  generatedCount: number
  total: number
  questions: Question[]

  // 答题
  currentIndex: number
  selected: string[]
  submitted: boolean
  lastCorrect: boolean
  records: AnswerRecord[]
  xp: number
  streak: number
  questionStartTs: number

  // 报告
  report: Report | null

  // actions
  resetSession: (input: string, difficulty: DifficultyRequest) => void
  setTaskId: (taskId: string) => void
  ingestTask: (state: TaskState) => void
  toggleSelect: (key: string) => void
  submitCurrent: () => boolean
  goNext: () => void
  startAnswering: () => void
  setReport: (r: Report) => void
}

function judge(question: Question, selected: string[]): boolean {
  if (question.answer.length !== selected.length) return false
  const a = [...question.answer].sort()
  const b = [...selected].sort()
  return a.every((v, i) => v === b[i])
}

export const useQuizStore = create<QuizState>((set, get) => ({
  userInput: '',
  difficulty: 'mixed',
  taskId: '',
  quizId: '',
  title: '',
  summary: '',
  status: 'idle',
  generatedCount: 0,
  total: 5,
  questions: [],
  currentIndex: 0,
  selected: [],
  submitted: false,
  lastCorrect: false,
  records: [],
  xp: 0,
  streak: 0,
  questionStartTs: 0,
  report: null,

  resetSession: (input, difficulty) =>
    set({
      userInput: input,
      difficulty,
      taskId: '',
      quizId: '',
      title: '',
      summary: '',
      status: 'idle',
      generatedCount: 0,
      total: 5,
      questions: [],
      currentIndex: 0,
      selected: [],
      submitted: false,
      lastCorrect: false,
      records: [],
      xp: 0,
      streak: 0,
      questionStartTs: 0,
      report: null,
    }),

  setTaskId: (taskId) => set({ taskId, status: 'pending' }),

  ingestTask: (state) =>
    set({
      status: state.status,
      generatedCount: state.generated_count,
      total: state.total,
      quizId: state.quiz_id,
      title: state.title,
      summary: state.summary,
      questions: state.questions,
    }),

  startAnswering: () => set({ questionStartTs: Date.now() }),

  toggleSelect: (key) => {
    const { submitted, questions, currentIndex, selected } = get()
    if (submitted) return
    const q = questions[currentIndex]
    if (!q) return
    if (q.type === 'multiple') {
      set({
        selected: selected.includes(key)
          ? selected.filter((k) => k !== key)
          : [...selected, key],
      })
    } else {
      set({ selected: [key] })
    }
  },

  submitCurrent: () => {
    const {
      questions,
      currentIndex,
      selected,
      records,
      xp,
      streak,
      questionStartTs,
    } = get()
    const q = questions[currentIndex]
    if (!q || selected.length === 0) return false
    const correct = judge(q, selected)
    const record: AnswerRecord = {
      question_id: q.id,
      selected_answers: selected,
      is_correct: correct,
      duration_ms: questionStartTs ? Date.now() - questionStartTs : 0,
    }
    set({
      submitted: true,
      lastCorrect: correct,
      records: [...records, record],
      xp: correct ? xp + XP_PER_CORRECT : xp,
      streak: correct ? streak + 1 : 0,
    })
    return correct
  },

  goNext: () =>
    set((s) => ({
      currentIndex: s.currentIndex + 1,
      selected: [],
      submitted: false,
      lastCorrect: false,
      questionStartTs: Date.now(),
    })),

  setReport: (report) => set({ report }),
}))
