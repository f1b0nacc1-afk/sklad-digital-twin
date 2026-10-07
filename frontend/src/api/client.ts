const TOKEN_KEY = 'sklad.token'

export const tokenStore = {
  get: () => localStorage.getItem(TOKEN_KEY),
  set: (token: string) => localStorage.setItem(TOKEN_KEY, token),
  clear: () => localStorage.removeItem(TOKEN_KEY),
}

export class ApiError extends Error {
  status: number
  detail: unknown

  constructor(status: number, detail: unknown) {
    super(typeof detail === 'string' ? detail : `HTTP ${status}`)
    this.status = status
    this.detail = detail
  }
}

let onUnauthorized: () => void = () => {}

export function setUnauthorizedHandler(handler: () => void) {
  onUnauthorized = handler
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers)
  const token = tokenStore.get()
  if (token) headers.set('Authorization', `Bearer ${token}`)
  if (init.body && !(init.body instanceof FormData)) headers.set('Content-Type', 'application/json')

  const resp = await fetch(path, { ...init, headers })
  if (resp.status === 401 && token) {
    tokenStore.clear()
    onUnauthorized()
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => null)
    throw new ApiError(resp.status, body?.detail ?? resp.statusText)
  }
  return resp.status === 204 ? (undefined as T) : resp.json()
}
