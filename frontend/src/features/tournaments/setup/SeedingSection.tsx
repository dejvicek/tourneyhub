import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import type { components } from "@/api/schema";
import { Button } from "@/components/ui/button";
import { setupMutations } from "@/features/tournaments/api";

import { seededEntries } from "./entries";
import { describeError, isChanged } from "./errors";
import { ArrowDownIcon, ArrowUpIcon, ShuffleIcon } from "./icons";
import { SegmentedControl } from "./SegmentedControl";
import type { SetupData } from "./SetupPage";
import { entryName } from "./summary";

/** Seeding by ranking or lot, "shuffle again", and reordering by hand (FR-034). */
export function SeedingSection({ data }: { data: SetupData }) {
  const { t } = useTranslation();
  const { leagueId, tournamentId, setup, nameOf, rankOf } = data;
  const method = useMutation(setupMutations.seeding(leagueId, tournamentId));
  const order = useMutation(setupMutations.seedOrder(leagueId, tournamentId));
  const shuffle = useMutation(setupMutations.draw(leagueId, tournamentId));
  const entries = seededEntries(data);
  const shown: components["schemas"]["SeedingMethod"] = method.isPending
    ? method.variables
    : setup.seeding_method;

  const move = (index: number, by: -1 | 1) => {
    const ids = entries.map((entry) => entry.id);
    const [moved] = ids.splice(index, 1);
    if (moved !== undefined) {
      ids.splice(index + by, 0, moved);
      order.mutate(ids);
    }
  };
  const failed = [method, order, shuffle].find((mutation) => mutation.isError);

  return (
    <section
      aria-labelledby="seeding-heading"
      className="grid content-start gap-4"
    >
      <div className="grid gap-1">
        <h2 id="seeding-heading" className="font-display text-display-section">
          {t("tournaments.setup.draw.seeding")}
        </h2>
        <p className="text-body-sm text-muted-foreground">
          {t("tournaments.setup.draw.seedingHint")}
        </p>
      </div>
      <SegmentedControl
        label={t("tournaments.setup.draw.seedingMethod")}
        value={shown}
        options={[
          { value: "ranking", label: t("tournaments.setup.draw.byRanking") },
          { value: "random", label: t("tournaments.setup.draw.byLot") },
        ]}
        onValueChange={(next) => {
          if (next !== setup.seeding_method) {
            method.mutate(next);
          }
        }}
      />
      {setup.seeding_method === "random" && (
        <Button
          type="button"
          variant="ghost"
          className="w-fit text-primary"
          disabled={shuffle.isPending}
          onClick={() => {
            shuffle.mutate({
              expected_draw_counter: setup.draw_counter,
              target: "seeds",
            });
          }}
        >
          <ShuffleIcon />
          {t("tournaments.setup.draw.shuffleAgain")}
        </Button>
      )}
      {failed?.isError && (
        <p
          role={isChanged(failed.error) ? "status" : "alert"}
          className="text-body-md text-destructive"
        >
          {describeError(failed.error, t)}
        </p>
      )}
      {entries.length === 0 ? (
        <p className="text-body-md text-muted-foreground">
          {t("tournaments.setup.draw.noEntries")}
        </p>
      ) : (
        <ol
          aria-label={t("tournaments.setup.draw.seedOrder")}
          className="grid gap-2"
        >
          {entries.map((entry, index) => {
            const name = entryName(t, entry.player_ids.map(nameOf));
            const ranks = entry.player_ids
              .map((id) => rankOf(id) ?? 0)
              .sort((a, b) => a - b);
            return (
              <li
                key={entry.id}
                className="flex items-center gap-3 rounded-lg border border-border-surface bg-card p-3"
              >
                <span className="w-9 text-center font-display text-score-m">
                  {entry.seed}
                </span>
                <div className="grid min-w-0 flex-1">
                  <span className="text-body-md font-bold break-words">
                    {name}
                  </span>
                  <span className="text-body-sm text-muted-foreground">
                    {ranks.length === 2
                      ? t("tournaments.setup.draw.rankedPair", {
                          first: ranks[0],
                          second: ranks[1],
                        })
                      : t("tournaments.setup.draw.rankedPlayer", {
                          rank: ranks[0],
                        })}
                  </span>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  disabled={index === 0 || order.isPending}
                  aria-label={t("tournaments.setup.draw.moveUp", { name })}
                  onClick={() => {
                    move(index, -1);
                  }}
                >
                  <ArrowUpIcon />
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  disabled={index === entries.length - 1 || order.isPending}
                  aria-label={t("tournaments.setup.draw.moveDown", { name })}
                  onClick={() => {
                    move(index, 1);
                  }}
                >
                  <ArrowDownIcon />
                </Button>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
