import { useTranslation } from "react-i18next";
import { generatePath, Link } from "react-router";

import { Button } from "@/components/ui/button";
import { paths } from "@/lib/paths";

import { seededEntries } from "./setup/entries";
import { HalvesSection } from "./setup/HalvesSection";
import { Notice } from "./setup/Notice";
import { PairMaker } from "./setup/PairMaker";
import { SeedingSection } from "./setup/SeedingSection";
import { type SetupData, SetupPage } from "./setup/SetupPage";
import { TopPlayersSection } from "./setup/TopPlayersSection";

/**
 * Screen 4: the halves and the draw of a DYP, the pairs of a Doubles, the
 * seeding of Singles, the top players of a Monster DYP (FR-033, FR-034, FR-041).
 */
export function SetupDrawPage() {
  const { t } = useTranslation();
  return (
    <SetupPage
      step={3}
      title={(type) => t(`tournaments.setup.draw.title.${type}`)}
    >
      {(data) => <DrawStep data={data} />}
    </SetupPage>
  );
}

function DrawStep({ data }: { data: SetupData }) {
  const { t } = useTranslation();
  const { leagueId, tournamentId, tournament, setup } = data;
  const entries = seededEntries(data);
  const type = tournament.type;
  const unpaired =
    type === "doubles" && entries.length * 2 !== setup.player_ids.length;
  const canContinue =
    type === "monster_dyp" || (entries.length >= 2 && !unpaired);
  const params = { leagueId, tournamentId };

  return (
    <div className="grid gap-6">
      <div className="grid gap-8 md:grid-cols-2 md:items-start">
        {type === "dyp" && <HalvesSection data={data} />}
        {type === "doubles" && <PairMaker data={data} />}
        {type === "monster_dyp" ? (
          <TopPlayersSection data={data} />
        ) : (
          <SeedingSection data={data} />
        )}
      </div>

      {unpaired && (
        <Notice variant="warning" title={t("tournaments.setup.draw.unpaired")}>
          {t("tournaments.setup.draw.unpairedBody")}
        </Notice>
      )}

      <div className="flex flex-col gap-3 md:flex-row md:justify-between">
        <Button asChild variant="ghost" className="h-14 px-6 text-button-sm">
          <Link to={generatePath(paths.setupPlayers, params)}>
            {t("tournaments.setup.back")}
          </Link>
        </Button>
        {/* TODO(foundation-buttons): size="lg" once Button has the 56 px Primary size */}
        {canContinue ? (
          <Button asChild className="h-14 px-6 text-button-lg md:min-w-60">
            <Link to={generatePath(paths.setupReview, params)}>
              {t("tournaments.setup.draw.next")}
            </Link>
          </Button>
        ) : (
          <Button disabled className="h-14 px-6 text-button-lg md:min-w-60">
            {t("tournaments.setup.draw.next")}
          </Button>
        )}
      </div>
    </div>
  );
}
