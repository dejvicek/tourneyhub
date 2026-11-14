import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";

import type { BracketSideData as BracketSide } from "@/features/finals/api";
import {
  type BracketContext,
  bracketTitles,
} from "@/features/tournaments/finals/bracketContext";
import {
  BracketView,
  CompactBracket,
  RoundList,
} from "@/features/tournaments/finals/BracketView";
import { PlacesSoFar } from "@/features/tournaments/finals/PlacesSoFar";
import { isLordHaveMercy } from "@/features/tournaments/finals/remix";
import { RemixRounds } from "@/features/tournaments/finals/RemixRounds";
import { useLayout } from "@/hooks/useLayout";

import { type PublicPlayer, publicQueries, type PublicTournament } from "./api";
import { useNames } from "./useNames";

interface Props {
  shareToken: string;
  tournament: PublicTournament;
  players: PublicPlayer[];
}

/**
 * The knockout, read-only (FR-070, FR-072): the same bracket as the
 * organizer's screen 9, with no way to enter a result, and while it runs the
 * places already decided. A Lord have mercy knockout has no bracket (BR-155),
 * so it reads round by round.
 */
export function PublicKnockout(props: Props) {
  return isLordHaveMercy(props.tournament.phases) ? (
    <PublicRemixKnockout {...props} />
  ) : (
    <PublicBracketKnockout {...props} />
  );
}

/** The knockout heading, the body and the places decided so far. */
function KnockoutSection({
  tournament,
  names,
  places,
  children,
}: {
  tournament: PublicTournament;
  names: ReturnType<typeof useNames>;
  places: ReturnType<typeof usePlaces>;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="knockout" className="min-w-0 space-y-3">
      <h2 id="knockout" className="font-display text-display-section">
        {t("publicView.tournament.knockoutHeading")}
      </h2>
      {children}
      {tournament.state !== "finished" && places.data !== undefined && (
        <PlacesSoFar
          rows={places.data.rows}
          entryName={(entryId) => names.ofEntry(entryId)}
        />
      )}
    </section>
  );
}

function PublicRemixKnockout({ shareToken, tournament, players }: Props) {
  const { t } = useTranslation();
  const names = useNames(players, tournament);
  const knockout = useQuery(
    publicQueries.knockoutRounds(shareToken, tournament.id, true),
  );
  const places = usePlaces(shareToken, tournament);

  return (
    <KnockoutSection tournament={tournament} names={names} places={places}>
      {knockout.data === undefined ? (
        knockout.isError ? (
          <p role="alert" className="text-body-md">
            {t("publicView.tournament.loadFailed")}
          </p>
        ) : (
          <p role="status" className="text-body-md text-muted-foreground">
            {t("loading")}
          </p>
        )
      ) : (
        <RemixRounds
          knockout={knockout.data}
          ctx={{
            playerName: (playerId) => names.ofPlayers([playerId]),
            resultHref: () => null,
          }}
        />
      )}
    </KnockoutSection>
  );
}

function usePlaces(shareToken: string, tournament: PublicTournament) {
  return useQuery(
    publicQueries.places(
      shareToken,
      tournament.id,
      tournament.state !== "finished",
    ),
  );
}

function PublicBracketKnockout({ shareToken, tournament, players }: Props) {
  const { t } = useTranslation();
  const layout = useLayout();
  const names = useNames(players, tournament);
  const bracket = useQuery(
    publicQueries.bracket(shareToken, tournament.id, true),
  );
  const places = usePlaces(shareToken, tournament);

  const ctx: BracketContext = {
    sideName: (side: BracketSide) =>
      side.is_bye
        ? t("finals.knockout.bye")
        : side.entry_id === null
          ? t("finals.knockout.tbd")
          : names.ofEntry(side.entry_id),
    canChange: false,
    resultHref: () => null,
    ...bracketTitles(t, bracket.data),
  };
  const shape = bracket.data;

  return (
    <KnockoutSection tournament={tournament} names={names} places={places}>
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
    </KnockoutSection>
  );
}
