import { useState } from 'react'
import { View, Text, Button } from '@tarojs/components'
import Taro from '@tarojs/taro'
import Mascot from '../../components/Mascot'
import { login } from '../../services/auth'
import './index.scss'

export default function Login() {
  const [logging, setLogging] = useState(false)
  const goHome = () => Taro.switchTab({ url: '/pages/index/index' })

  const wxLogin = async () => {
    if (logging) return
    setLogging(true)
    try {
      await login()
      Taro.showToast({ title: '登录成功，开始闯关吧！', icon: 'none' })
      setTimeout(goHome, 500)
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '登录失败，请重试', icon: 'none' })
      setLogging(false)
    }
  }

  return (
    <View className="page s1">
      <View className="scr s1-scr">
        <View className="hero">
          <View className="hero-logo">
            智趣 <Text className="em">AI</Text> 闯关
          </View>
          <View className="hero-slogan">万物皆可闯关</View>
        </View>

        <View className="mascot-stage">
          <Mascot type="wave" size={128} floaty />
          <View className="bubble">
            你好呀！我是小智{'\n'}把想学的东西丢给我，{'\n'}马上给你出一套
            <Text className="em">闯关题</Text>！
          </View>
        </View>

        <View className="sell-list">
          <View className="sell-item">一句话 → 自动生成 5 道闯关题</View>
          <View className="sell-item">边玩边学，答错也有深度讲解</View>
          <View className="sell-item">通关自动生成 AI 复盘报告</View>
        </View>

        <View className="login-zone">
          <Button
            className="btn btn-wx btn-block"
            hoverClass="hover"
            loading={logging}
            disabled={logging}
            onClick={wxLogin}
          >
            {logging ? '正在登录…' : '微信一键登录'}
          </Button>
          <Text className="skip-link" onClick={goHome}>
            暂不登录，先逛逛
          </Text>
          <Text className="protocol">登录即同意《用户协议》与《隐私政策》</Text>
        </View>
      </View>
    </View>
  )
}
