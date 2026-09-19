import { View, Text, Button, ScrollView } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Icon from '../../components/Icon'
import Mascot from '../../components/Mascot'
import { useQuizStore } from '../../store/quiz'
import './index.scss'

function formatDuration(ms: number): string {
  const totalSec = Math.round(ms / 1000)
  const m = Math.floor(totalSec / 60)
  const s = totalSec % 60
  return `${m}'${s.toString().padStart(2, '0')}"`
}

/** 成绩基调：驱动评价 chip、正确率环与数字的配色 */
type ScoreTone = 'good' | 'mid' | 'low'

const TONE_LABEL: Record<ScoreTone, string> = {
  good: '表现出色',
  mid: '稳步前进',
  low: '继续加油',
}
const TONE_RING: Record<ScoreTone, string> = {
  good: 'var(--green)',
  mid: 'var(--orange)',
  low: 'var(--red)',
}

export default function ReportPage() {
  const { report, records, total, xp, title } = useQuizStore()

  const correct = records.filter((r) => r.is_correct).length
  const accuracy = report?.accuracy ?? (total ? Math.round((correct / total) * 100) : 0)
  const totalMs = records.reduce((sum, r) => sum + (r.duration_ms || 0), 0)
  const deg = Math.round((accuracy / 100) * 360)
  const tone: ScoreTone = accuracy >= 80 ? 'good' : accuracy >= 60 ? 'mid' : 'low'

  const goPoster = () => Taro.navigateTo({ url: '/pages/poster/index' })
  const goHome = () => Taro.switchTab({ url: '/pages/index/index' })

  if (!report) {
    return (
      <View className="page report">
        <View className="scr empty">
          <Icon name="book" size={44} className="empty-ic" />
          <Text className="empty-tip">还没有报告，先去闯一关吧～</Text>
          <Button className="btn btn-block" hoverClass="hover" onClick={goHome}>
            返回首页
          </Button>
        </View>
      </View>
    )
  }

  const mastered = report.mastered_points.length ? report.mastered_points : ['继续保持']
  const weak = report.weak_points.length ? report.weak_points : ['暂无明显薄弱点']

  return (
    <View className="page report">
      <ScrollView scrollY className="scr">
        {/* 通关贺词：吉祥物 + 两侧小旗 */}
        <View className="report-hero">
          <Mascot type="grad" size={96} floaty className="hero-mascot" />
          <View className="hero-title-row">
            <Icon name="flag" size={20} className="hero-flag l" />
            <Text className="hero-title">通 关 ！</Text>
            <Icon name="flag" size={20} className="hero-flag r" />
          </View>
          <Text className="r-topic">
            {title} · {total} 题 · 难度混合
          </Text>
        </View>

        {/* 成绩单：本页唯一 elevated 主卡 */}
        <View className="score-card">
          <View className="sec-head">
            <View className="sec-ic t-yellow medal-ic">
              <Icon name="medal" size={16} />
            </View>
            <Text className="sec-title">本关成绩单</Text>
            <View className={`score-chip ${tone}`}>{TONE_LABEL[tone]}</View>
          </View>
          <View className="score-body">
            <View
              className="ring"
              style={{
                background: `conic-gradient(${TONE_RING[tone]} 0 ${deg}deg, #EDE8DC ${deg}deg 360deg)`,
              }}
            >
              <View className="ring-inner">
                <Text className={`ring-num ${tone}`}>
                  {accuracy}
                  <Text className="ring-unit">%</Text>
                </Text>
                <Text className="ring-cap">正确率</Text>
              </View>
            </View>
            <View className="score-stats">
              <View className="stat">
                <View className="stat-ic t-green">
                  <Icon name="check" size={13} />
                </View>
                <Text className="stat-label">答对题数</Text>
                <Text className="stat-val">
                  {correct} / {total}
                </Text>
              </View>
              <View className="stat">
                <View className="stat-ic t-blue">
                  <Icon name="clock" size={13} />
                </View>
                <Text className="stat-label">总用时</Text>
                <Text className="stat-val">{formatDuration(totalMs)}</Text>
              </View>
              <View className="stat">
                <View className="stat-ic t-yellow">
                  <Icon name="star" size={13} />
                </View>
                <Text className="stat-label">本关经验</Text>
                <Text className="stat-val">+{xp} XP</Text>
              </View>
            </View>
          </View>
        </View>

        {/* 知识总结 */}
        <View className="sum-card">
          <View className="sec-head">
            <View className="sec-ic t-blue">
              <Icon name="book" size={14} />
            </View>
            <Text className="sec-title">今日份知识总结</Text>
          </View>
          <View className="ol">
            {report.three_line_summary.map((s, i) => (
              <View className="li" key={i}>
                <Text className="li-no">{i + 1}</Text>
                <Text className="li-text">{s}</Text>
              </View>
            ))}
          </View>
        </View>

        {/* 掌握情况：标签 chips */}
        <View className="pw-grid">
          <View className="pw-card good">
            <View className="sec-head">
              <View className="sec-ic t-green">
                <Icon name="check" size={13} />
              </View>
              <Text className="sec-title t-good">已掌握</Text>
            </View>
            <View className="pw-chips">
              {mastered.map((p, i) => (
                <View className="pw-chip good" key={i}>
                  <Icon name="check" size={11} />
                  <Text>{p}</Text>
                </View>
              ))}
            </View>
          </View>
          <View className="pw-card bad2">
            <View className="sec-head">
              <View className="sec-ic t-red">
                <Icon name="cross" size={13} />
              </View>
              <Text className="sec-title t-bad">待加强</Text>
            </View>
            <View className="pw-chips">
              {weak.map((p, i) => (
                <View className="pw-chip bad" key={i}>
                  <Icon name="cross" size={11} />
                  <Text>{p}</Text>
                </View>
              ))}
            </View>
          </View>
        </View>

        {/* 复盘建议 */}
        {report.advice.length > 0 && (
          <View className="sum-card">
            <View className="sec-head">
              <View className="sec-ic t-yellow">
                <Icon name="bulb" size={14} />
              </View>
              <Text className="sec-title">复盘建议</Text>
            </View>
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

        {/* 金句便签 */}
        <View className="quote-bar">
          <Icon name="quote" size={18} className="quote-ic" />
          <Text className="quote-text">{report.share_quote}</Text>
        </View>

        {/* 底部操作 */}
        <View className="report-foot">
          <Button className="btn" hoverClass="hover" onClick={goPoster}>
            <Icon name="posterWhite" size={15} />
            生成分享海报
          </Button>
          <Button className="btn btn-ghost" hoverClass="hover" onClick={goHome}>
            <Icon name="replay" size={14} />
            再来一局
          </Button>
        </View>
      </ScrollView>
    </View>
  )
}
