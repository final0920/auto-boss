import { createFileRoute } from '@tanstack/react-router'
import { useEffect } from 'react'
import { useDevice } from '../lib/device-context'
import { useI18n } from '../lib/i18n'
import type { Device } from '../lib/device-context'

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

function ModeBadge({ mode }: { mode: Device['mode'] }) {
  const colors = {
    AUTO: 'bg-green-100 text-green-800',
    MANUAL: 'bg-blue-100 text-blue-800',
    PAUSED: 'bg-yellow-100 text-yellow-800',
  }
  return (
    <span className={`px-2 py-0.5 rounded text-xs font-medium ${colors[mode]}`}>{mode}</span>
  )
}

function StatusDot({ status }: { status: Device['status'] }) {
  const colors = {
    online: 'bg-green-500',
    offline: 'bg-gray-400',
    unauthorized: 'bg-red-500',
  }
  return <span className={`inline-block w-2 h-2 rounded-full ${colors[status]}`} />
}

function DeviceCard({ device }: { device: Device }) {
  const { t } = useI18n()
  const { setActiveDevice, setDeviceMode } = useDevice()

  return (
    <div className="border border-border rounded-lg p-4 bg-card space-y-3">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <StatusDot status={device.status} />
          <span className="font-medium">{device.model}</span>
          <span className="text-xs text-muted-foreground font-mono">{device.serial}</span>
        </div>
        <ModeBadge mode={device.mode} />
      </div>

      <div className="flex gap-4 text-sm text-muted-foreground">
        <span>{t.device.todayApplied}: <strong className="text-foreground">{device.todayApplied}</strong></span>
        <span>{t.device.dailyQuota}: <strong className="text-foreground">{device.dailyQuota}</strong></span>
        <span>{t.device.backend[device.backend]}</span>
      </div>

      <div className="flex gap-2">
        <button
          onClick={() => setActiveDevice(device)}
          className="px-3 py-1 text-xs rounded bg-primary text-primary-foreground hover:opacity-90"
        >
          {t.screen.title}
        </button>
        {device.mode !== 'MANUAL' ? (
          <button
            onClick={() => setDeviceMode(device.id, 'MANUAL')}
            className="px-3 py-1 text-xs rounded border border-border hover:bg-muted"
          >
            {t.device.mode.MANUAL}
          </button>
        ) : (
          <button
            onClick={() => setDeviceMode(device.id, 'AUTO')}
            className="px-3 py-1 text-xs rounded border border-border hover:bg-muted"
          >
            {t.device.mode.AUTO}
          </button>
        )}
      </div>
    </div>
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
    <div className="p-6 space-y-4">
      <h1 className="text-xl font-semibold">{t.device.title}</h1>
      {devices.length === 0 ? (
        <p className="text-muted-foreground">{t.device.noDevice}</p>
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
