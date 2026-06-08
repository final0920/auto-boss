import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { useI18n } from '../lib/i18n'
import { useDevice } from '../lib/device-context'
import { cn } from '../lib/utils'

interface HrMessage {
  id: string
  company: string
  hrName: string
  content: string
  receivedAt: string
  read: boolean
  takenOver: boolean
  applicationId: string
}

const MOCK_MESSAGES: HrMessage[] = [
  {
    id: 'm1', company: 'A公司', hrName: 'HR Lisa', applicationId: 'a1',
    content: '您好，我看了您的简历，请问方便明天下午视频面试吗？',
    receivedAt: '2026-06-08 14:32', read: false, takenOver: false,
  },
  {
    id: 'm2', company: 'B公司', hrName: 'HR Wang', applicationId: 'a2',
    content: '您好，我们对您的经历很感兴趣，能否介绍一下您最近的项目？',
    receivedAt: '2026-06-08 11:15', read: true, takenOver: false,
  },
  {
    id: 'm3', company: 'C公司', hrName: 'HR Chen', applicationId: 'a3',
    content: '感谢您的投递，但目前岗位已满。',
    receivedAt: '2026-06-07 17:05', read: true, takenOver: true,
  },
]

function InboxPage() {
  const { t } = useI18n()
  const navigate = useNavigate()
  const { activeDevice, setDeviceMode } = useDevice()
  const [messages, setMessages] = useState<HrMessage[]>(MOCK_MESSAGES)

  const unreadCount = messages.filter(m => !m.read).length

  const handleTakeover = (msg: HrMessage) => {
    // Mark as taken over + read
    setMessages(prev =>
      prev.map(m => m.id === msg.id ? { ...m, takenOver: true, read: true } : m),
    )
    // Switch device to MANUAL mode
    if (activeDevice) {
      setDeviceMode(activeDevice.id, 'MANUAL')
    }
    // TODO: apiPost(`/applications/${msg.applicationId}/takeover`)
    // Navigate to screen page
    navigate({ to: '/screen' })
  }

  const markRead = (id: string) =>
    setMessages(prev => prev.map(m => m.id === id ? { ...m, read: true } : m))

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center gap-3">
        <h1 className="text-xl font-semibold">{t.inbox.title}</h1>
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
            onClick={() => markRead(msg.id)}
            className={cn(
              'border border-border rounded-lg p-4 bg-card space-y-2 cursor-pointer',
              !msg.read && 'border-primary bg-primary/5',
              msg.takenOver && 'opacity-60',
            )}
          >
            <div className="flex items-start justify-between">
              <div>
                <div className="flex items-center gap-2">
                  {!msg.read && <span className="w-2 h-2 rounded-full bg-primary inline-block" />}
                  <span className="font-medium">{msg.company}</span>
                  <span className="text-sm text-muted-foreground">{msg.hrName}</span>
                </div>
                <p className="text-sm mt-1">{msg.content}</p>
                <p className="text-xs text-muted-foreground mt-1">{msg.receivedAt}</p>
              </div>

              {!msg.takenOver && (
                <button
                  onClick={e => { e.stopPropagation(); handleTakeover(msg) }}
                  className="shrink-0 px-3 py-1.5 text-sm rounded bg-primary text-primary-foreground hover:opacity-90"
                  title={t.inbox.takeoverDesc}
                >
                  {t.inbox.takeover}
                </button>
              )}
              {msg.takenOver && (
                <span className="text-xs text-muted-foreground shrink-0">已接管</span>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export const Route = createFileRoute('/inbox')({
  component: InboxPage,
})
