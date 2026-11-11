import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { components } from "@/api/schema";
import { Button } from "@/components/ui/button";
import { setupMutations } from "@/features/tournaments/api";

import { describeError, isChanged } from "./errors";
import { ShuffleIcon } from "./icons";
import { Notice } from "./Notice";
import { SegmentedControl } from "./SegmentedControl";
import type { SetupData } from "./SetupPage";

type Half = components["schemas"]["DypHalf"];
type Choice = Half | "unset";

/** DYP: the halves by the league ranking or by hand, and the draw of the pairs (FR-033, BR-031-BR-033). */
export function HalvesSection({ data }: { data: SetupData }) {
  const { t } = useTranslation();
  const { leagueId, tournamentId, setup, ranking, nameOf, rankOf } = data;
  const halves = useMutation(setupMutations.halves(leagueId, tournamentId));
  const draw = useMutation(setupMutations.draw(leagueId, tournamentId));

  const picked = ranking.filter((row) =>
    setup.player_ids.includes(row.player_id),
  );
  const halfOf = (id: string): Choice =>
    setup.halves.find((row) => row.player_id === id)?.half ?? "unset";
  const inHalf = (half: Half) =>
    picked.filter((row) => halfOf(row.player_id) === half);
  const top = inHalf("top");
  const bottom = inHalf("bottom");
  const leftOut = inHalf("left_out");
  const method: components["schemas"]["HalvesMethod"] = halves.isPending
    ? halves.variables.method
    : setup.halves_method;
  const odd = picked.length % 2 === 1;
  const complete =
    picked.every((row) => halfOf(row.player_id) !== "unset") &&
    top.length === bottom.length &&
    leftOut.length === (odd ? 1 : 0);

  const choose = (playerId: string, half: Choice) => {
    halves.mutate({
      method: "by_hand",
      halves: [
        ...setup.halves.filter((row) => row.player_id !== playerId),
        ...(half === "unset" ? [] : [{ player_id: playerId, half }]),
      ],
    });
  };
  const failed = [halves, draw].find((mutation) => mutation.isError);
  const column = (title: string, rows: typeof picked, tone: string) => (
    <div className="grid content-start gap-1">
      <h2 className="flex items-center gap-2 text-body-md font-bold">
        <span aria-hidden="true" className={`size-3 rounded-full ${tone}`} />
        {title}
      </h2>
      <ol className="grid gap-0.5">
        {rows.map((row) => (
          <li key={row.player_id} className="text-body-md">
            <span className="mr-2 text-muted-foreground">
              {rankOf(row.player_id)}
            </span>
            {row.name}
          </li>
        ))}
      </ol>
    </div>
  );

  return (
    <div className="grid content-start gap-6">
      <SegmentedControl
        label={t("tournaments.setup.draw.splitBy")}
        value={method}
        options={[
          { value: "ranking", label: t("tournaments.setup.draw.byRanking") },
          { value: "by_hand", label: t("tournaments.setup.draw.byHand") },
        ]}
        onValueChange={(next) => {
          if (next !== setup.halves_method) {
            halves.mutate({ method: next, halves: setup.halves });
          }
        }}
      />

      {method === "by_hand" && (
        <ul className="grid gap-3">
          {picked.map((row) => (
            <li
              key={row.player_id}
              className="rounded-lg border border-border-surface bg-card p-3"
            >
              <SegmentedControl
                label={`${String(rankOf(row.player_id))}. ${nameOf(row.player_id)}`}
                value={halfOf(row.player_id)}
                options={[
                  { value: "top", label: t("tournaments.setup.draw.top") },
                  {
                    value: "bottom",
                    label: t("tournaments.setup.draw.bottom"),
                  },
                  ...(odd
                    ? [
                        {
                          value: "left_out" as const,
                          label: t("tournaments.setup.draw.leftOut"),
                        },
                      ]
                    : []),
                ]}
                onValueChange={(half) => {
                  choose(row.player_id, half);
                }}
              />
            </li>
          ))}
        </ul>
      )}

      {complete ? (
        method === "ranking" && (
          <div className="grid grid-cols-2 gap-4 rounded-lg border border-border-surface bg-card p-4">
            {column(t("tournaments.setup.draw.topHalf"), top, "bg-team-a")}
            {column(
              t("tournaments.setup.draw.bottomHalf"),
              bottom,
              "bg-team-b",
            )}
          </div>
        )
      ) : (
        <Notice
          variant="warning"
          title={t("tournaments.setup.draw.unbalanced.title")}
        >
          {t("tournaments.setup.draw.unbalanced.body", {
            top: top.length,
            bottom: bottom.length,
          })}
        </Notice>
      )}

      {leftOut[0] !== undefined && (
        <Notice
          variant="info"
          title={t("tournaments.setup.draw.leftOutNote.title")}
        >
          {t("tournaments.setup.draw.leftOutNote.body", {
            name: nameOf(leftOut[0].player_id),
          })}
        </Notice>
      )}

      <div className="grid gap-1">
        <h2 className="font-display text-display-section">
          {t("tournaments.setup.draw.drawnPairs")}
        </h2>
        <p className="text-body-sm text-muted-foreground">
          {t("tournaments.setup.draw.drawnPairsHint")}
        </p>
        <Button
          type="button"
          variant="ghost"
          className="w-fit text-primary"
          disabled={draw.isPending || !complete}
          onClick={() => {
            draw.mutate({
              expected_draw_counter: setup.draw_counter,
              target: "pairs",
            });
          }}
        >
          <ShuffleIcon />
          {t("tournaments.setup.draw.drawAgain")}
        </Button>
        {failed?.isError && (
          <p
            role={isChanged(failed.error) ? "status" : "alert"}
            className="text-body-md text-destructive"
          >
            {describeError(failed.error, t)}
          </p>
        )}
      </div>
    </div>
  );
}
