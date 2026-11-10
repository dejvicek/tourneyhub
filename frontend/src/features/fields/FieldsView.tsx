import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router";

import type { PlayRead } from "@/demo/contract";
import { fieldMutations } from "@/features/fields/api";
import type { PlayModel } from "@/features/tournaments/play/model";
import { StandingsPanel } from "@/features/tournaments/play/StandingsPanel";
import { useNames } from "@/features/tournaments/play/useNames";

import { FieldCard } from "./FieldCard";
import { useFieldError } from "./useFieldError";
import { waitingReason } from "./waitingReason";

interface FieldsViewProps {
  leagueId: string;
  model: PlayModel;
  play: PlayRead | undefined;
  resultHref: (matchId: string) => string;
  moveHref: (matchId: string) => string;
  manageHref: string;
}

/**
 * Screen 6b: the fields now playing and the matches waiting for one
 * (FR-090–FR-094, BR-130–BR-135).
 */
export function FieldsView({
  leagueId,
  model,
  play,
  resultHref,
  moveHref,
  manageHref,
}: FieldsViewProps) {
  const { t, i18n } = useTranslation();
  const names = useNames(model);
  const place = useMutation(
    fieldMutations.place(leagueId, model.tournament.id),
  );
  const errorText = useFieldError(place.error);
  const playing = model.fields.filter((f) => f.match_id !== null).length;

  return (
    <div className="grid gap-8 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
      <div className="space-y-8">
        <section aria-labelledby="fields-now" className="space-y-3">
          <div className="flex flex-wrap items-end justify-between gap-x-4">
            <div>
              <h2 id="fields-now" className="font-display text-display-section">
                {t("roundRobin.fields.title")}
              </h2>
              <p className="text-body-sm text-muted-foreground">
                {t("fields.now.summary", {
                  count: model.fields.length,
                  playing,
                })}
              </p>
            </div>
            <Link
              to={manageHref}
              className="inline-flex min-h-11 items-center text-body-md font-bold text-secondary-foreground underline underline-offset-4"
            >
              {t("roundRobin.fields.manage")}
            </Link>
          </div>
          {errorText !== null && (
            <p role="alert" className="text-body-sm font-bold text-destructive">
              {errorText}
            </p>
          )}
          <ul className="grid gap-3 sm:grid-cols-2">
            {model.fields.map((field) => (
              <li key={field.id}>
                <FieldCard
                  model={model}
                  field={field}
                  resultHref={resultHref}
                  moveHref={moveHref}
                  putPending={place.isPending}
                  onPut={(matchId) => {
                    place.mutate({
                      placements: [{ match_id: matchId, field_id: field.id }],
                    });
                  }}
                />
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="fields-waiting" className="space-y-3">
          <h2 id="fields-waiting" className="font-display text-display-section">
            {t("fields.waiting.title")}
          </h2>
          <p className="text-body-sm text-muted-foreground">
            {t("fields.waiting.rule")}
          </p>
          {model.waiting.length === 0 ? (
            <p className="text-body-md">{t("fields.waiting.none")}</p>
          ) : (
            <ol className="space-y-2">
              {model.waiting.map((waiting, index) => {
                const info = model.matches.get(waiting.match_id);
                if (!info) {
                  return null;
                }
                return (
                  <li
                    key={waiting.match_id}
                    className="flex gap-3 rounded-lg border-2 border-dashed border-input p-3"
                  >
                    <span
                      aria-hidden="true"
                      className="flex size-8 shrink-0 items-center justify-center rounded-full bg-nav-active font-display text-score-s text-nav-active-foreground"
                    >
                      {index + 1}
                    </span>
                    <div className="min-w-0 flex-1 space-y-1">
                      <p className="text-body-md font-bold">
                        <span className="sr-only">
                          {t("fields.waiting.position", {
                            position: index + 1,
                          })}
                        </span>
                        {names.match(info.match.sides)}
                      </p>
                      <p className="text-body-sm text-muted-foreground">
                        {waitingReason(
                          t,
                          i18n.resolvedLanguage,
                          model,
                          waiting,
                        )}
                      </p>
                      <Link
                        to={moveHref(waiting.match_id)}
                        className="inline-flex min-h-11 items-center text-body-md font-bold text-secondary-foreground underline underline-offset-4"
                      >
                        {t("fields.waiting.put")}
                        <span className="sr-only">
                          {t("roundRobin.schedule.matchSuffix", {
                            match: names.match(info.match.sides),
                          })}
                        </span>
                      </Link>
                    </div>
                  </li>
                );
              })}
            </ol>
          )}
        </section>
      </div>
      <aside className="hidden lg:block">
        <StandingsPanel model={model} play={play} />
      </aside>
    </div>
  );
}
