import { createFileRoute } from '@tanstack/react-router'
import { useCallback } from 'react'
import { useDevice } from '../lib/device-context'
import { useI18n } from '../lib/i18n'
import { Button, Card, CardContent, Badge } from '../components/ui'
import { apiPost } from '../api'
import { ScrcpyPlayer } from '../components/ScrcpyPlayer'

function ScreenPage() {
  const { t } = useI18n()
  const { activeDevice, setDeviceMode } = useDevice()
  const isManual = activeDevice?.mode === 'MANUAL'

  // 手动模式下点击透传：归一化坐标发往后端
  const handleTap = useCallback(
    async (x: number, y: number) => {
      if (!activeDevice) return
      try {
        await apiPost(`/devices/${activeDevice.id}/control/tap`, { x, y })
      } catch {
        // 非致命：tap 失败不影响界面
      }
    },
    [activeDevice],
  )

  // 切换手动模式并同步后端
  const handleSwitchManual = useCallback(async () => {
    if (!activeDevice) return
    setDeviceMode(activeDevice.id, 'MANUAL')
    try {
      await apiPost(`/devices/${activeDevice.id}/mode`, { mode: 'MANUAL' })
    } catch {
      // 乐观更新已生效，后端失败忽略
    }
  }, [activeDevice, setDeviceMode])

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
      {/* 页头 */}
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <h1 className="font-serif text-2xl font-semibold text-foreground">
            {t.screen.title}
          </h1>
          <span className="text-muted-foreground">—</span>
          <span className="font-medium text-foreground">{activeDevice.model}</span>
          <Badge variant={isManual ? 'default' : 'warning'}>
            {t.device.mode[activeDevice.mode]}
          </Badge>
        </div>
        {!isManual && (
          <Button size="sm" onClick={handleSwitchManual}>
            {t.screen.switchManual}
          </Button>
        )}
      </div>

      {/* 视频画面：interactive=false 时组件内部显示遮罩提示 */}
      <ScrcpyPlayer
        deviceId={activeDevice.id}
        interactive={isManual}
        onTap={isManual ? handleTap : undefined}
      />
    </div>
  )
}

export const Route = createFileRoute('/screen')({
  component: ScreenPage,
})
