import { createFileRoute } from '@tanstack/react-router'
import { useDevice } from '../lib/device-context'
import { useI18n } from '../lib/i18n'
import { Card, CardContent } from '../components/ui'
import { ScrcpyPlayer } from '../components/ScrcpyPlayer'

function ScreenPage() {
  const { t } = useI18n()
  const { activeDevice } = useDevice()

  if (!activeDevice) {
    return (
      <div className="p-6 flex items-center justify-center h-full">
        <Card variant="subtle">
          <CardContent className="py-12 px-16 text-center">
            <p className="text-muted-foreground">{t.device.noDevice}</p>
          </CardContent>
        </Card>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-5">
      <div className="flex items-center gap-3">
        <h1 className="font-serif text-2xl font-semibold text-foreground">
          {t.screen.title}
        </h1>
        <span className="text-muted-foreground">—</span>
        <span className="font-medium text-foreground">{activeDevice.model}</span>
        <span className="text-xs text-muted-foreground px-2 py-1 rounded-lg bg-muted">
          只读投屏
        </span>
      </div>

      <p className="text-sm text-muted-foreground">
        投屏为只读模式，操控已禁用。如需手动操作请直接使用真机。
      </p>

      <ScrcpyPlayer
        deviceId={activeDevice.serial}
        interactive={false}
      />
    </div>
  )
}

export const Route = createFileRoute('/screen')({
  component: ScreenPage,
})
