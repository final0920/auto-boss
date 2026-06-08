import { io, type Socket } from 'socket.io-client'
import { getToken } from '../api'

let _socket: Socket | null = null

// Lazy singleton: connect on first call, reuse afterwards.
export function getSocket(): Socket {
  if (_socket && _socket.connected) return _socket

  _socket = io('/', {
    path: '/socket.io',
    transports: ['websocket'],
    auth: { token: getToken() },
    autoConnect: false,
  })

  return _socket
}

export function connectSocket() {
  const s = getSocket()
  if (!s.connected) s.connect()
  return s
}

export function disconnectSocket() {
  _socket?.disconnect()
}
