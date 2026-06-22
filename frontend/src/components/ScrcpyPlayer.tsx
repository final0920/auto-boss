import { useRef, useEffect, useState, useCallback } from 'react'
import { connectSocket } from '../lib/socket'
import { useI18n } from '../lib/i18n'
import { cn } from '../lib/utils'

interface ScrcpyPlayerProps {
  deviceId: string
  /** false 时在画面上叠加"仅手动"遮罩 */
  interactive: boolean
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

export function ScrcpyPlayer({ deviceId, interactive }: ScrcpyPlayerProps) {
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

      const socket = connectSocket()

      // 设备握手信息(device_name/width/height)，renderer 自适应，仅记录
      socket.on('device_info', (info: { device_name: string; width: number; height: number }) => {
        console.debug('scrcpy device_info', info)
      })

      // 视频帧：pts===null 为配置帧(SPS/PPS)，其余为编码帧；pts 单位微秒
      socket.on('frame', async (msg: { pts: number | null; data: ArrayBuffer }) => {
        if (!writer || disposed) return
        const data = new Uint8Array(msg.data)
        try {
          if (msg.pts === null) {
            await writer.write({ type: 'configuration', data })
            return
          }
          await writer.write({
            type: 'data',
            keyframe: containsH264Keyframe(data),
            pts: BigInt(msg.pts),
            data,
          })
        } catch {
          goFallback()
        }
      })

      // 后端通知降级(scrcpy server JAR 缺失等) → 切截图轮询
      socket.on('error', (msg: { message?: string; fallback?: string }) => {
        if (msg?.fallback === 'screenshot_polling') goFallback()
      })

      socket.emit('start', { serial: deviceId })
    }

    init().catch(goFallback)

    return () => {
      disposed = true
      const socket = connectSocket()
      socket.off('device_info')
      socket.off('frame')
      socket.off('error')
      socket.emit('stop', {})
      writer?.releaseLock()
      // 清空挂载点中的渲染器 canvas
      if (containerRef.current) containerRef.current.innerHTML = ''
    }
  }, [deviceId, fallback, goFallback])

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
      {/* 渲染器 canvas 动态插入此容器（只读模式不叠加任何遮罩，保持画面清晰） */}
      <div ref={containerRef} />
    </div>
  )
}
