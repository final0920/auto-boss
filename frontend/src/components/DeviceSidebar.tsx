import { useDevice, type Device } from '../lib/device-context'
import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'
import { Badge } from './ui'

function StatusDot({ status }: { status: Device['status'] }) {
  const cls = {
    online: 'bg-success',
    offline: 'bg-muted-foreground',
    unauthorized: 'bg-destructive',
  }
  return (
    <span className={cn('inline-block w-2 h-2 rounded-full shrink-0', cls[status])} />
  )
}

function ModeBadge({ mode }: { mode: Device['mode'] }) {
  const variant: Record<Device['mode'], 'success' | 'default' | 'warning'> = {
    AUTO: 'success',
    MANUAL: 'default',
    PAUSED: 'warning',
  }
  const { t } = useI18n()
  return <Badge variant={variant[mode]}>{t.device.mode[mode]}</Badge>
}

export function DeviceCard({ device }: { device: Device }) {
  const { t } = useI18n()
  const { activeDevice, setActiveDevice } = useDevice()
  const isActive = activeDevice?.id === device.id

  return (
    <button
      onClick={() => setActiveDevice(device)}
      className={cn(
        'sidebar-card w-full text-left space-y-2 transition-all duration-200 active:scale-[0.98]',
        isActive
          ? 'border-primary/40 bg-primary/8 shadow-shell'
          : 'hover:border-primary/20 hover:bg-primary/5 hover:-translate-y-0.5',
      )}
    >
      <div className="flex items-center gap-2">
        <StatusDot status={device.status} />
        <span className="text-sm font-semibold truncate flex-1">{device.model}</span>
        <ModeBadge mode={device.mode} />
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground pl-4">
        <span className="font-mono">{device.serial}</span>
        <span>
          <strong className="text-foreground">{device.todayApplied}</strong>
          <span className="mx-0.5">/</span>
          {device.dailyQuota}
        </span>
      </div>
      <div className="pl-4 text-xs text-muted-foreground">
        {t.device.backend[device.backend]}
      </div>
    </button>
  )
}

export function DeviceSidebar() {
  const { t } = useI18n()
  const { devices } = useDevice()

  return (
    <div className="w-52 border-r border-border/60 bg-sidebar flex flex-col shadow-shell-sidebar">
      <div className="px-4 py-3 border-b border-border/40">
        <span className="font-serif text-sm font-semibold text-primary">
          {t.device.title}
        </span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {devices.length === 0 ? (
          <p className="text-xs text-muted-foreground px-2 py-3">{t.device.noDevice}</p>
        ) : (
          devices.map(d => <DeviceCard key={d.id} device={d} />)
        )}
      </div>
    </div>
  )
}
