import { cn } from '../lib/utils'
import { useI18n } from '../lib/i18n'
import { Card, CardHeader, CardTitle, CardContent, Badge } from './ui'

export interface VlmCost {
  visionBackend: number
  planner: number
  inboxWatcher: number
  dailyBudget: number
  fused: boolean
}

function CostRow({
  label,
  used,
  budget,
}: {
  label: string
  used: number
  budget: number
}) {
  const pct = Math.min(100, Math.round((used / budget) * 100))
  const barVariant =
    pct > 85 ? 'bg-destructive' :
    pct > 60 ? 'bg-warning' :
    'bg-primary'

  return (
    <div className="space-y-1.5 group">
      <div className="flex justify-between text-xs">
        <span className="text-muted-foreground font-mono">{label}</span>
        <span className="tabular-nums font-mono">
          {used} / {budget}
          {/* hover 时显示百分比 */}
          <span className="ml-1.5 opacity-0 group-hover:opacity-60 transition-opacity text-muted-foreground">
            {pct}%
          </span>
        </span>
      </div>
      <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
        <div
          className={cn('h-1.5 rounded-full transition-all duration-300', barVariant)}
          style={{ width: `${pct}%` }}
        />
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
  const totalPct = Math.min(100, Math.round((total / cost.dailyBudget) * 100))

  const circuitVariant =
    cost.fused ? 'destructive' :
    totalPct > 60 ? 'warning' :
    'success'

  const circuitLabel = cost.fused
    ? `${t.logs.vlmFused}: OPEN`
    : 'CLOSED'

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="text-base">{t.logs.vlmCost}</CardTitle>
          <Badge variant={circuitVariant}>{circuitLabel}</Badge>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        <CostRow label="vision_backend" used={cost.visionBackend} budget={cost.dailyBudget} />
        <CostRow label="planner" used={cost.planner} budget={cost.dailyBudget} />
        <CostRow label="inbox_watcher" used={cost.inboxWatcher} budget={cost.dailyBudget} />
        <div className="border-t border-border/60 pt-3">
          <CostRow label={`${t.logs.vlmBudget} (total)`} used={total} budget={cost.dailyBudget} />
        </div>
      </CardContent>
    </Card>
  )
}
