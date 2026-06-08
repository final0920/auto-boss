import { useState } from 'react'
import { useI18n } from '../lib/i18n'

export interface RulesConfig {
  profile: string
  hardRules: string
  llmThreshold: number
  greetingPrompt: string
  dailyLimit: number
  minIntervalSec: number
  maxIntervalSec: number
}

interface RuleConfigFormProps {
  initialConfig: RulesConfig
  onSave: (cfg: RulesConfig) => Promise<void> | void
}

export function RuleConfigForm({ initialConfig, onSave }: RuleConfigFormProps) {
  const { t } = useI18n()
  const [cfg, setCfg] = useState<RulesConfig>(initialConfig)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)

  const update = <K extends keyof RulesConfig>(key: K, value: RulesConfig[K]) =>
    setCfg(prev => ({ ...prev, [key]: value }))

  const handleSave = async () => {
    setSaving(true)
    try {
      await onSave(cfg)
      setSaved(true)
      setTimeout(() => setSaved(false), 2000)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="space-y-5 max-w-2xl">
      <section className="space-y-1.5">
        <label className="text-sm font-medium">{t.rules.profile}</label>
        <textarea
          value={cfg.profile}
          onChange={e => update('profile', e.target.value)}
          rows={3}
          className="w-full rounded border border-border px-3 py-2 text-sm bg-background resize-y"
        />
      </section>

      <section className="space-y-1.5">
        <label className="text-sm font-medium">{t.rules.hardRules}</label>
        <textarea
          value={cfg.hardRules}
          onChange={e => update('hardRules', e.target.value)}
          rows={4}
          placeholder="每行一条规则"
          className="w-full rounded border border-border px-3 py-2 text-sm bg-background resize-y"
        />
      </section>

      <section className="space-y-1.5">
        <label className="text-sm font-medium">{t.rules.llmThreshold}: {cfg.llmThreshold}</label>
        <input
          type="range" min={0} max={100} value={cfg.llmThreshold}
          onChange={e => update('llmThreshold', Number(e.target.value))}
          className="w-full"
        />
        <p className="text-xs text-muted-foreground">评分 ≥ {cfg.llmThreshold} 才会自动投递</p>
      </section>

      <section className="space-y-1.5">
        <label className="text-sm font-medium">{t.rules.greetingPrompt}</label>
        <textarea
          value={cfg.greetingPrompt}
          onChange={e => update('greetingPrompt', e.target.value)}
          rows={3}
          className="w-full rounded border border-border px-3 py-2 text-sm bg-background resize-y"
        />
      </section>

      <section className="space-y-1.5">
        <label className="text-sm font-medium">{t.rules.rateLimit}</label>
        <div className="grid grid-cols-3 gap-3">
          {([
            ['dailyLimit', '每日上限'],
            ['minIntervalSec', '最小间隔(s)'],
            ['maxIntervalSec', '最大间隔(s)'],
          ] as const).map(([key, label]) => (
            <div key={key}>
              <label className="text-xs text-muted-foreground">{label}</label>
              <input
                type="number" value={cfg[key]}
                onChange={e => update(key, Number(e.target.value))}
                className="w-full rounded border border-border px-2 py-1 text-sm bg-background"
              />
            </div>
          ))}
        </div>
      </section>

      <button
        onClick={handleSave}
        disabled={saving}
        className="px-4 py-2 rounded bg-primary text-primary-foreground hover:opacity-90 text-sm disabled:opacity-50"
      >
        {saved ? '已保存 ✓' : saving ? '保存中...' : t.rules.save}
      </button>
    </div>
  )
}
