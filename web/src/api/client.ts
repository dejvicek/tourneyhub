import type { paths } from './schema'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1'

function getAuthHeaders(): Record<string, string> {
  const token = localStorage.getItem('accessToken')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

export async function apiClient<T extends keyof paths>(
  path: T | string,
  method: T extends keyof paths ? keyof paths[T] : string,
  options?: RequestInit,
): Promise<unknown> {
  const url = `${API_BASE_URL}${String(path)}`
  const response = await fetch(url, {
    ...options,
    method: String(method).toUpperCase(),
    headers: {
      'Content-Type': 'application/json',
      ...getAuthHeaders(),
      ...options?.headers,
    },
  })

  if (response.status === 401) {
    localStorage.removeItem('accessToken')
    window.location.href = '/login'
    throw new Error('Unauthorized')
  }

  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`)
  }

  if (response.status === 204) {
    return null
  }

  return response.json()
}
