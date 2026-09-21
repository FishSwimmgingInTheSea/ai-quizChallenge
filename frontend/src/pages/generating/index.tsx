import { useEffect, useRef, useState } from 'react'
import { View, Text, Button, ScrollView } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Mascot from '../../components/Mascot'
import { submitQuizTask } from '../../services/api'
import { startPolling } from '../../services/poll'
import { AUTO_KB_TOPIC, useQuizStore } from '../../store/quiz'
import { QuestionType } from '../../types'
import './index.scss'

const TYPE_LABEL: Record<QuestionType, string> = {
  single: '单选题',
  multiple: '多选题',
  judge: '判断题',
}

export default function Generating() {
  const store = useQuizStore()
  const {
    userInput,
    difficulty,
    kbDocIds,
    generateImages,
    total,
    generatedCount,
    status,
    phase,
    imageNotice,
    questions,
    setTaskId,
    ingestTask,
  } = store
  const [failed, setFailed] = useState(false)
  const stopRef = useRef<(() => void) | null>(null)

  const startTask = async () => {
    // 知识库自动出题：选了文档时允许空输入，主题由后端从文档推断
    if (!userInput && kbDocIds.length === 0) {
      Taro.navigateBack()
      return
    }
    setFailed(false)
    try {
      const { task_id } = await submitQuizTask({
        user_input: userInput,
        difficulty,
        // 选中知识库文档时随请求携带（后端校验归属与就绪状态）
        ...(kbDocIds.length ? { kb_doc_ids: kbDocIds } : {}),
        // 勾选配图时随请求携带（后端按登录/配额门禁决定是否生图）
        ...(generateImages ? { generate_images: true } : {}),
      })
      setTaskId(task_id)
      stopRef.current = startPolling(task_id, {
        onUpdate: ingestTask,
        onError: () => setFailed(true),
      })
    } catch {
      setFailed(true)
    }
  }

  useEffect(() => {
    startTask()
    return () => stopRef.current?.()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const startAnswering = () => {
    stopRef.current?.()
    useQuizStore.getState().startAnswering()
    Taro.redirectTo({ url: '/pages/quiz/index' })
  }

  const cancel = () => {
    stopRef.current?.()
    Taro.navigateBack()
  }

  const firstReady = generatedCount >= 1
  const pct = total ? Math.round((generatedCount / total) * 100) : 0
  // 联网检索阶段（quiz-web-search-grounding D8）：气泡切换为检索文案
  const isResearching = phase === 'researching' && status !== 'done'
  // 配图阶段（question-images）：题目已出齐，正在逐题生成配图
  const isImaging = phase === 'imaging' && status !== 'done'

  const rows = Array.from({ length: total }).map((_, i) => {
    const q = questions[i]
    if (i < generatedCount && q) {
      return {
        cls: 'done',
        no: '✓',
        text: `第 ${i + 1} 题 · ${TYPE_LABEL[q.type]}「${q.stem.slice(0, 14)}${
          q.stem.length > 14 ? '…' : ''
        }」`,
      }
    }
    if (i === generatedCount && status !== 'done' && !failed) {
      return { cls: 'ing', no: '◉', text: `第 ${i + 1} 题 · 正在生成` }
    }
    return { cls: 'wait', no: '○', text: `第 ${i + 1} 题 · 排队中` }
  })

  return (
    <View className="page generating">
      <ScrollView scrollY className="scr">
        <View className="topic-chip">主题：{userInput || AUTO_KB_TOPIC}</View>

        <View className="gen-stage">
          <Mascot type="think" size={112} floaty />
          <View className="bubble">
            {isImaging ? (
              <>
                题目已就绪，小智正在为它们画配图…{'\n'}
                <Text className="em">马上就能开始答题</Text>！
              </>
            ) : isResearching ? (
              kbDocIds.length > 0 ? (
                <>
                  小智正在钻研你选的知识库文档，{'\n'}必要时联网补充，
                  <Text className="em">不用干等</Text>！
                </>
              ) : (
                <>
                  小智正在全网检索最新资料…{'\n'}拿到最新知识就开始出题，
                  <Text className="em">不用干等</Text>！
                </>
              )
            ) : (
              <>
                小智正在拼命出题…{'\n'}一边出你一边答，
                <Text className="em">不用干等</Text>！
              </>
            )}
          </View>
        </View>

        {failed ? (
          <View className="gen-card">
            <View className="fail-tip">出题失败了，检查后端是否已启动～</View>
            <Button className="btn btn-block" hoverClass="hover" onClick={startTask}>
              重新出题
            </Button>
          </View>
        ) : (
          <View className="gen-card">
            <View className="pbar-label">
              <Text>出题进度</Text>
              <Text style={{ color: 'var(--green-dark)' }}>
                已出 {generatedCount} / {total}
              </Text>
            </View>
            <View className="pbar green">
              <View className="pbar-fill" style={{ width: `${pct}%` }} />
            </View>

            <View className="q-list">
              {rows.map((r, i) => (
                <View className={`q-item ${r.cls}`} key={i}>
                  <Text className="q-no">{r.no}</Text>
                  <Text className="q-text">{r.text}</Text>
                  {r.cls === 'ing' && (
                    <View className="dots">
                      <View className="d" />
                      <View className="d" />
                      <View className="d" />
                    </View>
                  )}
                </View>
              ))}
            </View>
            <View className="gen-tip">首题就绪即可开始答题，后续题目边答边到！</View>
            {imageNotice ? (
              <View className="img-notice">🖼️ {imageNotice}</View>
            ) : null}
          </View>
        )}

        {!failed && (
          <Button
            className={`btn btn-block ready-btn ${firstReady ? '' : 'btn-disabled'}`}
            hoverClass={firstReady ? 'hover' : ''}
            onClick={firstReady ? startAnswering : undefined}
          >
            {firstReady ? '第 1 题已就绪，立即开答！' : '小智正在出题…'}
          </Button>
        )}
        {!failed && (
          <Text className="skip-link center" onClick={cancel}>
            取消并返回首页
          </Text>
        )}

        {/* 底部安全占位盒：保证末尾内容能滚出手势横条遮挡区 */}
        <View className="scr-safe" />
      </ScrollView>
    </View>
  )
}
