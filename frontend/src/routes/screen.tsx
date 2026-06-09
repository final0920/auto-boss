import { createFileRoute } from '@tanstack/react-router'
import { useRef, useEffect, useState, useCallback } from 'react'
import { useDevice } from '../lib/device-context'
import { useI18n } from '../lib/i18n'
import { connectSocket } from '../lib/socket'
import { Button, Card, CardContent, Badge } from '../components/ui'
import { cn } from '../lib/utils'

// ScrcpyPlayer: socket.io receives 'video-data' (H.264 NAL units),
// decodes via WebCodecs VideoDecoder. Falls back to screenshot polling.
function ScrcpyPlayer({ deviceId }: { deviceId: string }) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [fallback, setFallback] = useState(false)
  const [screenshotUrl, setScreenshotUrl] = useState<string | null>(null)
  const { t } = useI18n()

  // WebCodecs decode path
  useEffect(() => {
    if (!('VideoDecoder' in window)) {
      setFallback(true)
      return
    }

    const socket = connectSocket()
    let decoder: VideoDecoder | null = null

    try {
      decoder = new VideoDecoder({
        output(frame) {
          const canvas = canvasRef.current
          if (!canvas) { frame.close(); return }
          const ctx = canvas.getContext('2d')
          if (!ctx) { frame.close(); return }
          canvas.width = frame.displayWidth
          canvas.height = frame.displayHeight
          ctx.drawImage(frame, 0, 0)
          frame.close()
        },
        error() {
          setFallback(true)
        },
      })

      // Configure for H.264 baseline
      decoder.configure({ codec: 'avc1.42E01E', optimizeForLatency: true })
    } catch {
      setFallback(true)
    }

    socket.on('video-data', (data: ArrayBuffer) => {
      if (!decoder || decoder.state === 'closed') return
      try {
        decoder.decode(new EncodedVideoChunk({
          type: 'key',
          timestamp: performance.now() * 1000,
          data,
        }))
      } catch {
        // non-fatal decode error; wait for next keyframe
      }
    })

    socket.emit('join-device', deviceId)

    return () => {
      socket.off('video-data')
      socket.emit('leave-device', deviceId)
      decoder?.close()
    }
  }, [deviceId])

  // Screenshot polling fallback
  useEffect(() => {
    if (!fallback) return
    let active = true
    const poll = async () => {
      while (active) {
        try {
          // TODO: apiGet returns blob URL
          const url = `/api/devices/${deviceId}/screenshot`
          setScreenshotUrl(url + `?t=${Date.now()}`)
        } catch { /* ignore */ }
        await new Promise(r => setTimeout(r, 1000))
      }
    }
    poll()
    return () => { active = false }
  }, [fallback, deviceId])

  if (fallback) {
    return (
      <div className="flex flex-col items-center gap-3">
        <p className="text-xs text-muted-foreground">{t.screen.fallback}</p>
        {screenshotUrl && (
          <img
            src={screenshotUrl}
            alt="screenshot"
            className="max-w-full rounded-2xl border border-border/60 shadow-shell"
          />
        )}
      </div>
    )
  }

  return (
    <canvas
      ref={canvasRef}
      className="max-w-full block rounded-2xl border border-border/60"
    />
  )
}

function ScreenPage() {
  const { t } = useI18n()
  const { activeDevice, setDeviceMode } = useDevice()
  const isManual = activeDevice?.mode === 'MANUAL'

  // Touch/click passthrough to /api/devices/:id/control/tap (MANUAL only)
  const handleCanvasClick = useCallback(
    async (e: React.MouseEvent<HTMLDivElement>) => {
      if (!isManual || !activeDevice) return
      const rect = e.currentTarget.getBoundingClientRect()
      const x = (e.clientX - rect.left) / rect.width
      const y = (e.clientY - rect.top) / rect.height
      // TODO: apiPost(`/devices/${activeDevice.id}/control/tap`, { x, y })
      console.log('tap', x, y)
    },
    [isManual, activeDevice],
  )

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
      {/* header */}
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
          <Button
            size="sm"
            onClick={() => setDeviceMode(activeDevice.id, 'MANUAL')}
          >
            {t.screen.switchManual}
          </Button>
        )}
      </div>

      {/* manual-only notice */}
      {!isManual && (
        <div className="flex items-center gap-2 bg-warning/10 border border-warning/30 text-warning-foreground rounded-xl px-4 py-2.5 text-sm">
          <span className="inline-block w-1.5 h-1.5 rounded-full bg-warning shrink-0" />
          {t.screen.manualOnly}
        </div>
      )}

      {/* player */}
      <div
        onClick={handleCanvasClick}
        className={cn(
          'rounded-2xl overflow-hidden',
          isManual ? 'cursor-crosshair' : 'cursor-not-allowed pointer-events-none opacity-75',
        )}
      >
        <ScrcpyPlayer deviceId={activeDevice.id} />
      </div>
    </div>
  )
}

export const Route = createFileRoute('/screen')({
  component: ScreenPage,
})
