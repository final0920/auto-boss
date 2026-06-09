import { createFileRoute } from '@tanstack/react-router'
import { useI18n } from '../lib/i18n'
import { useDevice } from '../lib/device-context'
import { Button, Card, CardContent } from '../components/ui'
import { TerminalPanel } from '../components/TerminalPanel'
import { apiPost } from '../api'
import { useCallback } from 'react'

function TerminalPage() {
  const { t } = useI18n()
  const { activeDevice, setDeviceMode } = useDevice()
  const isManual = activeDevice?.mode === 'MANUAL'

  // 切换手动模式并同步后端
  const handleSwitchManual = useCallback(async () => {
    if (!activeDevice) return
    setDeviceMode(activeDevice.id, 'MANUAL')
    try {
      await apiPost('/devices/mode', { mode: 'MANUAL' })
    } catch {
      // 乐观更新已生效，后端失败忽略
    }
  }, [activeDevice, setDeviceMode])

  if (!activeDevice) {
    return (
      <div className="p-6 flex items-center justify-center h-full">
        <p className="text-muted-foreground">{t.device.noDevice}</p>
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4 h-full flex flex-col">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-serif font-semibold text-foreground">{t.terminal.title}</h1>
        {!isManual && (
          <Button onClick={handleSwitchManual} size="sm">
            {t.terminal.switchManual}
          </Button>
        )}
      </div>

      {!isManual ? (
        <Card className="flex-1 flex items-center justify-center min-h-[300px]">
          <CardContent className="text-yellow-600 text-sm pt-6">
            {t.terminal.manualOnly}
          </CardContent>
        </Card>
      ) : (
        /* flex-1 让终端填满剩余高度 */
        <div className="flex-1 min-h-0">
          <TerminalPanel deviceId={activeDevice.serial} />
        </div>
      )}
    </div>
  )
}

export const Route = createFileRoute('/terminal')({
  component: TerminalPage,
})
