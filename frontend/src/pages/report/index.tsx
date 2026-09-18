import { View, Text, Button, ScrollView } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Mascot from '../../components/Mascot'
import { useQuizStore } from '../../store/quiz'
import './index.scss'

function formatDuration(ms: number): string {
  const totalSec = Math.round(ms / 1000)
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return `${m}'${s.toString().padStart(2, '0')}"`
}

export default function ReportPage() {
  const { report, records, total, xp, title, questions } = useQuizStore()

  const correct = records.filter((r) => r.is_correct).length
  const accuracy = report?.accuracy ?? (total ? Math.round((correct / total) * 100) : 0)
  const totalMs = records.reduce((sum, r) => sum + (r.duration_ms || 0), 0)
  const deg = Math.round((accuracy / 100) * 360)

  const goPoster = () => Taro.navigateTo({ url: '/pages/poster/index' })
  const goHome = () => Taro.switchTab({ url: '/pages/index/index' })

  if (!report) {
    return (
      <View className="page report">
        <View className="safe-top" />
        <View className="scr empty">
          <Text className="empty-tip">还没有报告，先去闯一关吧～</Text>
          <Button className="btn btn-block" hoverClass="hover" onClick={goHome}>
            返回首页
          </Button>
        </View>
      </View>
    )
  }

  return (
    <View className="page report">
      <View className="safe-top" />
      <ScrollView scrollY className="scr">
        <View className="report-hero">
          <Mascot type="grad" size={108} floaty className="hero-mascot" />
          <Text className="hero-title">通 关 ！</Text>
          <Text className="r-topic">
            {title} · {total} 题 · 难度混合
          </Text>
        </View>

        <View className="ring-zone">
          <View className="ring-wrap">
            <View
              className="ring"
              style={{
                background: `conic-gradient(var(--green) 0 ${deg}deg, #EDE8DC ${deg}deg 360deg)`,
              }}
            >
              <View className="ring-inner">
                <Text className="ring-num">
                  {accuracy}
                  <Text className="ring-unit">%</Text>
                </Text>
              </View>
            </View>
            <Text className="ring-cap">正确率</Text>
          </View>
          <View className="ring-side">
            <View className="stat">
              <Text className="ico">✅</Text>
              <Text>答对题数</Text>
              <Text className="val">
                {correct} / {total}
              </Text>
            </View>
            <View className="stat">
              <Text className="ico">⏱️</Text>
              <Text>总用时</Text>
              <Text className="val">{formatDuration(totalMs)}</Text>
            </View>
            <View className="stat">
              <Text className="ico">⭐</Text>
              <Text>本关经验</Text>
              <Text className="val">+{xp} XP</Text>
            </View>
          </View>
        </View>

        <View className="sum-card">
          <Text className="card-title">今日份知识总结</Text>
          <View className="ol">
            {report.three_line_summary.map((s, i) => (
              <View className="li" key={i}>
                <Text className="li-no">{i + 1}</Text>
                <Text className="li-text">{s}</Text>
              </View>
            ))}
          </View>
        </View>

        <View className="pw-grid">
          <View className="pw-card good">
            <Text className="pw-title t-good">✓ 已掌握</Text>
            <View className="pw-list">
              {(report.mastered_points.length
                ? report.mastered_points
                : ['继续保持']
              ).map((p, i) => (
                <Text className="pw-li good-li" key={i}>
                  {p}
                </Text>
              ))}
            </View>
          </View>
          <View className="pw-card bad2">
            <Text className="pw-title t-bad">✗ 待加强</Text>
            <View className="pw-list">
              {(report.weak_points.length
                ? report.weak_points
                : ['暂无明显薄弱点']
              ).map((p, i) => (
                <Text className="pw-li bad-li" key={i}>
                  {p}
                </Text>
              ))}
            </View>
          </View>
        </View>

        {report.advice.length > 0 && (
          <View className="sum-card advice-card">
            <Text className="card-title">复盘建议</Text>
            <View className="ol">
              {report.advice.map((s, i) => (
                <View className="li" key={i}>
                  <Text className="li-no">{i + 1}</Text>
                  <Text className="li-text">{s}</Text>
                </View>
              ))}
            </View>
          </View>
        )}

        <View className="quote-bar">「 {report.share_quote} 」</View>

        <View className="report-foot">
          <Button className="btn" hoverClass="hover" onClick={goPoster}>
            生成分享海报
          </Button>
          <Button className="btn btn-ghost" hoverClass="hover" onClick={goHome}>
            再来一局
          </Button>
        </View>
      </ScrollView>
    </View>
  )
}
