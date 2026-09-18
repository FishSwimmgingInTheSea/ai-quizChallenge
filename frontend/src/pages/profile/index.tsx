import { useState } from 'react'
import { View, Text, Button, ScrollView } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import Mascot from '../../components/Mascot'
import { getRecentQuizzes, getTotalXp, RecentQuiz } from '../../services/storage'
import './index.scss'

export default function Profile() {
  const [recent, setRecent] = useState<RecentQuiz[]>([])
  const [xp, setXp] = useState(0)

  useDidShow(() => {
    setRecent(getRecentQuizzes())
    setXp(getTotalXp())
  })

  const avg =
    recent.length > 0
      ? Math.round(recent.reduce((s, r) => s + r.accuracy, 0) / recent.length)
      : 0

  return (
    <View className="page profile">
      <View className="safe-top" />
      <ScrollView scrollY className="scr">
        <View className="profile-hero">
          <Mascot type="grad" size={72} floaty />
          <View className="hero-info">
            <Text className="hero-name">学习小达人</Text>
            <View className="badge b-xp">⭐ {xp} XP</View>
          </View>
        </View>

        <View className="stat-row">
          <View className="stat-box">
            <Text className="stat-num">{recent.length}</Text>
            <Text className="stat-label">闯关次数</Text>
          </View>
          <View className="stat-box">
            <Text className="stat-num">{avg}%</Text>
            <Text className="stat-label">平均正确率</Text>
          </View>
          <View className="stat-box">
            <Text className="stat-num">{xp}</Text>
            <Text className="stat-label">累计经验</Text>
          </View>
        </View>

        <View className="sec-mini-title">
          <Text>历史闯关</Text>
        </View>
        {recent.length === 0 ? (
          <View className="empty-card">还没有记录，去首页闯一关吧！</View>
        ) : (
          recent.map((r, i) => (
            <View className="recent-card" key={i}>
              <View className="rc-main">
                <Text className="rc-title">{r.title}</Text>
                <Text className="rc-sub">
                  {r.count} 题 · {r.time} · 正确率 {r.accuracy}%
                </Text>
              </View>
              <Text className="rc-stars">
                {'★'.repeat(r.stars)}
                {'☆'.repeat(5 - r.stars)}
              </Text>
            </View>
          ))
        )}

        <View className="future-note">
          错题本、艾宾浩斯复习、深度分析报告等能力将在 P1 阶段上线
        </View>

        <Button
          className="btn btn-block go-btn"
          hoverClass="hover"
          onClick={() => Taro.switchTab({ url: '/pages/index/index' })}
        >
          去闯关
        </Button>
      </ScrollView>
    </View>
  )
}
