import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { useI18n } from '../lib/i18n'

interface ScheduleConfig {
  inspectIntervalMin: number
  inspectIntervalJitterMin: number
  nightStopStart: string
  nightStopEnd: string
  rateLimitWindowStart: string
  rateLimitWindowEnd: string
  enabled: boolean
}

const DEFAULT: ScheduleConfig = {
  inspectIntervalMin: 3,
  inspectIntervalJitterMin: 2,
  nightStopStart: '23:00',
  nightStopEnd: '08:00',
  rateLimitWindowStart: '09:00',
  rateLimitWindowEnd: '22:00',
  enabled: true,
}

function ScheduledPage() {
  const { t } = useI18n()
  const [cfg, setCfg] = useState<ScheduleConfig>(DEFAULT)
  const [saved, setSaved] = useState(false)

  const update = <K extends keyof ScheduleConfig>(key: K, value: ScheduleConfig[K]) =>
    setCfg(prev => ({ ...prev, [key]: value }))

  const handleSave = () => {
    // TODO: apiPut('/config/schedule', cfg)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="p-6 space-y-6 max-w-lg">
      <h1 className="text-xl font-semibold">{t.scheduled.title}</h1>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium">启用定时任务</span>
          <button
            onClick={() => update('enabled', !cfg.enabled)}
            className={`w-10 h-5 rounded-full transition-colors ${cfg.enabled ? 'bg-primary' : 'bg-muted'}`}
          >
            <span className={`block w-4 h-4 rounded-full bg-white mx-0.5 transition-transform ${cfg.enabled ? 'translate-x-5' : 'translate-x-0'}`} />
          </button>
        </div>
      </section>

      <section className="space-y-2">
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

      <section className="space-y-2">
        <label className="text-sm font-medium">{t.scheduled.nightStop}</label>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground">停止时间</label>
            <input
              type="time" value={cfg.nightStopStart}
              onChange={e => update('nightStopStart', e.target.value)}
              className="w-full rounded border border-border px-2 py-1 text-sm bg-background"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">恢复时间</label>
            <input
              type="time" value={cfg.nightStopEnd}
              onChange={e => update('nightStopEnd', e.target.value)}
              className="w-full rounded border border-border px-2 py-1 text-sm bg-background"
            />
          </div>
        </div>
      </section>

      <section className="space-y-2">
        <label className="text-sm font-medium">{t.scheduled.rateLimitWindow}</label>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground">开始</label>
            <input
              type="time" value={cfg.rateLimitWindowStart}
              onChange={e => update('rateLimitWindowStart', e.target.value)}
              className="w-full rounded border border-border px-2 py-1 text-sm bg-background"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">结束</label>
            <input
              type="time" value={cfg.rateLimitWindowEnd}
              onChange={e => update('rateLimitWindowEnd', e.target.value)}
              className="w-full rounded border border-border px-2 py-1 text-sm bg-background"
            />
          </div>
        </div>
      </section>

      <button
        onClick={handleSave}
        className="px-4 py-2 rounded bg-primary text-primary-foreground hover:opacity-90 text-sm"
      >
        {saved ? '已保存 ✓' : t.rules.save}
      </button>
    </div>
  )
}

export const Route = createFileRoute('/scheduled')({
  component: ScheduledPage,
})
