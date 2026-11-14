import { useState } from "react";
import { useTranslation } from "react-i18next";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import type {
  PublicRemixKnockoutData,
  RemixKnockoutData,
} from "@/features/finals/api";
import { useLayout } from "@/hooks/useLayout";

import { nextRoundName } from "./remix";
import { type RemixContext, RemixMatchCard } from "./RemixMatchCard";

type Knockout = RemixKnockoutData | PublicRemixKnockoutData;
type Round = Knockout["rounds"][number];

interface Props {
  knockout: Knockout;
  ctx: RemixContext;
}

/** The round with a match to play, otherwise the newest (BR-140). */
function openRound(rounds: readonly Round[]): Round | undefined {
  return (
    rounds.find((round) =>
      round.matches.some((m) => m.state === "ready" || m.state === "on_field"),
    ) ?? rounds.at(-1)
  );
}

function RoundMatches({ round, ctx }: { round: Round; ctx: RemixContext }) {
  return (
    <ul className="space-y-3">
      {round.matches.map((match) => (
        <li key={match.match_id}>
          <RemixMatchCard roundName={round.name} match={match} ctx={ctx} />
        </li>
      ))}
    </ul>
  );
}

/** Phone: pick a drawn round, see its matches as cards. */
function RoundPicker({ knockout, ctx }: Props) {
  const { t } = useTranslation();
  const [picked, setPicked] = useState<string | undefined>(undefined);
  const current =
    knockout.rounds.find((round) => String(round.round_no) === picked) ??
    openRound(knockout.rounds);
  return (
    <div className="space-y-3">
      <ToggleGroup
        type="single"
        aria-label={t("finals.knockout.rounds")}
        value={current === undefined ? "" : String(current.round_no)}
        onValueChange={(value) => {
          if (value !== "") {
            setPicked(value);
          }
        }}
      >
        {knockout.rounds.map((round) => (
          <ToggleGroupItem key={round.round_no} value={String(round.round_no)}>
            {t(`finals.roundName.${round.name}`)}
          </ToggleGroupItem>
        ))}
      </ToggleGroup>
      {current && <RoundMatches round={current} ctx={ctx} />}
    </div>
  );
}

/**
 * Tablet and desktop: the drawn rounds side by side, then the rounds not
 * drawn yet as muted columns (BR-155).
 */
function RoundColumns({ knockout, ctx }: Props) {
  const { t, i18n } = useTranslation();
  const undrawn = Array.from(
    { length: Math.max(0, knockout.round_count - knockout.rounds.length) },
    (_, offset) => {
      const drawn = knockout.rounds.length + offset;
      const named = (done: number) =>
        nextRoundName({
          ...knockout,
          rounds: Array.from<unknown>({ length: done }),
        });
      const name = named(drawn);
      const previous = drawn === 0 ? null : named(drawn - 1);
      return { drawn, name, previous };
    },
  );
  return (
    <div
      role="region"
      aria-label={t("finals.knockout.rounds")}
      // eslint-disable-next-line jsx-a11y-x/no-noninteractive-tabindex -- a scrollable region must take focus so the keyboard can scroll it (WCAG 2.1.1)
      tabIndex={0}
      className="overflow-x-auto rounded-lg outline-hidden focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      <div className="flex min-w-max gap-6 py-1">
        {knockout.rounds.map((round) => (
          <div
            key={round.round_no}
            role="group"
            aria-label={t(`finals.roundName.${round.name}`)}
            className="w-60 space-y-3"
          >
            <h2 className="text-caption font-bold text-muted-foreground">
              {t(`finals.roundName.${round.name}`)}
            </h2>
            <RoundMatches round={round} ctx={ctx} />
          </div>
        ))}
        {undrawn.map(({ drawn, name, previous }) =>
          name === null ? null : (
            <div key={drawn} className="w-60 space-y-3 text-muted-foreground">
              <h2 className="text-caption font-bold">
                {t(`finals.roundName.${name}`)}
              </h2>
              <p className="rounded-lg border border-dashed border-input px-3 py-2 text-body-sm">
                {previous === null
                  ? t("finals.remix.drawnLater")
                  : t("finals.remix.drawnAfter", {
                      previous: t(
                        `finals.roundName.${previous}`,
                      ).toLocaleLowerCase(i18n.resolvedLanguage),
                    })}
              </p>
            </div>
          ),
        )}
      </div>
    </div>
  );
}

/** A Lord have mercy knockout round by round, for the organizer and the share link (BR-140). */
export function RemixRounds({ knockout, ctx }: Props) {
  const layout = useLayout();
  return layout === "phone" ? (
    // A new round resets the picked one, so the newest shows after a draw.
    <RoundPicker key={knockout.rounds.length} knockout={knockout} ctx={ctx} />
  ) : (
    <RoundColumns knockout={knockout} ctx={ctx} />
  );
}
