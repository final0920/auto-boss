import { cn } from '../lib/utils'
import { useI18n } from '../lib/i18n'

export interface Job {
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

export function ScoreBadge({ score }: { score: number }) {
  const color =
    score >= 80 ? 'bg-green-100 text-green-800' :
    score >= 60 ? 'bg-yellow-100 text-yellow-800' :
    'bg-red-100 text-red-800'
  return (
    <span className={cn('px-2 py-0.5 rounded text-xs font-semibold tabular-nums', color)}>
      {score}
    </span>
  )
}

interface JobCardProps {
  job: Job
  onBlacklist?: (id: string) => void
  onPin?: (id: string) => void
}

export function JobCard({ job, onBlacklist, onPin }: JobCardProps) {
  const { t } = useI18n()

  return (
    <div className={cn(
      'border border-border rounded-lg p-4 bg-card space-y-2 transition-opacity',
      job.blacklisted && 'opacity-40',
      job.pinned && 'border-primary',
    )}>
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-1.5">
            {job.pinned && <span className="text-xs">📌</span>}
            <span className="font-medium text-sm truncate">{job.title}</span>
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">{job.company} · {job.salary}</div>
        </div>
        <ScoreBadge score={job.score} />
      </div>

      <p className="text-xs text-muted-foreground leading-relaxed">{job.reason}</p>

      <div className="flex flex-wrap gap-1">
        {job.tags.map(tag => (
          <span key={tag} className="px-1.5 py-0.5 bg-muted rounded text-xs">{tag}</span>
        ))}
      </div>

      {(onPin || onBlacklist) && (
        <div className="flex gap-2 pt-1">
          {onPin && (
            <button
              onClick={() => onPin(job.id)}
              className="px-2 py-1 text-xs rounded border border-border hover:bg-muted"
            >
              {t.jobs.pin}
            </button>
          )}
          {onBlacklist && (
            <button
              onClick={() => onBlacklist(job.id)}
              className="px-2 py-1 text-xs rounded border border-destructive text-destructive hover:bg-destructive/10"
            >
              {t.jobs.blacklist}
            </button>
          )}
        </div>
      )}
    </div>
  )
}
