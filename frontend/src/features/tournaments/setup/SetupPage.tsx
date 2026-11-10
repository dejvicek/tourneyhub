import { useQuery } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { generatePath, Link } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { Skeleton } from "@/components/ui/skeleton";
import type { Player, RankingRow, TournamentSetupRead } from "@/demo/contract";
import {
  setupQueries,
  type TournamentDetail,
  tournamentQueries,
} from "@/features/tournaments/api";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

import { Notice } from "./Notice";
import { type SetupStep, SetupSteps } from "./SetupSteps";

/** What every step after the first needs, loaded and in hand. */
export interface SetupData {
  leagueId: string;
  tournamentId: string;
  tournament: TournamentDetail;
  setup: TournamentSetupRead;
  /** The league's active players in ranking order (BR-020). */
  ranking: (RankingRow & { name: string })[];
  /** A player's name, or "" for an unknown id. */
  nameOf: (playerId: string) => string;
  /** A player's place in the league ranking. */
  rankOf: (playerId: string) => number | undefined;
}

function useSetupData(): {
  data: SetupData | undefined;
  failed: boolean;
  type: TournamentDetail["type"] | undefined;
} {
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const tournament = useQuery(tournamentQueries.detail(leagueId, tournamentId));
  const setup = useQuery(setupQueries.detail(leagueId, tournamentId));
  const players = useQuery(setupQueries.players(leagueId));
  const ranking = useQuery(setupQueries.ranking(leagueId));

  const failed =
    tournament.isError || setup.isError || players.isError || ranking.isError;
  if (
    tournament.data === undefined ||
    setup.data === undefined ||
    players.data === undefined ||
    ranking.data === undefined
  ) {
    return { data: undefined, failed, type: tournament.data?.type };
  }
  const names = new Map(
    players.data.map((player: Player) => [player.id, player.name]),
  );
  const ranks = new Map(ranking.data.map((row) => [row.player_id, row.rank]));
  return {
    failed,
    type: tournament.data.type,
    data: {
      leagueId,
      tournamentId,
      tournament: tournament.data,
      setup: setup.data,
      ranking: ranking.data.map((row) => ({
        ...row,
        name: names.get(row.player_id) ?? "",
      })),
      nameOf: (playerId) => names.get(playerId) ?? "",
      rankOf: (playerId) => ranks.get(playerId),
    },
  };
}

interface SetupHeaderProps {
  step: SetupStep;
  title: string;
  type: TournamentDetail["type"] | undefined;
}

/** The step strip and the screen's title (the <title> and the one h1). */
export function SetupHeader({ step, title, type }: SetupHeaderProps) {
  return (
    <>
      <DocumentTitle screen={title} />
      <div className="grid gap-4">
        <SetupSteps current={step} type={type} />
        <div className="grid gap-1">
          <h1 className="font-display text-display-screen md:text-display-title">
            {title}
          </h1>
        </div>
      </div>
    </>
  );
}

interface SetupPageProps {
  step: SetupStep;
  title: (type: TournamentDetail["type"]) => string;
  children: (data: SetupData) => ReactNode;
}

/**
 * A setup step after the first: loads the tournament, its setup and the
 * league's players, and shows loading, failure and "already started" itself.
 */
export function SetupPage({ step, title, children }: SetupPageProps) {
  const { t } = useTranslation();
  const { data, failed, type } = useSetupData();
  const heading = title(type ?? "dyp");

  return (
    <section className="mx-auto grid w-full max-w-5xl gap-6">
      <SetupHeader step={step} title={heading} type={type} />
      {data === undefined ? (
        failed ? (
          <p role="alert">{t("tournaments.errors.load")}</p>
        ) : (
          <div role="status" className="grid gap-3">
            <span className="sr-only">{t("loading")}</span>
            <Skeleton className="h-24" />
            <Skeleton className="h-48" />
          </div>
        )
      ) : data.tournament.state === "setup" ? (
        children(data)
      ) : (
        <Notice variant="info" title={t("tournaments.setup.started.title")}>
          <p>{t("tournaments.setup.started.body")}</p>
          <Link
            to={generatePath(paths.tournament, {
              leagueId: data.leagueId,
              tournamentId: data.tournamentId,
            })}
            className="inline-flex min-h-11 items-center font-bold underline underline-offset-4"
          >
            {t("tournaments.setup.started.open")}
          </Link>
        </Notice>
      )}
    </section>
  );
}
