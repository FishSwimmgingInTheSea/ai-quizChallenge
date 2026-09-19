import { useRef, useState } from 'react'
import { View, Text, Button, ScrollView, Image, Input } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import Mascot from '../../components/Mascot'
import {
  getQuizRecords,
  getUserStats,
  recordToRecentView,
  updateProfile,
  uploadAvatar,
} from '../../services/api'
import { getRecentQuizzes, getTotalXp, RecentQuiz } from '../../services/storage'
import { toAbsoluteUrl } from '../../services/config'
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

  return (
    <View className="page profile">
      <ScrollView scrollY className="scr">
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
                <Mascot type="grad" size={72} floaty />
              )}
            </Button>
          ) : (
            <Mascot type="grad" size={72} floaty />
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

        <View className="stat-row">
          <View className="stat-box">
            <Text className="stat-num">{totalCount}</Text>
            <Text className="stat-label">闯关次数</Text>
          </View>
          <View className="stat-box">
            <Text className="stat-num">{avgAccuracy}%</Text>
            <Text className="stat-label">平均正确率</Text>
          </View>
          <View className="stat-box">
            <Text className="stat-num">{displayXp}</Text>
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
