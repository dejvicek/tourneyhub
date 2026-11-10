import { useTranslation } from "react-i18next";

import type { PlayModel, RoundData } from "./model";
import { ScheduleMatch } from "./ScheduleMatch";

interface ScheduleViewProps {
  model: PlayModel;
  resultHref: (matchId: string) => string;
}

function roundOrder(rounds: readonly RoundData[]): RoundData[] {
  const open = rounds.filter((r) => r.matches.some((m) => m.outcome === null));
  const done = rounds
    .filter((r) => r.matches.every((m) => m.outcome !== null))
    .reverse();
  return [...open, ...done];
}

/**
 * The group phase by round (screen 6): rounds still being played first, in
 * order, then the played rounds, newest first.
 */
export function ScheduleView({ model, resultHref }: ScheduleViewProps) {
  const { t, i18n } = useTranslation();
  const parts = new Intl.ListFormat(i18n.resolvedLanguage, {
    style: "short",
    type: "unit",
  });

  return (
    <div className="space-y-6">
      {roundOrder(model.groupRounds).map((round) => {
        const infos = round.matches.flatMap((m) => {
          const info = model.matches.get(m.id);
          return info ? [info] : [];
        });
        const played = infos.filter((i) => i.match.outcome !== null).length;
        const onField = infos.filter(
          (i) => i.match.outcome === null && i.field !== undefined,
        ).length;
        const waiting = infos.length - played - onField;
        const status =
          played === infos.length
            ? t("roundRobin.schedule.allPlayed", {
                played,
                total: infos.length,
              })
            : played === 0 && onField === 0
              ? t("roundRobin.schedule.roundWaiting")
              : parts.format([
                  ...(played > 0
                    ? [t("roundRobin.schedule.played", { count: played })]
                    : []),
                  ...(onField > 0
                    ? [t("roundRobin.schedule.onFields", { count: onField })]
                    : []),
                  ...(waiting > 0
                    ? [
                        t("roundRobin.schedule.waitingCount", {
                          count: waiting,
                        }),
                      ]
                    : []),
                ]);
        const headingId = `round-${round.id}`;
        return (
          <section
            key={round.id}
            aria-labelledby={headingId}
            className="space-y-2"
          >
            <div className="flex flex-wrap items-baseline justify-between gap-x-3">
              <h3 id={headingId} className="font-display text-display-section">
                {t("roundRobin.round", { number: round.round_no })}
              </h3>
              <p className="text-body-sm text-muted-foreground">{status}</p>
            </div>
            {round.sitting_out.length > 0 && (
              <p className="text-body-sm text-muted-foreground">
                {t("roundRobin.schedule.sittingOut", {
                  count: round.sitting_out.length,
                })}
              </p>
            )}
            <ul className="space-y-2">
              {infos.map((info) => (
                <li key={info.match.id}>
                  <ScheduleMatch
                    model={model}
                    info={info}
                    resultHref={resultHref(info.match.id)}
                  />
                </li>
              ))}
            </ul>
          </section>
        );
      })}
    </div>
  );
}
