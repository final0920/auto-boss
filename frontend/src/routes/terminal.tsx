import { createFileRoute } from '@tanstack/react-router'
import { useEffect, useRef } from 'react'
import { useI18n } from '../lib/i18n'
import { useDevice } from '../lib/device-context'
import { getToken } from '../api'
import { Button, Card, CardHeader, CardTitle, CardContent } from '../components/ui'

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
        fontFamily: 'SFMono-Regular, Menlo, Monaco, "Courier New", monospace',
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
    <div
      ref={containerRef}
      className="w-full h-full min-h-[400px]"
    />
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
        <h1 className="text-2xl font-serif font-semibold text-foreground">{t.terminal.title}</h1>
        {!isManual && (
          <Button
            onClick={() => setDeviceMode(activeDevice.id, 'MANUAL')}
            size="sm"
          >
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
        <Card className="flex-1 overflow-hidden p-0">
          <CardHeader className="pb-0 px-4 pt-3">
            <CardTitle className="text-sm font-mono text-muted-foreground">
              {activeDevice.serial}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-0 h-full">
            {/* xterm 容器：rounded-xl 玻璃边框 */}
            <div className="rounded-xl border border-border/60 overflow-hidden mx-4 mb-4" style={{ backdropFilter: 'blur(2px)' }}>
              <TerminalPanel deviceId={activeDevice.id} />
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  )
}

export const Route = createFileRoute('/terminal')({
  component: TerminalPage,
})
