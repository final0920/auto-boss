import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { useI18n } from '../lib/i18n'
import { Button, Card, CardHeader, CardTitle, CardContent, Input } from '../components/ui'

interface RulesConfig {
  profile: string
  hardRules: string
  llmThreshold: number
  greetingPrompt: string
  dailyLimit: number
  minIntervalSec: number
  maxIntervalSec: number
}

const DEFAULT_CONFIG: RulesConfig = {
  profile: 'React/TypeScript 前端工程师，5年经验，北京，薪资 20-35k',
  hardRules: '排除外包\n排除薪资低于15k\n排除非北京',
  llmThreshold: 70,
  greetingPrompt: '您好，我是一名有5年经验的前端工程师，对贵公司的{职位}岗位非常感兴趣，期待能有机会深入交流。',
  dailyLimit: 150,
  minIntervalSec: 20,
  maxIntervalSec: 90,
}

function RulesPage() {
  const { t } = useI18n()
  const [config, setConfig] = useState<RulesConfig>(DEFAULT_CONFIG)
  const [saved, setSaved] = useState(false)

  const update = <K extends keyof RulesConfig>(key: K, value: RulesConfig[K]) =>
    setConfig(prev => ({ ...prev, [key]: value }))

  const handleSave = () => {
    // TODO: apiPut('/config/rules', config)
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="p-6 space-y-4 max-w-2xl">
      <h1 className="text-2xl font-serif font-semibold text-foreground">{t.rules.title}</h1>

      {/* 候选人画像 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.rules.profile}</CardTitle>
        </CardHeader>
        <CardContent>
          <textarea
            value={config.profile}
            onChange={e => update('profile', e.target.value)}
            rows={3}
            className="w-full rounded-xl border border-border/60 bg-muted/50 px-4 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:border-primary/60 transition-all resize-y"
          />
        </CardContent>
      </Card>

      {/* 硬性规则 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.rules.hardRules}</CardTitle>
        </CardHeader>
        <CardContent>
          <textarea
            value={config.hardRules}
            onChange={e => update('hardRules', e.target.value)}
            rows={4}
            placeholder="每行一条规则"
            className="w-full rounded-xl border border-border/60 bg-muted/50 px-4 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:border-primary/60 transition-all resize-y"
          />
        </CardContent>
      </Card>

      {/* LLM 评分阈值 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">
            {t.rules.llmThreshold}
            <span className="ml-2 font-mono text-primary">{config.llmThreshold}</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <input
            type="range" min={0} max={100} value={config.llmThreshold}
            onChange={e => update('llmThreshold', Number(e.target.value))}
            className="w-full accent-primary"
          />
          <p className="text-xs text-muted-foreground">
            评分 &ge; {config.llmThreshold} 才会自动投递
          </p>
        </CardContent>
      </Card>

      {/* 打招呼模板 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.rules.greetingPrompt}</CardTitle>
        </CardHeader>
        <CardContent>
          <textarea
            value={config.greetingPrompt}
            onChange={e => update('greetingPrompt', e.target.value)}
            rows={3}
            className="w-full rounded-xl border border-border/60 bg-muted/50 px-4 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:border-primary/60 transition-all resize-y"
          />
        </CardContent>
      </Card>

      {/* 频率限制 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.rules.rateLimit}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-3 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">每日上限</label>
              <Input
                type="number"
                value={config.dailyLimit}
                onChange={e => update('dailyLimit', Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">最小间隔(s)</label>
              <Input
                type="number"
                value={config.minIntervalSec}
                onChange={e => update('minIntervalSec', Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">最大间隔(s)</label>
              <Input
                type="number"
                value={config.maxIntervalSec}
                onChange={e => update('maxIntervalSec', Number(e.target.value))}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Button onClick={handleSave}>
        {saved ? '已保存' : t.rules.save}
      </Button>
    </div>
  )
}

export const Route = createFileRoute('/rules')({
  component: RulesPage,
})
