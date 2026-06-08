import { createFileRoute } from '@tanstack/react-router'
import { useRef, useEffect, useState, useCallback } from 'react'
import { useDevice } from '../lib/device-context'
import { useI18n } from '../lib/i18n'
import { connectSocket } from '../lib/socket'

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
      <div className="flex flex-col items-center gap-2">
        <p className="text-xs text-muted-foreground">{t.screen.fallback}</p>
        {screenshotUrl && (
          <img src={screenshotUrl} alt="screenshot" className="max-w-full rounded border border-border" />
        )}
      </div>
    )
  }

  return <canvas ref={canvasRef} className="max-w-full rounded border border-border" />
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
      <div className="p-6 flex items-center justify-center h-full text-muted-foreground">
        {t.device.noDevice}
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t.screen.title} — {activeDevice.model}</h1>
        {!isManual && (
          <button
            onClick={() => setDeviceMode(activeDevice.id, 'MANUAL')}
            className="px-3 py-1.5 text-sm rounded bg-primary text-primary-foreground hover:opacity-90"
          >
            {t.screen.switchManual}
          </button>
        )}
      </div>

      {!isManual && (
        <div className="text-sm text-yellow-600 bg-yellow-50 border border-yellow-200 rounded px-3 py-2">
          {t.screen.manualOnly}
        </div>
      )}

      <div
        onClick={handleCanvasClick}
        className={isManual ? 'cursor-crosshair' : 'cursor-not-allowed pointer-events-none opacity-80'}
      >
        <ScrcpyPlayer deviceId={activeDevice.id} />
      </div>
    </div>
  )
}

export const Route = createFileRoute('/screen')({
  component: ScreenPage,
})
