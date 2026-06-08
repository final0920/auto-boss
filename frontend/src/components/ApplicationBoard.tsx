import { cn } from '../lib/utils'
import { useI18n } from '../lib/i18n'

export type AppStatus = 'PENDING' | 'CLAIMED' | 'SENDING' | 'SENT' | 'FAILED'

export interface Application {
  id: string
  jobTitle: string
  company: string
  status: AppStatus
  greeting: string
  failReason?: string
  sentAt?: string
}

const STATUS_ORDER: AppStatus[] = ['PENDING', 'CLAIMED', 'SENDING', 'SENT', 'FAILED']

interface AppCardProps {
  app: Application
  onConfirmSent?: (id: string) => void
  onConfirmNotSent?: (id: string) => void
}

function AppCard({ app, onConfirmSent, onConfirmNotSent }: AppCardProps) {
  const { t } = useI18n()
  const isSending = app.status === 'SENDING'

  return (
    <div className={cn(
      'border border-border rounded p-3 bg-background space-y-1 text-sm',
      isSending && 'border-yellow-400 bg-yellow-50',
    )}>
      <div className="font-medium text-sm">{app.jobTitle}</div>
      <div className="text-xs text-muted-foreground">{app.company}</div>
      {app.failReason && <div className="text-xs text-destructive">{app.failReason}</div>}
      {app.sentAt && <div className="text-xs text-muted-foreground">{app.sentAt}</div>}
      {isSending && onConfirmSent && onConfirmNotSent && (
        <div className="flex gap-2 pt-1">
          <button
            onClick={() => onConfirmSent(app.id)}
            className="px-2 py-1 text-xs rounded bg-green-600 text-white hover:bg-green-700"
          >
            {t.applications.confirmSent}
          </button>
          <button
            onClick={() => onConfirmNotSent(app.id)}
            className="px-2 py-1 text-xs rounded bg-red-600 text-white hover:bg-red-700"
          >
            {t.applications.confirmNotSent}
          </button>
        </div>
      )}
    </div>
  )
}

/** SENDING queue — shown prominently for crash-recovery confirm (AC8) */
export function PendingConfirmQueue({ apps, onConfirmSent, onConfirmNotSent }: {
  apps: Application[]
  onConfirmSent: (id: string) => void
  onConfirmNotSent: (id: string) => void
}) {
  const { t } = useI18n()
  const sendingApps = apps.filter(a => a.status === 'SENDING')
  if (sendingApps.length === 0) return null

  return (
    <div className="border border-yellow-300 rounded-lg p-4 bg-yellow-50 space-y-2">
      <h2 className="text-sm font-semibold text-yellow-800">
        {t.applications.pendingConfirm} ({sendingApps.length})
      </h2>
      <div className="space-y-2">
        {sendingApps.map(a => (
          <AppCard key={a.id} app={a} onConfirmSent={onConfirmSent} onConfirmNotSent={onConfirmNotSent} />
        ))}
      </div>
    </div>
  )
}

export function ApplicationBoard({ apps, onConfirmSent, onConfirmNotSent }: {
  apps: Application[]
  onConfirmSent: (id: string) => void
  onConfirmNotSent: (id: string) => void
}) {
  const { t } = useI18n()

  return (
    <div className="grid grid-cols-5 gap-3">
      {STATUS_ORDER.map(status => (
        <div key={status} className="space-y-2">
          <div className="flex items-center gap-1">
            <span className="text-xs font-semibold text-muted-foreground uppercase">
              {t.applications.status[status]}
            </span>
            <span className="text-xs text-muted-foreground">
              ({apps.filter(a => a.status === status).length})
            </span>
          </div>
          <div className="space-y-2 min-h-[80px]">
            {apps
              .filter(a => a.status === status)
              .map(a => (
                <AppCard key={a.id} app={a} onConfirmSent={onConfirmSent} onConfirmNotSent={onConfirmNotSent} />
              ))}
          </div>
        </div>
      ))}
    </div>
  )
}
