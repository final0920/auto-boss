import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { useI18n } from '../lib/i18n'

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
    <div className="p-6 space-y-6 max-w-2xl">
      <h1 className="text-xl font-semibold">{t.rules.title}</h1>

      <section className="space-y-2">
        <label className="text-sm font-medium">{t.rules.profile}</label>
        <textarea
          value={config.profile}
          onChange={e => update('profile', e.target.value)}
          rows={3}
          className="w-full rounded border border-border px-3 py-2 text-sm bg-background resize-y"
        />
      </section>

      <section className="space-y-2">
        <label className="text-sm font-medium">{t.rules.hardRules}</label>
        <textarea
          value={config.hardRules}
          onChange={e => update('hardRules', e.target.value)}
          rows={4}
          placeholder="每行一条规则"
          className="w-full rounded border border-border px-3 py-2 text-sm bg-background resize-y"
        />
      </section>

      <section className="space-y-2">
        <label className="text-sm font-medium">{t.rules.llmThreshold}: {config.llmThreshold}</label>
        <input
          type="range" min={0} max={100} value={config.llmThreshold}
          onChange={e => update('llmThreshold', Number(e.target.value))}
          className="w-full"
        />
        <p className="text-xs text-muted-foreground">评分 ≥ {config.llmThreshold} 才会自动投递</p>
      </section>

      <section className="space-y-2">
        <label className="text-sm font-medium">{t.rules.greetingPrompt}</label>
        <textarea
          value={config.greetingPrompt}
          onChange={e => update('greetingPrompt', e.target.value)}
          rows={3}
          className="w-full rounded border border-border px-3 py-2 text-sm bg-background resize-y"
        />
      </section>

      <section className="space-y-2">
        <label className="text-sm font-medium">{t.rules.rateLimit}</label>
        <div className="grid grid-cols-3 gap-3">
          <div>
            <label className="text-xs text-muted-foreground">每日上限</label>
            <input
              type="number" value={config.dailyLimit}
              onChange={e => update('dailyLimit', Number(e.target.value))}
              className="w-full rounded border border-border px-2 py-1 text-sm bg-background"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">最小间隔(s)</label>
            <input
              type="number" value={config.minIntervalSec}
              onChange={e => update('minIntervalSec', Number(e.target.value))}
              className="w-full rounded border border-border px-2 py-1 text-sm bg-background"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">最大间隔(s)</label>
            <input
              type="number" value={config.maxIntervalSec}
              onChange={e => update('maxIntervalSec', Number(e.target.value))}
              className="w-full rounded border border-border px-2 py-1 text-sm bg-background"
            />
          </div>
        </div>
      </section>

      <button
        onClick={handleSave}
        className="px-4 py-2 rounded bg-primary text-primary-foreground hover:opacity-90 text-sm"
      >
        {saved ? '已保存 ✓' : t.rules.save}
      </button>
    </div>
  )
}

export const Route = createFileRoute('/rules')({
  component: RulesPage,
})
