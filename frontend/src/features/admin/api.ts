import {
  mutationOptions,
  type QueryClient,
  queryOptions,
} from "@tanstack/react-query";

import { api, dataOf } from "@/api/client";

const scope = { id: "admin" };

export const adminQueries = {
  /** The sign-up code, or null while sign-up is closed (FR-005). */
  signupCode: () =>
    queryOptions({
      queryKey: ["admin", "signup-code"],
      queryFn: ({ signal }) =>
        dataOf(api.GET("/api/v1/admin/signup-code", { signal })),
    }),
  /** Every account, admins too (ADR-007). */
  organizers: () =>
    queryOptions({
      queryKey: ["admin", "organizers"],
      queryFn: ({ signal }) =>
        dataOf(api.GET("/api/v1/admin/organizers", { signal })),
    }),
};

/** Every write reloads what the admin sees, success or not (ADR-008). */
function reloaded(queryClient: QueryClient, key: "signup-code" | "organizers") {
  return () => queryClient.invalidateQueries({ queryKey: ["admin", key] });
}

export const adminMutations = {
  /** Sets the code, or closes sign-up with null (FR-005). */
  setSignupCode: (queryClient: QueryClient) =>
    mutationOptions({
      scope,
      mutationFn: (signupCode: string | null) =>
        dataOf(
          api.PUT("/api/v1/admin/signup-code", {
            body: { signup_code: signupCode },
          }),
        ),
      onSettled: reloaded(queryClient, "signup-code"),
    }),
  generateSignupCode: (queryClient: QueryClient) =>
    mutationOptions({
      scope,
      mutationFn: () => dataOf(api.POST("/api/v1/admin/signup-code/generate")),
      onSettled: reloaded(queryClient, "signup-code"),
    }),
  /**
   * Resets an account's password (FR-006, ADR-006): the response holds the
   * generated password, so the result is dropped as soon as nothing shows it.
   */
  resetPassword: (queryClient: QueryClient) =>
    mutationOptions({
      scope,
      gcTime: 0,
      mutationFn: (input: {
        userId: string;
        temporaryPassword: string | null;
      }) =>
        dataOf(
          api.POST("/api/v1/admin/organizers/{user_id}/password-reset", {
            params: { path: { user_id: input.userId } },
            body: { temporary_password: input.temporaryPassword },
          }),
        ),
      onSettled: reloaded(queryClient, "organizers"),
    }),
};
