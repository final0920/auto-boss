import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useState, useCallback } from 'react'
import { useDevice } from '../lib/device-context'
import { useI18n } from '../lib/i18n'
import type { Device, DeviceMode } from '../lib/device-context'
import { Button, Card, CardHeader, CardTitle, CardContent, Badge } from '../components/ui'
import { cn } from '../lib/utils'
import { apiGet, apiPost } from '../api'

// 后端 /devices/usb 返回的原始设备结构（DeviceInfo）
interface RawDevice {
  serial: string
  state: string
  transport: string
  model: string
  online: boolean
}

// 后端 /logs/quota 返回结构
interface QuotaResp {
  apply_count: number
  daily_apply_limit: number
}

// 后端 DeviceInfo → 前端 Device 适配：补 id(用 serial)、state→status 映射、填充全局模式与配额
function toDevice(r: RawDevice, mode: DeviceMode, applied: number, limit: number): Device {
  return {
    id: r.serial,
    serial: r.serial,
    model: r.model || r.serial,
    status: r.online ? 'online' : r.state === 'unauthorized' ? 'unauthorized' : 'offline',
    mode,
    backend: 'auto',
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

function ModeBadge({ mode }: { mode: Device['mode'] }) {
  const { t } = useI18n()
  const variant: Record<Device['mode'], 'success' | 'default' | 'warning'> = {
    AUTO: 'success',
    MANUAL: 'default',
    PAUSED: 'warning',
  }
  return <Badge variant={variant[mode]}>{t.device.mode[mode]}</Badge>
}

function StatusBadge({ status }: { status: Device['status'] }) {
  const { t } = useI18n()
  const variant: Record<Device['status'], 'success' | 'outline' | 'destructive'> = {
    online: 'success',
    offline: 'outline',
    unauthorized: 'destructive',
  }
  return <Badge variant={variant[status]}>{t.device.status[status]}</Badge>
}

function DeviceCard({ device }: { device: Device }) {
  const { t } = useI18n()
  const { setActiveDevice, setDeviceMode } = useDevice()

  // 切换模式：乐观更新，同步到后端
  const handleModeToggle = useCallback(async () => {
    const next = device.mode !== 'MANUAL' ? 'MANUAL' : 'AUTO'
    setDeviceMode(device.id, next)
    try {
      // 后端路径为 /devices/mode，device_id 走 body
      await apiPost('/devices/mode', { device_id: device.id, mode: next })
    } catch {
      // 失败时回滚
      setDeviceMode(device.id, device.mode)
    }
  }, [device.id, device.mode, setDeviceMode])

  return (
    <Card variant="interactive">
      <CardHeader>
        <div className="flex items-center justify-between gap-2">
          <div className="flex items-center gap-2 min-w-0">
            <StatusDot status={device.status} />
            <CardTitle className="text-base truncate">{device.model}</CardTitle>
            <span className="text-xs text-muted-foreground font-mono shrink-0">{device.serial}</span>
          </div>
          <div className="flex items-center gap-1.5 shrink-0">
            <StatusBadge status={device.status} />
            <ModeBadge mode={device.mode} />
          </div>
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
          <span>{t.device.backend[device.backend]}</span>
        </div>

        {/* 投递进度条 */}
        <div className="h-1.5 rounded-full bg-muted overflow-hidden mb-4">
          <div
            className="h-full rounded-full bg-primary transition-all duration-300"
            style={{ width: `${device.dailyQuota > 0 ? Math.min(100, (device.todayApplied / device.dailyQuota) * 100) : 0}%` }}
          />
        </div>

        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => setActiveDevice(device)}
          >
            {t.screen.title}
          </Button>
          <Button
            size="sm"
            variant="outline"
            onClick={handleModeToggle}
          >
            {device.mode !== 'MANUAL' ? t.device.mode.MANUAL : t.device.mode.AUTO}
          </Button>
        </div>
      </CardContent>
    </Card>
  )
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

    // 设备列表用 /devices/usb(仅在线真机，排除模拟器)；并行拉全局模式与配额填充卡片
    Promise.all([
      apiGet<RawDevice[]>('/devices/usb'),
      apiGet<{ mode: DeviceMode }>('/devices/mode').catch(() => ({ mode: 'AUTO' as DeviceMode })),
      apiGet<QuotaResp>('/logs/quota').catch(() => null),
    ])
      .then(([raws, modeResp, quota]) => {
        if (cancelled) return
        const applied = quota?.apply_count ?? 0
        const limit = quota?.daily_apply_limit ?? 0
        setDevices(raws.map(r => toDevice(r, modeResp.mode, applied, limit)))
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
