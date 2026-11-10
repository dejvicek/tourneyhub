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
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const me = useQuery({ ...authQueries.me(), retry: false });
  const logOut = useMutation(authMutations.logOut(queryClient));
  const layout = useLayout();

  if (me.data === undefined) {
    return me.isPending || onAuthScreen ? null : (
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
        <DropdownMenuLabel className="text-body-sm font-normal text-muted-foreground">
          {t("auth.account.signedInAs", { name })}
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild className="text-body-md">
          <Link to={paths.myLeagues}>{t("auth.account.myLeagues")}</Link>
        </DropdownMenuItem>
        <DropdownMenuItem asChild className="text-body-md">
          <Link to={paths.changePassword}>
            {t("auth.account.changePassword")}
          </Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem
          className="text-body-md"
          onSelect={() => {
            logOut.mutate(undefined, {
              onSettled: () => {
                void navigate(paths.login, { replace: true });
              },
            });
          }}
        >
          {t("auth.account.logOut")}
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
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
