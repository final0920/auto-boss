import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useState } from 'react'
import { useI18n } from '../lib/i18n'
import { Button, Card, CardHeader, CardTitle, CardContent, Input } from '../components/ui'
import { apiGet, apiPut } from '../api'

interface RulesConfig {
  profile: string
  hardRules: string
  llmThreshold: number
  greetingPrompt: string
  dailyLimit: number
  minIntervalSec: number
  maxIntervalSec: number
}

// 后端未连通时的合理默认值，仅作表单初始展位
const FALLBACK: RulesConfig = {
  profile: '',
  hardRules: '',
  llmThreshold: 70,
  greetingPrompt: '',
  dailyLimit: 150,
  minIntervalSec: 20,
  maxIntervalSec: 90,
}

function RulesPage() {
  const { t } = useI18n()
  const [config, setConfig] = useState<RulesConfig>(FALLBACK)
  const [loading, setLoading] = useState(true)
  const [saveState, setSaveState] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')

  // 从后端加载当前规则配置
  useEffect(() => {
    let cancelled = false
    apiGet<RulesConfig>('/config/rules')
      .then(data => {
        if (!cancelled) setConfig(data)
      })
      .catch(() => {
        // 加载失败：保留 fallback，允许用户编辑后保存
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => { cancelled = true }
  }, [])

  const update = <K extends keyof RulesConfig>(key: K, value: RulesConfig[K]) =>
    setConfig(prev => ({ ...prev, [key]: value }))

  const handleSave = async () => {
    setSaveState('saving')
    try {
      await apiPut('/config/rules', config)
      setSaveState('saved')
      setTimeout(() => setSaveState('idle'), 2000)
    } catch {
      setSaveState('error')
      setTimeout(() => setSaveState('idle'), 3000)
    }
  }

  const saveLabel =
    saveState === 'saving' ? '保存中…' :
    saveState === 'saved'  ? '已保存' :
    saveState === 'error'  ? '保存失败，重试' :
    t.rules.save

  return (
    <div className="p-6 space-y-4 max-w-2xl">
      <h1 className="text-2xl font-serif font-semibold text-foreground">{t.rules.title}</h1>

      {loading && (
        <p className="text-sm text-muted-foreground">加载配置中…</p>
      )}

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
            disabled={loading}
            className="w-full rounded-xl border border-border/60 bg-muted/50 px-4 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:border-primary/60 transition-all resize-y disabled:opacity-50"
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
            disabled={loading}
            placeholder="每行一条规则"
            className="w-full rounded-xl border border-border/60 bg-muted/50 px-4 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:border-primary/60 transition-all resize-y disabled:opacity-50"
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
            disabled={loading}
            onChange={e => update('llmThreshold', Number(e.target.value))}
            className="w-full accent-primary disabled:opacity-50"
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
            disabled={loading}
            className="w-full rounded-xl border border-border/60 bg-muted/50 px-4 py-2 text-sm placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40 focus-visible:border-primary/60 transition-all resize-y disabled:opacity-50"
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
                disabled={loading}
                onChange={e => update('dailyLimit', Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">最小间隔(s)</label>
              <Input
                type="number"
                value={config.minIntervalSec}
                disabled={loading}
                onChange={e => update('minIntervalSec', Number(e.target.value))}
              />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">最大间隔(s)</label>
              <Input
                type="number"
                value={config.maxIntervalSec}
                disabled={loading}
                onChange={e => update('maxIntervalSec', Number(e.target.value))}
              />
            </div>
          </div>
        </CardContent>
      </Card>

      <Button
        onClick={handleSave}
        disabled={loading || saveState === 'saving'}
        variant={saveState === 'error' ? 'outline' : 'default'}
      >
        {saveLabel}
      </Button>
    </div>
  )
}

export const Route = createFileRoute('/rules')({
  component: RulesPage,
})
