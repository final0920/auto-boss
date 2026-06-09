import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { useI18n } from '../lib/i18n'
import { Button, Card, CardContent } from '../components/ui'
import { JobCard } from '../components/JobCard'
import type { Job } from '../components/JobCard'
import { apiGet, apiPost } from '../api'

function JobsPage() {
  const { t } = useI18n()
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [fetching, setFetching] = useState(false)

  // 加载职位列表
  const loadJobs = () => {
    setLoading(true)
    setError(null)
    apiGet<Job[]>('/jobs')
      .then(setJobs)
      .catch(() => setError('加载职位失败，请稍后重试'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadJobs()
  }, [])

  // 触发后端重新抓取职位
  const handleFetch = async () => {
    setFetching(true)
    try {
      await apiPost('/jobs/fetch')
      loadJobs()
    } catch {
      setError('抓取失败，请检查后端连接')
    } finally {
      setFetching(false)
    }
  }

  // 切换黑名单状态（乐观更新）
  const toggleBlacklist = async (id: string) => {
    const target = jobs.find(j => j.id === id)
    if (!target) return
    const next = !target.blacklisted
    setJobs(prev => prev.map(j => j.id === id ? { ...j, blacklisted: next } : j))
    try {
      await apiPost(`/jobs/${id}/blacklist`, { blacklisted: next })
    } catch {
      setJobs(prev => prev.map(j => j.id === id ? { ...j, blacklisted: target.blacklisted } : j))
    }
  }

  // 切换置顶状态（乐观更新）
  const togglePin = async (id: string) => {
    const target = jobs.find(j => j.id === id)
    if (!target) return
    const next = !target.pinned
    setJobs(prev => prev.map(j => j.id === id ? { ...j, pinned: next } : j))
    try {
      await apiPost(`/jobs/${id}/pin`, { pinned: next })
    } catch {
      setJobs(prev => prev.map(j => j.id === id ? { ...j, pinned: target.pinned } : j))
    }
  }

  const pinned = jobs.filter(j => j.pinned)
  const rest = jobs.filter(j => !j.pinned)

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-serif text-2xl font-semibold">{t.jobs.title}</h1>
        <Button variant="default" size="sm" onClick={handleFetch} disabled={fetching}>
          {fetching ? '抓取中…' : t.jobs.fetch}
        </Button>
      </div>

      {loading && (
        <Card variant="subtle">
          <CardContent className="py-10 text-center">
            <p className="text-muted-foreground text-sm">加载中…</p>
          </CardContent>
        </Card>
      )}

      {!loading && error && (
        <Card variant="subtle" className="border-destructive/40 bg-destructive/5">
          <CardContent className="py-8 text-center">
            <p className="text-destructive text-sm">{error}</p>
          </CardContent>
        </Card>
      )}

      {!loading && !error && jobs.length === 0 && (
        <Card variant="subtle">
          <CardContent className="py-10 text-center">
            <p className="text-muted-foreground text-sm">暂无职位，点击"抓取"获取最新数据</p>
          </CardContent>
        </Card>
      )}

      {!loading && !error && jobs.length > 0 && (
        <>
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
            {rest.length > 0 ? (
              <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
                {rest.map(j => (
                  <JobCard key={j.id} job={j} onBlacklist={toggleBlacklist} onPin={togglePin} />
                ))}
              </div>
            ) : (
              <Card variant="subtle">
                <CardContent className="py-8 text-center">
                  <p className="text-muted-foreground text-sm">所有职位均已置顶</p>
                </CardContent>
              </Card>
            )}
          </section>
        </>
      )}
    </div>
  )
}

export const Route = createFileRoute('/jobs')({
  component: JobsPage,
})
