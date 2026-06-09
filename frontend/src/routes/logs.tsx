import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'
import { Card, CardHeader, CardTitle, CardContent, Badge } from '../components/ui'
import { apiGet } from '../api'
import { openSse } from '../lib/sse'

interface LogEntry {
  id: string
  ts: string
  level: 'info' | 'warn' | 'error'
  message: string
  source?: string
}

// 后端 /logs/quota 返回的配额快照字段
interface QuotaSnapshot {
  vision_backend: number
  planner: number
  inbox_watcher: number
  daily_budget: number
  fused: boolean
}

// 内部展示用结构，保持与原 VlmCost 命名一致方便渲染复用
interface VlmCost {
  visionBackend: number
  planner: number
  inboxWatcher: number
  dailyBudget: number
  fused: boolean
}

// 将后端 quota 快照映射为前端展示结构
function quotaToVlm(q: QuotaSnapshot): VlmCost {
  return {
    visionBackend: q.vision_backend,
    planner: q.planner,
    inboxWatcher: q.inbox_watcher,
    dailyBudget: q.daily_budget,
    fused: q.fused,
  }
}

function CostRow({ label, used, total }: { label: string; used: number; total: number }) {
  const pct = Math.min(100, Math.round((used / total) * 100))
  const barVariant =
    pct > 85 ? 'bg-destructive' :
    pct > 60 ? 'bg-warning' :
    'bg-primary'

  return (
    <div className="space-y-1.5">
      <div className="flex justify-between text-xs">
        <span className="font-mono text-muted-foreground">{label}</span>
        <span className="font-mono tabular-nums">{used}/{total}</span>
      </div>
      <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
        <div className={cn('h-1.5 rounded-full transition-all duration-300', barVariant)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

const levelStyle: Record<LogEntry['level'], string> = {
  info: 'text-foreground',
  warn: 'text-yellow-600',
  error: 'text-destructive',
}

function LogsPage() {
  const { t } = useI18n()
  const [logs, setLogs] = useState<LogEntry[]>([])
  const [vlm, setVlm] = useState<VlmCost | null>(null)
  const [vlmError, setVlmError] = useState(false)
  const listRef = useRef<HTMLDivElement>(null)

  // 初始加载配额，接口改为 /logs/quota
  useEffect(() => {
    apiGet<QuotaSnapshot>('/logs/quota')
      .then(q => setVlm(quotaToVlm(q)))
      .catch(() => setVlmError(true))
  }, [])

  // SSE 日志流：路径改为 /api/logs/stream
  useEffect(() => {
    const cleanup = openSse('/api/logs/stream', e => {
      try {
        const entry = JSON.parse(e.data) as LogEntry
        setLogs(prev => [...prev.slice(-500), entry])
      } catch {
        // 忽略格式异常的推送
      }
    })
    return cleanup
  }, [])

  // 轮询配额：后端无 SSE vlm-cost 端点，改为每 5s 拉取一次
  useEffect(() => {
    const timer = setInterval(() => {
      apiGet<QuotaSnapshot>('/logs/quota')
        .then(q => {
          setVlm(quotaToVlm(q))
          setVlmError(false)
        })
        .catch(() => {
          // 轮询失败不重置已有数据，只在初始失败时显示错误态
        })
    }, 5000)
    return () => clearInterval(timer)
  }, [])

  // 新日志时自动滚到底部
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [logs])

  const totalVlm = vlm ? vlm.visionBackend + vlm.planner + vlm.inboxWatcher : 0
  const totalPct = vlm ? Math.min(100, Math.round((totalVlm / vlm.dailyBudget) * 100)) : 0

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-serif font-semibold text-foreground">{t.logs.title}</h1>

      {/* VLM 成本面板 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">{t.logs.vlmCost}</CardTitle>
            {vlm && (
              <Badge variant={vlm.fused ? 'destructive' : totalPct > 60 ? 'warning' : 'success'}>
                {vlm.fused ? `${t.logs.vlmFused}: OPEN` : 'CLOSED'}
              </Badge>
            )}
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {vlmError && (
            <p className="text-xs text-muted-foreground">VLM 成本数据暂不可用</p>
          )}
          {!vlmError && !vlm && (
            <p className="text-xs text-muted-foreground">加载中…</p>
          )}
          {vlm && (
            <>
              <CostRow label="vision_backend" used={vlm.visionBackend} total={vlm.dailyBudget} />
              <CostRow label="planner" used={vlm.planner} total={vlm.dailyBudget} />
              <CostRow label="inbox_watcher" used={vlm.inboxWatcher} total={vlm.dailyBudget} />
              <div className="border-t border-border/60 pt-3">
                <CostRow label={`${t.logs.vlmBudget} (total)`} used={totalVlm} total={vlm.dailyBudget} />
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* 日志流 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">运行日志</CardTitle>
        </CardHeader>
        <CardContent className="p-0">
          <div
            ref={listRef}
            className="rounded-b-2xl bg-[#0d1117] p-4 h-96 overflow-auto font-mono text-xs space-y-1 border-t border-border/60"
          >
            {logs.length === 0 ? (
              <span className="text-muted-foreground">等待日志流…</span>
            ) : (
              logs.map(entry => (
                <div key={entry.id} className={cn('flex gap-2', levelStyle[entry.level])}>
                  <span className="text-muted-foreground shrink-0 tabular-nums">{entry.ts}</span>
                  {entry.source && (
                    <span className="text-blue-400 shrink-0">[{entry.source}]</span>
                  )}
                  <span>{entry.message}</span>
                </div>
              ))
            )}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export const Route = createFileRoute('/logs')({
  component: LogsPage,
})
