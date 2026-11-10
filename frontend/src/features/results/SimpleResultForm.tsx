import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { MATCH_POINTS } from "@/demo/rules";
import { sidesOf } from "@/features/tournaments/play/model";

import type { ResultFormContext } from "./formContext";
import { Playfield } from "./Playfield";
import { simpleOutcome, simpleWrite } from "./resultDraft";
import { SidePanel } from "./SidePanel";

/** Points after a win, and whether they put the winner alone on top. */
function afterWin(
  context: ResultFormContext,
  winnerIndex: 0 | 1,
): { points: number; top: boolean } | null {
  const { info, standings } = context;
  const entryId = sidesOf(info.match)[winnerIndex].entry_id;
  if (
    info.phase.kind !== "group" ||
    info.match.outcome !== null ||
    standings === undefined ||
    entryId === null
  ) {
    return null;
  }
  const mine = standings.find((row) => row.entry_id === entryId);
  if (!mine) {
    return null;
  }
  const points = mine.points + MATCH_POINTS.win;
  const top = standings.every(
    (row) => row.entry_id === entryId || row.points < points,
  );
  return { points, top };
}

/**
 * Screen 7: a BO1 result with the bead counters. Open the match, tap the
 * winner's last bead, save: three taps (FR-082); the other pair's goals add
 * the score (FR-051).
 */
export function SimpleResultForm({ context }: { context: ResultFormContext }) {
  const { t } = useTranslation();
  const { info, names, firstNames, goalsPerGame, required, drawAllowed } =
    context;
  const game = info.match.is_walkover ? undefined : info.match.games[0];
  const [a, setA] = useState<number | null>(
    game?.score_1 ?? (game?.winner === "side_1" ? goalsPerGame : null),
  );
  const [b, setB] = useState<number | null>(
    game?.score_2 ?? (game?.winner === "side_2" ? goalsPerGame : null),
  );
  const outcome = simpleOutcome(a, b, goalsPerGame, required, drawAllowed);
  const body = simpleWrite(outcome);

  let sentence: string;
  switch (outcome.kind) {
    case "empty":
      sentence = t("results.simple.empty");
      break;
    case "incomplete":
      sentence = t("results.simple.incomplete");
      break;
    case "needsScores":
      sentence = t("results.simple.needsScores");
      break;
    case "winnerOnly":
      sentence = t("results.simple.winnerOnly", {
        names: firstNames[outcome.winner === "side_1" ? 0 : 1],
      });
      break;
    case "win": {
      const index = outcome.winner === "side_1" ? 0 : 1;
      const after = afterWin(context, index);
      const values = {
        names: firstNames[index],
        score: t("roundRobin.score", {
          a: Math.max(outcome.a, outcome.b),
          b: Math.min(outcome.a, outcome.b),
        }),
      };
      sentence =
        after?.top === true
          ? t("results.simple.winTop", { ...values, count: after.points })
          : t("results.simple.win", values);
      break;
    }
    case "draw":
      sentence = t("results.simple.draw", {
        score: t("roundRobin.score", { a: outcome.a, b: outcome.a }),
        count: MATCH_POINTS.draw,
      });
      break;
    case "drawNotAllowed":
      sentence = t("results.simple.drawNotAllowed");
      break;
  }

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
      <p className="text-body-md text-muted-foreground">
        {t("results.simple.hint")}{" "}
        {drawAllowed
          ? t("results.simple.drawsAllowed")
          : t("results.simple.drawsNotAllowed")}
      </p>
      <Playfield>
        <SidePanel
          side="a"
          names={names[0]}
          seed={context.seeds[0]}
          goalsPerGame={goalsPerGame}
          value={a}
          onChange={setA}
          disabled={context.locked}
        />
        <SidePanel
          side="b"
          names={names[1]}
          seed={context.seeds[1]}
          goalsPerGame={goalsPerGame}
          value={b}
          onChange={setB}
          disabled={context.locked}
        />
      </Playfield>
      <p role="status" className="text-body-lg font-bold">
        {sentence}
      </p>
      <Button
        type="submit"
        disabled={body === null || context.pending || context.locked}
        className="h-14 w-full rounded-lg text-button-lg"
      >
        {/* TODO(foundation-buttons): size lg after the rebase. */}
        {t("results.save")}
      </Button>
    </form>
  );
}
