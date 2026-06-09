import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { useI18n } from '../lib/i18n'
import { Button } from '../components/ui'
import { JobCard } from '../components/JobCard'
import type { Job } from '../components/JobCard'

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

function JobsPage() {
  const { t } = useI18n()
  const [jobs, setJobs] = useState<Job[]>(MOCK_JOBS)

  const toggleBlacklist = (id: string) =>
    setJobs(prev => prev.map(j => j.id === id ? { ...j, blacklisted: !j.blacklisted } : j))

  const togglePin = (id: string) =>
    setJobs(prev => prev.map(j => j.id === id ? { ...j, pinned: !j.pinned } : j))

  const pinned = jobs.filter(j => j.pinned)
  const rest = jobs.filter(j => !j.pinned)

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-serif text-2xl font-semibold">{t.jobs.title}</h1>
        <Button variant="default" size="sm">
          {t.jobs.fetch}
        </Button>
      </div>

      {pinned.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center gap-2">
            <span className="w-1.5 h-1.5 rounded-full bg-primary" />
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              置顶
            </span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {pinned.map(j => (
              <JobCard key={j.id} job={j} onBlacklist={toggleBlacklist} onPin={togglePin} />
            ))}
          </div>
        </section>
      )}

      <section className="space-y-3">
        {pinned.length > 0 && (
          <div className="flex items-center gap-2">
            <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wide">
              全部职位
            </span>
          </div>
        )}
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {rest.map(j => (
            <JobCard key={j.id} job={j} onBlacklist={toggleBlacklist} onPin={togglePin} />
          ))}
        </div>
      </section>
    </div>
  )
}

export const Route = createFileRoute('/jobs')({
  component: JobsPage,
})
