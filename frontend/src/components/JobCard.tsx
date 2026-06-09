import { cn } from '../lib/utils'
import { useI18n } from '../lib/i18n'
import { Badge, Button, Card, CardContent } from './ui'

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
  const variant =
    score >= 80 ? 'success' :
    score >= 60 ? 'warning' :
    'destructive'
  return (
    <Badge variant={variant} className="tabular-nums text-xs">
      {score}
    </Badge>
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
    <Card
      variant="interactive"
      className={cn(
        job.blacklisted && 'opacity-40',
        job.pinned && 'border-primary/50',
      )}
    >
      <CardContent className="p-4 space-y-2">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0">
            <div className="flex items-center gap-1.5">
              {job.pinned && (
                <span className="w-1.5 h-1.5 rounded-full bg-primary shrink-0" />
              )}
              <span className="font-serif font-semibold text-sm leading-snug truncate">
                {job.title}
              </span>
            </div>
            <div className="text-xs text-muted-foreground mt-0.5">
              {job.company} · {job.salary}
            </div>
          </div>
          <ScoreBadge score={job.score} />
        </div>

        <p className="text-xs text-muted-foreground leading-relaxed">{job.reason}</p>

        <div className="flex flex-wrap gap-1">
          {job.tags.map(tag => (
            <Badge key={tag} variant="outline" className="text-xs px-2 py-0.5">
              {tag}
            </Badge>
          ))}
        </div>

        {(onPin || onBlacklist) && (
          <div className="flex gap-2 pt-1">
            {onPin && (
              <Button
                variant="outline"
                size="sm"
                onClick={() => onPin(job.id)}
                className="h-7 px-2 text-xs"
              >
                {t.jobs.pin}
              </Button>
            )}
            {onBlacklist && (
              <Button
                variant="destructive"
                size="sm"
                onClick={() => onBlacklist(job.id)}
                className="h-7 px-2 text-xs"
              >
                {t.jobs.blacklist}
              </Button>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  )
}
