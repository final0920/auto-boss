import { useEffect, useRef, useState } from 'react'
import { getToken } from '../api'

interface TerminalPanelProps {
  deviceId: string
}

export function TerminalPanel({ deviceId }: TerminalPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const [status, setStatus] = useState<'connecting' | 'connected' | 'disconnected'>('connecting')

  useEffect(() => {
    let disposed = false
    setStatus('connecting')

    async function init() {
      const { Terminal } = await import('@xterm/xterm')
      const { FitAddon } = await import('@xterm/addon-fit')
      // @ts-ignore — CSS module handled by bundler
      await import('@xterm/xterm/css/xterm.css')

      if (disposed || !containerRef.current) return

      const term = new Terminal({
        cursorBlink: true,
        fontSize: 13,
        fontFamily: 'SFMono-Regular, Menlo, Monaco, "Courier New", monospace',
        theme: { background: '#0d1117', foreground: '#c9d1d9' },
      })
      const fitAddon = new FitAddon()
      term.loadAddon(fitAddon)
      term.open(containerRef.current)
      fitAddon.fit()

      const token = getToken()
      const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
      const ws = new WebSocket(
        `${proto}://${window.location.host}/ws/terminal/${deviceId}?token=${encodeURIComponent(token)}`,
      )

      ws.onopen = () => {
        setStatus('connected')
        term.writeln('\r\n\x1b[32mConnected\x1b[0m\r\n')
      }
      ws.onmessage = e => term.write(typeof e.data === 'string' ? e.data : new Uint8Array(e.data))
      ws.onclose = () => {
        setStatus('disconnected')
        term.writeln('\r\n\x1b[31mDisconnected\x1b[0m')
      }

      term.onData(data => { if (ws.readyState === WebSocket.OPEN) ws.send(data) })

      const observer = new ResizeObserver(() => fitAddon.fit())
      if (containerRef.current) observer.observe(containerRef.current)

      return () => {
        observer.disconnect()
        ws.close()
        term.dispose()
      }
    }

    let cleanup: (() => void) | undefined
    init().then(fn => { cleanup = fn })

    return () => {
      disposed = true
      cleanup?.()
    }
  }, [deviceId])

  /* 状态指示点颜色 */
  const dotCls =
    status === 'connected' ? 'bg-success' :
    status === 'disconnected' ? 'bg-destructive' :
    'bg-muted-foreground animate-pulse'

  const statusLabel =
    status === 'connected' ? '已连接' :
    status === 'disconnected' ? '已断开' :
    '连接中…'

  return (
    <div className="flex flex-col gap-2 h-full">
      {/* 标题栏：设备 ID + 连接状态 */}
      <div className="flex items-center gap-2 px-1">
        <span className={`w-2 h-2 rounded-full shrink-0 ${dotCls}`} />
        <span className="font-mono text-xs text-muted-foreground">
          {deviceId} — {statusLabel}
        </span>
      </div>
      <div
        ref={containerRef}
        className="flex-1 min-h-[400px] rounded-xl border border-border/60 overflow-hidden"
        style={{ backdropFilter: 'blur(2px)' }}
      />
    </div>
  )
}
