import { createFileRoute } from '@tanstack/react-router'
import { useCallback, useEffect, useState } from 'react'
import { useDevice } from '../lib/device-context'
import { useI18n } from '../lib/i18n'
import type { Device } from '../lib/device-context'
import { Badge, Button, Card, CardHeader, CardTitle, CardContent } from '../components/ui'
import { cn } from '../lib/utils'
import { apiGet, getPipelineStatus, startPipeline, stopPipeline } from '../api'
import type { PipelineStatus } from '../api'

// 后端 /devices/usb 返回的原始设备结构（DeviceInfo）
interface RawDevice {
  serial: string
  state: string
  transport: string
  model: string
  online: boolean
}

function toDevice(r: RawDevice, applied: number, limit: number): Device {
  return {
    id: r.serial,
    serial: r.serial,
    model: r.model || r.serial,
    status: r.online ? 'online' : r.state === 'unauthorized' ? 'unauthorized' : 'offline',
    todayApplied: applied,
    dailyQuota: limit,
  }
}

function StatusDot({ status }: { status: Device['status'] }) {
  const cls = {
    online: 'bg-success',
    offline: 'bg-muted-foreground',
    unauthorized: 'bg-destructive',
  }
  return <span className={cn('inline-block w-2 h-2 rounded-full shrink-0', cls[status])} />
}

function DeviceStatusBadge({ status }: { status: Device['status'] }) {
  const { t } = useI18n()
  const variant: Record<Device['status'], 'success' | 'outline' | 'destructive'> = {
    online: 'success',
    offline: 'outline',
    unauthorized: 'destructive',
  }
  return <Badge variant={variant[status]}>{t.device.status[status]}</Badge>
}

// ---------------------------------------------------------------------------
// Runner 控制面板：状态 / 子态 / 统计 / 启停（M3）
// ---------------------------------------------------------------------------

const RUNNER_STATE_META: Record<PipelineStatus['state'], { label: string; variant: 'success' | 'warning' | 'destructive' | 'outline' }> = {
  IDLE: { label: '未启动', variant: 'outline' },
  RUNNING: { label: '运行中', variant: 'success' },
  PAUSED_GEETEST: { label: '风控暂停', variant: 'destructive' },
  STOPPED: { label: '已停止', variant: 'outline' },
}

const STAT_LABELS: Record<string, string> = {
  collected: '采集',
  prefilter_fail: '初筛淘汰',
  screened: '已打分',
  applied: '已投递',
  dup: '已投过',
  failed: '失败',
  inbox_new: 'HR 新回复',
}

function RunnerPanel({ serial }: { serial?: string }) {
  const [st, setSt] = useState<PipelineStatus | null>(null)
  const [busy, setBusy] = useState(false)
  const [actionError, setActionError] = useState('')

  const refresh = useCallback(() => {
    getPipelineStatus().then(setSt).catch(() => {})
  }, [])

  useEffect(() => {
    refresh()
    const t = setInterval(refresh, 5000)
    return () => clearInterval(t)
  }, [refresh])

  const onStart = async () => {
    setBusy(true)
    setActionError('')
    try {
      await startPipeline(serial)
      refresh()
    } catch {
      setActionError('启动失败（可能已在运行或无在线设备）')
    } finally {
      setBusy(false)
    }
  }

  const onStop = async () => {
    setBusy(true)
    setActionError('')
    try {
      await stopPipeline()
      refresh()
    } catch {
      setActionError('停止请求失败')
    } finally {
      setBusy(false)
    }
  }

  const meta = st ? RUNNER_STATE_META[st.state] : RUNNER_STATE_META.IDLE
  const running = st?.active ?? false

  return (
    <Card>
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <CardTitle className="text-base">自动投递</CardTitle>
            <Badge variant={meta.variant}>{meta.label}</Badge>
            {st?.state === 'RUNNING' && st.sub_state === 'inbox_only' && (
              <Badge variant="warning">仅巡检（配额满/夜停）</Badge>
            )}
          </div>
          <div className="flex items-center gap-2">
            {running ? (
              <Button size="sm" variant="outline" disabled={busy} onClick={onStop}>
                {busy ? '停止中…' : '停止'}
              </Button>
            ) : (
              <Button size="sm" disabled={busy} onClick={onStart}>
                {busy ? '启动中…' : '开始自动投递'}
              </Button>
            )}
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-3">
        {st?.paused_reason && (
          <p className="text-sm text-destructive">{st.paused_reason}</p>
        )}
        {st?.last_error && st.state !== 'RUNNING' && (
          <p className="text-xs text-muted-foreground">最近错误：{st.last_error}</p>
        )}
        {actionError && <p className="text-sm text-destructive">{actionError}</p>}

        <div className="flex flex-wrap gap-x-6 gap-y-1.5 text-sm text-muted-foreground">
          <span>
            今日投递：
            <strong className="text-foreground">{st?.today_applied ?? 0}</strong>
            <span className="opacity-70"> / {st?.daily_limit ?? '—'}</span>
          </span>
          {st && Object.entries(st.stats).map(([k, v]) => (
            <span key={k}>
              {STAT_LABELS[k] ?? k}：<strong className="text-foreground">{v}</strong>
            </span>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

// ---------------------------------------------------------------------------

function DeviceCard({ device }: { device: Device }) {
  const { t } = useI18n()
  const { setActiveDevice } = useDevice()

  return (
    <Card variant="interactive">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <StatusDot status={device.status} />
            <CardTitle className="text-base truncate">{device.model}</CardTitle>
            <span className="text-xs text-muted-foreground font-mono shrink-0">{device.serial}</span>
          </div>
          <DeviceStatusBadge status={device.status} />
        </div>
      </CardHeader>
      <CardContent>
        <div className="flex gap-5 text-sm text-muted-foreground mb-4">
          <span>
            {t.device.todayApplied}：
            <strong className="text-foreground">{device.todayApplied}</strong>
          </span>
          <span>
            {t.device.dailyQuota}：
            <strong className="text-foreground">{device.dailyQuota}</strong>
          </span>
        </div>

        {/* 投递进度条 */}
        <div className="h-1.5 rounded-full bg-muted overflow-hidden mb-4">
          <div
            className="h-full rounded-full bg-primary transition-all duration-300"
            style={{ width: `${device.dailyQuota > 0 ? Math.min(100, (device.todayApplied / device.dailyQuota) * 100) : 0}%` }}
          />
        </div>

        <div className="flex gap-2">
          <Button size="sm" onClick={() => setActiveDevice(device)}>
            {t.screen.title}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
}

interface QuotaResp {
  apply_count: number
  daily_apply_limit: number
}

function IndexPage() {
  const { t } = useI18n()
  const { devices, setDevices } = useDevice()
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)

    Promise.all([
      apiGet<RawDevice[]>('/devices/usb'),
      apiGet<QuotaResp>('/logs/quota').catch(() => null),
    ])
      .then(([raws, quota]) => {
        if (cancelled) return
        const applied = quota?.apply_count ?? 0
        const limit = quota?.daily_apply_limit ?? 0
        setDevices(raws.map(r => toDevice(r, applied, limit)))
      })
      .catch(() => {
        if (!cancelled) setError('无法连接到后端，请确认服务已启动')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })

    return () => { cancelled = true }
  }, [setDevices])

  return (
    <div className="p-6 space-y-6">
      <h1 className="font-serif text-2xl font-semibold text-foreground">{t.device.title}</h1>

      {/* Runner 控制面板（投递引擎启停 + 实时统计） */}
      <RunnerPanel serial={devices[0]?.serial} />

      {loading && (
        <Card variant="subtle">
          <CardContent className="py-10 text-center">
            <p className="text-muted-foreground text-sm">加载中…</p>
          </CardContent>
        </Card>
      )}

      {!loading && error && (
        <Card variant="subtle" className="border-destructive/40 bg-destructive/5">
          <CardContent className="py-8 text-center">
            <p className="text-destructive text-sm">{error}</p>
          </CardContent>
        </Card>
      )}

      {!loading && !error && devices.length === 0 && (
        <Card variant="subtle">
          <CardContent className="py-10 text-center">
            <p className="text-muted-foreground">{t.device.noDevice}</p>
          </CardContent>
        </Card>
      )}

      {!loading && !error && devices.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {devices.map(d => <DeviceCard key={d.id} device={d} />)}
        </div>
      )}
    </div>
  )
}

export const Route = createFileRoute('/')({
  component: IndexPage,
})
