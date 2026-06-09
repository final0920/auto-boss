import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'
import { Card, CardHeader, CardTitle, CardContent, Badge } from '../components/ui'

interface LogEntry {
  id: string
  ts: string
  level: 'info' | 'warn' | 'error'
  message: string
  source?: string
}

interface VlmCost {
  visionBackend: number
  planner: number
  inboxWatcher: number
  dailyBudget: number
  fused: boolean
}

const MOCK_LOGS: LogEntry[] = [
  { id: '1', ts: '10:23:01', level: 'info', message: 'Pipeline started', source: 'pipeline' },
  { id: '2', ts: '10:23:05', level: 'info', message: 'Collected 24 jobs', source: 'collector' },
  { id: '3', ts: '10:23:12', level: 'info', message: 'Screener: job j42 score=87 -> CLAIMED', source: 'screener' },
  { id: '4', ts: '10:23:45', level: 'info', message: 'Dispatcher: sent greeting for j42', source: 'dispatcher' },
  { id: '5', ts: '10:25:00', level: 'warn', message: 'Backend switched: uia->vision (hit rate 0.61)', source: 'backend' },
  { id: '6', ts: '10:30:00', level: 'error', message: 'VLM budget exceeded (150 calls/day), circuit breaker OPEN', source: 'rate_limiter' },
]

const MOCK_VLM: VlmCost = {
  visionBackend: 48,
  planner: 62,
  inboxWatcher: 12,
  dailyBudget: 150,
  fused: false,
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
  const [logs, _setLogs] = useState<LogEntry[]>(MOCK_LOGS)
  const [vlm] = useState<VlmCost>(MOCK_VLM)
  const listRef = useRef<HTMLDivElement>(null)

  // SSE log stream
  useEffect(() => {
    // TODO: replace mock with real SSE
    // const cleanup = openSse('/api/events/logs', e => {
    //   const entry = JSON.parse(e.data) as LogEntry
    //   setLogs(prev => [...prev.slice(-500), entry])
    // })
    // return cleanup
  }, [])

  // Auto-scroll
  useEffect(() => {
    listRef.current?.scrollTo({ top: listRef.current.scrollHeight, behavior: 'smooth' })
  }, [logs])

  const totalVlm = vlm.visionBackend + vlm.planner + vlm.inboxWatcher
  const totalPct = Math.min(100, Math.round((totalVlm / vlm.dailyBudget) * 100))

  return (
    <div className="p-6 space-y-4">
      <h1 className="text-2xl font-serif font-semibold text-foreground">{t.logs.title}</h1>

      {/* VLM 成本面板 */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base">{t.logs.vlmCost}</CardTitle>
            <Badge variant={vlm.fused ? 'destructive' : totalPct > 60 ? 'warning' : 'success'}>
              {vlm.fused ? `${t.logs.vlmFused}: OPEN` : 'CLOSED'}
            </Badge>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          <CostRow label="vision_backend" used={vlm.visionBackend} total={vlm.dailyBudget} />
          <CostRow label="planner" used={vlm.planner} total={vlm.dailyBudget} />
          <CostRow label="inbox_watcher" used={vlm.inboxWatcher} total={vlm.dailyBudget} />
          <div className="border-t border-border/60 pt-3">
            <CostRow label={`${t.logs.vlmBudget} (total)`} used={totalVlm} total={vlm.dailyBudget} />
          </div>
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
            {logs.map(entry => (
              <div key={entry.id} className={cn('flex gap-2', levelStyle[entry.level])}>
                <span className="text-muted-foreground shrink-0 tabular-nums">{entry.ts}</span>
                {entry.source && (
                  <span className="text-blue-400 shrink-0">[{entry.source}]</span>
                )}
                <span>{entry.message}</span>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  )
}

export const Route = createFileRoute('/logs')({
  component: LogsPage,
})
