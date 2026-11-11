import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { setupMutations } from "@/features/tournaments/api";

import { describeError, isChanged } from "./errors";
import { ShuffleIcon } from "./icons";
import { Notice } from "./Notice";
import type { SetupData } from "./SetupPage";
import { entryName } from "./summary";

/** Doubles: the organizer puts the players into pairs (FR-033, BR-003, BR-030). */
export function PairMaker({ data }: { data: SetupData }) {
  const { t } = useTranslation();
  const { leagueId, tournamentId, setup, ranking, nameOf } = data;
  const [selected, setSelected] = useState<string[]>([]);
  const save = useMutation(setupMutations.pairs(leagueId, tournamentId));
  const draw = useMutation(setupMutations.draw(leagueId, tournamentId));

  const pairs = setup.entries
    .filter((entry) => entry.stage === "main")
    .map((entry): [string, string] => [
      entry.player_ids[0] ?? "",
      entry.player_ids[1] ?? "",
    ]);
  const paired = new Set(pairs.flat());
  const alone = ranking.filter(
    (row) =>
      setup.player_ids.includes(row.player_id) && !paired.has(row.player_id),
  );
  const failed = [save, draw].find((mutation) => mutation.isError);
  const [first, second] = selected;

  return (
    <div className="grid content-start gap-4">
      <div className="grid gap-1">
        <h2 className="font-display text-display-section">
          {t("tournaments.setup.draw.pairsHeading")}
        </h2>
        <p id="pair-maker-hint" className="text-body-sm text-muted-foreground">
          {t("tournaments.setup.draw.pairsHint")}
        </p>
      </div>

      {alone.length > 0 ? (
        <ToggleGroup
          type="multiple"
          value={selected}
          aria-label={t("tournaments.setup.draw.unpairedPlayers")}
          aria-describedby="pair-maker-hint"
          onValueChange={(next) => {
            setSelected(next.slice(-2));
          }}
        >
          {alone.map((row) => (
            <ToggleGroupItem key={row.player_id} value={row.player_id}>
              {row.name}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      ) : (
        <Notice
          variant="info"
          title={t("tournaments.setup.draw.everyonePaired")}
        />
      )}

      <div className="flex flex-wrap gap-2">
        <Button
          type="button"

          disabled={
            first === undefined || second === undefined || save.isPending
          }
          onClick={() => {
            if (first !== undefined && second !== undefined) {
              save.mutate([...pairs, [first, second]], {
                onSuccess: () => {
                  setSelected([]);
                },
              });
            }
          }}
        >
          {t("tournaments.setup.draw.makePair")}
        </Button>
        <Button
          type="button"
          variant="ghost"
          className="text-primary"
          disabled={alone.length < 2 || draw.isPending}
          onClick={() => {
            draw.mutate({
              expected_draw_counter: setup.draw_counter,
              target: "pairs",
            });
          }}
        >
          <ShuffleIcon />
          {t("tournaments.setup.draw.pairRest")}
        </Button>
      </div>

      {failed?.isError && (
        <p
          role={isChanged(failed.error) ? "status" : "alert"}
          className="text-body-md text-destructive"
        >
          {describeError(failed.error, t)}
        </p>
      )}

      {pairs.length > 0 && (
        <ul className="grid gap-2">
          {pairs.map((pair) => {
            const name = entryName(t, pair.map(nameOf));
            return (
              <li
                key={pair.join("+")}
                className="flex items-center justify-between gap-3 rounded-lg border border-border-surface bg-card p-3"
              >
                <span className="text-body-md font-bold">{name}</span>
                <Button
                  type="button"
                  variant="ghost"

                  disabled={save.isPending}
                  aria-label={t("tournaments.setup.draw.breakUp", { name })}
                  onClick={() => {
                    save.mutate(pairs.filter((other) => other !== pair));
                  }}
                >
                  {t("tournaments.setup.draw.breakUpShort")}
                </Button>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
