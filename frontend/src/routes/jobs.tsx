import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'

interface Job {
  id: string
  title: string
  company: string
  salary: string
  score: number
  reason: string
  tags: string[]
  blacklisted: boolean
  pinned: boolean
}

const MOCK_JOBS: Job[] = [
  {
    id: 'j1', title: '前端工程师', company: '某科技公司', salary: '15-25k',
    score: 87, reason: '技术栈匹配，规模合适', tags: ['React', 'TypeScript'], blacklisted: false, pinned: true,
  },
  {
    id: 'j2', title: '全栈开发', company: '另一家公司', salary: '20-30k',
    score: 62, reason: '部分匹配，需要后端经验', tags: ['Node.js', 'Vue'], blacklisted: false, pinned: false,
  },
  {
    id: 'j3', title: '外包项目', company: '外包公司', salary: '8-12k',
    score: 23, reason: '薪资偏低，外包性质', tags: ['外包'], blacklisted: true, pinned: false,
  },
]

function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 80 ? 'bg-green-100 text-green-800' :
    score >= 60 ? 'bg-yellow-100 text-yellow-800' :
    'bg-red-100 text-red-800'
  return <span className={cn('px-2 py-0.5 rounded text-xs font-medium', color)}>{score}</span>
}

function JobCard({ job, onBlacklist, onPin }: {
  job: Job
  onBlacklist: (id: string) => void
  onPin: (id: string) => void
}) {
  const { t } = useI18n()

  return (
    <div className={cn(
      'border border-border rounded-lg p-4 bg-card space-y-2',
      job.blacklisted && 'opacity-50',
      job.pinned && 'border-primary',
    )}>
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-2">
            <span className="font-medium">{job.title}</span>
            {job.pinned && <span className="text-xs text-primary">📌</span>}
          </div>
          <div className="text-sm text-muted-foreground">{job.company} · {job.salary}</div>
        </div>
        <ScoreBadge score={job.score} />
      </div>

      <p className="text-sm text-muted-foreground">{job.reason}</p>

      <div className="flex flex-wrap gap-1">
        {job.tags.map(tag => (
          <span key={tag} className="px-2 py-0.5 bg-muted rounded text-xs">{tag}</span>
        ))}
      </div>

      <div className="flex gap-2 pt-1">
        <button
          onClick={() => onPin(job.id)}
          className="px-2 py-1 text-xs rounded border border-border hover:bg-muted"
        >
          {t.jobs.pin}
        </button>
        <button
          onClick={() => onBlacklist(job.id)}
          className="px-2 py-1 text-xs rounded border border-destructive text-destructive hover:bg-destructive/10"
        >
          {t.jobs.blacklist}
        </button>
      </div>
    </div>
  )
}

function JobsPage() {
  const { t } = useI18n()
  const [jobs, setJobs] = useState<Job[]>(MOCK_JOBS)

  const toggleBlacklist = (id: string) =>
    setJobs(prev => prev.map(j => j.id === id ? { ...j, blacklisted: !j.blacklisted } : j))

  const togglePin = (id: string) =>
    setJobs(prev => prev.map(j => j.id === id ? { ...j, pinned: !j.pinned } : j))

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t.jobs.title}</h1>
        <button className="px-3 py-1.5 text-sm rounded bg-primary text-primary-foreground hover:opacity-90">
          {t.jobs.fetch}
        </button>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
        {jobs.map(j => (
          <JobCard key={j.id} job={j} onBlacklist={toggleBlacklist} onPin={togglePin} />
        ))}
      </div>
    </div>
  )
}

export const Route = createFileRoute('/jobs')({
  component: JobsPage,
})
