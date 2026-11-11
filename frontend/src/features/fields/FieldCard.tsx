import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import type { components } from "@/api/schema";
import { Button } from "@/components/ui/button";
import { FieldBadge } from "@/features/tournaments/play/FieldBadge";
import type { PlayModel } from "@/features/tournaments/play/model";
import { useNames } from "@/features/tournaments/play/useNames";
import { cn } from "@/lib/utils";

type FieldRead = components["schemas"]["FieldRead"];

interface FieldCardProps {
  model: PlayModel;
  field: FieldRead;
  resultHref: (matchId: string) => string;
  moveHref: (matchId: string) => string;
  /** Puts a waiting match on this free field (FR-093). */
  onPut: (matchId: string) => void;
  putPending: boolean;
}

const DOT = { side_1: "bg-team-a", side_2: "bg-team-b" } as const;

/** One field: its match with "Enter result" and "Move", or free (Figma: Field card). */
export function FieldCard({
  model,
  field,
  resultHref,
  moveHref,
  onPut,
  putPending,
}: FieldCardProps) {
  const { t } = useTranslation();
  const names = useNames(model);
  const [picking, setPicking] = useState(false);
  const info =
    field.match_id === null ? undefined : model.matches.get(field.match_id);
  const headingId = `field-${field.id}`;

  if (!info) {
    const busyPlayers = new Set(
      model.fields.flatMap((f) => {
        const m =
          f.match_id === null ? undefined : model.matches.get(f.match_id);
        return m ? m.match.sides.flatMap((s) => s.player_ids) : [];
      }),
    );
    return (
      <article
        aria-labelledby={headingId}
        className="space-y-3 rounded-lg border-2 border-dashed border-input p-4"
      >
        <h3 id={headingId}>
          <FieldBadge number={field.number} free size="large" />
        </h3>
        <p className="font-display text-display-name">
          {t("fields.card.free")}
        </p>
        <p className="text-body-sm text-muted-foreground">
          {t("fields.card.freeHint")}
        </p>
        {model.waiting.length > 0 && (
          <Button
            type="button"
            variant="text"
            aria-expanded={picking}
            className="px-0 font-bold text-secondary-foreground"
            onClick={() => {
              setPicking(!picking);
            }}
          >
            {t("fields.card.putHere")}
          </Button>
        )}
        {picking && (
          <ul className="space-y-2">
            {model.waiting.map((w) => {
              const waiting = model.matches.get(w.match_id);
              if (!waiting) {
                return null;
              }
              const blocked = waiting.match.sides.some((s) =>
                s.player_ids.some((id) => busyPlayers.has(id)),
              );
              return (
                <li
                  key={w.match_id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border-surface bg-card p-3 text-card-foreground"
                >
                  <span className="text-body-sm">
                    {names.match(waiting.match.sides)}
                    {blocked && (
                      <span className="block text-caption text-muted-foreground">
                        {t("fields.card.blocked")}
                      </span>
                    )}
                  </span>
                  <Button
                    type="button"
                    variant="outline"
                    disabled={blocked || putPending}
                    onClick={() => {
                      onPut(w.match_id);
                    }}
                  >
                    {t("fields.card.putOn", { number: field.number })}
                    <span className="sr-only">
                      {t("roundRobin.schedule.matchSuffix", {
                        match: names.match(waiting.match.sides),
                      })}
                    </span>
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </article>
    );
  }

  const { match } = info;
  return (
    <article
      aria-labelledby={headingId}
      className="space-y-3 rounded-lg border border-border-surface bg-card p-4 text-card-foreground"
    >
      <div className="flex items-center justify-between gap-3">
        <h3 id={headingId}>
          <FieldBadge number={field.number} size="large" />
        </h3>
        <span className="text-body-sm text-muted-foreground">
          {t("fields.card.detail", {
            round: info.round.round_no,
            format: t(`roundRobin.format.${info.format}`),
          })}
        </span>
      </div>
      <ul className="space-y-1">
        {match.sides.map((side, i) => (
          <li
            key={side.entry_id ?? i}
            className="flex items-center gap-2 text-body-lg font-bold"
          >
            <span
              aria-hidden="true"
              className={cn(
                "size-3 shrink-0 rounded-full",
                i === 0 ? DOT.side_1 : DOT.side_2,
              )}
            />
            {names.side(side)}
          </li>
        ))}
      </ul>
      <Button asChild size="lg" className="w-full">
        <Link to={resultHref(match.id)}>
          {t("roundRobin.schedule.enterResult")}
          <span className="sr-only">
            {t("roundRobin.schedule.matchSuffix", {
              match: names.match(match.sides),
            })}
          </span>
        </Link>
      </Button>
      <Button asChild variant="text" className="w-full">
        <Link to={moveHref(match.id)}>
          {t("fields.card.move")}
          <span className="sr-only">
            {t("roundRobin.schedule.matchSuffix", {
              match: names.match(match.sides),
            })}
          </span>
        </Link>
      </Button>
    </article>
  );
}
