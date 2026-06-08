import { useState } from 'react'
import { useI18n } from '../lib/i18n'

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
    <div className="space-y-5 max-w-lg">
      {/* Enable toggle */}
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium">启用定时任务</span>
        <button
          onClick={() => update('enabled', !cfg.enabled)}
          className={`relative w-10 h-5 rounded-full transition-colors ${cfg.enabled ? 'bg-primary' : 'bg-muted'}`}
        >
          <span className={`absolute top-0.5 w-4 h-4 rounded-full bg-white shadow transition-transform ${cfg.enabled ? 'translate-x-5' : 'translate-x-0.5'}`} />
        </button>
      </div>

      {/* Inspect interval */}
      <section className="space-y-1.5">
        <label className="text-sm font-medium">{t.scheduled.inspectInterval}</label>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground">间隔(min)</label>
            <input
              type="number" value={cfg.inspectIntervalMin} min={1}
              onChange={e => update('inspectIntervalMin', Number(e.target.value))}
              className="w-full rounded border border-border px-2 py-1 text-sm bg-background"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">随机抖动(min)</label>
            <input
              type="number" value={cfg.inspectIntervalJitterMin} min={0}
              onChange={e => update('inspectIntervalJitterMin', Number(e.target.value))}
              className="w-full rounded border border-border px-2 py-1 text-sm bg-background"
            />
          </div>
        </div>
      </section>

      {/* Night stop */}
      <section className="space-y-1.5">
        <label className="text-sm font-medium">{t.scheduled.nightStop}</label>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground">停止</label>
            <input type="time" value={cfg.nightStopStart}
              onChange={e => update('nightStopStart', e.target.value)}
              className="w-full rounded border border-border px-2 py-1 text-sm bg-background"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">恢复</label>
            <input type="time" value={cfg.nightStopEnd}
              onChange={e => update('nightStopEnd', e.target.value)}
              className="w-full rounded border border-border px-2 py-1 text-sm bg-background"
            />
          </div>
        </div>
      </section>

      {/* Rate limit window */}
      <section className="space-y-1.5">
        <label className="text-sm font-medium">{t.scheduled.rateLimitWindow}</label>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground">开始</label>
            <input type="time" value={cfg.rateLimitWindowStart}
              onChange={e => update('rateLimitWindowStart', e.target.value)}
              className="w-full rounded border border-border px-2 py-1 text-sm bg-background"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">结束</label>
            <input type="time" value={cfg.rateLimitWindowEnd}
              onChange={e => update('rateLimitWindowEnd', e.target.value)}
              className="w-full rounded border border-border px-2 py-1 text-sm bg-background"
            />
          </div>
        </div>
      </section>

      <button
        onClick={handleSave}
        disabled={saving}
        className="px-4 py-2 rounded bg-primary text-primary-foreground hover:opacity-90 text-sm disabled:opacity-50"
      >
        {saved ? '已保存 ✓' : saving ? '保存中...' : t.rules.save}
      </button>
    </div>
  )
}
