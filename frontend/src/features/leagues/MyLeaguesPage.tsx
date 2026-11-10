import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type SubmitEvent, useState } from "react";
import { useTranslation } from "react-i18next";
import { generatePath, Link, useNavigate } from "react-router";

import { DocumentTitle } from "@/components/DocumentTitle";
import { PageFallback } from "@/components/PageFallback";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { fieldErrors } from "@/features/auth/fieldErrors";
import { FormField } from "@/features/auth/FormField";
import { paths } from "@/lib/paths";

import { leagueMutations, leagueQueries } from "./api";
import { EmptyState } from "./EmptyState";
import { useSeasonName } from "./useSeasonName";
import { uuidv7 } from "./uuidv7";

/**
 * The organizer's home (FR-007): their leagues, oldest first, as cards like
 * the design's tournament items, and "New league" in a dialog (FR-010).
 */
export function MyLeaguesPage() {
  const { t } = useTranslation();
  const leagues = useQuery(leagueQueries.list());

  return (
    <section className="space-y-6">
      <DocumentTitle screen={t("leagues.myLeagues.title")} />
      <header className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
        <div className="space-y-2">
          <h1 className="font-display text-display-title">
            {t("leagues.myLeagues.title")}
          </h1>
          <p className="text-body-md text-muted-foreground">
            {t("leagues.myLeagues.lead")}
          </p>
        </div>
        {leagues.data !== undefined && leagues.data.length > 0 && (
          <CreateLeague />
        )}
      </header>
      {leagues.isPending ? (
        <PageFallback />
      ) : leagues.isError ? (
        <div role="alert" className="space-y-3">
          <p className="text-body-md">{t("leagues.myLeagues.loadFailed")}</p>
          <Button
            type="button"
            variant="outline"
            onClick={() => {
              void leagues.refetch();
            }}
          >
            {t("leagues.myLeagues.retry")}
          </Button>
        </div>
      ) : leagues.data.length === 0 ? (
        <EmptyState
          title={t("leagues.myLeagues.empty")}
          body={t("leagues.myLeagues.emptyBody")}
        >
          <CreateLeague />
        </EmptyState>
      ) : (
        <ul className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
          {leagues.data.map((league) => (
            <li key={league.id}>
              <LeagueCard id={league.id} name={league.name} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** One league: its name and active season; the whole card is the link. */
function LeagueCard({ id, name }: { id: string; name: string }) {
  const { t } = useTranslation();
  const seasonName = useSeasonName();
  // P5a's list has ids and names only; the season comes with the league,
  // which the league's screens read next anyway.
  const detail = useQuery(leagueQueries.detail(id));
  const active = detail.data?.seasons.find((s) => s.state === "active");

  return (
    <Link
      to={generatePath(paths.tournaments, { leagueId: id })}
      aria-label={t("leagues.myLeagues.open", { name })}
      className="flex min-h-24 items-center justify-between gap-3 rounded-lg border border-border-surface bg-card px-4 py-3.5 text-card-foreground hover:border-primary focus-visible:ring-[3px] focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background focus-visible:outline-hidden"
    >
      <span className="min-w-0 space-y-1">
        <span className="block font-display text-display-name break-words">
          {name}
        </span>
        <span className="block text-body-sm text-muted-foreground">
          {active === undefined ? null : seasonName(active)}
        </span>
      </span>
      <span aria-hidden="true" className="text-display-section text-primary">
        ›
      </span>
    </Link>
  );
}

/** "New league": a name, then the league opens on its tournaments. */
function CreateLeague() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const create = useMutation(leagueMutations.create(queryClient));
  const [open, setOpen] = useState(false);
  // One id per dialog, so a repeated submit finds the same league (ADR-008).
  const [id, setId] = useState(uuidv7);

  function submit(event: SubmitEvent<HTMLFormElement>) {
    event.preventDefault();
    const value = new FormData(event.currentTarget).get("name");
    create.mutate(
      { id, name: typeof value === "string" ? value : "" },
      {
        onSuccess: (league) => {
          void navigate(
            generatePath(paths.tournaments, { leagueId: league.id }),
          );
        },
      },
    );
  }

  const errors = fieldErrors(t, create.error);
  const failed = create.isError && errors.name === undefined;

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) {
          setId(uuidv7());
          create.reset();
        }
      }}
    >
      <DialogTrigger asChild>
        <Button type="button" size="lg" className="w-full md:w-auto">
          {t("leagues.myLeagues.new")}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form noValidate onSubmit={submit} className="space-y-4">
          <DialogHeader>
            <DialogTitle>{t("leagues.create.title")}</DialogTitle>
            <DialogDescription>
              {t("leagues.create.description")}
            </DialogDescription>
          </DialogHeader>
          <FormField
            label={t("leagues.create.name")}
            name="name"
            autoComplete="off"
            required
            maxLength={100}
            placeholder={t("leagues.create.namePlaceholder")}
            error={errors.name}
          />
          <p role="alert" className="text-body-md font-bold text-destructive">
            {failed ? t("leagues.settings.generic") : undefined}
          </p>
          <DialogFooter className="gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() => {
                setOpen(false);
              }}
            >
              {t("leagues.create.cancel")}
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending
                ? t("leagues.create.submitting")
                : t("leagues.create.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
