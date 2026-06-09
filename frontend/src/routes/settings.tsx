import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { useI18n, type Locale } from '../lib/i18n'
import { Button, Card, CardHeader, CardTitle, CardContent, Input } from '../components/ui'

type BackendOverride = 'auto' | 'uia' | 'vision'

interface SettingsState {
  backendOverride: BackendOverride
  backendLocked: boolean
  language: Locale
  theme: 'light' | 'dark'
  // model info display only — keys are never stored in frontend
  modelName: string
  modelBaseUrl: string
}

const DEFAULT: SettingsState = {
  backendOverride: 'auto',
  backendLocked: false,
  language: 'zh',
  theme: 'light',
  modelName: 'gpt-5.5',
  modelBaseUrl: 'https://gpt.pkpp.cn',
}

function SettingsPage() {
  const { t, setLocale } = useI18n()
  const [cfg, setCfg] = useState<SettingsState>(DEFAULT)
  const [saved, setSaved] = useState(false)

  const update = <K extends keyof SettingsState>(key: K, value: SettingsState[K]) =>
    setCfg(prev => ({ ...prev, [key]: value }))

  const handleSave = () => {
    setLocale(cfg.language)
    // TODO: apiPut('/config/settings', { backendOverride: cfg.backendOverride, backendLocked: cfg.backendLocked })
    setSaved(true)
    setTimeout(() => setSaved(false), 2000)
  }

  return (
    <div className="p-6 space-y-4 max-w-lg">
      <h1 className="text-2xl font-serif font-semibold text-foreground">{t.settings.title}</h1>

      {/* 模型配置 — 只读展示，Key 走 .env */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.settings.modelConfig}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Model</label>
              <Input value={cfg.modelName} readOnly className="cursor-not-allowed opacity-70" />
            </div>
            <div className="space-y-1">
              <label className="text-xs text-muted-foreground">Base URL</label>
              <Input value={cfg.modelBaseUrl} readOnly className="cursor-not-allowed opacity-70" />
            </div>
          </div>
          {/* API Key 提示：Key 走 .env，后端覆盖，前端不存储 */}
          <p className="text-xs text-muted-foreground bg-muted/60 border border-border/60 rounded-xl px-3 py-2">
            {t.settings.apiKeyNote}
          </p>
        </CardContent>
      </Card>

      {/* 后端覆盖 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.settings.backendOverride}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            {(['auto', 'uia', 'vision'] as BackendOverride[]).map(opt => (
              <Button
                key={opt}
                variant={cfg.backendOverride === opt ? 'default' : 'outline'}
                size="sm"
                onClick={() => update('backendOverride', opt)}
              >
                {opt === 'auto' ? '自动' : opt === 'uia' ? '控件树' : '视觉'}
              </Button>
            ))}
          </div>
          {cfg.backendOverride !== 'auto' && (
            <label className="flex items-center gap-2 text-sm cursor-pointer select-none">
              <input
                type="checkbox"
                id="lock-backend"
                checked={cfg.backendLocked}
                onChange={e => update('backendLocked', e.target.checked)}
                className="rounded accent-primary"
              />
              锁定（禁止自动切换）
            </label>
          )}
          <p className="text-xs text-muted-foreground">{t.settings.backendOverrideNote}</p>
        </CardContent>
      </Card>

      {/* 语言 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.settings.language}</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2">
            {(['zh', 'en'] as Locale[]).map(lang => (
              <Button
                key={lang}
                variant={cfg.language === lang ? 'default' : 'outline'}
                size="sm"
                onClick={() => update('language', lang)}
              >
                {lang === 'zh' ? '中文' : 'English'}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* 主题 — 侧栏已有切换，此处说明 */}
      <Card>
        <CardHeader>
          <CardTitle className="text-base">{t.settings.theme}</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <div className="flex gap-2">
            {(['light', 'dark'] as const).map(th => (
              <Button
                key={th}
                variant={cfg.theme === th ? 'default' : 'outline'}
                size="sm"
                onClick={() => update('theme', th)}
              >
                {th === 'light' ? '浅色' : '深色'}
              </Button>
            ))}
          </div>
          <p className="text-xs text-muted-foreground">
            主题切换也可通过侧栏底部的切换按钮快速操作，设置在此保存后同步。
          </p>
        </CardContent>
      </Card>

      <Button onClick={handleSave}>
        {saved ? '已保存' : t.settings.save}
      </Button>
    </div>
  )
}

export const Route = createFileRoute('/settings')({
  component: SettingsPage,
})
