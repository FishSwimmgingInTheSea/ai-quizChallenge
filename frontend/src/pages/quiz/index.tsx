import { useEffect, useRef, useState } from 'react'
import { View, Text, Button, ScrollView } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Mascot from '../../components/Mascot'
import { generateReport } from '../../services/api'
import { startPolling } from '../../services/poll'
import { addRecentQuiz, addTotalXp } from '../../services/storage'
import { useQuizStore } from '../../store/quiz'
import { QuestionType } from '../../types'
import './index.scss'

const TYPE_LABEL: Record<QuestionType, string> = {
  single: '单选题',
  multiple: '多选题',
  judge: '判断题',
}
const TYPE_BADGE: Record<QuestionType, string> = {
  single: 'b-single',
  multiple: 'b-multi',
  judge: 'b-judge',
}
const DIFF_LEVEL = { easy: 1, medium: 2, hard: 3 }

export default function Quiz() {
  const store = useQuizStore()
  const {
    total,
    questions,
    currentIndex,
    selected,
    submitted,
    lastCorrect,
    records,
    xp,
    streak,
    status,
    taskId,
    title,
    userInput,
    quizId,
    toggleSelect,
    submitCurrent,
    goNext,
    ingestTask,
  } = store
  const [foldOpen, setFoldOpen] = useState(false)
  const [finishing, setFinishing] = useState(false)
  const stopRef = useRef<(() => void) | null>(null)

  // 边答边轮询后续题目
  useEffect(() => {
    if (status !== 'done' && taskId) {
      stopRef.current = startPolling(taskId, { onUpdate: ingestTask })
    }
    return () => stopRef.current?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const q = questions[currentIndex]
  const isLast = currentIndex >= total - 1

  // 退出确认
  const confirmExit = () => {
    Taro.showModal({
      title: '退出闯关？',
      content: '本局进度将不会保存哦',
      confirmText: '狠心退出',
      cancelText: '继续答题',
      success: (r) => {
        if (r.confirm) {
          stopRef.current?.()
          Taro.switchTab({ url: '/pages/index/index' })
        }
      },
    })
  }

  const finish = async () => {
    setFinishing(true)
    stopRef.current?.()
    const correct = records.filter((r) => r.is_correct).length
    const accuracy = total ? Math.round((correct / total) * 100) : 0
    try {
      const report = await generateReport({
        quiz_id: quizId || 'quiz_local',
        topic: title || userInput,
        questions,
        answer_records: records,
      })
      useQuizStore.getState().setReport(report)
    } catch {
      // 兜底：后端不可用时用本地统计生成极简报告
      useQuizStore.getState().setReport({
        accuracy,
        mastered_points: [],
        weak_points: [],
        three_line_summary: ['完成了本次闯关！', '继续保持学习节奏。', '温故而知新。'],
        advice: ['稍后可再挑战一次巩固记忆。'],
        share_quote: '把知识做成关卡，记忆会更深。',
      })
    }
    // 记录到最近闯关 + 累计 XP
    addRecentQuiz({
      title: title || userInput.slice(0, 12),
      count: total,
      accuracy,
      stars: Math.max(1, Math.round((accuracy / 100) * 5)),
      time: '刚刚',
    })
    addTotalXp(xp)
    setFinishing(false)
    Taro.redirectTo({ url: '/pages/report/index' })
  }

  const onContinue = () => {
    setFoldOpen(false)
    if (isLast) {
      finish()
    } else {
      goNext()
    }
  }

  // 题目尚未就绪
  if (!q) {
    return (
      <View className="page quiz">
        <View className="safe-top" />
        <View className="scr waiting">
          <Mascot type="think" size={108} floaty />
          <Text className="waiting-tip">小智还在赶制这道题…马上好！</Text>
        </View>
      </View>
    )
  }

  const level = DIFF_LEVEL[q.difficulty] || 1
  const answerCount = q.answer.length

  const optClass = (key: string): string => {
    if (!submitted) return selected.includes(key) ? 'selected' : ''
    const isAnswer = q.answer.includes(key)
    const isChosen = selected.includes(key)
    if (isAnswer) return 'correct'
    if (isChosen) return 'wrong'
    return 'dim'
  }

  const judgeClass = (key: string): string => {
    if (!submitted) return selected.includes(key) ? 'selected' : ''
    const isAnswer = q.answer.includes(key)
    const isChosen = selected.includes(key)
    if (isAnswer) return 'correct'
    if (isChosen) return 'wrong'
    return 'dim'
  }

  const canSubmit = selected.length > 0

  return (
    <View className="page quiz">
      <View className="safe-top" />
      <ScrollView scrollY className="scr">
        <View className="top-nav">
          <Button className="x-btn" hoverClass="hover" onClick={confirmExit}>
            ✕
          </Button>
          <Text className="title">
            第 {currentIndex + 1} / {total} 题
          </Text>
          {streak > 0 ? (
            <View className="badge b-streak streak-badge">🔥 连击 ×{streak}</View>
          ) : (
            <View className="streak-placeholder" />
          )}
        </View>

        <View className="q-dots">
          {Array.from({ length: total }).map((_, i) => {
            let cls = ''
            if (i < records.length) cls = records[i].is_correct ? 'ok' : 'bad'
            else if (i === currentIndex) cls = 'cur'
            return <View className={`dot ${cls}`} key={i} />
          })}
        </View>

        <View className="quiz-meta">
          <View className={`badge ${TYPE_BADGE[q.type]}`}>{TYPE_LABEL[q.type]}</View>
          <View className="badge b-point">知识点：{q.knowledge_point}</View>
          <View className="diff-stars">
            {'★'.repeat(level)}
            <Text className="off">{'★'.repeat(3 - level)}</Text>
          </View>
        </View>

        <View className="stem-card">
          <Text className="stem-no">Q{currentIndex + 1}</Text>
          <Text className="stem-text">{q.stem}</Text>
        </View>

        {q.type === 'multiple' && !submitted && (
          <View className="multi-hint">
            多选题：本题共有 {answerCount} 个正确答案，选齐才算对
          </View>
        )}

        {q.type === 'judge' ? (
          <View className="judge-row">
            {q.options.map((opt) => (
              <View
                key={opt.key}
                className={`judge-opt ${opt.key === 'A' ? 'j-yes' : 'j-no'} ${judgeClass(
                  opt.key,
                )}`}
                onClick={() => toggleSelect(opt.key)}
              >
                <Text className="big">{opt.key === 'A' ? '✓' : '✗'}</Text>
                <Text className="lbl">{opt.text}</Text>
              </View>
            ))}
          </View>
        ) : (
          <View className="opts">
            {q.options.map((opt) => (
              <View
                key={opt.key}
                className={`opt ${optClass(opt.key)}`}
                onClick={() => toggleSelect(opt.key)}
              >
                <Text className="key">{opt.key}</Text>
                <Text className="txt">{opt.text}</Text>
                {submitted && q.answer.includes(opt.key) && (
                  <Text className="mark">✓</Text>
                )}
                {submitted && selected.includes(opt.key) && !q.answer.includes(opt.key) && (
                  <Text className="mark">✗</Text>
                )}
              </View>
            ))}
          </View>
        )}

        {!submitted && (
          <View className="quiz-foot">
            <View className="xp-inline">
              <Text>本关已得 ⭐ +{xp} XP</Text>
              <Text>{q.type === 'multiple' ? `已选 ${selected.length} 项` : '选好后提交'}</Text>
            </View>
            <Button
              className={`btn btn-block ${canSubmit ? '' : 'btn-disabled'}`}
              hoverClass={canSubmit ? 'hover' : ''}
              onClick={canSubmit ? () => submitCurrent() : undefined}
            >
              提交答案
            </Button>
          </View>
        )}

        {submitted && (
          <View className="fb-sheet">
            <View className="fb-head">
              <Mascot type={lastCorrect ? 'cheer' : 'sweat'} size={62} />
              <View className={`fb-title ${lastCorrect ? 'ok' : 'bad'}`}>
                <Text className="t-main">{lastCorrect ? '答对啦！' : '差一点！'}</Text>
                <Text className="t-sub">
                  {lastCorrect
                    ? `第 ${currentIndex + 1} 题 · 答对了，继续冲！`
                    : `正确答案是 ${q.answer.join('、')} · 别灰心，看看讲解`}
                </Text>
                <View className="reward-row">
                  {lastCorrect ? (
                    <>
                      <View className="badge b-xp">⭐ +10 XP</View>
                      {streak > 0 && <View className="badge b-streak">🔥 ×{streak}</View>}
                    </>
                  ) : (
                    <>
                      <View className="badge badge-zero">⭐ +0 XP</View>
                      <View className="badge b-streak muted">🔥 连击中断</View>
                    </>
                  )}
                </View>
              </View>
            </View>

            <View className="fb-body">
              <View className={`explain-card ${lastCorrect ? 'ok' : 'bad'}`}>
                <View className="head">
                  <Text className="icon">{lastCorrect ? '📖' : '✏️'}</Text>
                  <Text className="h-title">{lastCorrect ? '老师讲解' : '错题订正'}</Text>
                  <View className="badge b-point">{q.knowledge_point}</View>
                </View>
                <Text className="body">
                  {foldOpen || q.explanation.length <= 80
                    ? q.explanation
                    : `${q.explanation.slice(0, 80)}…`}
                </Text>
                {q.explanation.length > 80 && (
                  <Text className="fold" onClick={() => setFoldOpen(!foldOpen)}>
                    {foldOpen ? '收起讲解 ▴' : '展开完整讲解 ▾'}
                  </Text>
                )}
              </View>
            </View>

            <Button
              className={`btn btn-block continue-btn ${lastCorrect ? 'btn-green' : 'btn-soft'}`}
              hoverClass="hover"
              onClick={onContinue}
            >
              {isLast ? '查看通关报告' : lastCorrect ? '继续闯关' : '知道了，继续'}
            </Button>
          </View>
        )}
      </ScrollView>

      {finishing && (
        <View className="finishing-mask">
          <View className="finishing-card">
            <Mascot type="grad" size={90} floaty />
            <Text className="finishing-tip">小智正在生成复盘报告…</Text>
          </View>
        </View>
      )}
    </View>
  )
}
