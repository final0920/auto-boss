import { createRootRoute, Outlet, Link } from '@tanstack/react-router'
import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'
import { ThemeToggle } from '../components/ThemeToggle'
import {
  Monitor, Smartphone, Briefcase, Send, Mail, Filter,
  Clock, BarChart2, Terminal, Settings,
} from 'lucide-react'

function RootLayout() {
  const { t } = useI18n()

  const navItems = [
    { to: '/', label: t.nav.devices, icon: Smartphone },
    { to: '/screen', label: t.nav.screen, icon: Monitor },
    { to: '/jobs', label: t.nav.jobs, icon: Briefcase },
    { to: '/applications', label: t.nav.applications, icon: Send },
    { to: '/inbox', label: t.nav.inbox, icon: Mail },
    { to: '/rules', label: t.nav.rules, icon: Filter },
    { to: '/scheduled', label: t.nav.scheduled, icon: Clock },
    { to: '/logs', label: t.nav.logs, icon: BarChart2 },
    { to: '/terminal', label: t.nav.terminal, icon: Terminal },
    { to: '/settings', label: t.nav.settings, icon: Settings },
  ] as const

  return (
    <div className="relative flex h-screen overflow-hidden bg-background">
      {/* 装饰渐变光斑（书卷气暖色） */}
      <div
        aria-hidden
        className="pointer-events-none absolute -left-24 -top-32 h-96 w-96 rounded-full opacity-50 blur-3xl"
        style={{ background: 'radial-gradient(circle, rgba(201,100,66,0.18), transparent 70%)' }}
      />
      <div
        aria-hidden
        className="pointer-events-none absolute -bottom-24 right-0 h-96 w-96 rounded-full opacity-40 blur-3xl"
        style={{ background: 'radial-gradient(circle, rgba(228,178,160,0.20), transparent 70%)' }}
      />

      {/* 侧栏（玻璃卡 + 图标+文字展开式 + 染色长投影） */}
      <aside className="sidebar-card relative z-10 m-3 flex w-56 flex-col gap-1 px-3 py-4 shadow-shell-sidebar">
        {/* 品牌区 */}
        <div className="mb-4 flex items-center gap-2.5 px-1">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-primary text-primary-foreground shadow-sm">
            <span className="font-serif text-sm font-bold">B</span>
          </div>
          <div className="leading-tight">
            <div className="font-serif text-sm font-semibold text-foreground">Boss AutoApply</div>
            <div className="text-[11px] text-muted-foreground">自动求职控制台</div>
          </div>
        </div>

        {/* 导航（图标 + 文字） */}
        <nav className="flex flex-1 flex-col gap-0.5">
          {navItems.map(({ to, label, icon: Icon }) => (
            <Link
              key={to}
              to={to}
              title={label}
              className={cn(
                'flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium text-muted-foreground transition-all',
                'hover:bg-muted hover:text-foreground active:scale-[0.98]',
                '[&.active]:bg-primary/10 [&.active]:font-semibold [&.active]:text-primary',
              )}
            >
              <Icon size={18} className="shrink-0" />
              <span>{label}</span>
            </Link>
          ))}
        </nav>

        {/* 底部：主题切换 */}
        <div className="mt-2 flex items-center justify-between border-t border-border/50 px-1 pt-3">
          <span className="text-xs text-muted-foreground">主题</span>
          <ThemeToggle />
        </div>
      </aside>

      {/* 主内容区 */}
      <main className="relative z-10 flex-1 overflow-auto p-3">
        <Outlet />
      </main>
    </div>
  )
}

export const Route = createRootRoute({
  component: RootLayout,
})
