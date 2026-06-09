import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { useI18n } from '../lib/i18n'
import { ApplicationBoard, PendingConfirmQueue } from '../components/ApplicationBoard'
import type { Application, AppStatus } from '../components/ApplicationBoard'
import { Card, CardContent } from '../components/ui'
import { apiGet, apiPost } from '../api'
import { openSse } from '../lib/sse'

function ApplicationsPage() {
  const { t } = useI18n()
  const [apps, setApps] = useState<Application[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 初始加载
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    apiGet<Application[]>('/applications')
      .then(data => {
        if (!cancelled) setApps(data)
      })
      .catch(() => {
        if (!cancelled) setError('加载投递记录失败，请稍后重试')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [])

  // SSE 实时推送：后端推送 application 状态变更
  useEffect(() => {
    const cleanup = openSse('/api/events/applications', e => {
      try {
        const updated = JSON.parse(e.data) as Application
        setApps(prev => {
          const idx = prev.findIndex(a => a.id === updated.id)
          if (idx === -1) return [...prev, updated]
          const next = [...prev]
          next[idx] = updated
          return next
        })
      } catch {
        // 忽略格式异常的推送
      }
    })
    return cleanup
  }, [])

  // 人工确认已发送
  const confirmSent = async (id: string) => {
    setApps(prev => prev.map(a => a.id === id ? { ...a, status: 'SENT' as AppStatus } : a))
    try {
      await apiPost(`/applications/${id}/confirm-sent`)
    } catch {
      // 失败时回滚
      setApps(prev => prev.map(a => a.id === id ? { ...a, status: 'SENDING' as AppStatus } : a))
    }
  }

  // 人工确认未发送
  const confirmNotSent = async (id: string) => {
    setApps(prev =>
      prev.map(a =>
        a.id === id ? { ...a, status: 'FAILED' as AppStatus, failReason: '人工确认未发送' } : a,
      ),
    )
    try {
      await apiPost(`/applications/${id}/confirm-not-sent`)
    } catch {
      setApps(prev => prev.map(a => a.id === id ? { ...a, status: 'SENDING' as AppStatus, failReason: undefined } : a))
    }
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="font-serif text-2xl font-semibold">{t.applications.title}</h1>

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

      {!loading && !error && (
        <>
          {/* SENDING 待确认队列 — 崩溃恢复确认 */}
          <PendingConfirmQueue
            apps={apps}
            onConfirmSent={confirmSent}
            onConfirmNotSent={confirmNotSent}
          />

          {apps.length === 0 ? (
            <Card variant="subtle">
              <CardContent className="py-10 text-center">
                <p className="text-muted-foreground text-sm">暂无投递记录</p>
              </CardContent>
            </Card>
          ) : (
            /* 状态机泳道看板 */
            <ApplicationBoard
              apps={apps}
              onConfirmSent={confirmSent}
              onConfirmNotSent={confirmNotSent}
            />
          )}
        </>
      )}
    </div>
  )
}

export const Route = createFileRoute('/applications')({
  component: ApplicationsPage,
})
