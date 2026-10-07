import { useQuery, useQueryClient } from '@tanstack/react-query'
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import { api, setUnauthorizedHandler, tokenStore } from './api/client'
import type { TokenOut, User } from './api/types'

interface AuthState {
  user: User | null
  loading: boolean
  login: (login: string, password: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthState | null>(null)

export function AuthProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  const [token, setToken] = useState(tokenStore.get())

  const logout = useCallback(() => {
    tokenStore.clear()
    setToken(null)
    queryClient.clear()
  }, [queryClient])

  useEffect(() => setUnauthorizedHandler(logout), [logout])

  const me = useQuery({
    queryKey: ['me', token],
    queryFn: () => api<User>('/api/auth/me'),
    enabled: !!token,
    retry: false,
  })

  const login = async (loginName: string, password: string) => {
    const res = await api<TokenOut>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify({ login: loginName, password }),
    })
    tokenStore.set(res.access_token)
    setToken(res.access_token)
  }

  const value: AuthState = {
    user: token ? (me.data ?? null) : null,
    loading: !!token && me.isLoading,
    login,
    logout,
  }
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider')
  return ctx
}
