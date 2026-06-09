import { cn } from '../lib/utils'
import { useI18n } from '../lib/i18n'
import { Button, Card, CardContent, CardHeader, CardTitle } from './ui'

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
    <Card
      variant="interactive"
      className={cn(isSending && 'border-warning/60 bg-warning/5')}
    >
      <CardContent className="p-3 space-y-1">
        <div className="font-serif font-semibold text-sm leading-snug">{app.jobTitle}</div>
        <div className="text-xs text-muted-foreground">{app.company}</div>
        {app.failReason && (
          <div className="text-xs text-destructive">{app.failReason}</div>
        )}
        {app.sentAt && (
          <div className="text-xs text-muted-foreground">{app.sentAt}</div>
        )}
        {isSending && onConfirmSent && onConfirmNotSent && (
          <div className="flex gap-2 pt-1">
            <Button
              size="sm"
              variant="default"
              className="h-7 px-2 text-xs"
              onClick={() => onConfirmSent(app.id)}
            >
              {t.applications.confirmSent}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 px-2 text-xs"
              onClick={() => onConfirmNotSent(app.id)}
            >
              {t.applications.confirmNotSent}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  )
}

/** SENDING queue shown prominently for crash-recovery confirm */
export function PendingConfirmQueue({ apps, onConfirmSent, onConfirmNotSent }: {
  apps: Application[]
  onConfirmSent: (id: string) => void
  onConfirmNotSent: (id: string) => void
}) {
  const { t } = useI18n()
  const sendingApps = apps.filter(a => a.status === 'SENDING')
  if (sendingApps.length === 0) return null

  return (
    <Card variant="default" className="border-warning/50 bg-warning/5">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-warning-foreground">
          {t.applications.pendingConfirm}
          <span className="ml-1.5 font-sans text-xs font-semibold text-muted-foreground">
            ({sendingApps.length})
          </span>
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0 space-y-2">
        {sendingApps.map(a => (
          <AppCard
            key={a.id}
            app={a}
            onConfirmSent={onConfirmSent}
            onConfirmNotSent={onConfirmNotSent}
          />
        ))}
      </CardContent>
    </Card>
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
      {STATUS_ORDER.map(status => {
        const lane = apps.filter(a => a.status === status)
        return (
          <div key={status} className="space-y-2">
            <div className="flex items-center gap-1.5 px-0.5">
              <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
                {t.applications.status[status]}
              </span>
              <span className="text-xs text-muted-foreground/70">({lane.length})</span>
            </div>
            <div className="space-y-2 min-h-[80px]">
              {lane.map(a => (
                <AppCard
                  key={a.id}
                  app={a}
                  onConfirmSent={onConfirmSent}
                  onConfirmNotSent={onConfirmNotSent}
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}
