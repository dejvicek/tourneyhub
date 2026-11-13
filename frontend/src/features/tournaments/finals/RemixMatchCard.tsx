import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import type { components } from "@/api/schema";
import { Button } from "@/components/ui/button";
import type {
  PublicRemixKnockoutData,
  RemixKnockoutData,
} from "@/features/finals/api";
import { cn } from "@/lib/utils";

type RoundName = components["schemas"]["RoundName"];
export type RemixMatch = (
  RemixKnockoutData | PublicRemixKnockoutData
)["rounds"][number]["matches"][number];
export type RemixSide = RemixMatch["sides"][number];

/** What the rounds view needs from its page (BR-084). */
export interface RemixContext {
  playerName: (playerId: string) => string;
  /** Where "Enter result" goes for a match; null when it cannot be entered. */
  resultHref: (match: RemixMatch) => string | null;
  /** Whether the viewer may change results (the organizer, not the share link). */
  canChange: boolean;
}

/** The title of a match in its round: "Semifinal 1", "Third place". */
function useMatchTitle(roundName: RoundName, match: RemixMatch): string {
  const { t } = useTranslation();
  return match.kind === "third_place"
    ? t("finals.matchTitle.third_place")
    : t(`finals.matchTitle.${roundName}`, { n: match.position });
}

/** Shapes, not colours, tell the winner: a filled dot, a hollow one for the rest. */
function Dot({ filled }: { filled: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "mt-1.5 size-3 shrink-0 rounded-full border-2 border-current",
        filled && "bg-current",
      )}
    />
  );
}

function SideRow({
  side,
  ctx,
  won,
  score,
}: {
  side: RemixSide;
  ctx: RemixContext;
  won: boolean;
  score: number | undefined;
}) {
  const { t } = useTranslation();
  return (
    <li className="flex items-start gap-2">
      <Dot filled={won} />
      <span
        className={cn(
          "min-w-0 flex-1 break-words",
          won ? "font-bold" : "font-normal",
          side.player_ids.length === 0 && "text-muted-foreground",
        )}
      >
        {side.is_bye
          ? t("finals.knockout.bye")
          : side.player_ids.length === 0
            ? t("finals.knockout.tbd")
            : side.player_ids.map((id, index) => (
                <span key={id}>
                  {index > 0 && " / "}
                  {ctx.playerName(id)}
                  {side.left_player_ids.includes(id) && (
                    <span className="ml-1 rounded-sm border border-current px-1 text-caption font-normal">
                      {t("finals.remix.left")}
                    </span>
                  )}
                </span>
              ))}
        {won && (
          <span className="sr-only"> ({t("finals.knockout.winner")})</span>
        )}
      </span>
      {score !== undefined && (
        <span className="font-display text-score-s">{score}</span>
      )}
    </li>
  );
}

const BOX_STATE = {
  played: "border-border-surface bg-card text-card-foreground",
  ready: "border-team-a bg-card text-card-foreground",
  on_field: "border-team-a bg-card text-card-foreground",
  bye: "border-dashed border-input bg-transparent text-muted-foreground",
} as const satisfies Record<RemixMatch["state"], string>;

/** One match of a round: both sides, the score, its state and a way in. */
export function RemixMatchCard({
  roundName,
  match,
  ctx,
}: {
  roundName: RoundName;
  match: RemixMatch;
  ctx: RemixContext;
}) {
  const { t } = useTranslation();
  const title = useMatchTitle(roundName, match);
  const href = ctx.resultHref(match);
  const played = match.state === "played";
  const winner =
    match.outcome === "side_1" ? 0 : match.outcome === "side_2" ? 1 : null;
  const status =
    match.state === "played"
      ? t("finals.knockout.played")
      : match.state === "bye"
        ? t("finals.knockout.bye")
        : match.state === "on_field"
          ? t("finals.knockout.onField", { field: match.field_number })
          : t("finals.knockout.ready");
  return (
    <article
      aria-label={title}
      className={cn(
        "space-y-2 rounded-lg border p-3 text-body-sm",
        BOX_STATE[match.state],
      )}
    >
      <header className="flex items-baseline justify-between gap-3">
        <p className="text-body-md font-bold">{title}</p>
        <p className="text-caption text-muted-foreground">{status}</p>
      </header>
      <ul className="space-y-1.5">
        {([0, 1] as const).map((index) => (
          <SideRow
            key={index}
            side={match.sides[index]}
            ctx={ctx}
            won={winner === index}
            score={match.score?.[index]}
          />
        ))}
      </ul>
      {match.is_walkover && (
        <p className="text-caption">{t("finals.knockout.walkover")}</p>
      )}
      {"winner_locked" in match && match.winner_locked && (
        <p className="text-caption">{t("finals.remix.winnerFixed")}</p>
      )}
      {href !== null && (
        <Button
          asChild
          variant={played ? "outline" : "default"}
          className="w-full"
        >
          <Link
            to={href}
            aria-label={t(
              played
                ? "finals.knockout.changeResultFor"
                : "finals.knockout.enterResultFor",
              { match: title },
            )}
          >
            {t(
              played
                ? "finals.knockout.changeResult"
                : "finals.knockout.enterResult",
            )}
          </Link>
        </Button>
      )}
    </article>
  );
}
