import { create } from 'zustand'
import { getFeatures } from '../services/api'
import {
  AnswerRecord,
  DifficultyRequest,
  Question,
  RecordDetail,
  Report,
  TaskState,
} from '../types'

const XP_PER_CORRECT = 10

/** 空输入 + 知识库自动出题的展示主题（与后端 AUTO_KB_TOPIC 文案对齐）。 */
export const AUTO_KB_TOPIC = '知识库自动出题'

/** UUID v4 风格随机串，不引入额外依赖（用户系统方案设计 §10.5）。 */
function newClientRecordId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0
    const v = c === 'x' ? r : (r & 0x3) | 0x8
    return v.toString(16)
  })
}

export interface QuizState {
  // 输入
  userInput: string
  difficulty: DifficultyRequest
  // 选中的知识库文档（kb-rag）：提交出题时随请求携带；空 = 不用知识库
  kbDocIds: number[]
  kbDocNames: string[]

  // 是否为题目生成配图（question-images）：仅登录有效，随出题请求携带
  generateImages: boolean
  // 后端配图功能系统级可用（meta/features）：false = 首页隐藏配图开关
  imageGenAvailable: boolean

  // 本局幂等键：结算接口防重复写入（用户系统方案设计 §7.5）
  clientRecordId: string

  // 任务
  taskId: string
  quizId: string
  title: string
  summary: string
  status: TaskState['status'] | 'idle'
  /** 生成阶段：researching / generating / imaging；空串为旧语义 */
  phase: string
  /** 配图降级友好提示（question-images）：空串表示无提示 */
  imageNotice: string
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
  resetSession: (
    input: string,
    difficulty: DifficultyRequest,
    kb?: { docIds: number[]; docNames: string[] },
  ) => void
  setKbSelection: (docIds: number[], docNames: string[]) => void
  setGenerateImages: (v: boolean) => void
  /** 拉取后端功能标志；失败兜底为关闭（与后端静默降级基调一致） */
  fetchFeatures: () => Promise<void>
  setTaskId: (taskId: string) => void
  ingestTask: (state: TaskState) => void
  toggleSelect: (key: string) => void
  submitCurrent: () => boolean
  goNext: () => void
  startAnswering: () => void
  setReport: (r: Report) => void
  /** 历史报告回看：用服务端单局详情水合 store，报告页/海报页即可直接渲染 */
  hydrateRecord: (detail: RecordDetail) => void
  /** 再战=重做原题：水合历史题目但清空作答/报告与幂等键，作为全新一局重新开答 */
  replayRecord: (detail: RecordDetail) => void
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
  kbDocIds: [],
  kbDocNames: [],
  generateImages: false,
  imageGenAvailable: false,
  clientRecordId: '',
  taskId: '',
  quizId: '',
  title: '',
  summary: '',
  status: 'idle',
  phase: '',
  imageNotice: '',
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

  resetSession: (input, difficulty, kb) =>
    set({
      userInput: input,
      difficulty,
      kbDocIds: kb?.docIds ?? [],
      kbDocNames: kb?.docNames ?? [],
      clientRecordId: newClientRecordId(),
      taskId: '',
      quizId: '',
      title: '',
      summary: '',
      status: 'idle',
      phase: '',
      imageNotice: '',
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

  setKbSelection: (docIds, docNames) =>
    set({ kbDocIds: docIds, kbDocNames: docNames }),

  setGenerateImages: (v) => set({ generateImages: v }),

  fetchFeatures: async () => {
    try {
      const f = await getFeatures()
      // 功能不可用时同步收回已勾选的配图请求，避免“开关隐藏但仍传 generate_images”
      set(
        f.image_gen_enabled
          ? { imageGenAvailable: true }
          : { imageGenAvailable: false, generateImages: false },
      )
    } catch {
      set({ imageGenAvailable: false, generateImages: false })
    }
  },

  setTaskId: (taskId) => set({ taskId, status: 'pending' }),

  ingestTask: (state) =>
    set({
      status: state.status,
      phase: state.phase ?? '',
      imageNotice: state.image_notice ?? '',
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

  hydrateRecord: (detail) =>
    set({
      userInput: detail.record.title,
      title: detail.record.title,
      summary: '',
      taskId: '',
      quizId: '',
      status: 'idle',
      phase: '',
      imageNotice: '',
      generatedCount: detail.record.question_count,
      total: detail.record.question_count,
      questions: detail.questions.map((q) => ({
        id: q.question_id,
        type: q.type,
        stem: q.stem,
        options: q.options,
        answer: q.answer,
        explanation: q.explanation,
        knowledge_point: q.knowledge_point,
        difficulty: q.difficulty,
        image_url: q.image_url ?? '',
      })),
      currentIndex: 0,
      selected: [],
      submitted: false,
      lastCorrect: false,
      records: detail.questions.map((q) => ({
        question_id: q.question_id,
        selected_answers: q.selected_answers,
        is_correct: q.is_correct,
        duration_ms: q.duration_ms,
      })),
      xp: detail.record.xp_earned,
      streak: 0,
      questionStartTs: 0,
      report: detail.report,
    }),

  replayRecord: (detail) =>
    set({
      userInput: detail.record.title,
      difficulty: 'mixed',
      clientRecordId: newClientRecordId(),
      taskId: '',
      quizId: '',
      title: detail.record.title,
      summary: '',
      status: 'idle',
      phase: '',
      imageNotice: '',
      generatedCount: detail.record.question_count,
      total: detail.record.question_count,
      questions: detail.questions.map((q) => ({
        id: q.question_id,
        type: q.type,
        stem: q.stem,
        options: q.options,
        answer: q.answer,
        explanation: q.explanation,
        knowledge_point: q.knowledge_point,
        difficulty: q.difficulty,
        image_url: q.image_url ?? '',
      })),
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
}))
