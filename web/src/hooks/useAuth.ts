import { useMutation } from '@tanstack/react-query'
import { apiClient } from '../api/client'

function useLogin() {
  return useMutation({
    mutationFn: (body: { email: string; password: string }) =>
      apiClient('/auth/login', 'post', { body: JSON.stringify(body) }),
    onSuccess: (data: unknown) => {
      const token = (data as { accessToken?: string })?.accessToken
      if (token) {
        localStorage.setItem('accessToken', token)
      }
    },
  })
}

function useRegister() {
  return useMutation({
    mutationFn: (body: {
      email: string
      password: string
      displayName?: string
      consentPolicyVersion: string
    }) => apiClient('/auth/register', 'post', { body: JSON.stringify(body) }),
  })
}

function useVerifyEmail() {
  return useMutation({
    mutationFn: (body: { token: string }) =>
      apiClient('/auth/verify-email', 'post', { body: JSON.stringify(body) }),
  })
}

function useResetPassword() {
  return useMutation({
    mutationFn: (body: { email?: string; token?: string; newPassword?: string }) =>
      apiClient('/auth/password-reset', 'post', { body: JSON.stringify(body) }),
  })
}

function useLogout() {
  const logout = () => {
    localStorage.removeItem('accessToken')
    window.location.href = '/login'
  }
  return logout
}

function getToken(): string | null {
  return localStorage.getItem('accessToken')
}

export { useLogin, useRegister, useVerifyEmail, useResetPassword, useLogout, getToken }
