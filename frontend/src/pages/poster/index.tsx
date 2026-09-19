import { View, Text, Button, Canvas, ScrollView } from '@tarojs/components'
import Taro, { useShareAppMessage } from '@tarojs/taro'
import Mascot from '../../components/Mascot'
import { useQuizStore } from '../../store/quiz'
import './index.scss'

export default function Poster() {
  const { report, records, total, title } = useQuizStore()
  const correct = records.filter((r) => r.is_correct).length
  const accuracy = report?.accuracy ?? (total ? Math.round((correct / total) * 100) : 0)
  const totalMs = records.reduce((sum, r) => sum + (r.duration_ms || 0), 0)
  const durText = `${Math.floor(totalMs / 60000)}'${Math.floor((totalMs % 60000) / 1000)
    .toString()
    .padStart(2, '0')}"`
  const quote = report?.share_quote || '把知识做成关卡，记忆会更深。'

  useShareAppMessage(() => ({
    title: `我在「智趣 AI 闯关」学了「${title}」，正确率 ${accuracy}%，来挑战我！`,
    path: '/pages/index/index',
  }))

  const savePoster = () => {
    const ctx = Taro.createCanvasContext('posterCanvas')
    const W = 300
    const H = 470

    // 卡片底
    ctx.setFillStyle('#ffffff')
    ctx.fillRect(0, 0, W, H)

    // 顶部橙色渐变
    const grad = ctx.createLinearGradient(0, 0, W, 150)
    grad.addColorStop(0, '#FF7548')
    grad.addColorStop(1, '#FF9A6E')
    ctx.setFillStyle(grad)
    ctx.fillRect(0, 0, W, 150)

    ctx.setTextAlign('center')
    ctx.setFillStyle('#ffffff')
    ctx.setFontSize(20)
    ctx.fillText('智趣 AI 闯关', W / 2, 46)
    ctx.setFontSize(17)
    ctx.fillText(`「 ${quote.slice(0, 12)} 」`, W / 2, 90)
    if (quote.length > 12) {
      ctx.fillText(`${quote.slice(12, 24)}`, W / 2, 116)
    }

    // 主体
    ctx.setFillStyle('#8A8478')
    ctx.setFontSize(12)
    ctx.fillText(`🎯 ${title} · ${total} 题`, W / 2, 190)

    ctx.setFillStyle('#EA5A24')
    ctx.setFontSize(46)
    ctx.fillText(`${accuracy}%`, W / 2, 250)

    ctx.setFillStyle('#8A8478')
    ctx.setFontSize(11)
    ctx.fillText(`答题正确率 · 用时 ${durText}`, W / 2, 275)

    // 二维码占位（棋盘格）
    const qx = W / 2 - 36
    const qy = 320
    ctx.setFillStyle('#2E2A26')
    ctx.fillRect(qx, qy, 72, 72)
    ctx.setFillStyle('#ffffff')
    for (let r = 0; r < 6; r++) {
      for (let c = 0; c < 6; c++) {
        if ((r + c) % 2 === 0) {
          ctx.fillRect(qx + 6 + c * 10, qy + 6 + r * 10, 10, 10)
        }
      }
    }
    ctx.setFillStyle('#8A8478')
    ctx.setFontSize(11)
    ctx.fillText('扫码和我一起闯关 · 万物皆可闯关', W / 2, 424)

    ctx.draw(false, () => {
      Taro.canvasToTempFilePath({
        canvasId: 'posterCanvas',
        success: (res) => persist(res.tempFilePath),
        fail: () => Taro.showToast({ title: '生成失败，请重试', icon: 'none' }),
      })
    })
  }

  const persist = (filePath: string) => {
    Taro.saveImageToPhotosAlbum({
      filePath,
      success: () => Taro.showToast({ title: '已保存到相册', icon: 'success' }),
      fail: (err) => {
        if (String(err.errMsg).includes('auth')) {
          Taro.showModal({
            title: '需要相册权限',
            content: '请在设置中开启保存图片权限',
            success: (r) => r.confirm && Taro.openSetting(),
          })
        } else {
          Taro.showToast({ title: '已取消保存', icon: 'none' })
        }
      },
    })
  }

  return (
    <View className="page poster-page">
      <ScrollView scrollY className="scr">
        <View className="poster-stage">
          <View className="poster">
            <View className="stamp-round">
              闯关{'\n'}成功
            </View>
            <View className="p-top">
              <View className="p-logo">
                智趣 <Text className="em">AI</Text> 闯关
              </View>
              <View className="p-quote">「 {quote} 」</View>
            </View>
            <View className="p-body">
              <Text className="p-topic">🎯 {title} · {total} 题</Text>
              <Text className="p-acc">
                {accuracy}
                <Text className="p-acc-unit">%</Text>
              </Text>
              <Text className="p-acc-sub">答题正确率 · 用时 {durText}</Text>
              <Mascot type="grad" size={86} className="p-mascot" />
              <View className="p-code">
                <View className="qr" />
                <View className="qr-side">
                  扫码和我一起闯关{'\n'}万物皆可闯关 ✏️
                </View>
              </View>
            </View>
          </View>

          <View className="poster-ops">
            <Button className="btn btn-ghost" hoverClass="hover" onClick={savePoster}>
              保存海报
            </Button>
            <Button className="btn btn-wx" hoverClass="hover" openType="share">
              分享给好友
            </Button>
          </View>
        </View>
      </ScrollView>

      {/* 离屏 Canvas，仅用于生成保存图片 */}
      <Canvas
        canvasId="posterCanvas"
        className="poster-canvas-offscreen"
        style={{ width: '300px', height: '470px' }}
      />
    </View>
  )
}
