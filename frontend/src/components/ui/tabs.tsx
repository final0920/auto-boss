import { createContext, useContext, useState, type ReactNode } from 'react'
import { cn } from '../../lib/utils'

interface TabsContextValue {
  active: string
  setActive: (v: string) => void
}

const TabsContext = createContext<TabsContextValue>({ active: '', setActive: () => {} })

export function Tabs({ defaultValue, children, className }: {
  defaultValue: string
  children: ReactNode
  className?: string
}) {
  const [active, setActive] = useState(defaultValue)
  return (
    <TabsContext.Provider value={{ active, setActive }}>
      <div className={className}>{children}</div>
    </TabsContext.Provider>
  )
}

export function TabsList({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <div className={cn('flex gap-1 border-b border-border', className)}>{children}</div>
  )
}

export function TabsTrigger({ value, children }: { value: string; children: ReactNode }) {
  const { active, setActive } = useContext(TabsContext)
  return (
    <button
      onClick={() => setActive(value)}
      className={cn(
        'px-3 py-2 text-sm -mb-px border-b-2 transition-colors',
        active === value
          ? 'border-primary text-primary font-medium'
          : 'border-transparent text-muted-foreground hover:text-foreground',
      )}
    >
      {children}
    </button>
  )
}

export function TabsContent({ value, children, className }: {
  value: string
  children: ReactNode
  className?: string
}) {
  const { active } = useContext(TabsContext)
  if (active !== value) return null
  return <div className={className}>{children}</div>
}
