import { cn } from '../lib/utils'
import { useI18n } from '../lib/i18n'

export interface VlmCost {
  visionBackend: number
  planner: number
  inboxWatcher: number
  dailyBudget: number
  fused: boolean
}

function CostBar({ label, used, budget }: { label: string; used: number; budget: number }) {
  const pct = Math.min(100, Math.round((used / budget) * 100))
  const barColor =
    pct > 85 ? 'bg-red-500' :
    pct > 60 ? 'bg-yellow-500' :
    'bg-green-500'

  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="tabular-nums">{used} / {budget}</span>
      </div>
      <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
        <div className={cn('h-1.5 rounded-full transition-all', barColor)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

interface CostMonitorProps {
  cost: VlmCost
}

/**
 * Displays three-path VLM cost bars and circuit-breaker status (AC13).
 * Three consumers (vision_backend / planner / inbox_watcher) share one daily budget.
 */
export function CostMonitor({ cost }: CostMonitorProps) {
  const { t } = useI18n()
  const total = cost.visionBackend + cost.planner + cost.inboxWatcher

  return (
    <div className="border border-border rounded-lg p-4 bg-card space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold">{t.logs.vlmCost}</h3>
        <span className={cn(
          'px-2 py-0.5 rounded text-xs font-medium',
          cost.fused ? 'bg-red-100 text-red-700' : 'bg-green-100 text-green-700',
        )}>
          {cost.fused ? `${t.logs.vlmFused}: OPEN` : 'CLOSED'}
        </span>
      </div>

      <CostBar label="vision_backend" used={cost.visionBackend} budget={cost.dailyBudget} />
      <CostBar label="planner" used={cost.planner} budget={cost.dailyBudget} />
      <CostBar label="inbox_watcher" used={cost.inboxWatcher} budget={cost.dailyBudget} />

      <div className="border-t border-border pt-2">
        <CostBar label={`${t.logs.vlmBudget} (total)`} used={total} budget={cost.dailyBudget} />
      </div>
    </div>
  )
}
