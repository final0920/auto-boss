import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

export type DeviceMode = 'AUTO' | 'MANUAL' | 'PAUSED'

export interface Device {
  id: string
  serial: string
  model: string
  status: 'online' | 'offline' | 'unauthorized'
  mode: DeviceMode
  backend: 'uia' | 'vision' | 'auto'
  todayApplied: number
  dailyQuota: number
}

interface DeviceContextValue {
  devices: Device[]
  activeDevice: Device | null
  setActiveDevice: (device: Device | null) => void
  setDevices: (devices: Device[]) => void
  setDeviceMode: (deviceId: string, mode: DeviceMode) => void
  updateDevice: (device: Device) => void
}

const DeviceContext = createContext<DeviceContextValue | null>(null)

export function DeviceProvider({ children }: { children: ReactNode }) {
  const [devices, setDevices] = useState<Device[]>([])
  const [activeDevice, setActiveDevice] = useState<Device | null>(null)

  const setDeviceMode = useCallback((deviceId: string, mode: DeviceMode) => {
    setDevices(prev =>
      prev.map(d => (d.id === deviceId ? { ...d, mode } : d)),
    )
    setActiveDevice(prev => (prev?.id === deviceId ? { ...prev, mode } : prev))
  }, [])

  const updateDevice = useCallback((device: Device) => {
    setDevices(prev => prev.map(d => (d.id === device.id ? device : d)))
    setActiveDevice(prev => (prev?.id === device.id ? device : prev))
  }, [])

  return (
    <DeviceContext.Provider
      value={{ devices, activeDevice, setActiveDevice, setDevices, setDeviceMode, updateDevice }}
    >
      {children}
    </DeviceContext.Provider>
  )
}

export function useDevice() {
  const ctx = useContext(DeviceContext)
  if (!ctx) throw new Error('useDevice must be used within DeviceProvider')
  return ctx
}
