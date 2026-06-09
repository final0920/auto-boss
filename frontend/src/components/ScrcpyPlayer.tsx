import { useRef, useEffect, useState } from 'react'
import { connectSocket } from '../lib/socket'
import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'

interface ScrcpyPlayerProps {
  deviceId: string
  /** If false, overlay a "manual only" mask over the canvas */
  interactive: boolean
  onTap?: (x: number, y: number) => void
}

function useScreenshotPolling(deviceId: string, active: boolean) {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!active) return
    let alive = true
    ;(async () => {
      while (alive) {
        setUrl(`/api/devices/${deviceId}/screenshot?t=${Date.now()}`)
        await new Promise(r => setTimeout(r, 1000))
      }
    })()
    return () => { alive = false }
  }, [deviceId, active])

  return url
}

export function ScrcpyPlayer({ deviceId, interactive, onTap }: ScrcpyPlayerProps) {
  const { t } = useI18n()
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const [fallback, setFallback] = useState(false)
  const screenshotUrl = useScreenshotPolling(deviceId, fallback)

  // WebCodecs decode path
  useEffect(() => {
    if (!('VideoDecoder' in window)) { setFallback(true); return }

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
        error() { setFallback(true) },
      })
      decoder.configure({ codec: 'avc1.42E01E', optimizeForLatency: true })
    } catch { setFallback(true); return }

    socket.on('video-data', (data: ArrayBuffer) => {
      if (!decoder || decoder.state === 'closed') return
      try {
        decoder.decode(new EncodedVideoChunk({
          type: 'key',
          timestamp: performance.now() * 1000,
          data,
        }))
      } catch { /* wait for next keyframe */ }
    })

    socket.emit('join-device', deviceId)
    return () => {
      socket.off('video-data')
      socket.emit('leave-device', deviceId)
      decoder?.close()
    }
  }, [deviceId])

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!interactive || !onTap) return
    const rect = e.currentTarget.getBoundingClientRect()
    onTap(
      (e.clientX - rect.left) / rect.width,
      (e.clientY - rect.top) / rect.height,
    )
  }

  if (fallback) {
    return (
      <div className="space-y-2">
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
    <div
      onClick={handleClick}
      className={cn(
        'relative rounded-2xl overflow-hidden border border-border/60',
        interactive ? 'cursor-crosshair' : 'cursor-not-allowed',
      )}
    >
      <canvas ref={canvasRef} className="max-w-full block" />
      {!interactive && (
        <div className="absolute inset-0 bg-background/30 backdrop-blur-sm flex items-center justify-center rounded-2xl">
          <span className="text-xs text-foreground bg-card/80 backdrop-blur px-3 py-1.5 rounded-full border border-border/60">
            {t.screen.manualOnly}
          </span>
        </div>
      )}
    </div>
  )
}
