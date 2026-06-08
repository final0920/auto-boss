import { useDevice, type Device } from '../lib/device-context'
import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'

function StatusDot({ status }: { status: Device['status'] }) {
  const colors = { online: 'bg-green-500', offline: 'bg-gray-400', unauthorized: 'bg-red-500' }
  return <span className={cn('inline-block w-2 h-2 rounded-full shrink-0', colors[status])} />
}

export function DeviceCard({ device }: { device: Device }) {
  const { t } = useI18n()
  const { activeDevice, setActiveDevice } = useDevice()
  const isActive = activeDevice?.id === device.id

  const modeColors = { AUTO: 'text-green-700', MANUAL: 'text-blue-700', PAUSED: 'text-yellow-700' }

  return (
    <button
      onClick={() => setActiveDevice(device)}
      className={cn(
        'w-full text-left px-3 py-2 rounded-md space-y-1 transition-colors',
        isActive ? 'bg-primary/10 border border-primary' : 'hover:bg-muted border border-transparent',
      )}
    >
      <div className="flex items-center gap-2">
        <StatusDot status={device.status} />
        <span className="text-sm font-medium truncate">{device.model}</span>
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground pl-4">
        <span className={cn('font-medium', modeColors[device.mode])}>{t.device.mode[device.mode]}</span>
        <span>{device.todayApplied}/{device.dailyQuota}</span>
      </div>
    </button>
  )
}

export function DeviceSidebar() {
  const { t } = useI18n()
  const { devices } = useDevice()

  return (
    <div className="w-48 border-r border-border bg-card flex flex-col">
      <div className="px-3 py-2 border-b border-border">
        <span className="text-xs font-semibold text-muted-foreground uppercase">{t.device.title}</span>
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1">
        {devices.length === 0 ? (
          <p className="text-xs text-muted-foreground px-1 py-2">{t.device.noDevice}</p>
        ) : (
          devices.map(d => <DeviceCard key={d.id} device={d} />)
        )}
      </div>
    </div>
  )
}
