import { useCallback, useEffect, useState } from 'react'
import { View, Text, Button, ScrollView } from '@tarojs/components'
import Taro, { useDidShow } from '@tarojs/taro'
import Mascot from '../../components/Mascot'
import { deleteKbDocument, getKbDocuments, uploadKbDocument } from '../../services/api'
import { useQuizStore } from '../../store/quiz'
import { useUserStore } from '../../store/user'
import { KbDocument } from '../../types'
import './index.scss'

/** 选择模式下最多可勾选的文档数（对齐后端 GenerateQuizRequest 约束）。 */
const MAX_SELECT = 10

const STATUS_LABEL: Record<string, { text: string; cls: string }> = {
  processing: { text: '解析中', cls: 'st-processing' },
  ready: { text: '可出题', cls: 'st-ready' },
  failed: { text: '解析失败', cls: 'st-failed' },
}

function fmtSize(bytes: number): string {
  if (!bytes) return '0B'
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)}KB`
  return `${(bytes / 1024 / 1024).toFixed(1)}MB`
}

export default function KbPage() {
  // 从首页"选文档出题"进入时带 mode=select：勾选 ready 文档回填出题请求
  const selectMode =
    Taro.getCurrentInstance().router?.params?.mode === 'select'
  const isLoggedIn = useUserStore((s) => s.isLoggedIn)
  const [docs, setDocs] = useState<KbDocument[]>([])
  const [loaded, setLoaded] = useState(false)
  const [uploading, setUploading] = useState(false)
  // 选择模式本地勾选集（初始取已选）
  const [selected, setSelected] = useState<number[]>([])

  const refresh = useCallback(async () => {
    if (!useUserStore.getState().isLoggedIn) {
      setLoaded(true)
      return
    }
    try {
      const page = await getKbDocuments({ limit: 50 })
      setDocs(page.documents)
    } catch {
      // 网络异常保留旧列表，不打扰
    } finally {
      setLoaded(true)
    }
  }, [])

  useDidShow(() => {
    if (selectMode) {
      setSelected(useQuizStore.getState().kbDocIds)
    }
    refresh()
  })

  // 有"解析中"文档时轮询刷新（后台上台任务完成即变 ready/failed，全终态自动停）
  useEffect(() => {
    const busy = docs.some((d) => d.status === 'processing')
    if (!busy) return
    const timer = setInterval(refresh, 3000)
    return () => clearInterval(timer)
  }, [docs, refresh])

  const goLogin = () => Taro.navigateTo({ url: '/pages/login/index' })

  const handleUpload = async () => {
    if (uploading) return
    try {
      const res = await Taro.chooseMessageFile({
        count: 1,
        type: 'file',
        extension: ['pdf', 'docx', 'md', 'txt'],
      })
      const file = res.tempFiles?.[0]
      if (!file) return
      setUploading(true)
      await uploadKbDocument(file.path)
      Taro.showToast({ title: '已上传，正在解析…', icon: 'none' })
      await refresh()
    } catch (e: any) {
      Taro.showToast({ title: e?.message || '上传失败', icon: 'none' })
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = (doc: KbDocument) => {
    Taro.showModal({
      title: '删除文档',
      content: `确定删除「${doc.filename}」吗？出题时将不再可用。`,
      confirmColor: '#EA5A24',
      success: (res) => {
        if (!res.confirm) return
        deleteKbDocument(doc.doc_id)
          .then(() => {
            setSelected((ids) => ids.filter((id) => id !== doc.doc_id))
            Taro.showToast({ title: '已删除', icon: 'none' })
            return refresh()
          })
          .catch((e: any) => {
            Taro.showToast({ title: e?.message || '删除失败', icon: 'none' })
          })
      },
    })
  }

  const toggleSelect = (doc: KbDocument) => {
    if (doc.status !== 'ready') return
    setSelected((ids) =>
      ids.includes(doc.doc_id)
        ? ids.filter((id) => id !== doc.doc_id)
        : ids.length >= MAX_SELECT
          ? (Taro.showToast({ title: `最多选 ${MAX_SELECT} 个文档`, icon: 'none' }), ids)
          : [...ids, doc.doc_id],
    )
  }

  const confirmSelection = () => {
    if (selected.length > MAX_SELECT) {
      Taro.showToast({ title: `最多选 ${MAX_SELECT} 个文档`, icon: 'none' })
      return
    }
    const names = docs
      .filter((d) => selected.includes(d.doc_id))
      .map((d) => d.filename)
    useQuizStore.getState().setKbSelection(selected, names)
    Taro.navigateBack()
  }

  const readyCount = docs.filter((d) => d.status === 'ready').length

  const renderBody = () => {
    if (!isLoggedIn) {
      return (
        <View className="kb-empty">
          <Mascot type="think" size={64} floaty />
          <View className="kb-empty-text">
            知识库是你的私人学习资料库{'\n'}上传文档，出题只考你文档里的内容
          </View>
          <Button className="btn btn-wx" hoverClass="hover" onClick={goLogin}>
            登录后使用知识库
          </Button>
        </View>
      )
    }
    if (!loaded) return <View className="kb-empty-text">加载中…</View>
    if (docs.length === 0) {
      return (
        <View className="kb-empty">
          <Mascot type="think" size={64} floaty />
          <View className="kb-empty-text">
            还没有文档{'\n'}上传一份培训资料 / 题库 / 讲义试试吧
          </View>
        </View>
      )
    }
    return docs.map((doc) => {
      const st = STATUS_LABEL[doc.status] || STATUS_LABEL.processing
      const isSel = selected.includes(doc.doc_id)
      return (
        <View
          key={doc.doc_id}
          className={`kb-card ${selectMode && isSel ? 'sel' : ''} ${
            selectMode && doc.status !== 'ready' ? 'dim' : ''
          }`}
          onClick={() => selectMode && toggleSelect(doc)}
        >
          {selectMode && (
            <View className={`kb-check ${isSel ? 'on' : ''}`}>
              {isSel ? '✓' : ''}
            </View>
          )}
          <View className="kb-main">
            <Text className="kb-filename">{doc.filename}</Text>
            <Text className="kb-meta">
              {doc.doc_type.toUpperCase()} · {fmtSize(doc.file_size)}
              {doc.status === 'ready' && doc.chunk_count > 0
                ? ` · ${doc.chunk_count} 块`
                : ''}
              {' · '}
              {doc.created_at.slice(5, 16)}
            </Text>
            {doc.status === 'failed' && doc.error && (
              <Text className="kb-error">解析失败：{doc.error}</Text>
            )}
          </View>
          <View className={`kb-status ${st.cls}`}>{st.text}</View>
          {!selectMode && (
            <Text className="kb-del" onClick={() => handleDelete(doc)}>
              删除
            </Text>
          )}
        </View>
      )
    })
  }

  return (
    <View className="page kb">
      <ScrollView scrollY className="scr">
        <View className="kb-top">
          <Mascot type="think" size={44} />
          <View className="bubble">
            {selectMode ? (
              <>
                勾选文档作为出题依据，{'\n'}
                <Text className="em">只考你上传的资料</Text>（最多 {MAX_SELECT} 个）
              </>
            ) : (
              <>上传私有文档建知识库，出题优先引用你的资料</>
            )}
          </View>
        </View>

        {isLoggedIn && (
          <>
            <Button
              className="btn btn-block btn-soft upload-btn"
              hoverClass="hover"
              disabled={uploading}
              onClick={handleUpload}
            >
              {uploading ? '上传中…' : '＋ 上传文档'}
            </Button>
            <View className="kb-tip">
              支持 PDF / Word / Markdown / TXT，单个 ≤ 10MB；从聊天记录中选取
            </View>
          </>
        )}

        <View className="sec-mini-title">
          <Text>我的文档{isLoggedIn && readyCount > 0 ? `（${readyCount} 个可出题）` : ''}</Text>
        </View>

        {renderBody()}

        {selectMode && isLoggedIn && (
          <Button
            className="btn btn-block kb-confirm"
            hoverClass="hover"
            disabled={selected.length === 0}
            onClick={selected.length > 0 ? confirmSelection : undefined}
          >
            {selected.length > 0
              ? `确定，用 ${selected.length} 个文档出题`
              : '勾选上方"可出题"文档'}
          </Button>
        )}

        {/* 底部安全占位盒：保证末尾按钮能滚出手势横条遮挡区 */}
        <View className="scr-safe" />
      </ScrollView>
    </View>
  )
}
