import { api } from './client'
import type { UserProfile, CopyTradeConfig, Position, TradeLogEntry } from './types'

export const userApi = {
  getMe: () => api.get<UserProfile>('/me'),
  updateSettings: (data: { language?: string }) => api.patch<UserProfile>('/settings', data),
}

export const configApi = {
  list: () => api.get<CopyTradeConfig[]>('/configs'),
  create: (data: Partial<CopyTradeConfig>) => api.post<CopyTradeConfig>('/configs', data),
  update: (id: string, data: Partial<CopyTradeConfig>) => api.patch<CopyTradeConfig>(`/configs/${id}`, data),
}

export const positionApi = {
  list: () => api.get<Position[]>('/positions'),
}

export const historyApi = {
  list: (page = 1, limit = 20) => api.get<TradeLogEntry[]>(`/history?page=${page}&limit=${limit}`),
}
