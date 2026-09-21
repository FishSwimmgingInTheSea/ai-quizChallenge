import { useRef, useState } from 'react'
import { View, Text, Button, ScrollView, Image, Input, Form } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import Icon from '../../components/Icon'
import Mascot from '../../components/Mascot'
import {
  getQuizRecordDetail,
  getQuizRecords,
  getUserStats,
  recordToRecentView,
  updateProfile,
  uploadAvatar,
} from '../../services/api'
import { getRecentQuizzes, getTotalXp, RecentQuiz } from '../../services/storage'
import { toAbsoluteUrl } from '../../services/config'
import { clearToken } from '../../services/token'
import { useQuizStore } from '../../store/quiz'
import { useUserStore } from '../../store/user'
import './index.scss'

export default function Profile() {
  const [recent, setRecent] = useState<RecentQuiz[]>([])
  const [localXp, setLocalXp] = useState(0)
  // 登录态下的服务端统计（方案 §8.3：我的-统计）；null = 匿名态按本地现算
  const [stats, setStats] = useState<{
    count: number
    avg: number
    correct: number
  } | null>(null)
  const profile = useUserStore((s) => s.profile)
  const isLoggedIn = useUserStore((s) => s.isLoggedIn)
  const setProfile = useUserStore((s) => s.setProfile)

  // 昵称行内编辑（已登录，input type="nickname"，方案 §6.4）
  // 对齐官方示例：不绑定 value（微信昵称填入是原生行为，绑定值会被模拟器/真机
  // 回写，导致填入的昵称一闪又被旧值打回）；实时值只记 ref，保存以
  // confirm/blur 事件带回的最终值为准
  const [editing, setEditing] = useState(false)
  const draftRef = useRef('')
  // onConfirm / onBlur 双触发防重入锁
  const saveLockRef = useRef(false)
  const [uploading, setUploading] = useState(false)
  // 历史报告回看：水合 quiz store 后跳报告页
  const hydrateRecord = useQuizStore((s) => s.hydrateRecord)
  const [openingReport, setOpeningReport] = useState(false)

  useDidShow(() => {
    // 数据源切换（方案 §8.3）：登录态读服务端，匿名态读本地
    if (useUserStore.getState().isLoggedIn) {
      setStats(null)
      getUserStats()
        .then((s) =>
          setStats({
            count: s.total_count,
            avg: s.avg_accuracy,
            correct: s.total_correct,
          }),
        )
        .catch(() => setStats(null)) // 失败回退本地口径展示
      getQuizRecords({ limit: 20 })
        .then((page) => setRecent(page.records.map(recordToRecentView)))
        .catch(() => setRecent([]))
      setLocalXp(0)
    } else {
      setStats(null)
      setRecent(getRecentQuizzes())
      setLocalXp(getTotalXp())
    }
  })

  const displayName = isLoggedIn ? profile?.nickname || '学习小达人' : '学习小达人'
  const displayXp = isLoggedIn ? profile?.total_xp ?? 0 : localXp
  const avatarSrc = isLoggedIn ? toAbsoluteUrl(profile?.avatar_url || '') : ''

  const goLogin = () => Taro.navigateTo({ url: '/pages/login/index' })

  const startEdit = () => {
    draftRef.current = ''
    setEditing(true)
  }

  const saveNickname = async (evtValue?: string) => {
    if (saveLockRef.current || !editing) return
    saveLockRef.current = true
    setEditing(false)
    // 取值优先级：form 提交/键盘 confirm 事件带回的原生当前值 > 输入过程 ref 记录；
    // 微信昵称填入不派发可靠事件，官方推荐用 form 在提交时刻收集原生值
    const name = (typeof evtValue === 'string' ? evtValue : draftRef.current).trim()
    try {
      if (!name) {
        Taro.showToast({ title: '没填昵称，未保存', icon: 'none' })
      } else if (name !== profile?.nickname) {
        const updated = await updateProfile({ nickname: name })
        setProfile(updated)
        Taro.showToast({ title: '昵称已更新', icon: 'success' })
      }
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '昵称保存失败', icon: 'none' })
    } finally {
      saveLockRef.current = false
    }
  }

  const cancelEdit = () => {
    if (saveLockRef.current) return
    setEditing(false)
  }

  // chooseAvatar -> 上传 -> 绑定资料（两步，方案 §6.3）
  const handleChooseAvatar = async (tempPath?: string) => {
    if (!tempPath || uploading) return
    setUploading(true)
    try {
      const { avatar_url } = await uploadAvatar(tempPath)
      const updated = await updateProfile({ avatar_url })
      setProfile(updated)
      Taro.showToast({ title: '头像已更新', icon: 'none' })
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '头像更新失败', icon: 'none' })
    } finally {
      setUploading(false)
    }
  }

  const localAvg =
    recent.length > 0
      ? Math.round(recent.reduce((s, r) => s + r.accuracy, 0) / recent.length)
      : 0
  // 匿名态无服务端聚合：按每局 题数×正确率 折算答对数再求和（与 localAvg 同口径回退）
  const localCorrect = recent.reduce(
    (s, r) => s + Math.round((r.count * r.accuracy) / 100),
    0,
  )
  const totalCount = stats ? stats.count : recent.length
  const avgAccuracy = stats ? stats.avg : localAvg
  const totalCorrect = stats ? stats.correct : localCorrect

  // 点记录卡回看该局复盘报告：匿名引导登录，本地记录无服务端报告
  const openReport = async (r: RecentQuiz) => {
    if (!isLoggedIn) {
      Taro.navigateTo({ url: '/pages/login/index' })
      return
    }
    if (r.id == null || openingReport) return
    setOpeningReport(true)
    Taro.showLoading({ title: '加载报告中' })
    try {
      const detail = await getQuizRecordDetail(r.id)
      Taro.hideLoading()
      if (!detail.report) {
        Taro.showToast({ title: '这局当时没生成报告', icon: 'none' })
        return
      }
      hydrateRecord(detail)
      Taro.navigateTo({ url: '/pages/report/index' })
    } catch (e: any) {
      Taro.hideLoading()
      Taro.showToast({ title: e?.message || '加载失败，请重试', icon: 'none' })
    } finally {
      setOpeningReport(false)
    }
  }

  const goKb = () => {
    if (!useUserStore.getState().isLoggedIn) {
      Taro.navigateTo({ url: '/pages/login/index' })
      return
    }
    Taro.navigateTo({ url: '/pages/kb/index' })
  }

  const handleLogout = () => {
    Taro.showModal({
      title: '退出登录',
      content: '退出后本地记录仍保留，云端记录登录后可继续查看',
      success: (res) => {
        if (!res.confirm) return
        clearToken()
        useUserStore.getState().clear()
        setStats(null)
        setRecent(getRecentQuizzes())
        setLocalXp(getTotalXp())
        Taro.showToast({ title: '已退出登录', icon: 'none' })
      },
    })
  }

  return (
    <View className="page profile">
      <ScrollView scrollY className="scr">
        {/* 头部卡：头像 + 昵称 + XP，暖色渐变底 */}
        <View className="hero-card">
          <View className="profile-hero">
            {isLoggedIn ? (
              <Button
                className="avatar-btn"
                openType="chooseAvatar"
                onChooseAvatar={(e: any) => handleChooseAvatar(e?.detail?.avatarUrl)}
              >
                {avatarSrc ? (
                  <Image className="avatar-img" src={avatarSrc} mode="aspectFill" />
                ) : (
                  <Mascot type="grad" size={64} floaty />
                )}
              </Button>
            ) : (
              <Mascot type="grad" size={64} floaty />
            )}
            <View className="hero-info">
              {/* 官方推荐用 form 收集 nickname 输入：提交时刻直接读输入框原生当前值，
                  不依赖 input/blur 事件是否触发（微信昵称填入不派发可靠事件）；
                  保存/取消显式按钮，结束编辑不再依赖失焦 */}
              {isLoggedIn && editing ? (
                <Form
                  className="nick-form"
                  onSubmit={(e: any) => saveNickname(e?.detail?.value?.nickname)}
                >
                  <Input
                    className="hero-name-input"
                    type="nickname"
                    name="nickname"
                    maxlength={16}
                    focus
                    placeholder="输入新昵称"
                    onInput={(e: any) => {
                      // 只记 ref 不 setState，避免编辑期间重渲染回写输入框
                      draftRef.current = e.detail.value
                    }}
                    onConfirm={(e: any) => saveNickname(e?.detail?.value)}
                  />
                  <View className="nick-ops">
                    <Button className="nick-save" hoverClass="none" formType="submit">
                      保存昵称
                    </Button>
                    <Text className="nick-cancel" onClick={cancelEdit}>
                      取消
                    </Text>
                  </View>
                </Form>
              ) : (
                <Text
                  className="hero-name"
                  onClick={isLoggedIn ? startEdit : undefined}
                >
                  {displayName}
                </Text>
              )}
              <View className="badge b-xp">⭐ {displayXp} XP</View>
              {!isLoggedIn && (
                <Text className="login-hint" onClick={goLogin}>
                  登录后同步闯关进度 ›
                </Text>
              )}
            </View>
          </View>
          {isLoggedIn && (
            <View className="hero-tip">点头像换头像 · 点昵称改名</View>
          )}
        </View>

        {/* 统计：数字为主角，图标与标签同行居中；XP 已在头部卡徽章展示，此处只放战绩指标 */}
        <View className="stat-row">
          <View className="stat-box">
            <Text className="stat-num">{totalCount}</Text>
            <View className="stat-label-row">
              <View className="stat-ic t-orange">
                <Icon name="flag" size={11} />
              </View>
              <Text className="stat-label">闯关次数</Text>
            </View>
          </View>
          <View className="stat-box">
            <Text className="stat-num">{avgAccuracy}%</Text>
            <View className="stat-label-row">
              <View className="stat-ic t-green">
                <Icon name="target" size={11} />
              </View>
              <Text className="stat-label">平均正确率</Text>
            </View>
          </View>
          <View className="stat-box">
            <Text className="stat-num">{totalCorrect}</Text>
            <View className="stat-label-row">
              <View className="stat-ic t-green">
                <Icon name="check" size={11} />
              </View>
              <Text className="stat-label">累计答对</Text>
            </View>
          </View>
        </View>

        {/* 快捷入口：横排 图标 + 文案 + 箭头 */}
        <View className="act-grid">
          <View className="act-tile" onClick={goKb}>
            <View className="act-ic t-blue">
              <Icon name="book" size={17} />
            </View>
            <View className="act-txt">
              <Text className="act-title">我的知识库</Text>
              <Text className="act-sub">上传文档出题</Text>
            </View>
            <Text className="act-arrow">›</Text>
          </View>
          <View
            className="act-tile"
            onClick={() => Taro.switchTab({ url: '/pages/index/index' })}
          >
            <View className="act-ic t-orange">
              <Icon name="flag" size={17} />
            </View>
            <View className="act-txt">
              <Text className="act-title">开始闯关</Text>
              <Text className="act-sub">万物皆可闯关</Text>
            </View>
            <Text className="act-arrow">›</Text>
          </View>
        </View>

        {/* 闯关档案：完整历史 + 报告回看（首页只留最近 3 条快捷再战） */}
        <View className="sec-mini-title">
          <View className="sec-ic t-yellow">
            <Icon name="flag" size={13} />
          </View>
          <Text>闯关档案</Text>
          {recent.length > 0 && (
            <Text className="sec-count">共 {totalCount} 次</Text>
          )}
        </View>
        {recent.length === 0 ? (
          <View className="empty-card">还没有记录，去首页闯一关吧！</View>
        ) : (
          recent.map((r, i) => (
            <View className="recent-card" key={i} onClick={() => openReport(r)}>
              <View className="rc-ic">
                <Icon name="medal" size={16} />
              </View>
              <View className="rc-main">
                <Text className="rc-title">{r.title}</Text>
                <Text className="rc-sub">
                  {r.count} 题 · {r.time} · 正确率 {r.accuracy}%
                </Text>
                <Text className="rc-stars">
                  {'★'.repeat(r.stars)}
                  {'☆'.repeat(5 - r.stars)}
                </Text>
              </View>
              {isLoggedIn ? (
                <View className="rc-go">
                  <Icon name="book" size={12} />
                  <Text>报告</Text>
                </View>
              ) : (
                <Text className="rc-lock">登录可看报告</Text>
              )}
            </View>
          ))
        )}
        {!isLoggedIn && recent.length > 0 && (
          <View className="anon-tip">
            当前为本地记录；登录后每局复盘报告云端保存，随时回看
          </View>
        )}

        <View className="future-note">
          错题本、艾宾浩斯复习、深度分析报告等能力将在 P1 阶段上线
        </View>

        {isLoggedIn ? (
          <View className="logout-row" onClick={handleLogout}>
            退出登录
          </View>
        ) : (
          <Button className="btn btn-block go-btn" hoverClass="hover" onClick={goLogin}>
            <Icon name="rocketWhite" size={16} />
            立即登录
          </Button>
        )}

        {/* 底部安全占位盒：保证末尾按钮能滚出手势横条遮挡区 */}
        <View className="scr-safe" />
      </ScrollView>
    </View>
  )
}
