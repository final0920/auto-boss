import { createFileRoute, useNavigate } from '@tanstack/react-router'
import { useState } from 'react'
import { useI18n } from '../lib/i18n'
import { useDevice } from '../lib/device-context'
import { Badge } from '../components/ui'
import { InboxPanel } from '../components/InboxPanel'
import type { HrMessage } from '../components/InboxPanel'

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
    setMessages(prev =>
      prev.map(m => m.id === msg.id ? { ...m, takenOver: true, read: true } : m),
    )
    if (activeDevice) {
      setDeviceMode(activeDevice.id, 'MANUAL')
    }
    // TODO: apiPost(`/applications/${msg.applicationId}/takeover`)
    navigate({ to: '/screen' })
  }

  const markRead = (id: string) =>
    setMessages(prev => prev.map(m => m.id === id ? { ...m, read: true } : m))

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <h1 className="font-serif text-2xl font-semibold">{t.inbox.title}</h1>
        {unreadCount > 0 && (
          <Badge variant="destructive" className="rounded-full px-2 py-0.5 text-xs">
            {unreadCount}
          </Badge>
        )}
      </div>

      <InboxPanel
        messages={messages}
        onMarkRead={markRead}
        onTakeover={handleTakeover}
      />
    </div>
  )
}

export const Route = createFileRoute('/inbox')({
  component: InboxPage,
})
