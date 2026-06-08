import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'

export interface HrMessage {
  id: string
  company: string
  hrName: string
  content: string
  receivedAt: string
  read: boolean
  takenOver: boolean
  applicationId: string
}

interface TakeoverButtonProps {
  onTakeover: () => void
  disabled?: boolean
}

export function TakeoverButton({ onTakeover, disabled }: TakeoverButtonProps) {
  const { t } = useI18n()
  return (
    <button
      onClick={onTakeover}
      disabled={disabled}
      title={t.inbox.takeoverDesc}
      className={cn(
        'shrink-0 px-3 py-1.5 text-sm rounded transition-colors',
        disabled
          ? 'bg-muted text-muted-foreground cursor-not-allowed'
          : 'bg-primary text-primary-foreground hover:opacity-90',
      )}
    >
      {t.inbox.takeover}
    </button>
  )
}

interface InboxPanelProps {
  messages: HrMessage[]
  onMarkRead: (id: string) => void
  onTakeover: (msg: HrMessage) => void
}

export function InboxPanel({ messages, onMarkRead, onTakeover }: InboxPanelProps) {
  const { t } = useI18n()
  const unreadCount = messages.filter(m => !m.read).length

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3">
        <h2 className="text-base font-semibold">{t.inbox.title}</h2>
        {unreadCount > 0 && (
          <span className="px-2 py-0.5 rounded-full bg-red-500 text-white text-xs font-medium">
            {unreadCount}
          </span>
        )}
      </div>

      <div className="space-y-3">
        {messages.map(msg => (
          <div
            key={msg.id}
            onClick={() => onMarkRead(msg.id)}
            className={cn(
              'border border-border rounded-lg p-4 bg-card space-y-2 cursor-pointer transition-colors',
              !msg.read && 'border-primary bg-primary/5',
              msg.takenOver && 'opacity-60',
            )}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  {!msg.read && <span className="w-2 h-2 rounded-full bg-primary inline-block shrink-0" />}
                  <span className="font-medium text-sm">{msg.company}</span>
                  <span className="text-xs text-muted-foreground">{msg.hrName}</span>
                </div>
                <p className="text-sm mt-1 leading-relaxed">{msg.content}</p>
                <p className="text-xs text-muted-foreground mt-1">{msg.receivedAt}</p>
              </div>

              {msg.takenOver ? (
                <span className="text-xs text-muted-foreground shrink-0">已接管</span>
              ) : (
                <div onClick={e => e.stopPropagation()}>
                  <TakeoverButton onTakeover={() => onTakeover(msg)} />
                </div>
              )}
            </div>
          </div>
        ))}

        {messages.length === 0 && (
          <p className="text-sm text-muted-foreground">{t.common.loading}</p>
        )}
      </div>
    </div>
  )
}
