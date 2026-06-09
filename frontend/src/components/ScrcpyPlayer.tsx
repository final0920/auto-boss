import { useRef, useEffect, useState, useCallback } from 'react'
import { connectSocket } from '../lib/socket'
import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'

interface ScrcpyPlayerProps {
  deviceId: string
  /** false 时在画面上叠加"仅手动"遮罩 */
  interactive: boolean
  onTap?: (x: number, y: number) => void
}

/** 截图轮询降级路径（WebCodecs 不可用时启用） */
function useScreenshotPolling(deviceId: string, active: boolean) {
  const [url, setUrl] = useState<string | null>(null)

  useEffect(() => {
    if (!active) return
    let alive = true
    ;(async () => {
      while (alive) {
        setUrl(`/api/media/screenshot/${deviceId}?t=${Date.now()}`)
        await new Promise(r => setTimeout(r, 1000))
      }
    })()
    return () => { alive = false }
  }, [deviceId, active])

  return url
}

/**
 * 判断一段 H.264 Annex-B 数据中是否含有 IDR（关键帧）NAL 单元。
 * 检测 start-code 后的 NAL type（低5位 = 5 → IDR）。
 */
function containsH264Keyframe(buf: Uint8Array): boolean {
  for (let i = 0; i + 4 < buf.length; i++) {
    const is4 = buf[i] === 0 && buf[i + 1] === 0 && buf[i + 2] === 0 && buf[i + 3] === 1
    const is3 = buf[i] === 0 && buf[i + 1] === 0 && buf[i + 2] === 1
    if (is4 || is3) {
      const nalByte = buf[i + (is4 ? 4 : 3)]
      if (nalByte !== undefined && (nalByte & 0x1f) === 5) return true
    }
  }
  return false
}

export function ScrcpyPlayer({ deviceId, interactive, onTap }: ScrcpyPlayerProps) {
  const { t } = useI18n()
  // 挂载点 div，解码器渲染器的 canvas 会直接插入其中
  const containerRef = useRef<HTMLDivElement>(null)
  const [fallback, setFallback] = useState(false)
  const [codecReady, setCodecReady] = useState(false)
  const screenshotUrl = useScreenshotPolling(deviceId, fallback)

  const goFallback = useCallback(() => setFallback(true), [])

  // WebCodecs 解码路径
  useEffect(() => {
    if (fallback) return
    if (!('VideoDecoder' in window)) { goFallback(); return }

    let disposed = false
    let writer: WritableStreamDefaultWriter | null = null

    async function init() {
      const { WebCodecsVideoDecoder, BitmapVideoFrameRenderer } =
        await import('@yume-chan/scrcpy-decoder-webcodecs')
      const { ScrcpyVideoCodecId } = await import('@yume-chan/scrcpy')

      if (disposed || !containerRef.current) return

      // 把渲染器的内部 canvas 插入挂载点
      const renderer = new BitmapVideoFrameRenderer()
      const rendererCanvas = renderer.canvas as HTMLCanvasElement
      rendererCanvas.className = 'max-w-full block'
      containerRef.current.appendChild(rendererCanvas)

      let decoder
      try {
        decoder = new WebCodecsVideoDecoder({
          codec: ScrcpyVideoCodecId.H264,
          renderer,
        })
      } catch {
        goFallback()
        return
      }

      writer = decoder.writable.getWriter() as WritableStreamDefaultWriter
      if (!disposed) setCodecReady(true)

      let configSent = false  // SPS/PPS 配置包只发一次

      const socket = connectSocket()
      socket.on('video-data', async (raw: ArrayBuffer | Uint8Array) => {
        if (!writer || disposed) return
        const data = raw instanceof Uint8Array ? raw : new Uint8Array(raw)
        try {
          if (!configSent) {
            // 首帧同时作为 configuration 包（含 SPS/PPS）
            await writer.write({ type: 'configuration', data })
            configSent = true
          }
          await writer.write({
            type: 'data',
            keyframe: containsH264Keyframe(data),
            pts: BigInt(Math.round(performance.now() * 1000)),
            data,
          })
        } catch {
          goFallback()
        }
      })

      socket.emit('join-device', deviceId)
    }

    init().catch(goFallback)

    return () => {
      disposed = true
      const socket = connectSocket()
      socket.off('video-data')
      socket.emit('leave-device', deviceId)
      writer?.releaseLock()
      // 清空挂载点中的渲染器 canvas
      if (containerRef.current) containerRef.current.innerHTML = ''
    }
  }, [deviceId, fallback, goFallback])

  const handleClick = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!interactive || !onTap) return
    const rect = e.currentTarget.getBoundingClientRect()
    onTap(
      (e.clientX - rect.left) / rect.width,
      (e.clientY - rect.top) / rect.height,
    )
  }

  // 截图降级路径
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
      {/* WebCodecs 等待首帧时显示占位骨架 */}
      {!codecReady && (
        <div className="absolute inset-0 flex items-center justify-center bg-muted/60 rounded-2xl min-h-[200px]">
          <span className="text-xs text-muted-foreground animate-pulse">等待视频流…</span>
        </div>
      )}
      {/* 渲染器 canvas 动态插入此容器 */}
      <div ref={containerRef} />
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
