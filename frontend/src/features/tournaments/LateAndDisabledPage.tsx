import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { DocumentTitle } from "@/components/DocumentTitle";
import { Button } from "@/components/ui/button";
import { finalsMutations, finalsQueries } from "@/features/finals/api";
import { standingsQueries } from "@/features/standings/api";
import { tournamentQueries } from "@/features/tournaments/api";
import { useRouteParam } from "@/hooks/useRouteParam";

import { errorText } from "./finals/errorText";
import { LatePlayerSheet } from "./finals/LatePlayerSheet";
import { localDate, shortName, useRoster } from "./finals/names";
import { Notice } from "./finals/Notice";
import { ScreenHeader } from "./finals/ScreenHeader";
import { LoadError, Loading } from "./finals/StateMessage";

/**
 * Screen 12: the players of a running Swiss or Monster DYP (FR-044, FR-047,
 * FR-048, BR-064, BR-067): disable and enable, and add a late player.
 */
export function LateAndDisabledPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const tournament = useQuery(tournamentQueries.detail(leagueId, tournamentId));
  const participants = useQuery(
    finalsQueries.participants(leagueId, tournamentId),
  );
  const players = useQuery(finalsQueries.players(leagueId));
  const standings = useQuery(
    standingsQueries.season(leagueId, tournament.data?.season_id),
  );
  const roster = useRoster(leagueId, tournament.data?.entries);
  const setDisabled = useMutation(
    finalsMutations.setDisabled(queryClient, leagueId, tournamentId),
  );
  const [announcement, setAnnouncement] = useState("");

  if (tournament.isError || participants.isError) {
    return (
      <LoadError
        onRetry={() => {
          void tournament.refetch();
          void participants.refetch();
        }}
      />
    );
  }
  const data = tournament.data;
  const rows = participants.data;
  if (data === undefined || rows === undefined) {
    return <Loading />;
  }

  const group = data.phases.find((phase) => phase.kind === "group");
  const roundsPlayed = data.rounds.filter(
    (r) => r.phase_id === group?.id,
  ).length;
  const takesLate =
    (group?.format === "swiss" || group?.format === "monster_dyp") &&
    !data.phases.some((phase) => phase.kind === "knockout");
  const activeCount = rows.filter((row) => row.state !== "disabled").length;
  const inTournament = new Set(data.entries.flatMap((e) => e.player_ids));
  const points = new Map(
    (standings.data ?? []).map((row) => [row.player_id, row.points]),
  );
  const ranked = [...(players.data ?? [])]
    .filter((p) => p.removed_at === null)
    .sort(
      (a, b) =>
        (points.get(b.id) ?? 0) - (points.get(a.id) ?? 0) ||
        a.name.localeCompare(b.name),
    );
  const candidates = ranked.flatMap((player, index) =>
    inTournament.has(player.id)
      ? []
      : [
          {
            id: player.id,
            name: shortName(player.name),
            rank: index + 1,
            points: points.get(player.id) ?? 0,
          },
        ],
  );
  // FR-048: only BH1 and BH2 make missed rounds unfair.
  const usesBuchholz =
    group?.tiebreakers?.some((key) => key === "bh1" || key === "bh2") ?? false;

  const statusLine = (row: (typeof rows)[number]): string => {
    if (row.state === "disabled") {
      return t("finals.players.disabledSince", {
        round: row.disabled_since_round ?? 0,
      });
    }
    if (row.joined_round !== null) {
      return t("finals.players.joined", { round: row.joined_round });
    }
    if (row.state === "sat_out") {
      return t("finals.players.satOut", { round: row.sat_out_round ?? 0 });
    }
    return t("finals.players.playing");
  };

  return (
    <div className="space-y-6">
      <DocumentTitle screen={`${data.name} · ${t("finals.players.title")}`} />
      <ScreenHeader title={data.name} subtitle={t("finals.players.title")} />
      <p className="text-body-sm text-muted-foreground">
        {t("finals.rounds.summary", {
          date: localDate(data.date),
          count: rows.length,
        })}
      </p>
      {takesLate ? (
        <LatePlayerSheet
          leagueId={leagueId}
          tournamentId={tournamentId}
          candidates={candidates}
          fromRound={roundsPlayed + 1}
          warn={usesBuchholz}
          onAdded={(name) => {
            setAnnouncement(
              t("finals.players.lateDone", { name, round: roundsPlayed + 1 }),
            );
          }}
        />
      ) : (
        <Notice tone="info" title={t("finals.players.notAllowed")} />
      )}
      <section aria-labelledby="players-heading" className="space-y-2">
        <h2 id="players-heading" className="font-display text-display-section">
          {t("finals.players.summary", {
            count: rows.length,
            active: activeCount,
          })}
        </h2>
        <p className="text-body-sm text-muted-foreground">
          {t("finals.players.help")}
        </p>
        <p role="status" className="min-h-5 text-body-sm font-bold">
          {announcement}
        </p>
        {setDisabled.isError && (
          <p role="alert" className="text-body-sm">
            {errorText(t, setDisabled.error)}
          </p>
        )}
        <ul className="border-t border-border">
          {rows.map((row) => {
            const name = roster.entry(row.entry_id);
            const disabled = row.state === "disabled";
            const pending =
              setDisabled.isPending &&
              setDisabled.variables.entryId === row.entry_id;
            return (
              <li
                key={row.entry_id}
                className="flex items-center gap-3 border-b border-border py-2.5"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-body-md font-bold break-words">{name}</p>
                  <p
                    className={
                      disabled
                        ? "text-body-sm text-notice-warning-foreground"
                        : "text-body-sm text-muted-foreground"
                    }
                  >
                    {statusLine(row)}
                  </p>
                </div>
                {takesLate && (
                  <Button
                    type="button"
                    variant="outline"
                    className="min-h-11"
                    disabled={pending}
                    aria-label={
                      disabled
                        ? t("finals.players.enableFor", { name })
                        : t("finals.players.disableFor", { name })
                    }
                    onClick={() => {
                      // The target state (ADR-008): disabled or not, never a toggle.
                      setDisabled.mutate(
                        { entryId: row.entry_id, disabled: !disabled },
                        {
                          onSuccess: () => {
                            setAnnouncement(
                              disabled
                                ? t("finals.players.enabledDone", { name })
                                : t("finals.players.disabledDone", { name }),
                            );
                          },
                        },
                      );
                    }}
                  >
                    {disabled
                      ? t("finals.players.enable")
                      : t("finals.players.disable")}
                  </Button>
                )}
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
