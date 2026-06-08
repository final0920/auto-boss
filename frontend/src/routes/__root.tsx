import { createRootRoute, Outlet, Link } from '@tanstack/react-router'
import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'
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
    <div className="flex h-screen bg-background">
      {/* Sidebar */}
      <aside className="w-16 flex flex-col items-center py-4 gap-1 border-r border-border bg-card">
        <div className="mb-4 w-8 h-8 rounded-md bg-primary flex items-center justify-center">
          <span className="text-primary-foreground text-xs font-bold">B</span>
        </div>
        {navItems.map(({ to, label, icon: Icon }) => (
          <Link
            key={to}
            to={to}
            title={label}
            className={cn(
              'w-10 h-10 flex items-center justify-center rounded-md',
              'text-muted-foreground hover:text-foreground hover:bg-muted transition-colors',
              '[&.active]:text-primary [&.active]:bg-muted',
            )}
          >
            <Icon size={18} />
          </Link>
        ))}
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}

export const Route = createRootRoute({
  component: RootLayout,
})
