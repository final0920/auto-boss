import { createFileRoute } from '@tanstack/react-router'
import { useEffect } from 'react'
import { useDevice } from '../lib/device-context'
import { useI18n } from '../lib/i18n'
import type { Device } from '../lib/device-context'
import { Button, Card, CardHeader, CardTitle, CardContent, Badge } from '../components/ui'
import { cn } from '../lib/utils'

// Mock data for development
const MOCK_DEVICES: Device[] = [
  {
    id: 'dev1',
    serial: 'ABCD1234',
    model: 'Pixel 7',
    status: 'online',
    mode: 'AUTO',
    backend: 'uia',
    todayApplied: 12,
    dailyQuota: 150,
  },
]

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

        {/* progress bar */}
        <div className="h-1.5 rounded-full bg-muted overflow-hidden mb-4">
          <div
            className="h-full rounded-full bg-primary transition-all duration-300"
            style={{ width: `${Math.min(100, (device.todayApplied / device.dailyQuota) * 100)}%` }}
          />
        </div>

        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => setActiveDevice(device)}
          >
            {t.screen.title}
          </Button>
          {device.mode !== 'MANUAL' ? (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setDeviceMode(device.id, 'MANUAL')}
            >
              {t.device.mode.MANUAL}
            </Button>
          ) : (
            <Button
              size="sm"
              variant="outline"
              onClick={() => setDeviceMode(device.id, 'AUTO')}
            >
              {t.device.mode.AUTO}
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  )
}

function IndexPage() {
  const { t } = useI18n()
  const { devices, setDevices } = useDevice()

  useEffect(() => {
    // TODO: replace mock with apiGet<Device[]>('/devices')
    setDevices(MOCK_DEVICES)
  }, [setDevices])

  return (
    <div className="p-6 space-y-6">
      <h1 className="font-serif text-2xl font-semibold text-foreground">{t.device.title}</h1>
      {devices.length === 0 ? (
        <Card variant="subtle">
          <CardContent className="py-10 text-center">
            <p className="text-muted-foreground">{t.device.noDevice}</p>
          </CardContent>
        </Card>
      ) : (
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
