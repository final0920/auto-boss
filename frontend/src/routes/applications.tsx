import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'

type AppStatus = 'PENDING' | 'CLAIMED' | 'SENDING' | 'SENT' | 'FAILED'

interface Application {
  id: string
  jobTitle: string
  company: string
  status: AppStatus
  greeting: string
  failReason?: string
  sentAt?: string
}

const MOCK_APPS: Application[] = [
  { id: 'a1', jobTitle: '前端工程师', company: 'A公司', status: 'SENT', greeting: '您好，我对贵公司岗位很感兴趣', sentAt: '2026-06-08 10:23' },
  { id: 'a2', jobTitle: '全栈开发', company: 'B公司', status: 'SENDING', greeting: '您好，期待能有机会交流' },
  { id: 'a3', jobTitle: '前端开发', company: 'C公司', status: 'CLAIMED', greeting: '您好，我有5年React经验' },
  { id: 'a4', jobTitle: 'React工程师', company: 'D公司', status: 'PENDING', greeting: '' },
  { id: 'a5', jobTitle: '大前端', company: 'E公司', status: 'FAILED', greeting: '您好', failReason: '验证码触发' },
]

const STATUS_ORDER: AppStatus[] = ['PENDING', 'CLAIMED', 'SENDING', 'SENT', 'FAILED']

function AppCard({ app, onConfirmSent, onConfirmNotSent }: {
  app: Application
  onConfirmSent: (id: string) => void
  onConfirmNotSent: (id: string) => void
}) {
  const { t } = useI18n()
  const isSending = app.status === 'SENDING'

  return (
    <div className={cn(
      'border border-border rounded p-3 bg-background space-y-1 text-sm',
      isSending && 'border-yellow-400 bg-yellow-50',
    )}>
      <div className="font-medium">{app.jobTitle}</div>
      <div className="text-muted-foreground">{app.company}</div>
      {app.failReason && (
        <div className="text-xs text-destructive">{app.failReason}</div>
      )}
      {app.sentAt && (
        <div className="text-xs text-muted-foreground">{app.sentAt}</div>
      )}
      {isSending && (
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

function ApplicationsPage() {
  const { t } = useI18n()
  const [apps, setApps] = useState<Application[]>(MOCK_APPS)

  const confirmSent = (id: string) =>
    setApps(prev => prev.map(a => a.id === id ? { ...a, status: 'SENT' as AppStatus } : a))

  const confirmNotSent = (id: string) =>
    setApps(prev => prev.map(a => a.id === id ? { ...a, status: 'FAILED' as AppStatus, failReason: '人工确认未发送' } : a))

  const sendingApps = apps.filter(a => a.status === 'SENDING')

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-xl font-semibold">{t.applications.title}</h1>

      {/* SENDING pending confirm queue */}
      {sendingApps.length > 0 && (
        <div className="border border-yellow-300 rounded-lg p-4 bg-yellow-50 space-y-2">
          <h2 className="text-sm font-semibold text-yellow-800">{t.applications.pendingConfirm} ({sendingApps.length})</h2>
          <div className="space-y-2">
            {sendingApps.map(a => (
              <AppCard key={a.id} app={a} onConfirmSent={confirmSent} onConfirmNotSent={confirmNotSent} />
            ))}
          </div>
        </div>
      )}

      {/* Kanban swimlanes */}
      <div className="grid grid-cols-5 gap-3">
        {STATUS_ORDER.map(status => (
          <div key={status} className="space-y-2">
            <div className="flex items-center gap-1">
              <span className="text-xs font-semibold text-muted-foreground uppercase">{t.applications.status[status]}</span>
              <span className="text-xs text-muted-foreground">({apps.filter(a => a.status === status).length})</span>
            </div>
            <div className="space-y-2 min-h-[80px]">
              {apps
                .filter(a => a.status === status)
                .map(a => (
                  <AppCard key={a.id} app={a} onConfirmSent={confirmSent} onConfirmNotSent={confirmNotSent} />
                ))
              }
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export const Route = createFileRoute('/applications')({
  component: ApplicationsPage,
})
