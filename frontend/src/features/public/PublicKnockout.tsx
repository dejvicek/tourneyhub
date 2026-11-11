import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type {
  BracketMatchData as BracketMatch,
  BracketRoundData as BracketRound,
  BracketSideData as BracketSide,
} from "@/features/finals/api";
import type { BracketContext } from "@/features/tournaments/finals/bracketContext";
import {
  BracketView,
  CompactBracket,
  RoundList,
} from "@/features/tournaments/finals/BracketView";
import { PlacesSoFar } from "@/features/tournaments/finals/PlacesSoFar";
import { useLayout } from "@/hooks/useLayout";

import { type PublicPlayer, publicQueries, type PublicTournament } from "./api";
import { useNames } from "./useNames";

/**
 * The knockout, read-only (FR-070, FR-072): the same bracket as the
 * organizer's screen 9, with no way to enter a result, and while it runs the
 * places already decided.
 */
export function PublicKnockout({
  shareToken,
  tournament,
  players,
}: {
  shareToken: string;
  tournament: PublicTournament;
  players: PublicPlayer[];
}) {
  const { t } = useTranslation();
  const layout = useLayout();
  const names = useNames(players, tournament);
  const bracket = useQuery(
    publicQueries.bracket(shareToken, tournament.id, true),
  );
  const places = useQuery(
    publicQueries.places(
      shareToken,
      tournament.id,
      tournament.state !== "finished",
    ),
  );

  const ctx: BracketContext = {
    sideName: (side: BracketSide) =>
      side.is_bye
        ? t("finals.knockout.bye")
        : side.entry_id === null
          ? t("finals.knockout.tbd")
          : names.ofEntry(side.entry_id),
    resultHref: () => null,
    matchTitle: (round: BracketRound, match: BracketMatch) =>
      match.kind === "third_place"
        ? t("finals.matchTitle.third_place")
        : t(`finals.matchTitle.${round.name}`, { n: match.position }),
  };
  const shape = bracket.data;

  return (
    <section aria-labelledby="knockout" className="min-w-0 space-y-3">
      <h2 id="knockout" className="font-display text-display-section">
        {t("publicView.tournament.knockoutHeading")}
      </h2>
      {shape === undefined ? (
        bracket.isError ? (
          <p role="alert" className="text-body-md">
            {t("publicView.tournament.loadFailed")}
          </p>
        ) : (
          <p role="status" className="text-body-md text-muted-foreground">
            {t("loading")}
          </p>
        )
      ) : layout === "phone" ? (
        shape.size <= 4 ? (
          <CompactBracket bracket={shape} ctx={ctx} />
        ) : (
          <RoundList bracket={shape} ctx={ctx} />
        )
      ) : (
        <BracketView bracket={shape} ctx={ctx} />
      )}
      {tournament.state !== "finished" && places.data !== undefined && (
        <PlacesSoFar
          rows={places.data.rows}
          entryName={(entryId) => names.ofEntry(entryId)}
        />
      )}
    </section>
  );
}
