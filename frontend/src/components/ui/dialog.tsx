import { type ReactNode } from 'react'
import { cn } from '../../lib/utils'

interface DialogProps {
  open: boolean
  onClose: () => void
  title?: string
  children: ReactNode
  className?: string
}

export function Dialog({ open, onClose, title, children, className }: DialogProps) {
  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      {/* Panel */}
      <div className={cn('relative z-10 bg-card rounded-lg shadow-lg border border-border min-w-80 max-w-lg w-full mx-4', className)}>
        {title && (
          <div className="flex items-center justify-between px-4 py-3 border-b border-border">
            <span className="font-semibold text-sm">{title}</span>
            <button onClick={onClose} className="text-muted-foreground hover:text-foreground text-lg leading-none">&times;</button>
          </div>
        )}
        <div className="p-4">{children}</div>
      </div>
    </div>
  )
}
