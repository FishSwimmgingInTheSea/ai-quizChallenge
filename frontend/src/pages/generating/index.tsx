import { useEffect, useRef, useState } from 'react'
import { View, Text, Button, ScrollView } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Mascot from '../../components/Mascot'
import { submitQuizTask } from '../../services/api'
import { startPolling } from '../../services/poll'
import { useQuizStore } from '../../store/quiz'
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
    total,
    generatedCount,
    status,
    questions,
    setTaskId,
    ingestTask,
  } = store
  const [failed, setFailed] = useState(false)
  const stopRef = useRef<(() => void) | null>(null)

  const startTask = async () => {
    if (!userInput) {
      Taro.navigateBack()
      return
    }
    setFailed(false)
    try {
      const { task_id } = await submitQuizTask({
        user_input: userInput,
        difficulty,
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
      <View className="safe-top" />
      <ScrollView scrollY className="scr">
        <View className="gen-top">
          <Button className="x-btn" hoverClass="hover" onClick={cancel}>
            ✕
          </Button>
          <Text className="gen-title">
            {failed ? '出题失败了…' : '小智正在出题…'}
          </Text>
        </View>
        <View className="topic-chip">主题：{userInput}</View>

        <View className="gen-stage">
          <Mascot type="think" size={112} floaty />
          <View className="bubble">
            小智正在拼命出题…{'\n'}一边出你一边答，
            <Text className="em">不用干等</Text>！
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
      </ScrollView>
    </View>
  )
}
