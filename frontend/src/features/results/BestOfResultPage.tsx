import { useState } from "react";
import { useTranslation } from "react-i18next";

import { StickyActions } from "@/components/StickyActions";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { MATCH_POINTS } from "@/lib/rules";
import { cn } from "@/lib/utils";

import type { ResultFormContext } from "./formContext";
import { Playfield } from "./Playfield";
import {
  type EntryMode,
  type GameDraft,
  gameWinner,
  MAX_GAMES,
  series,
  seriesWrite,
  type Side,
} from "./resultDraft";
import { SidePanel } from "./SidePanel";

function initialGames(context: ResultFormContext): GameDraft[] {
  const { match, format } = context.info;
  const saved = match.is_walkover ? [] : match.games;
  return Array.from({ length: MAX_GAMES[format] }, (_, i) => {
    const game = saved[i];
    return {
      a: game?.score_1 ?? null,
      b: game?.score_2 ?? null,
      winner: game && game.winner !== "draw" ? game.winner : null,
    };
  });
}

/**
 * Screen 7b: a BO2, BO3 or BO5 result, game by game: the goals of each
 * game, or only who won it, one tap per game (FR-050, FR-051, FR-082,
 * BR-121). Games after the series is decided are not needed. Not a route:
 * the result overlay (EnterResultPage) shows it for a best-of match.
 */
export function BestOfResultPage({ context }: { context: ResultFormContext }) {
  const { t } = useTranslation();
  const { info, names, firstNames, required, drawAllowed, goalsPerGame } =
    context;
  const format = info.format;
  const saved = info.match.games;
  const [mode, setMode] = useState<EntryMode>(
    !required && saved.length > 0 && saved.every((g) => g.score_1 === null)
      ? "winners"
      : "goals",
  );
  const [games, setGames] = useState<GameDraft[]>(() => initialGames(context));
  const result = series(games, format, mode);
  const [selected, setSelected] = useState(
    () => Math.min(result.needed, MAX_GAMES[format]) - 1,
  );
  const body = seriesWrite(games, format, mode, drawAllowed);
  const visible = Math.min(result.needed, MAX_GAMES[format]);
  const current = games[selected];

  const update = (index: number, change: Partial<GameDraft>) => {
    const next = games.map((game, i) =>
      i === index ? { ...game, ...change } : game,
    );
    setGames(next);
    // A finished game moves on to the next one still needed.
    const done = next[index];
    if (mode === "goals" && done && gameWinner(done, "goals") !== null) {
      const after = series(next, format, "goals");
      if (after.outcome === null && after.needed - 1 > index) {
        setSelected(after.needed - 1);
      }
    }
  };

  const winnerName = (side: Side) => firstNames[side === "side_1" ? 0 : 1];
  let sentence: string;
  if (result.outcome === null) {
    sentence = t("results.bestOf.open", {
      a: result.wins[0],
      b: result.wins[1],
    });
  } else if (result.outcome === "draw") {
    sentence = drawAllowed
      ? t("results.bestOf.draw", { count: MATCH_POINTS.draw })
      : t("results.bestOf.drawNotAllowed");
  } else {
    sentence = t("results.bestOf.win", {
      names: winnerName(result.outcome),
      score: t("roundRobin.score", {
        a: Math.max(...result.wins),
        b: Math.min(...result.wins),
      }),
    });
  }

  const scoreCard = (
    <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-3 rounded-lg border border-border-surface bg-card p-3 text-card-foreground">
      <span className="text-body-md font-bold">{names[0]}</span>
      <span
        className="font-display text-score-l whitespace-nowrap"
        aria-label={t("results.bestOf.games", {
          a: result.wins[0],
          b: result.wins[1],
        })}
      >
        <span className="text-team-a">{result.wins[0]}</span>
        {" : "}
        <span className="text-team-b">{result.wins[1]}</span>
      </span>
      <span className="text-right text-body-md font-bold">{names[1]}</span>
    </div>
  );

  return (
    <form
      className="space-y-4"
      onSubmit={(event) => {
        event.preventDefault();
        if (body !== null) {
          context.onSave(body);
        }
      }}
    >
      <Tabs
        value={mode}
        onValueChange={(value) => {
          setMode(value === "winners" ? "winners" : "goals");
        }}
      >
        <TabsList aria-label={t("results.bestOf.mode")}>
          <TabsTrigger value="goals">{t("results.bestOf.goals")}</TabsTrigger>
          <TabsTrigger value="winners" disabled={required}>
            {t("results.bestOf.winnersOnly")}
          </TabsTrigger>
        </TabsList>
        {required && (
          <p className="text-body-sm text-muted-foreground">
            {t("results.bestOf.scoresRequired")}
          </p>
        )}
        {scoreCard}
        <TabsContent value="goals" className="space-y-4">
          <div
            role="group"
            aria-label={t("results.bestOf.gameList")}
            className="flex flex-wrap gap-2"
          >
            {games.slice(0, visible).map((game, index) => {
              const winner = gameWinner(game, "goals");
              const isSelected = index === selected;
              return (
                <button
                  // Games are numbered by position.
                  key={index}
                  type="button"
                  aria-pressed={isSelected}
                  onClick={() => {
                    setSelected(index);
                  }}
                  className={cn(
                    "flex min-h-11 min-w-24 flex-col items-start justify-center rounded-lg border-2 bg-card px-3 py-1 text-left text-card-foreground outline-hidden focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background",
                    isSelected ? "border-team-a" : "border-border-surface",
                  )}
                >
                  <span className="flex items-center gap-1.5 text-caption font-bold">
                    {winner !== null && (
                      <span
                        aria-hidden="true"
                        className={cn(
                          "size-2.5 rounded-full",
                          winner === "side_1" ? "bg-team-a" : "bg-team-b",
                        )}
                      />
                    )}
                    {t("results.bestOf.game", { number: index + 1 })}
                  </span>
                  <span className="text-body-sm">
                    {game.a !== null && game.b !== null
                      ? t("roundRobin.score", { a: game.a, b: game.b })
                      : t("results.bestOf.now")}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="text-body-md text-muted-foreground">
            {t("results.bestOf.editing", { number: selected + 1 })}
          </p>
          {current && (
            <Playfield>
              <SidePanel
                side="a"
                names={names[0]}
                seed={context.seeds[0]}
                goalsPerGame={goalsPerGame}
                value={current.a}
                disabled={context.locked}
                onChange={(a) => {
                  update(selected, { a });
                }}
              />
              <SidePanel
                side="b"
                names={names[1]}
                seed={context.seeds[1]}
                goalsPerGame={goalsPerGame}
                value={current.b}
                disabled={context.locked}
                onChange={(b) => {
                  update(selected, { b });
                }}
              />
            </Playfield>
          )}
        </TabsContent>
        <TabsContent value="winners" className="space-y-2">
          {games.map((game, index) => {
            const label = t("results.bestOf.game", { number: index + 1 });
            if (index >= visible) {
              return result.outcome !== null &&
                result.outcome !== "draw" &&
                format !== "bo2" ? (
                <p
                  // Games are numbered by position.
                  key={index}
                  className="rounded-lg border-2 border-dashed border-input p-3 text-body-sm text-muted-foreground"
                >
                  <span className="font-bold">{label}</span>{" "}
                  {t("results.bestOf.notNeeded", {
                    names: winnerName(result.outcome),
                    count: Math.max(...result.wins),
                  })}
                </p>
              ) : null;
            }
            return (
              <div
                // Games are numbered by position.
                key={index}
                className="flex flex-wrap items-center gap-3"
              >
                <span className="w-16 text-body-md font-bold">{label}</span>
                <ToggleGroup
                  type="single"
                  aria-label={t("results.bestOf.winnerOf", {
                    number: index + 1,
                  })}
                  value={game.winner ?? ""}
                  disabled={context.locked}
                  onValueChange={(value) => {
                    if (value === "side_1" || value === "side_2") {
                      update(index, { winner: value });
                    }
                  }}
                >
                  <ToggleGroupItem value="side_1">
                    {firstNames[0]}
                  </ToggleGroupItem>
                  <ToggleGroupItem value="side_2">
                    {firstNames[1]}
                  </ToggleGroupItem>
                </ToggleGroup>
              </div>
            );
          })}
        </TabsContent>
      </Tabs>
      <p role="status" className="text-body-lg font-bold">
        {sentence}
      </p>
      <StickyActions>
        <Button
          type="submit"
          disabled={body === null || context.pending || context.locked}
          size="lg"
          className="w-full"
        >
          {t("results.save")}
        </Button>
        {context.actions}
      </StickyActions>
    </form>
  );
}
