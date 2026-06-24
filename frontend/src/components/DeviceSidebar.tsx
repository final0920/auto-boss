import { useDevice, type Device } from '../lib/device-context'
import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'

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
      </div>
      <div className="flex items-center justify-between text-xs text-muted-foreground pl-4">
        <span className="font-mono">{device.serial}</span>
        <span>
          <strong className="text-foreground">{device.todayApplied}</strong>
          <span className="mx-0.5">/</span>
          {device.dailyQuota}
        </span>
      </div>
    </button>
  )
}

export function DeviceSidebar() {
  const { t } = useI18n()
  const { devices } = useDevice()

  return (
    <div className="w-52 border-r border-border/60 bg-sidebar flex flex-col shadow-shell-sidebar shrink-0">
      <div className="px-4 py-3 border-b border-border/40 flex items-center gap-2">
        <span className="font-serif text-sm font-semibold text-primary flex-1">
          {t.device.title}
        </span>
        {/* 在线设备数角标 */}
        {devices.length > 0 && (
          <span className="text-[10px] tabular-nums font-mono text-muted-foreground">
            {devices.filter(d => d.status === 'online').length}/{devices.length}
          </span>
        )}
      </div>
      <div className="flex-1 overflow-y-auto p-2 space-y-1.5">
        {devices.length === 0 ? (
          /* 空态：居中图标 + 提示文字 */
          <div className="flex flex-col items-center justify-center gap-2 py-8 text-center">
            <div className="w-10 h-10 rounded-full bg-muted flex items-center justify-center text-muted-foreground/50">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="5" y="2" width="14" height="20" rx="2" />
                <line x1="12" y1="18" x2="12" y2="18.01" strokeWidth="2" strokeLinecap="round" />
              </svg>
            </div>
            <p className="text-xs text-muted-foreground leading-snug px-2">{t.device.noDevice}</p>
          </div>
        ) : (
          devices.map(d => <DeviceCard key={d.id} device={d} />)
        )}
      </div>
    </div>
  )
}
