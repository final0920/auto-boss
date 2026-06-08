import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useRef } from 'react'
import { useI18n } from '../lib/i18n'
import { useDevice } from '../lib/device-context'
import { getToken } from '../api'

function TerminalPanel({ deviceId }: { deviceId: string }) {
  const containerRef = useRef<HTMLDivElement>(null)
  const termRef = useRef<import('@xterm/xterm').Terminal | null>(null)
  const wsRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    let term: import('@xterm/xterm').Terminal
    let fitAddon: import('@xterm/addon-fit').FitAddon

    async function init() {
      const { Terminal } = await import('@xterm/xterm')
      const { FitAddon } = await import('@xterm/addon-fit')
      // @ts-ignore — CSS module import; bundler handles this
      await import('@xterm/xterm/css/xterm.css')

      if (!containerRef.current) return

      term = new Terminal({
        cursorBlink: true,
        fontSize: 13,
        fontFamily: 'Menlo, Monaco, "Courier New", monospace',
        theme: { background: '#0d1117', foreground: '#c9d1d9' },
      })
      fitAddon = new FitAddon()
      term.loadAddon(fitAddon)
      term.open(containerRef.current)
      fitAddon.fit()
      termRef.current = term

      // Connect WebSocket terminal
      const token = getToken()
      const ws = new WebSocket(
        `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/ws/terminal/${deviceId}?token=${encodeURIComponent(token)}`,
      )
      wsRef.current = ws

      ws.onopen = () => term.writeln('\r\n\x1b[32mConnected\x1b[0m\r\n')
      ws.onmessage = e => term.write(e.data)
      ws.onclose = () => term.writeln('\r\n\x1b[31mDisconnected\x1b[0m')

      term.onData(data => {
        if (ws.readyState === WebSocket.OPEN) ws.send(data)
      })

      const observer = new ResizeObserver(() => fitAddon.fit())
      observer.observe(containerRef.current)

      return () => observer.disconnect()
    }

    init()

    return () => {
      wsRef.current?.close()
      termRef.current?.dispose()
    }
  }, [deviceId])

  return (
    <div ref={containerRef} className="w-full h-full min-h-[400px]" />
  )
}

function TerminalPage() {
  const { t } = useI18n()
  const { activeDevice, setDeviceMode } = useDevice()
  const isManual = activeDevice?.mode === 'MANUAL'

  if (!activeDevice) {
    return (
      <div className="p-6 flex items-center justify-center h-full text-muted-foreground">
        {t.device.noDevice}
      </div>
    )
  }

  return (
    <div className="p-6 space-y-4 h-full flex flex-col">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">{t.terminal.title}</h1>
        {!isManual && (
          <button
            onClick={() => setDeviceMode(activeDevice.id, 'MANUAL')}
            className="px-3 py-1.5 text-sm rounded bg-primary text-primary-foreground hover:opacity-90"
          >
            {t.terminal.switchManual}
          </button>
        )}
      </div>

      {!isManual ? (
        <div className="flex-1 flex items-center justify-center rounded-lg bg-black/90 text-yellow-400 text-sm">
          {t.terminal.manualOnly}
        </div>
      ) : (
        <div className="flex-1 rounded-lg overflow-hidden border border-border bg-black">
          <TerminalPanel deviceId={activeDevice.id} />
        </div>
      )}
    </div>
  )
}

export const Route = createFileRoute('/terminal')({
  component: TerminalPage,
})
