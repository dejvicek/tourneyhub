import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { generatePath, Link } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { PageFallback } from "@/components/PageFallback";
import { useLayout } from "@/hooks/useLayout";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

import { leagueQueries } from "./api";
import { CopyShareLink } from "./CopyShareLink";
import { DeleteLeague } from "./DeleteLeague";
import { LeagueDetailsForm } from "./LeagueDetailsForm";
import { PlacementPointsForm } from "./PlacementPointsForm";
import { SeasonsSection } from "./SeasonsSection";
import { SettingsSection } from "./SettingsSection";

/**
 * League settings (FR-011, FR-013, FR-020–FR-022, FR-070): cards in one
 * column on a phone, two from desktop width; the destructive card last.
 */
export function LeagueSettingsPage() {
  const { t } = useTranslation();
  const leagueId = useRouteParam("leagueId");
  const layout = useLayout();
  // The screen's main resource: a failure goes to the area's error boundary.
  const league = useQuery({
    ...leagueQueries.detail(leagueId),
    throwOnError: true,
  });
  const active = league.data?.seasons.find((s) => s.state === "active");

  return (
    <section className="space-y-6">
      <DocumentTitle screen={t("leagues.settings.title")} />
      <header className="space-y-2">
        <h1 className="font-display text-display-title">
          {t("leagues.settings.title")}
        </h1>
        <p className="text-body-md text-muted-foreground">
          {t("leagues.settings.lead")}
        </p>
      </header>
      {league.data === undefined ? (
        <PageFallback />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2 lg:items-start">
          <div className="space-y-4">
            <LeagueDetailsForm key={league.data.id} league={league.data} />
            <SettingsSection
              id="share-link"
              title={t("leagues.settings.share.heading")}
              description={t("leagues.settings.share.body")}
            >
              {/* The desktop sidebar has its own copy button. */}
              {layout !== "desktop" && <CopyShareLink leagueId={leagueId} />}
              <Link
                to={generatePath(paths.publicLeague, {
                  shareToken: league.data.share_token,
                })}
                className="inline-flex min-h-11 items-center text-body-md font-bold text-primary underline underline-offset-4"
              >
                {t("leagues.settings.share.open")}
              </Link>
            </SettingsSection>
          </div>
          <div className="space-y-4">
            {active !== undefined && (
              <PlacementPointsForm
                key={active.id}
                leagueId={leagueId}
                season={active}
              />
            )}
            <SeasonsSection leagueId={leagueId} seasons={league.data.seasons} />
            <DeleteLeague leagueId={leagueId} name={league.data.name} />
          </div>
        </div>
      )}
    </section>
  );
}
