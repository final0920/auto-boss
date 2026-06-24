import { createContext, useContext, useState, type ReactNode } from 'react'

export interface Device {
  id: string
  serial: string
  model: string
  status: 'online' | 'offline' | 'unauthorized'
  todayApplied: number
  dailyQuota: number
}

interface DeviceContextValue {
  devices: Device[]
  activeDevice: Device | null
  setActiveDevice: (device: Device | null) => void
  setDevices: (devices: Device[]) => void
}

const DeviceContext = createContext<DeviceContextValue | null>(null)

export function DeviceProvider({ children }: { children: ReactNode }) {
  const [devices, setDevices] = useState<Device[]>([])
  const [activeDevice, setActiveDevice] = useState<Device | null>(null)

  return (
    <DeviceContext.Provider
      value={{ devices, activeDevice, setActiveDevice, setDevices }}
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
