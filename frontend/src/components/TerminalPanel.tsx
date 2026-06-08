import { useEffect, useRef } from 'react'
import { getToken } from '../api'

interface TerminalPanelProps {
  deviceId: string
}

export function TerminalPanel({ deviceId }: TerminalPanelProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    let disposed = false

    async function init() {
      const { Terminal } = await import('@xterm/xterm')
      const { FitAddon } = await import('@xterm/addon-fit')
      // @ts-ignore — CSS module handled by bundler
      await import('@xterm/xterm/css/xterm.css')

      if (disposed || !containerRef.current) return

      const term = new Terminal({
        cursorBlink: true,
        fontSize: 13,
        fontFamily: 'Menlo, Monaco, "Courier New", monospace',
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

      ws.onopen = () => term.writeln('\r\n\x1b[32mConnected\x1b[0m\r\n')
      ws.onmessage = e => term.write(typeof e.data === 'string' ? e.data : new Uint8Array(e.data))
      ws.onclose = () => term.writeln('\r\n\x1b[31mDisconnected\x1b[0m')

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

  return <div ref={containerRef} className="w-full h-full min-h-[400px]" />
}
