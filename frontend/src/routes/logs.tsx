import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useRef, useState } from 'react'
import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'

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

function CostBar({ label, used, total }: { label: string; used: number; total: number }) {
  const pct = Math.min(100, Math.round((used / total) * 100))
  const color = pct > 85 ? 'bg-red-500' : pct > 60 ? 'bg-yellow-500' : 'bg-green-500'
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span>{label}</span>
        <span>{used}/{total}</span>
      </div>
      <div className="w-full h-2 bg-muted rounded-full">
        <div className={cn('h-2 rounded-full', color)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
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

  const levelColor = {
    info: 'text-foreground',
    warn: 'text-yellow-600',
    error: 'text-red-600',
  }

  const totalVlm = vlm.visionBackend + vlm.planner + vlm.inboxWatcher

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-semibold">{t.logs.title}</h1>

      {/* VLM cost panel */}
      <div className="border border-border rounded-lg p-4 bg-card space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold">{t.logs.vlmCost}</h2>
          {vlm.fused && (
            <span className="px-2 py-0.5 rounded bg-red-100 text-red-700 text-xs font-medium">
              {t.logs.vlmFused}: OPEN
            </span>
          )}
        </div>
        <CostBar label="vision_backend" used={vlm.visionBackend} total={vlm.dailyBudget} />
        <CostBar label="planner" used={vlm.planner} total={vlm.dailyBudget} />
        <CostBar label="inbox_watcher" used={vlm.inboxWatcher} total={vlm.dailyBudget} />
        <CostBar label={t.logs.vlmBudget + ' (total)'} used={totalVlm} total={vlm.dailyBudget} />
      </div>

      {/* Log stream */}
      <div
        ref={listRef}
        className="border border-border rounded-lg bg-black/90 p-3 h-96 overflow-auto font-mono text-xs space-y-0.5"
      >
        {logs.map(entry => (
          <div key={entry.id} className={cn('flex gap-2', levelColor[entry.level])}>
            <span className="text-muted-foreground shrink-0">{entry.ts}</span>
            {entry.source && (
              <span className="text-blue-400 shrink-0">[{entry.source}]</span>
            )}
            <span>{entry.message}</span>
          </div>
        ))}
      </div>
    </div>
  )
}

export const Route = createFileRoute('/logs')({
  component: LogsPage,
})
