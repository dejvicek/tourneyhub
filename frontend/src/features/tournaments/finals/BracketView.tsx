import { cn } from "cn";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type { BracketData as BracketRead } from "@/features/finals/api";

import { type BracketContext, sideAt } from "./bracketContext";
import { FinalCard, MatchBox, MatchCard } from "./BracketParts";

interface ViewProps {
  bracket: BracketRead;
  ctx: BracketContext;
}

/**
 * Tablet and desktop: every round in a column, the rounds side by side, as
 * wide as the bracket needs (it scrolls in two dimensions, guide §6 A15).
 */
export function BracketView({ bracket, ctx }: ViewProps) {
  const { t } = useTranslation();
  return (
    <div
      role="region"
      aria-label={t("finals.knockout.bracket")}
      // eslint-disable-next-line jsx-a11y-x/no-noninteractive-tabindex -- a scrollable region must take focus so the keyboard can scroll it (WCAG 2.1.1)
      tabIndex={0}
      className="overflow-x-auto rounded-lg outline-hidden focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      <div className="flex min-w-max gap-10 py-1">
        {bracket.rounds.map((round) => (
          <div
            key={round.round_no}
            role="group"
            aria-label={t(`finals.roundName.${round.name}`)}
            className="flex w-56 flex-col justify-around gap-3"
          >
            <h2 className="text-caption font-bold text-muted-foreground">
              {t(`finals.roundName.${round.name}`)}
            </h2>
            {round.matches.map((match) =>
              match.kind === "standard" && round.name === "final" ? (
                <FinalCard
                  key={match.match_id}
                  ctx={ctx}
                  round={round}
                  match={match}
                />
              ) : (
                <MatchBox
                  key={match.match_id}
                  ctx={ctx}
                  round={round}
                  match={match}
                  titled={
                    round.name !== "round_of_16" || match.kind !== "standard"
                  }
                  className={cn(
                    match.kind === "standard" &&
                      round.name !== "final" &&
                      "after:absolute after:top-1/2 after:left-full after:h-px after:w-10 after:bg-border",
                  )}
                />
              ),
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

/** Phone, 4 entries (the design): the semifinals side by side above the final. */
export function CompactBracket({ bracket, ctx }: ViewProps) {
  const { t } = useTranslation();
  const [semifinals, last] = bracket.rounds;
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        {semifinals?.matches.map((match) => (
          <MatchBox
            key={match.match_id}
            ctx={ctx}
            round={semifinals}
            match={match}
            titled
          />
        ))}
      </div>
      <div aria-hidden="true" className="mx-auto h-5 w-px bg-border" />
      {last?.matches.map((match) =>
        match.kind === "standard" ? (
          <FinalCard
            key={match.match_id}
            ctx={ctx}
            round={last}
            match={match}
          />
        ) : (
          <div key={match.match_id} className="space-y-2">
            <h2 className="text-body-md font-bold">
              {t("finals.roundName.final")}
            </h2>
            <MatchBox ctx={ctx} round={last} match={match} titled />
          </div>
        ),
      )}
    </div>
  );
}

/** Phone, 8 or 16 entries: pick a round, see its matches as cards. */
export function RoundList({ bracket, ctx }: ViewProps) {
  const { t } = useTranslation();
  const open = bracket.rounds.find((round) =>
    round.matches.some((m) => m.state === "ready" || m.state === "on_field"),
  );
  const [picked, setPicked] = useState<string | undefined>(undefined);
  const current =
    bracket.rounds.find((round) => String(round.round_no) === picked) ??
    open ??
    bracket.rounds[0];
  return (
    <div className="space-y-3">
      <ToggleGroup
        type="single"
        aria-label={t("finals.knockout.rounds")}
        value={String(current?.round_no)}
        onValueChange={(value) => {
          if (value !== "") {
            setPicked(value);
          }
        }}
      >
        {bracket.rounds.map((round) => (
          <ToggleGroupItem key={round.round_no} value={String(round.round_no)}>
            {t(`finals.roundName.${round.name}`)}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      {current && (
        <ul className="space-y-3">
          {current.matches.map((match) => (
            <li key={match.match_id}>
              {match.state === "bye" ? (
                <p className="rounded-lg border border-dashed border-input px-3 py-2 text-body-sm text-muted-foreground">
                  {t("finals.knockout.byeFor", {
                    name: ctx.sideName(
                      sideAt(match, sideAt(match, 0).is_bye ? 1 : 0),
                    ),
                  })}
                </p>
              ) : (
                <MatchCard ctx={ctx} round={current} match={match} />
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export { FinalCard };
