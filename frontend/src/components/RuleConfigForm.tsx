import { useState } from 'react'
import { useI18n } from '../lib/i18n'
import { Button, Card, CardHeader, CardTitle, CardContent, Input } from './ui'

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
    <div className="space-y-4 max-w-2xl">
      {/* 候选人画像 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.rules.profile}</CardTitle>
        </CardHeader>
        <CardContent>
          <textarea
            value={cfg.profile}
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
            value={cfg.hardRules}
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
            <span className="ml-2 font-mono text-primary">{cfg.llmThreshold}</span>
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <input
            type="range" min={0} max={100} value={cfg.llmThreshold}
            onChange={e => update('llmThreshold', Number(e.target.value))}
            className="w-full accent-primary"
          />
          <p className="text-xs text-muted-foreground">
            评分 &ge; {cfg.llmThreshold} 才会自动投递
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
            value={cfg.greetingPrompt}
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
            {([
              ['dailyLimit', '每日上限'],
              ['minIntervalSec', '最小间隔(s)'],
              ['maxIntervalSec', '最大间隔(s)'],
            ] as const).map(([key, label]) => (
              <div key={key} className="space-y-1">
                <label className="text-xs text-muted-foreground">{label}</label>
                <Input
                  type="number"
                  value={cfg[key]}
                  onChange={e => update(key, Number(e.target.value))}
                />
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      <Button onClick={handleSave} disabled={saving}>
        {saved ? '已保存' : saving ? '保存中...' : t.rules.save}
      </Button>
    </div>
  )
}
