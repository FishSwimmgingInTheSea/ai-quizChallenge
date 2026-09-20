import { useState } from 'react'
import { View, Text, Textarea, Button, ScrollView } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import Icon from '../../components/Icon'
import Mascot from '../../components/Mascot'
import { INSPIRATIONS } from '../../constants/inspirations'
import { getQuizRecords, recordToRecentView } from '../../services/api'
import { getRecentQuizzes, getTotalXp, RecentQuiz } from '../../services/storage'
import { useQuizStore } from '../../store/quiz'
import { useUserStore } from '../../store/user'
import './index.scss'

const MAX_LEN = 100
/** 首页只留最近 3 条快捷再战入口，完整档案在「我的-闯关档案」（避免两页重复） */
const RECENT_LIMIT = 3

export default function Home() {
  const [value, setValue] = useState('')
  const [recent, setRecent] = useState<RecentQuiz[]>([])
  const [localXp, setLocalXp] = useState(0)
  const resetSession = useQuizStore((s) => s.resetSession)
  // 知识库选择（kb-rag）：从 kb 页返回后自动同步
  const kbDocIds = useQuizStore((s) => s.kbDocIds)
  const kbDocNames = useQuizStore((s) => s.kbDocNames)
  const setKbSelection = useQuizStore((s) => s.setKbSelection)
  // 生成配图开关（question-images）：仅登录可见/可开
  const generateImages = useQuizStore((s) => s.generateImages)
  const setGenerateImages = useQuizStore((s) => s.setGenerateImages)
  const isLoggedIn = useUserStore((s) => s.isLoggedIn)
  // XP 徽章：登录态读 user store（服务端权威），匿名读本地（方案 §8.3）
  const serverXp = useUserStore((s) =>
    s.isLoggedIn ? s.profile?.total_xp ?? 0 : null,
  )
  const xp = serverXp ?? localXp

  useDidShow(() => {
    // 回调内用 getState 取实时登录态，避免闭包过期
    if (useUserStore.getState().isLoggedIn) {
      getQuizRecords({ limit: RECENT_LIMIT })
        .then((page) => setRecent(page.records.map(recordToRecentView)))
        .catch(() => setRecent([])) // 网络异常静默空态，不打扰
    } else {
      setRecent(getRecentQuizzes().slice(0, RECENT_LIMIT))
      setLocalXp(getTotalXp())
    }
  })

  const go = () => {
    const input = value.trim()
    // 选了知识库文档时允许留空：后端从文档概览自推主题自动出题
    if (input.length > 0 && input.length < 2) {
      Taro.showToast({ title: '再多写一点点吧～', icon: 'none' })
      return
    }
    if (input.length === 0 && kbDocIds.length === 0) {
      Taro.showToast({ title: '写点想学的内容，或先选知识库文档', icon: 'none' })
      return
    }
    resetSession(input, 'mixed', kbDocIds.length
      ? { docIds: kbDocIds, docNames: kbDocNames }
      : undefined)
    Taro.navigateTo({ url: '/pages/generating/index' })
  }

  const goKbSelect = () => {
    if (!useUserStore.getState().isLoggedIn) {
      Taro.navigateTo({ url: '/pages/login/index' })
      return
    }
    Taro.navigateTo({ url: '/pages/kb/index?mode=select' })
  }

  const removeKbDoc = (idx: number) => {
    setKbSelection(
      kbDocIds.filter((_, i) => i !== idx),
      kbDocNames.filter((_, i) => i !== idx),
    )
  }

  const toggleImages = () => {
    if (!useUserStore.getState().isLoggedIn) {
      Taro.navigateTo({ url: '/pages/login/index' })
      return
    }
    setGenerateImages(!generateImages)
  }

  return (
    <View className="page home">
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
            placeholder={
              kbDocNames.length > 0
                ? '可不填：想考哪部分就写一句\n留空则由小智通读文档自动出题'
                : '什么是 RAG？它和传统搜索有什么区别\n一句话、一段话、一个主题都行…\n粘贴网页链接也可以'
            }
            placeholderClass="paper-ph"
            onInput={(e) => setValue(e.detail.value)}
            autoHeight={false}
          />
          <View className="char-count">
            {value.length} / {MAX_LEN}
          </View>
        </View>

        {isLoggedIn && (
          <View className="kb-sec">
            <View className="kb-sec-head">
              <Text className="kb-sec-title">知识库出题</Text>
              <Text className="kb-sec-link" onClick={goKbSelect}>
                {kbDocNames.length > 0 ? '修改选择' : '选择文档 ›'}
              </Text>
            </View>
            {kbDocNames.length > 0 ? (
              <>
                <View className="kb-sec-chips">
                  {kbDocNames.map((name, i) => (
                    <View key={`${kbDocIds[i]}-${name}`} className="kb-chip">
                      <Text className="kb-chip-name">{name}</Text>
                      <Text className="kb-chip-x" onClick={() => removeKbDoc(i)}>
                        ×
                      </Text>
                    </View>
                  ))}
                </View>
                <View className="kb-sec-tip">上方留空 = 按文档内容自动出题</View>
              </>
            ) : (
              <View className="kb-sec-none">
                不选也行，AI 自由发挥；选了文档，出题只考你的资料
              </View>
            )}
          </View>
        )}

        {isLoggedIn && (
          <View className="img-sec" onClick={toggleImages}>
            <View className="img-sec-main">
              <Text className="img-sec-title">🖼️ 生成图片</Text>
              <Text className="img-sec-tip">
                为每道题配一张相关插画，学习更直观（每日 20 张）
              </Text>
            </View>
            <View className={`img-switch ${generateImages ? 'on' : ''}`}>
              <View className="img-switch-dot" />
            </View>
          </View>
        )}

        <Button className="btn btn-block go-btn" hoverClass="hover" onClick={go}>
          <Icon name="rocketWhite" size={18} />
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
          <View className="sec-ic t-orange">
            <Icon name="clock" size={13} />
          </View>
          <Text>最近闯关</Text>
          {recent.length > 0 && (
            <Text
              className="sec-link"
              onClick={() => Taro.switchTab({ url: '/pages/profile/index' })}
            >
              查看全部 ›
            </Text>
          )}
        </View>
        {recent.length === 0 ? (
          <View className="recent-empty">还没有闯关记录，输入一句话开始吧！</View>
        ) : (
          recent.map((r, i) => (
            <View className="recent-card" key={i}>
              <View className="rc-ic">
                <Icon name="medal" size={16} />
              </View>
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
                <Icon name="replay" size={11} />
                再战
              </Button>
            </View>
          ))
        )}
      </ScrollView>
    </View>
  )
}
