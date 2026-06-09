import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { useI18n } from '../lib/i18n'
import { useDevice } from '../lib/device-context'
import { Badge, Card, CardContent } from '../components/ui'
import { InboxPanel } from '../components/InboxPanel'
import type { HrMessage } from '../components/InboxPanel'
import { apiGet, apiPost } from '../api'
import { openSse } from '../lib/sse'

function InboxPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const { activeDevice, setDeviceMode } = useDevice()
  const [messages, setMessages] = useState<HrMessage[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 初始加载收件箱
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    apiGet<HrMessage[]>('/inbox')
      .then(data => {
        if (!cancelled) setMessages(data)
      })
      .catch(() => {
        if (!cancelled) setError('加载消息失败，请稍后重试')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [])

  // SSE 实时推送新消息
  useEffect(() => {
    const cleanup = openSse('/api/events/inbox', e => {
      try {
        const msg = JSON.parse(e.data) as HrMessage
        setMessages(prev => {
          const idx = prev.findIndex(m => m.id === msg.id)
          if (idx === -1) return [msg, ...prev]
          const next = [...prev]
          next[idx] = msg
          return next
        })
      } catch {
        // 忽略格式异常的推送
      }
    })
    return cleanup
  }, [])

  const unreadCount = messages.filter(m => !m.read).length

  // 接管对话：切换设备为手动模式，跳转镜像页
  const handleTakeover = async (msg: HrMessage) => {
    setMessages(prev =>
      prev.map(m => m.id === msg.id ? { ...m, takenOver: true, read: true } : m),
    )
    if (activeDevice) {
      setDeviceMode(activeDevice.id, 'MANUAL')
    }
    try {
      await apiPost(`/applications/${msg.applicationId}/takeover`)
    } catch {
      // 非致命错误：接管请求失败时仍允许用户进入手动模式
    }
    navigate({ to: '/screen' })
  }

  // 标记已读
  const markRead = async (id: string) => {
    setMessages(prev => prev.map(m => m.id === id ? { ...m, read: true } : m))
    try {
      await apiPost(`/inbox/${id}/read`)
    } catch {
      // 非致命：已读状态只影响 badge 计数
    }
  }

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="font-serif text-2xl font-semibold">{t.inbox.title}</h1>
        {unreadCount > 0 && (
          <Badge variant="destructive" className="rounded-full px-2 py-0.5 text-xs">
            {unreadCount}
          </Badge>
        )}
      </div>

      {loading && (
        <Card variant="subtle">
          <CardContent className="py-10 text-center">
            <p className="text-muted-foreground text-sm">加载中…</p>
          </CardContent>
        </Card>
      )}

      {!loading && error && (
        <Card variant="subtle" className="border-destructive/40 bg-destructive/5">
          <CardContent className="py-8 text-center">
            <p className="text-destructive text-sm">{error}</p>
          </CardContent>
        </Card>
      )}

      {!loading && !error && messages.length === 0 && (
        <Card variant="subtle">
          <CardContent className="py-10 text-center">
            <p className="text-muted-foreground text-sm">暂无消息</p>
          </CardContent>
        </Card>
      )}

      {!loading && !error && messages.length > 0 && (
        <InboxPanel
          messages={messages}
          onMarkRead={markRead}
          onTakeover={handleTakeover}
        />
      )}
    </div>
  )
}

export const Route = createFileRoute('/inbox')({
  component: InboxPage,
})
