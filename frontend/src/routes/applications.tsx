import { createFileRoute } from '@tanstack/react-router'
import { useCallback, useEffect, useState } from 'react'
import { ApplicationTable, PendingConfirmQueue } from '../components/ApplicationBoard'
import { Button, Card, CardContent, Input } from '../components/ui'
import { cn } from '../lib/utils'
import { getApplications, getApplicationStats, getSending, confirmApplication, clearHistory } from '../api'
import type { ApplicationRecord } from '../api'

const PAGE = 20

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
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<Record<string, number>>({})
  const [sending, setSending] = useState<ApplicationRecord[]>([])
  const [page, setPage] = useState(1)
  const [statusFilter, setStatusFilter] = useState('')
  const [keyword, setKeyword] = useState('')
  const [debouncedKw, setDebouncedKw] = useState('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // 关键词防抖 300ms → 触发后端搜索
  useEffect(() => {
    const t = setTimeout(() => setDebouncedKw(keyword.trim()), 300)
    return () => clearTimeout(t)
  }, [keyword])

  // 切状态 / 改搜索词 → 回第 1 页
  useEffect(() => { setPage(1) }, [statusFilter, debouncedKw])

  // 历史列表 + 全局计数：后端分页查询（翻页/筛选/搜索/手动刷新触发，不自动轮询）
  const loadList = useCallback(() => {
    setLoading(true)
    Promise.all([
      getApplications({
        status: statusFilter || undefined,
        keyword: debouncedKw || undefined,
        skip: (page - 1) * PAGE,
        limit: PAGE,
      }),
      getApplicationStats(debouncedKw || undefined),
    ])
      .then(([pg, st]) => { setApps(pg.items); setTotal(pg.total); setStats(st); setError(null) })
      .catch(() => setError('加载投递记录失败，请确认后端已启动'))
      .finally(() => setLoading(false))
  }, [statusFilter, debouncedKw, page])

  useEffect(() => { loadList() }, [loadList])

  // 待确认队列：独立全量拉取 + 5s 轮询（SENDING 可能不在当前页，必须独立）
  const loadSending = useCallback(() => {
    getSending().then(setSending).catch(() => { /* 非致命 */ })
  }, [])
  useEffect(() => {
    loadSending()
    const t = setInterval(loadSending, 5000)
    return () => clearInterval(t)
  }, [loadSending])

  const confirm = async (id: number, sent: boolean) => {
    try {
      await confirmApplication(id, sent)
      loadSending()
      loadList()
    } catch { /* 下轮自然纠正 */ }
  }

  const onClear = async () => {
    if (!window.confirm('确定清空全部投递历史？\n（岗位 / 投递记录 / HR消息 / 日志 / 今日配额计数将被删除，规则配置保留）')) return
    try {
      await clearHistory()
      setPage(1)
      loadList()
      loadSending()
    } catch {
      window.alert('清空失败，请确认后端在线')
    }
  }

  const totalPages = Math.max(1, Math.ceil(total / PAGE))

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center justify-between gap-3">
        <h1 className="font-serif text-2xl font-semibold">投递历史记录</h1>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => { loadList(); loadSending() }}>刷新</Button>
          <Button variant="outline" size="sm" onClick={onClear}>清空历史</Button>
        </div>
      </div>

      {error && (
        <Card variant="subtle" className="border-destructive/40 bg-destructive/5">
          <CardContent className="py-8 text-center">
            <p className="text-destructive text-sm">{error}</p>
          </CardContent>
        </Card>
      )}

      {!error && (
        <>
          <PendingConfirmQueue apps={sending} onConfirm={confirm} />

          {/* 筛选栏：状态 chips（计数来自后端 /stats，全局）+ 关键词搜索 */}
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
                <span className="ml-1 opacity-70">({stats[f.key] ?? 0})</span>
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

          {loading && apps.length === 0 ? (
            <Card variant="subtle">
              <CardContent className="py-10 text-center">
                <p className="text-muted-foreground text-sm">加载中…</p>
              </CardContent>
            </Card>
          ) : (
            <ApplicationTable apps={apps} />
          )}

          {/* 分页器：上一页 / 下一页 + 页码信息（简洁版） */}
          <div className="flex items-center justify-center gap-4 pt-1">
            <Button variant="outline" size="sm" disabled={page <= 1 || loading} onClick={() => setPage(p => p - 1)}>
              ‹ 上一页
            </Button>
            <span className="text-sm text-muted-foreground">
              第 {page} / {totalPages} 页 · 共 {total} 条
            </span>
            <Button variant="outline" size="sm" disabled={page >= totalPages || loading} onClick={() => setPage(p => p + 1)}>
              下一页 ›
            </Button>
          </div>
        </>
      )}
    </div>
  )
}

export const Route = createFileRoute('/applications')({
  component: ApplicationsPage,
})
