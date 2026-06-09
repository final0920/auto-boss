import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { useI18n } from '../lib/i18n'
import { ApplicationBoard, PendingConfirmQueue } from '../components/ApplicationBoard'
import type { Application, AppStatus } from '../components/ApplicationBoard'

const MOCK_APPS: Application[] = [
  { id: 'a1', jobTitle: '前端工程师', company: 'A公司', status: 'SENT', greeting: '您好，我对贵公司岗位很感兴趣', sentAt: '2026-06-08 10:23' },
  { id: 'a2', jobTitle: '全栈开发', company: 'B公司', status: 'SENDING', greeting: '您好，期待能有机会交流' },
  { id: 'a3', jobTitle: '前端开发', company: 'C公司', status: 'CLAIMED', greeting: '您好，我有5年React经验' },
  { id: 'a4', jobTitle: 'React工程师', company: 'D公司', status: 'PENDING', greeting: '' },
  { id: 'a5', jobTitle: '大前端', company: 'E公司', status: 'FAILED', greeting: '您好', failReason: '验证码触发' },
]

function ApplicationsPage() {
  const { t } = useI18n()
  const [apps, setApps] = useState<Application[]>(MOCK_APPS)

  const confirmSent = (id: string) =>
    setApps(prev => prev.map(a => a.id === id ? { ...a, status: 'SENT' as AppStatus } : a))

  const confirmNotSent = (id: string) =>
    setApps(prev =>
      prev.map(a =>
        a.id === id ? { ...a, status: 'FAILED' as AppStatus, failReason: '人工确认未发送' } : a,
      ),
    )

  return (
    <div className="p-6 space-y-6">
      <h1 className="font-serif text-2xl font-semibold">{t.applications.title}</h1>

      {/* SENDING 待确认队列 — crash-recovery confirm */}
      <PendingConfirmQueue
        apps={apps}
        onConfirmSent={confirmSent}
        onConfirmNotSent={confirmNotSent}
      />

      {/* 状态机泳道看板 */}
      <ApplicationBoard
        apps={apps}
        onConfirmSent={confirmSent}
        onConfirmNotSent={confirmNotSent}
      />
    </div>
  )
}

export const Route = createFileRoute('/applications')({
  component: ApplicationsPage,
})
