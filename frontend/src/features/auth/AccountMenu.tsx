import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link, useMatch, useNavigate } from "react-router";

import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useLayout } from "@/hooks/useLayout";
import { paths } from "@/lib/paths";

import { authMutations, authQueries } from "./api";

/**
 * The organizer's account in the header, next to the language switch
 * (FR-081): their name opens My leagues, Change password and Log out. Logged
 * out, a "Log in" link. Share-link views have no account (FR-070), and the
 * auth screens need no link to themselves.
 */
export function AccountMenu() {
  const publicLeague = useMatch(paths.publicLeague);
  const publicTournament = useMatch(paths.publicTournament);
  const login = useMatch(paths.login);
  const signUp = useMatch(paths.signUp);

  if (publicLeague !== null || publicTournament !== null) {
    return null;
  }
  return <Account onAuthScreen={login !== null || signUp !== null} />;
}

function Account({ onAuthScreen }: { onAuthScreen: boolean }) {
  const { t } = useTranslation();
  const me = useQuery({ ...authQueries.me(), retry: false });
  const layout = useLayout();

  if (me.data === undefined) {
    return me.isLoading || onAuthScreen ? null : (
      <Button asChild variant="text">
        <Link to={paths.login}>{t("auth.account.logIn")}</Link>
      </Button>
    );
  }
  const name = me.data.display_name;
  const wide = layout === "desktop";
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        {wide ? (
          // Desktop: the sidebar's user, avatar and name (Figma "D Dejv").
          <Button type="button" variant="ghost" className="justify-start px-2">
            <Initial name={name} />
            <span>{t("auth.account.signedInAs", { name })}</span>
          </Button>
        ) : (
          <Button
            type="button"
            variant="outline"
            aria-label={t("auth.account.menu", { name })}
            size="icon"
          >
            <Initial name={name} />
          </Button>
        )}
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="min-w-56">
        <AccountMenuItems />
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/**
 * The account's entries in a menu: who is signed in, My leagues,
 * Administration (instance admins), Change password and Log out. The header's account menu and a tournament's
 * overflow menu on a phone both show them.
 */
export function AccountMenuItems() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const me = useQuery({ ...authQueries.me(), retry: false });
  // The menu closes, and this component with it, before the answer comes
  // back, so the redirect is part of the mutation's options, not of `mutate`.
  const clearSession = authMutations.logOut(queryClient);
  const logOut = useMutation({
    ...clearSession,
    onSettled: (...settled) => {
      void clearSession.onSettled?.(...settled);
      void navigate(paths.login, { replace: true });
    },
  });
  const name = me.data?.display_name;
  // ADR-006: until the new password is chosen, only it and log out work.
  const mustChangePassword = me.data?.must_change_password === true;
  const isAdmin = me.data?.is_admin === true;

  return (
    <>
      {name !== undefined && (
        <>
          <DropdownMenuLabel className="text-body-sm font-normal text-muted-foreground">
            {t("auth.account.signedInAs", { name })}
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
        </>
      )}
      {!mustChangePassword && (
        <DropdownMenuItem asChild className="text-body-md">
          <Link to={paths.myLeagues}>{t("auth.account.myLeagues")}</Link>
        </DropdownMenuItem>
      )}
      {isAdmin && !mustChangePassword && (
        <DropdownMenuItem asChild className="text-body-md">
          <Link to={paths.admin}>{t("auth.account.administration")}</Link>
        </DropdownMenuItem>
      )}
      <DropdownMenuItem asChild className="text-body-md">
        <Link to={paths.changePassword}>
          {t("auth.account.changePassword")}
        </Link>
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem
        className="text-body-md"
        onSelect={() => {
          logOut.mutate();
        }}
      >
        {t("auth.account.logOut")}
      </DropdownMenuItem>
    </>
  );
}

function Initial({ name }: { name: string }) {
  return (
    <span
      aria-hidden="true"
      className="flex size-8 shrink-0 items-center justify-center rounded-full bg-nav-active font-display text-display-section text-nav-active-foreground"
    >
      {initialOf(name)}
    </span>
  );
}

/** The first letter of the name, as the design's sidebar avatar ("D Dejv"). */
function initialOf(name: string): string {
  return Array.from(name.trim())[0]?.toUpperCase() ?? "?";
}
