import { io, type Socket } from 'socket.io-client'
import { getToken } from '../api'

let _socket: Socket | null = null

// Lazy singleton: connect on first call, reuse afterwards.
function getSocket(): Socket {
  if (_socket && _socket.connected) return _socket

  // scrcpy 视频流走 /scrcpy 命名空间；token 放 query(后端 sio_auth_ok 从 QUERY_STRING 读)
  _socket = io('/scrcpy', {
    path: '/socket.io',
    transports: ['websocket'],
    query: { token: getToken() },
    autoConnect: false,
  })

  return _socket
}

export function connectSocket() {
  const s = getSocket()
  if (!s.connected) s.connect()
  return s
}
