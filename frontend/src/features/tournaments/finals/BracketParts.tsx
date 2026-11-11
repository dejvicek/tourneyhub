import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import { Button } from "@/components/ui/button";
import type {
  BracketMatchData as BracketMatch,
  BracketRoundData as BracketRound,
} from "@/features/finals/api";
import { cn } from "@/lib/utils";

import { type BracketContext, sideAt } from "./bracketContext";

/** Shapes, not colours, tell the winner: a filled dot, a hollow one for the rest. */
function Dot({ filled }: { filled: boolean }) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        "size-3 shrink-0 rounded-full border-2 border-current",
        filled && "bg-current",
      )}
    />
  );
}

function winnerSide(match: BracketMatch): 0 | 1 | null {
  return match.outcome === "side_1" ? 0 : match.outcome === "side_2" ? 1 : null;
}

/** "Enter result" for a match to play, "Change result" for a played one (FR-053). */
function ResultLink({
  href,
  match,
  title,
  inverse,
  className,
}: {
  href: string;
  match: BracketMatch;
  title: string;
  inverse?: boolean;
  className?: string;
}) {
  const { t } = useTranslation();
  const played = match.state === "played";
  return (
    <Button
      asChild
      variant={inverse ? "feature" : played ? "outline" : "default"}
      className={className}
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
  );
}

/** Why a played match can't be changed: a later match has a result (BR-094). */
function LockedNote({
  ctx,
  match,
  className,
}: {
  ctx: BracketContext;
  match: BracketMatch;
  className?: string;
}) {
  const { t } = useTranslation();
  if (!ctx.canChange || match.state !== "played" || !match.result_locked) {
    return null;
  }
  return (
    <p className={cn("text-caption", className)}>
      {t("finals.knockout.locked")}
    </p>
  );
}

interface SideRowProps {
  match: BracketMatch;
  index: 0 | 1;
  name: string;
  muted: boolean;
}

function SideRow({ match, index, name, muted }: SideRowProps) {
  const { t } = useTranslation();
  const side = sideAt(match, index);
  const won = winnerSide(match) === index;
  const score = match.score?.[index];
  return (
    <li className="flex items-center gap-2">
      <Dot filled={won} />
      {side.seed !== null && (
        <span
          className={cn(
            "w-5 shrink-0 text-caption",
            muted && "text-muted-foreground",
          )}
        >
          {side.seed}
        </span>
      )}
      <span
        className={cn(
          "min-w-0 flex-1 break-words",
          won ? "font-bold" : "font-normal",
          muted && "text-muted-foreground",
        )}
      >
        {name}
        {won && (
          <span className="sr-only"> ({t("finals.knockout.winner")})</span>
        )}
      </span>
      {score !== undefined && (
        <span
          className={cn(
            "font-display text-score-s",
            !won && match.outcome !== null && "opacity-80",
          )}
        >
          {score}
        </span>
      )}
    </li>
  );
}

const BOX_STATE = {
  played: "border-border-surface bg-card text-card-foreground",
  ready: "border-team-a bg-card text-card-foreground",
  waiting: "border-dashed border-input bg-transparent text-foreground",
  bye: "border-dashed border-input bg-transparent text-muted-foreground",
  // A match on a field is a ready match: one style for both.
  on_field: "border-team-a bg-card text-card-foreground",
} as const satisfies Record<BracketMatch["state"], string>;

interface MatchBoxProps {
  ctx: BracketContext;
  round: BracketRound;
  match: BracketMatch;
  /** Shows the title above the sides (the Semifinal card). */
  titled?: boolean;
  className?: string;
}

/** The design's Bracket match / Semifinal card: both sides, the score, and a way in when it can be played. */
export function MatchBox({
  ctx,
  round,
  match,
  titled,
  className,
}: MatchBoxProps) {
  const { t } = useTranslation();
  const title = ctx.matchTitle(round, match);
  const href = ctx.resultHref(match);
  const muted = match.state === "waiting" || match.state === "bye";
  return (
    <div
      className={cn(
        "relative rounded-lg border p-3 text-body-sm",
        BOX_STATE[match.state],
        className,
      )}
    >
      {titled && <p className="mb-1.5 text-caption font-bold">{title}</p>}
      <ul className="space-y-1.5">
        {([0, 1] as const).map((index) => (
          <SideRow
            key={index}
            match={match}
            index={index}
            name={ctx.sideName(sideAt(match, index))}
            muted={muted && sideAt(match, index).entry_id === null}
          />
        ))}
      </ul>
      {match.is_walkover && (
        <p className="mt-1 text-caption">{t("finals.knockout.walkover")}</p>
      )}
      {match.state !== "played" && match.field_number !== null && (
        <p className="mt-1 text-caption font-bold">
          {t("finals.knockout.onField", { field: match.field_number })}
        </p>
      )}
      {href !== null && (
        <ResultLink
          href={href}
          match={match}
          title={title}
          className="mt-2 w-full"
        />
      )}
      <LockedNote ctx={ctx} match={match} className="mt-2" />
    </div>
  );
}

interface FinalCardProps {
  ctx: BracketContext;
  round: BracketRound;
  match: BracketMatch;
}

/** The final on the green playfield: its own format, the field, and a Feature button. */
export function FinalCard({ ctx, round, match }: FinalCardProps) {
  const { t } = useTranslation();
  const href = ctx.resultHref(match);
  const title = ctx.matchTitle(round, match);
  const format = t(`finals.format.${match.match_format}`);
  const winner = winnerSide(match);
  return (
    <section
      aria-label={title}
      className="space-y-3 rounded-lg bg-field p-4 text-field-foreground"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="font-display text-display-section">{title}</h2>
        <p className="text-caption font-bold">
          {match.field_number === null
            ? format
            : t("finals.knockout.formatAndField", {
                format,
                field: match.field_number,
              })}
        </p>
      </div>
      <ul className="space-y-2">
        {([0, 1] as const).map((index) => (
          <li key={index} className="flex items-center gap-3 text-body-md">
            <span
              aria-hidden="true"
              className={cn(
                "size-3.5 shrink-0 rounded-full",
                index === 0 ? "bg-team-a" : "bg-team-b",
              )}
            />
            <span
              className={cn(
                "min-w-0 flex-1 break-words",
                winner === index ? "font-bold" : "",
              )}
            >
              {ctx.sideName(sideAt(match, index))}
              {winner === index && (
                <span className="sr-only">
                  {" "}
                  ({t("finals.knockout.winner")})
                </span>
              )}
            </span>
            {match.score !== null && (
              <span className="font-display text-score-m">
                {match.score[index]}
              </span>
            )}
          </li>
        ))}
      </ul>
      {href !== null && (
        <ResultLink
          href={href}
          match={match}
          title={title}
          inverse
          className="w-full"
        />
      )}
    </section>
  );
}

/** The design's Match card: one match in the phone's list for a round. */
export function MatchCard({ ctx, round, match }: MatchBoxProps) {
  const { t } = useTranslation();
  const title = ctx.matchTitle(round, match);
  const href = ctx.resultHref(match);
  const boxState = BOX_STATE[match.state];
  const status =
    match.state === "played"
      ? t("finals.knockout.played")
      : match.state === "waiting"
        ? t("finals.knockout.waiting")
        : t("finals.knockout.ready");
  return (
    <article
      aria-label={title}
      className={cn("space-y-2 rounded-lg border p-3", boxState)}
    >
      <header className="flex items-baseline justify-between gap-3">
        <p className="text-body-md font-bold">{title}</p>
        <p className="text-caption text-muted-foreground">
          {status}
          {match.field_number !== null &&
            `, ${t("finals.knockout.onField", { field: match.field_number })}`}
        </p>
      </header>
      <ul className="space-y-1.5 text-body-sm">
        {([0, 1] as const).map((index) => (
          <SideRow
            key={index}
            match={match}
            index={index}
            name={ctx.sideName(sideAt(match, index))}
            muted={sideAt(match, index).entry_id === null}
          />
        ))}
      </ul>
      {match.next_number !== null && (
        <p className="text-caption text-muted-foreground">
          {t("finals.knockout.winnerPlays", {
            match: ctx.titleOfNumber(match.next_number),
          })}
        </p>
      )}
      {href !== null && (
        <ResultLink
          href={href}
          match={match}
          title={title}
          className="w-full"
        />
      )}
      <LockedNote ctx={ctx} match={match} />
    </article>
  );
}
