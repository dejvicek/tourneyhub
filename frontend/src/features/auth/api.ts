import {
  mutationOptions,
  type QueryClient,
  queryOptions,
} from "@tanstack/react-query";

import { api, dataOf } from "@/api/client";
import { provisionalApi } from "@/api/provisional";
import { forgetSession, isLoggedOut, setAccessToken } from "@/api/token";
import type { Language } from "@/i18n/language";

// Every route here is the backend's; only the demo account is the demo's.

/** The refresh and logout routes require it against CSRF (ADR-006). */
const CSRF = { "X-Requested-With": "tourneyhub" };

export const authQueries = {
  me: () =>
    queryOptions({
      queryKey: ["me"],
      queryFn: ({ signal }) => dataOf(api.GET("/api/v1/me", { signal })),
      // After a logout there is nobody to ask about (it would only be a 401).
      enabled: !isLoggedOut(),
    }),
  /** Demo only: the seeded account the login screen offers. */
  demoAccount: () =>
    queryOptions({
      queryKey: ["demo", "account"],
      queryFn: ({ signal }) =>
        dataOf(provisionalApi.GET("/api/v1/demo/account", { signal })),
      staleTime: Infinity,
    }),
};

export interface Credentials {
  email: string;
  password: string;
}

export interface SignUp extends Credentials {
  signupCode: string;
  displayName: string;
  language: Language;
}

export const authMutations = {
  logIn: (queryClient: QueryClient) =>
    mutationOptions({
      mutationFn: async (credentials: Credentials) => {
        const { access_token } = await dataOf(
          api.POST("/api/v1/auth/login", { body: credentials }),
        );
        setAccessToken(access_token);
      },
      // eslint-disable-next-line no-restricted-syntax -- only a success sets the token; a failure leaves nothing to reload
      onSuccess: () => queryClient.invalidateQueries({ queryKey: ["me"] }),
    }),
  signUp: (queryClient: QueryClient) =>
    mutationOptions({
      mutationFn: async (input: SignUp) => {
        const { access_token } = await dataOf(
          api.POST("/api/v1/auth/signup", {
            body: {
              signup_code: input.signupCode,
              email: input.email,
              display_name: input.displayName,
              password: input.password,
              language: input.language,
            },
          }),
        );
        setAccessToken(access_token);
      },
      // eslint-disable-next-line no-restricted-syntax -- only a success sets the token; a failure leaves nothing to reload
      onSuccess: () => queryClient.invalidateQueries({ queryKey: ["me"] }),
    }),
  changePassword: () =>
    mutationOptions({
      mutationFn: (input: { currentPassword: string; newPassword: string }) =>
        dataOf(
          api.POST("/api/v1/auth/password", {
            body: {
              current_password: input.currentPassword,
              new_password: input.newPassword,
            },
          }),
        ),
    }),
  logOut: (queryClient: QueryClient) =>
    mutationOptions({
      mutationFn: () =>
        dataOf(
          api.POST("/api/v1/auth/logout", {
            params: { header: CSRF },
          }),
        ),
      // Logged out on this device whatever the answer: nothing of the
      // organizer's data stays in the cache.
      onSettled: () => {
        forgetSession();
        queryClient.clear();
      },
    }),
};

/**
 * Restores the session from the refresh cookie when no access token is in
 * memory, as after a reload (ADR-006). True if it worked.
 */
export async function restoreSession(): Promise<boolean> {
  if (isLoggedOut()) {
    return false;
  }
  try {
    const { access_token } = await dataOf(
      api.POST("/api/v1/auth/refresh", { params: { header: CSRF } }),
    );
    setAccessToken(access_token);
    return true;
  } catch {
    return false;
  }
}
