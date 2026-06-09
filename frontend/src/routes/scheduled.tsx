import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { useI18n } from '../lib/i18n'
import { Button, Card, CardHeader, CardTitle, CardContent, Input } from '../components/ui'
import { apiGet, apiPut } from '../api'

interface ScheduleConfig {
  inspectIntervalMin: number
  inspectIntervalJitterMin: number
  nightStopStart: string
  nightStopEnd: string
  rateLimitWindowStart: string
  rateLimitWindowEnd: string
  enabled: boolean
}

// 后端未连通时的合理默认值
const FALLBACK: ScheduleConfig = {
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
  const [cfg, setCfg] = useState<ScheduleConfig>(FALLBACK)
  const [loading, setLoading] = useState(true)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  // 从后端加载定时配置
  useEffect(() => {
    let cancelled = false
    apiGet<ScheduleConfig>('/config/schedule')
      .then(data => {
        if (!cancelled) setCfg(data)
      })
      .catch(() => {
        // 加载失败：保留 fallback，允许用户编辑后保存
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  const update = <K extends keyof ScheduleConfig>(key: K, value: ScheduleConfig[K]) =>
    setCfg(prev => ({ ...prev, [key]: value }))

  const handleSave = async () => {
    setSaveState('saving')
    try {
      await apiPut('/config/schedule', cfg)
      setSaveState('saved')
      setTimeout(() => setSaveState('idle'), 2000)
    } catch {
      setSaveState('error')
      setTimeout(() => setSaveState('idle'), 3000)
    }
  }

  const saveLabel =
    saveState === 'saving' ? '保存中…' :
    saveState === 'saved'  ? '已保存' :
    saveState === 'error'  ? '保存失败，重试' :
    t.rules.save

  return (
    <div className="p-6 space-y-4 max-w-lg">
      <h1 className="text-2xl font-serif font-semibold text-foreground">{t.scheduled.title}</h1>

      {loading && (
        <p className="text-sm text-muted-foreground">加载配置中…</p>
      )}

      {/* 启用开关 */}
      <Card>
        <CardContent className="pt-5">
          <div className="flex items-center justify-between">
            <span className="text-sm font-medium">启用定时任务</span>
            <button
              onClick={() => update('enabled', !cfg.enabled)}
              disabled={loading}
              className={`relative w-11 h-6 rounded-full transition-colors duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 disabled:opacity-50 ${cfg.enabled ? 'bg-primary' : 'bg-muted'}`}
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
                disabled={loading}
                onChange={e => update('inspectIntervalMin', Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">随机抖动(min)</label>
              <Input
                type="number"
                value={cfg.inspectIntervalJitterMin}
                min={0}
                disabled={loading}
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
              <label className="text-xs text-muted-foreground">停止时间</label>
              <Input
                type="time"
                value={cfg.nightStopStart}
                disabled={loading}
                onChange={e => update('nightStopStart', e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">恢复时间</label>
              <Input
                type="time"
                value={cfg.nightStopEnd}
                disabled={loading}
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
                disabled={loading}
                onChange={e => update('rateLimitWindowStart', e.target.value)}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">结束</label>
              <Input
                type="time"
                value={cfg.rateLimitWindowEnd}
                disabled={loading}
                onChange={e => update('rateLimitWindowEnd', e.target.value)}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Button
        onClick={handleSave}
        disabled={loading || saveState === 'saving'}
        variant={saveState === 'error' ? 'outline' : 'default'}
      >
        {saveLabel}
      </Button>
    </div>
  )
}

export const Route = createFileRoute('/scheduled')({
  component: ScheduledPage,
})
