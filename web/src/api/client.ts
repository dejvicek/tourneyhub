import type { paths } from './schema';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080/api/v1';

export async function apiClient<T extends keyof paths>(
  path: T,
  method: keyof paths[T],
  options?: RequestInit
): Promise<unknown> {
  const url = `${API_BASE_URL}${String(path)}`;
  const response = await fetch(url, {
    ...options,
    method: String(method).toUpperCase(),
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });

  if (!response.ok) {
    throw new Error(`API Error: ${response.status} ${response.statusText}`);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return null;
  }

  return response.json();
}