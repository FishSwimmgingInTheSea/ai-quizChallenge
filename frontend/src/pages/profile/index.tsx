import { useRef, useState } from 'react'
import { View, Text, Button, ScrollView, Image, Input } from '@tarojs/components'
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
  const [stats, setStats] = useState<{ count: number; avg: number } | null>(null)
  const profile = useUserStore((s) => s.profile)
  const isLoggedIn = useUserStore((s) => s.isLoggedIn)
  const setProfile = useUserStore((s) => s.setProfile)

  // 昵称行内编辑（已登录，input type="nickname"，方案 §6.4）
  const [editing, setEditing] = useState(false)
  const [draftName, setDraftName] = useState('')
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
        .then((s) => setStats({ count: s.total_count, avg: s.avg_accuracy }))
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
    setDraftName(displayName)
    setEditing(true)
  }

  const saveNickname = async () => {
    if (saveLockRef.current || !editing) return
    saveLockRef.current = true
    setEditing(false)
    const name = draftName.trim()
    try {
      if (name && name !== profile?.nickname) {
        const updated = await updateProfile({ nickname: name })
        setProfile(updated)
      }
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '昵称保存失败', icon: 'none' })
    } finally {
      saveLockRef.current = false
    }
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
  const totalCount = stats ? stats.count : recent.length
  const avgAccuracy = stats ? stats.avg : localAvg

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
              {isLoggedIn && editing ? (
                <Input
                  className="hero-name-input"
                  type="nickname"
                  value={draftName}
                  maxlength={16}
                  focus
                  placeholder="输入新昵称"
                  onInput={(e: any) => setDraftName(e.detail.value)}
                  onConfirm={saveNickname}
                  onBlur={saveNickname}
                />
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

        {/* 统计：数字为主角，图标与标签同行居中 */}
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
            <Text className="stat-num">{displayXp}</Text>
            <View className="stat-label-row">
              <View className="stat-ic t-yellow">
                <Icon name="star" size={11} />
              </View>
              <Text className="stat-label">累计经验</Text>
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
      </ScrollView>
    </View>
  )
}
