import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { generatePath } from "react-router";

import { Button } from "@/components/ui/button";
import { leagueQueries } from "@/features/leagues/api";
import { paths } from "@/lib/paths";

/** Copies the league's share link (FR-070) and announces the outcome. */
export function CopyShareLink({ leagueId }: { leagueId: string }) {
  const { t } = useTranslation();
  const settings = useQuery(leagueQueries.settings(leagueId));
  const [status, setStatus] = useState<"copied" | "failed" | null>(null);
  const shareToken = settings.data?.share_token;

  return (
    <div className="space-y-1">
      <Button
        type="button"
        variant="outline"
        className="w-full"
        disabled={shareToken === undefined}
        onClick={() => {
          if (shareToken === undefined) {
            return;
          }
          const url = new URL(
            generatePath(paths.publicLeague, { shareToken }),
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
        {t("shell.copyShareLink")}
      </Button>
      <p role="status" className="text-caption text-muted-foreground">
        {status === "copied" && t("shell.shareLinkCopied")}
        {status === "failed" && t("shell.shareLinkFailed")}
      </p>
    </div>
  );
}
