import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router";

import { ApiError } from "@/api/client";
import { paths } from "@/lib/paths";

import { authQueries } from "./api";
import { useOutsideArea } from "./useOutsideArea";

/**
 * ADR-006: while an admin's reset requires a new password, the one screen
 * that works is the password change. Any other organizer or admin screen
 * goes there, so the account never sits on a page whose every call answers
 * 403. The server refuses those calls whatever this does.
 *
 * The account is read from the same `me` query as the account menu. If a
 * call answers 403 `password_change_required` (a reset made in another tab or
 * by an admin meanwhile), `me` is read again.
 */
export function PasswordChangeRedirect() {
  const navigate = useNavigate();
  const location = useLocation();
  const queryClient = useQueryClient();
  const outside = useOutsideArea();
  const me = useQuery({
    ...authQueries.me(),
    retry: false,
    enabled: !outside,
  });
  const required = me.data?.must_change_password === true;
  const onPasswordScreen = location.pathname === paths.changePassword;

  useEffect(() => {
    if (required && !outside && !onPasswordScreen) {
      void navigate(paths.changePassword, { replace: true });
    }
  }, [required, outside, onPasswordScreen, navigate]);

  useEffect(() => {
    const refused = (error: unknown) =>
      error instanceof ApiError && error.code === "password_change_required";
    const reread = () =>
      queryClient.invalidateQueries({ queryKey: authQueries.me().queryKey });
    const stopQueries = queryClient.getQueryCache().subscribe((event) => {
      if (event.type === "updated" && refused(event.query.state.error)) {
        void reread();
      }
    });
    const stopMutations = queryClient.getMutationCache().subscribe((event) => {
      if (event.type === "updated" && refused(event.mutation.state.error)) {
        void reread();
      }
    });
    return () => {
      stopQueries();
      stopMutations();
    };
  }, [queryClient]);

  return null;
}
