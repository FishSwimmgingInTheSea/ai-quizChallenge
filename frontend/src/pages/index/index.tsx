import { useState } from 'react'
import { View, Text, Textarea, Button, ScrollView } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import Mascot from '../../components/Mascot'
import { INSPIRATIONS } from '../../constants/inspirations'
import { getRecentQuizzes, getTotalXp, RecentQuiz } from '../../services/storage'
import { useQuizStore } from '../../store/quiz'
import './index.scss'

const MAX_LEN = 100

export default function Home() {
  const [value, setValue] = useState('')
  const [recent, setRecent] = useState<RecentQuiz[]>([])
  const [xp, setXp] = useState(0)
  const resetSession = useQuizStore((s) => s.resetSession)

  useDidShow(() => {
    setRecent(getRecentQuizzes())
    setXp(getTotalXp())
  })

  const go = () => {
    const input = value.trim()
    if (input.length < 2) {
      Taro.showToast({ title: '再多写一点点吧～', icon: 'none' })
      return
    }
    resetSession(input, 'mixed')
    Taro.navigateTo({ url: '/pages/generating/index' })
  }

  return (
    <View className="page home">
      <View className="safe-top" />
      <ScrollView scrollY className="scr">
        <View className="home-top">
          <Mascot type="wave" size={58} />
          <View className="bubble">Hi～今天想学点啥？</View>
          <View className="wallet badge b-xp">⭐ {xp} XP</View>
        </View>

        <View className="paper-card">
          <Textarea
            className="paper-input"
            value={value}
            maxlength={MAX_LEN}
            placeholder={'什么是 RAG？它和传统搜索有什么区别\n一句话、一段话、一个主题都行…'}
            placeholderClass="paper-ph"
            onInput={(e) => setValue(e.detail.value)}
            autoHeight={false}
          />
          <View className="char-count">
            {value.length} / {MAX_LEN}
          </View>
        </View>
        <Button className="btn btn-block go-btn" hoverClass="hover" onClick={go}>
          GO！开始闯关
        </Button>

        <View className="insp">
          <View className="insp-title">试试这些</View>
          <View className="insp-tags">
            {INSPIRATIONS.map((t) => (
              <View
                key={t.text}
                className={`badge ${t.cls}`}
                onClick={() => setValue(t.text)}
              >
                {t.text}
              </View>
            ))}
          </View>
        </View>

        <View className="sec-mini-title">
          <Text>最近闯关</Text>
        </View>
        {recent.length === 0 ? (
          <View className="recent-empty">还没有闯关记录，输入一句话开始吧！</View>
        ) : (
          recent.map((r, i) => (
            <View className="recent-card" key={i}>
              <View className="rc-main">
                <Text className="rc-title">{r.title}</Text>
                <Text className="rc-sub">
                  {r.count} 题 · {r.time}
                </Text>
                <Text className="rc-stars">
                  {'★'.repeat(r.stars)}
                  {'☆'.repeat(5 - r.stars)} · 正确率 {r.accuracy}%
                </Text>
              </View>
              <Button
                className="mini-btn"
                hoverClass="hover"
                onClick={() => {
                  resetSession(r.title, 'mixed')
                  Taro.navigateTo({ url: '/pages/generating/index' })
                }}
              >
                再战
              </Button>
            </View>
          ))
        )}
      </ScrollView>
    </View>
  )
}
