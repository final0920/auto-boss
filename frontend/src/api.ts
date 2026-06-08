import redaxios from 'redaxios'

// Token is fetched from the backend via /api/token after initial page load.
// It is NOT stored in localStorage or any persistent browser storage.
let _token = ''

export function setToken(t: string) {
  _token = t
}

export function getToken() {
  return _token
}

const api = redaxios.create({
  baseURL: '/api',
  headers: {
    'Content-Type': 'application/json',
  },
})

// Inject auth token on every request
api.defaults.headers = api.defaults.headers ?? {}

// Interceptor-style wrapper: use typed helper functions instead of raw api
export async function apiGet<T>(path: string, params?: Record<string, unknown>): Promise<T> {
  const res = await api.get<T>(path, {
    params,
    headers: { Authorization: `Bearer ${_token}` },
  })
  return res.data
}

export async function apiPost<T>(path: string, body?: unknown): Promise<T> {
  const res = await api.post<T>(path, body, {
    headers: { Authorization: `Bearer ${_token}` },
  })
  return res.data
}

export async function apiPut<T>(path: string, body?: unknown): Promise<T> {
  const res = await api.put<T>(path, body, {
    headers: { Authorization: `Bearer ${_token}` },
  })
  return res.data
}

export async function apiDelete<T>(path: string): Promise<T> {
  const res = await api.delete<T>(path, {
    headers: { Authorization: `Bearer ${_token}` },
  })
  return res.data
}

export default api
