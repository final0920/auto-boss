import { useState } from 'react'
import { useI18n } from '../lib/i18n'
import { Button, Card, CardHeader, CardTitle, CardContent, Input } from './ui'

export interface ScheduleConfig {
  inspectIntervalMin: number
  inspectIntervalJitterMin: number
  nightStopStart: string
  nightStopEnd: string
  rateLimitWindowStart: string
  rateLimitWindowEnd: string
  enabled: boolean
}

interface CronEditorProps {
  initialConfig: ScheduleConfig
  onSave: (cfg: ScheduleConfig) => Promise<void> | void
}

export function CronEditor({ initialConfig, onSave }: CronEditorProps) {
  const { t } = useI18n()
  const [cfg, setCfg] = useState<ScheduleConfig>(initialConfig)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const update = <K extends keyof ScheduleConfig>(key: K, value: ScheduleConfig[K]) =>
    setCfg(prev => ({ ...prev, [key]: value }))

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave(cfg)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-4 max-w-lg">
      {/* 启用开关 */}
      <Card>
        <CardContent className="pt-5">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">启用定时任务</span>
            <button
              onClick={() => update('enabled', !cfg.enabled)}
              className={`relative w-11 h-6 rounded-full transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 ${cfg.enabled ? 'bg-primary' : 'bg-muted'}`}
              aria-checked={cfg.enabled}
              role="switch"
            >
              <span
                className={`absolute top-1 w-4 h-4 rounded-full bg-card shadow-sm transition-transform duration-200 ${cfg.enabled ? 'translate-x-6' : 'translate-x-1'}`}
              />
            </button>
          </div>
        </CardContent>
      </Card>

      {/* 检查间隔 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.scheduled.inspectInterval}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">间隔(min)</label>
              <Input
                type="number"
                value={cfg.inspectIntervalMin}
                min={1}
                onChange={e => update('inspectIntervalMin', Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">随机抖动(min)</label>
              <Input
                type="number"
                value={cfg.inspectIntervalJitterMin}
                min={0}
                onChange={e => update('inspectIntervalJitterMin', Number(e.target.value))}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 夜间停止 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.scheduled.nightStop}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">停止</label>
              <Input
                type="time"
                value={cfg.nightStopStart}
                onChange={e => update('nightStopStart', e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">恢复</label>
              <Input
                type="time"
                value={cfg.nightStopEnd}
                onChange={e => update('nightStopEnd', e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* 限速窗口 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.scheduled.rateLimitWindow}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">开始</label>
              <Input
                type="time"
                value={cfg.rateLimitWindowStart}
                onChange={e => update('rateLimitWindowStart', e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">结束</label>
              <Input
                type="time"
                value={cfg.rateLimitWindowEnd}
                onChange={e => update('rateLimitWindowEnd', e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Button onClick={handleSave} disabled={saving}>
        {saved ? '已保存' : saving ? '保存中...' : t.rules.save}
      </Button>
    </div>
  )
}
