import { useEffect, useState } from 'react'
import { View, Text, ScrollView, Image } from '@tarojs/components'
import Taro, { useRouter } from '@tarojs/taro'
import Icon from '../../components/Icon'
import Mascot from '../../components/Mascot'
import { getQuizRecordDetail } from '../../services/api'
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

export default function Review() {
  const router = useRouter()
  const questions = useQuizStore((s) => s.questions)
  const records = useQuizStore((s) => s.records)
  const title = useQuizStore((s) => s.title)
  const hydrateRecord = useQuizStore((s) => s.hydrateRecord)
  const [loading, setLoading] = useState(false)
  // 逐题配图加载失败态：以题目 id 记录，失败则隐藏该题配图
  const [imgErrors, setImgErrors] = useState<Record<string, boolean>>({})

  // 携带记录 id 打开时（历史回顾）：拉详情并水合 store；否则直接用已水合的题目
  useEffect(() => {
    const id = Number(router.params.id)
    if (!id) return
    setLoading(true)
    getQuizRecordDetail(id)
      .then((detail) => hydrateRecord(detail))
      .catch(() => Taro.showToast({ title: '加载失败，请重试', icon: 'none' }))
      .finally(() => setLoading(false))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const recordOf = (qid: string) => records.find((r) => r.question_id === qid)

  if (loading) {
    return (
      <View className="page review">
        <View className="scr empty">
          <Mascot type="think" size={100} floaty />
          <Text className="empty-tip">正在加载题目回顾…</Text>
        </View>
      </View>
    )
  }

  if (!questions.length) {
    return (
      <View className="page review">
        <View className="scr empty">
          <Icon name="book" size={44} className="empty-ic" />
          <Text className="empty-tip">没有可回顾的题目</Text>
        </View>
      </View>
    )
  }

  return (
    <View className="page review">
      <ScrollView scrollY className="scr">
        <View className="review-head">
          <Text className="review-title">{title || '题目回顾'}</Text>
          <Text className="review-sub">共 {questions.length} 题 · 逐题查看配图、答案与讲解</Text>
        </View>

        {questions.map((q, i) => {
          const rec = recordOf(q.id)
          const correct = rec?.is_correct ?? false
          const chosen = rec?.selected_answers ?? []
          return (
            <View className="review-item" key={q.id}>
              <View className="ri-head">
                <View className={`badge ${TYPE_BADGE[q.type]}`}>
                  {TYPE_LABEL[q.type]}
                </View>
                <View className="badge b-point">知识点：{q.knowledge_point}</View>
                {rec && (
                  <View className={`ri-result ${correct ? 'ok' : 'bad'}`}>
                    {correct ? '✓ 答对' : '✗ 答错'}
                  </View>
                )}
              </View>

              <View className="stem-card">
                <Text className="stem-no">Q{i + 1}</Text>
                <Text className="stem-text">{q.stem}</Text>
                {q.image_url && !imgErrors[q.id] && (
                  <Image
                    className="q-image"
                    src={q.image_url}
                    mode="aspectFit"
                    onError={() => setImgErrors((m) => ({ ...m, [q.id]: true }))}
                  />
                )}
              </View>

              <View className="ri-opts">
                {q.options.map((opt) => {
                  const isAnswer = q.answer.includes(opt.key)
                  const isChosen = chosen.includes(opt.key)
                  let cls = ''
                  if (isAnswer) cls = 'correct'
                  else if (isChosen) cls = 'wrong'
                  return (
                    <View className={`ri-opt ${cls}`} key={opt.key}>
                      <Text className="key">{opt.key}</Text>
                      <Text className="txt">{opt.text}</Text>
                      {isAnswer && <Text className="mark">✓ 正确答案</Text>}
                      {!isAnswer && isChosen && <Text className="mark">✗ 你的选择</Text>}
                    </View>
                  )
                })}
              </View>

              <View className="ri-explain">
                <View className="ri-explain-head">
                  <Text className="icon">📖</Text>
                  <Text className="h-title">讲解</Text>
                </View>
                <Text className="ri-explain-body">{q.explanation}</Text>
              </View>
            </View>
          )
        })}

        {/* 底部安全占位盒：保证末尾内容能滚出手势横条遮挡区 */}
        <View className="scr-safe" />
      </ScrollView>
    </View>
  )
}
