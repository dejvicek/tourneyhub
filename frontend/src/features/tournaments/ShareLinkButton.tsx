import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { generatePath } from "react-router";

import { Button } from "@/components/ui/button";
import { CheckIcon, LinkIcon } from "@/components/ui/icons";
import { leagueQueries } from "@/features/leagues/api";
import { paths } from "@/lib/paths";

/**
 * The share-link icon in a tournament's header (Figma 6 and 10): copies the
 * viewer's link to this tournament (FR-070) and announces the outcome.
 */
export function ShareLinkButton({
  leagueId,
  tournamentId,
}: {
  leagueId: string;
  tournamentId: string;
}) {
  const { t } = useTranslation();
  const league = useQuery(leagueQueries.detail(leagueId));
  const [status, setStatus] = useState<"copied" | "failed" | null>(null);
  const shareToken = league.data?.share_token;

  return (
    <>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        aria-label={t("tournaments.header.shareLink")}
        disabled={shareToken === undefined}
        onClick={() => {
          if (shareToken === undefined) {
            return;
          }
          const url = new URL(
            generatePath(paths.publicTournament, { shareToken, tournamentId }),
            window.location.origin,
          );
          navigator.clipboard.writeText(url.href).then(
            () => {
              setStatus("copied");
            },
            () => {
              setStatus("failed");
            },
          );
        }}
      >
        {status === "copied" ? <CheckIcon /> : <LinkIcon />}
      </Button>
      <span aria-live="polite" className="sr-only">
        {status === "copied" && t("shell.shareLinkCopied")}
        {status === "failed" && t("shell.shareLinkFailed")}
      </span>
    </>
  );
}
