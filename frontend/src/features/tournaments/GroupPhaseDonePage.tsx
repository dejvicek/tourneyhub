import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { generatePath, Link, useNavigate } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { RadioGroup } from "@/components/ui/radio-group";
import { Switch } from "@/components/ui/switch";
import { resultMutations } from "@/features/results/api";
import { useRouteParam } from "@/hooks/useRouteParam";
import { paths } from "@/lib/paths";

import { MinusIcon, PlusIcon } from "./play/icons";
import { entryPlayers, groupProgress, shortName } from "./play/model";
import { Notice } from "./play/Notice";
import { OptionCard } from "./play/OptionCard";
import { StandingsNotes } from "./play/StandingsNotes";
import { StandingsTable } from "./play/StandingsTable";
import { TempChrome } from "./play/TempChrome";
import { usePlay } from "./play/usePlay";

type Next = "knockout" | "finish";

/** The first-round pairs of a bracket of `size` seeds, 1 v N, 2 v N-1 … */
function firstRound(size: number): [number, number][] {
  const pairs: [number, number][] = [];
  for (let seed = 1; seed <= size / 2; seed++) {
    pairs.push([seed, size + 1 - seed]);
  }
  return pairs;
}

const isPowerOfTwo = (n: number) => n >= 2 && (n & (n - 1)) === 0;

/**
 * Screen 8: the round robin is played. Its final standings, then the
 * choice of FR-040: a knockout of the best entries (FR-045, BR-080) or
 * finishing now, after a confirmation.
 */
export function GroupPhaseDonePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const leagueId = useRouteParam("leagueId");
  const tournamentId = useRouteParam("tournamentId");
  const { model, play, failed } = usePlay(leagueId, tournamentId);
  const finish = useMutation(resultMutations.finish(leagueId, tournamentId));
  const [next, setNext] = useState<Next>("knockout");
  const [qualifiers, setQualifiers] = useState(4);
  const [thirdPlace, setThirdPlace] = useState(false);
  const params = { leagueId, tournamentId };
  const title = t("roundRobin.done.screenTitle");

  if (!model || !play) {
    return (
      <>
        <DocumentTitle screen={title} />
        <p role={failed ? "alert" : "status"}>
          {failed ? t("roundRobin.loadFailed") : t("loading")}
        </p>
      </>
    );
  }
  const progress = groupProgress(model);
  const entries = play.standings.length;
  // BR-080: at least 2, or 4 with a third-place match; at most every entry.
  const min = thirdPlace ? 4 : 2;
  const count = Math.min(Math.max(qualifiers, min), entries);
  const atCut = play.standings[count - 1];
  const belowCut = play.standings[count];
  const lotAtCut = atCut !== undefined && belowCut?.place === atCut.place;
  const seedName = (seed: number) => {
    const row = play.standings[seed - 1];
    return row ? entryPlayers(model, row.entry_id).map(shortName) : [];
  };

  return (
    <TempChrome
      leagueId={leagueId}
      tournamentId={tournamentId}
      title={title}
      subtitle={t("roundRobin.done.subtitle", {
        tournament: model.tournament.name,
        played: progress.played,
        total: progress.total,
      })}
    >
      <DocumentTitle screen={title} />
      {!play.group_done && (
        <Notice variant="warning" title={t("roundRobin.done.notYetTitle")}>
          <p>
            {t("roundRobin.done.notYet", {
              count: progress.total - progress.played,
            })}
          </p>
          <Link
            to={generatePath(paths.tournament, params)}
            className="inline-flex min-h-11 items-center font-bold underline underline-offset-4"
          >
            {t("roundRobin.done.backToSchedule")}
          </Link>
        </Notice>
      )}
      <div className="grid gap-8 md:grid-cols-2">
        <section aria-labelledby="final-standings" className="space-y-3">
          <h2
            id="final-standings"
            className="font-display text-display-section"
          >
            {t("roundRobin.done.standings")}
          </h2>
          <StandingsTable
            model={model}
            rows={play.standings}
            caption={t("roundRobin.done.standings")}
            cutAfter={
              next === "knockout" && count < entries ? count : undefined
            }
          />
          <StandingsNotes model={model} rows={play.standings} />
        </section>

        {play.group_done && model.tournament.state === "in_progress" && (
          <section aria-labelledby="what-next" className="space-y-4">
            <h2 id="what-next" className="font-display text-display-section">
              {t("roundRobin.done.next")}
            </h2>
            <RadioGroup
              aria-labelledby="what-next"
              value={next}
              onValueChange={(value) => {
                setNext(value === "finish" ? "finish" : "knockout");
              }}
              className="gap-2"
            >
              <OptionCard
                value="knockout"
                title={t("roundRobin.done.knockout")}
                description={t("roundRobin.done.knockoutText")}
              />
              <OptionCard
                value="finish"
                title={t("roundRobin.done.finish")}
                description={t("roundRobin.done.finishText")}
              />
            </RadioGroup>

            {next === "knockout" ? (
              <>
                <div className="flex items-center justify-between gap-4 border-t pt-4">
                  <div>
                    <p id="qualifiers" className="text-body-md font-bold">
                      {t("roundRobin.done.qualifiers")}
                    </p>
                    <p className="text-body-sm text-muted-foreground">
                      {t("roundRobin.done.qualifiersHint", { count: min })}
                    </p>
                  </div>
                  <div
                    role="group"
                    aria-labelledby="qualifiers"
                    className="flex items-center gap-2"
                  >
                    <Button
                      type="button"
                      variant="outline"
                      className="size-11"
                      disabled={count <= min}
                      aria-label={t("roundRobin.done.fewer")}
                      onClick={() => {
                        setQualifiers(count - 1);
                      }}
                    >
                      {/* TODO(foundation-buttons): size icon is 44 px after the rebase. */}
                      <MinusIcon className="size-5" />
                    </Button>
                    <output
                      aria-live="polite"
                      className="w-8 text-center font-display text-score-l"
                    >
                      {count}
                    </output>
                    <Button
                      type="button"
                      variant="outline"
                      className="size-11"
                      disabled={count >= entries}
                      aria-label={t("roundRobin.done.more")}
                      onClick={() => {
                        setQualifiers(count + 1);
                      }}
                    >
                      <PlusIcon className="size-5" />
                    </Button>
                  </div>
                </div>
                <div className="flex items-center justify-between gap-4 border-t pt-4">
                  <div>
                    <p id="third-place" className="text-body-md font-bold">
                      {t("roundRobin.done.thirdPlace")}
                    </p>
                    <p className="text-body-sm text-muted-foreground">
                      {t("roundRobin.done.thirdPlaceHint")}
                    </p>
                  </div>
                  <Switch
                    aria-labelledby="third-place"
                    checked={thirdPlace}
                    disabled={entries < 4}
                    onCheckedChange={setThirdPlace}
                  />
                </div>
                {lotAtCut && (
                  <p className="text-body-sm text-muted-foreground">
                    {t("roundRobin.done.lot", { place: atCut.place })}
                  </p>
                )}
                <div className="space-y-2">
                  <h3 className="font-display text-display-section">
                    {t(
                      count === 2
                        ? "roundRobin.done.preview.final"
                        : count === 4
                          ? "roundRobin.done.preview.semifinals"
                          : count === 8
                            ? "roundRobin.done.preview.quarterfinals"
                            : "roundRobin.done.preview.firstRound",
                    )}
                  </h3>
                  {isPowerOfTwo(count) ? (
                    <ul className="grid gap-2 sm:grid-cols-2">
                      {firstRound(count).map(([a, b]) => (
                        <li
                          key={a}
                          className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-center gap-2 rounded-lg border border-border-surface bg-card p-3 text-body-sm text-card-foreground"
                        >
                          <span>
                            <span className="font-display text-score-s">
                              {a}
                            </span>{" "}
                            {seedName(a).join(" ")}
                          </span>
                          <span className="text-caption font-bold text-muted-foreground">
                            {t("roundRobin.done.preview.versus")}
                          </span>
                          <span className="text-right">
                            <span className="font-display text-score-s">
                              {b}
                            </span>{" "}
                            {seedName(b).join(" ")}
                          </span>
                        </li>
                      ))}
                    </ul>
                  ) : (
                    <p className="text-body-sm text-muted-foreground">
                      {t("roundRobin.done.preview.byes", {
                        count: 2 ** Math.ceil(Math.log2(count)) - count,
                      })}
                    </p>
                  )}
                </div>
                <Notice
                  variant="warning"
                  title={t("roundRobin.done.lockTitle")}
                >
                  {t("roundRobin.done.lockBody")}
                </Notice>
                <Button
                  type="button"
                  className="h-14 w-full rounded-lg text-button-lg"
                  onClick={() => {
                    // The knockout is drawn on screen 13 (FR-045), with these choices.
                    const search = new URLSearchParams({
                      qualifiers: String(count),
                      thirdPlace: String(thirdPlace),
                    });
                    void navigate(
                      `${generatePath(paths.startKnockout, params)}?${search.toString()}`,
                    );
                  }}
                >
                  {/* TODO(foundation-buttons): size lg after the rebase. */}
                  {t("roundRobin.done.draw")}
                </Button>
              </>
            ) : (
              <>
                {finish.isError && (
                  <p
                    role="alert"
                    className="text-body-md font-bold text-destructive"
                  >
                    {finish.error.status === 409
                      ? t("roundRobin.done.finishChanged")
                      : t("roundRobin.done.finishFailed")}
                  </p>
                )}
                {/* FR-040: finishing asks first; the design draws no confirm. */}
                <AlertDialog>
                  <AlertDialogTrigger asChild>
                    <Button
                      type="button"
                      className="h-14 w-full rounded-lg text-button-lg"
                      disabled={finish.isPending}
                    >
                      {/* TODO(foundation-buttons): size lg after the rebase. */}
                      {t("roundRobin.done.finishButton")}
                    </Button>
                  </AlertDialogTrigger>
                  <AlertDialogContent>
                    <AlertDialogHeader>
                      <AlertDialogTitle>
                        {t("roundRobin.done.confirmTitle")}
                      </AlertDialogTitle>
                      <AlertDialogDescription>
                        {t("roundRobin.done.confirmBody")}
                      </AlertDialogDescription>
                    </AlertDialogHeader>
                    <AlertDialogFooter>
                      <AlertDialogCancel>
                        {t("roundRobin.done.confirmCancel")}
                      </AlertDialogCancel>
                      <AlertDialogAction
                        onClick={() => {
                          finish.mutate(undefined, {
                            onSuccess: () => {
                              void navigate(
                                generatePath(paths.finished, params),
                              );
                            },
                          });
                        }}
                      >
                        {t("roundRobin.done.confirmAction")}
                      </AlertDialogAction>
                    </AlertDialogFooter>
                  </AlertDialogContent>
                </AlertDialog>
              </>
            )}
          </section>
        )}
      </div>
    </TempChrome>
  );
}
