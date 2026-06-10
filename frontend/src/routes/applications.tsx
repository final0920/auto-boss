import { createFileRoute } from '@tanstack/react-router'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { ApplicationTable, PendingConfirmQueue } from '../components/ApplicationBoard'
import { Card, CardContent, Input } from '../components/ui'
import { cn } from '../lib/utils'
import { getApplications, confirmApplication } from '../api'
import type { ApplicationRecord } from '../api'

const FILTERS: { key: string; label: string }[] = [
  { key: '', label: '全部' },
  { key: 'SENT', label: '已投递' },
  { key: 'FAILED', label: '未投递' },
  { key: 'DUP', label: '已投过' },
  { key: 'SENDING', label: '投递中' },
  { key: 'PENDING', label: '待筛选' },
]

function ApplicationsPage() {
  const [apps, setApps] = useState<ApplicationRecord[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState('')
  const [keyword, setKeyword] = useState('')

  const refresh = useCallback(() => {
    getApplications()
      .then(data => { setApps(data); setError(null) })
      .catch(() => setError('加载投递记录失败，请确认后端已启动'))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    refresh()
    const timer = setInterval(refresh, 5000)
    return () => clearInterval(timer)
  }, [refresh])

  const confirm = async (id: number, sent: boolean) => {
    try {
      await confirmApplication(id, sent)
      refresh()
    } catch { /* 下轮轮询自然纠正 */ }
  }

  // 前端筛选：状态 + 关键词（公司/岗位/JD）
  const filtered = useMemo(() => {
    let list = apps
    if (statusFilter) list = list.filter(a => a.status === statusFilter)
    const kw = keyword.trim()
    if (kw) {
      list = list.filter(a =>
        (a.job?.company ?? '').includes(kw)
        || (a.job?.title ?? '').includes(kw)
        || (a.job?.jd ?? '').includes(kw),
      )
    }
    return list
  }, [apps, statusFilter, keyword])

  const counts = useMemo(() => {
    const c: Record<string, number> = { '': apps.length }
    for (const a of apps) c[a.status] = (c[a.status] ?? 0) + 1
    return c
  }, [apps])

  return (
    <div className="p-6 space-y-5">
      <h1 className="font-serif text-2xl font-semibold">投递历史记录</h1>

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
          <PendingConfirmQueue apps={apps} onConfirm={confirm} />

          {/* 筛选栏：状态 chips + 关键词 */}
          <div className="flex flex-wrap items-center gap-2">
            {FILTERS.map(f => (
              <button
                key={f.key}
                onClick={() => setStatusFilter(f.key)}
                className={cn(
                  'rounded-full px-3 py-1 text-xs font-medium border transition-colors',
                  statusFilter === f.key
                    ? 'bg-primary text-primary-foreground border-primary'
                    : 'bg-card text-muted-foreground border-border/60 hover:text-foreground',
                )}
              >
                {f.label}
                {counts[f.key] != null && (
                  <span className="ml-1 opacity-70">({counts[f.key] ?? 0})</span>
                )}
              </button>
            ))}
            <div className="ml-auto w-56">
              <Input
                placeholder="搜索 公司 / 岗位 / JD…"
                value={keyword}
                onChange={e => setKeyword(e.target.value)}
              />
            </div>
          </div>

          <ApplicationTable apps={filtered} />
        </>
      )}
    </div>
  )
}

export const Route = createFileRoute('/applications')({
  component: ApplicationsPage,
})
