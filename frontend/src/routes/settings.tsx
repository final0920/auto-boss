import { createFileRoute } from '@tanstack/react-router'
import { useState } from 'react'
import { useI18n, type Locale } from '../lib/i18n'

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
    <div className="p-6 space-y-6 max-w-lg">
      <h1 className="text-xl font-semibold">{t.settings.title}</h1>

      {/* Model config — read-only display, key is in .env */}
      <section className="border border-border rounded-lg p-4 space-y-3 bg-card">
        <h2 className="text-sm font-semibold">{t.settings.modelConfig}</h2>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-muted-foreground">Model</label>
            <input
              value={cfg.modelName} readOnly
              className="w-full rounded border border-border px-2 py-1 text-sm bg-muted cursor-not-allowed"
            />
          </div>
          <div>
            <label className="text-xs text-muted-foreground">Base URL</label>
            <input
              value={cfg.modelBaseUrl} readOnly
              className="w-full rounded border border-border px-2 py-1 text-sm bg-muted cursor-not-allowed"
            />
          </div>
        </div>
        <p className="text-xs text-muted-foreground bg-yellow-50 border border-yellow-200 rounded px-3 py-2">
          {t.settings.apiKeyNote}
        </p>
      </section>

      {/* Backend override */}
      <section className="space-y-2">
        <label className="text-sm font-medium">{t.settings.backendOverride}</label>
        <div className="flex gap-2">
          {(['auto', 'uia', 'vision'] as BackendOverride[]).map(opt => (
            <button
              key={opt}
              onClick={() => update('backendOverride', opt)}
              className={`px-3 py-1.5 text-sm rounded border ${
                cfg.backendOverride === opt
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'border-border hover:bg-muted'
              }`}
            >
              {opt === 'auto' ? '自动' : opt === 'uia' ? '控件树' : '视觉'}
            </button>
          ))}
        </div>
        {cfg.backendOverride !== 'auto' && (
          <div className="flex items-center gap-2">
            <input
              type="checkbox" id="lock-backend"
              checked={cfg.backendLocked}
              onChange={e => update('backendLocked', e.target.checked)}
              className="rounded"
            />
            <label htmlFor="lock-backend" className="text-sm">
              锁定（禁止自动切换）
            </label>
          </div>
        )}
        <p className="text-xs text-muted-foreground">{t.settings.backendOverrideNote}</p>
      </section>

      {/* Language */}
      <section className="space-y-2">
        <label className="text-sm font-medium">{t.settings.language}</label>
        <div className="flex gap-2">
          {(['zh', 'en'] as Locale[]).map(lang => (
            <button
              key={lang}
              onClick={() => update('language', lang)}
              className={`px-3 py-1.5 text-sm rounded border ${
                cfg.language === lang
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'border-border hover:bg-muted'
              }`}
            >
              {lang === 'zh' ? '中文' : 'English'}
            </button>
          ))}
        </div>
      </section>

      {/* Theme */}
      <section className="space-y-2">
        <label className="text-sm font-medium">{t.settings.theme}</label>
        <div className="flex gap-2">
          {(['light', 'dark'] as const).map(th => (
            <button
              key={th}
              onClick={() => update('theme', th)}
              className={`px-3 py-1.5 text-sm rounded border ${
                cfg.theme === th
                  ? 'bg-primary text-primary-foreground border-primary'
                  : 'border-border hover:bg-muted'
              }`}
            >
              {th === 'light' ? '浅色' : '深色'}
            </button>
          ))}
        </div>
      </section>

      <button
        onClick={handleSave}
        className="px-4 py-2 rounded bg-primary text-primary-foreground hover:opacity-90 text-sm"
      >
        {saved ? '已保存 ✓' : t.settings.save}
      </button>
    </div>
  )
}

export const Route = createFileRoute('/settings')({
  component: SettingsPage,
})
