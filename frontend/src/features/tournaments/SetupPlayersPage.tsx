import { useMutation } from "@tanstack/react-query";
import { useId, useState } from "react";
import { useTranslation } from "react-i18next";
import { generatePath, Link, useNavigate } from "react-router";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { setupMutations } from "@/features/tournaments/api";
import { useLayout } from "@/hooks/useLayout";
import { paths } from "@/lib/paths";

import { describeError } from "./setup/errors";
import { PersonPlusIcon, SearchIcon } from "./setup/icons";
import { Notice } from "./setup/Notice";
import { entryCount, minimumPlayers, roundRobinSize } from "./setup/schedule";
import { type SetupData, SetupPage } from "./setup/SetupPage";
import { SoFarCard } from "./setup/SoFarCard";

/** Searching ignores case and accents: "Novak" finds "Nováková". */
function plain(text: string): string {
  return text
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLowerCase();
}

/** Screen 3: pick tonight's players from the league list (FR-032). */
export function SetupPlayersPage() {
  const { t } = useTranslation();
  return (
    <SetupPage step={2} title={() => t("tournaments.setup.players.title")}>
      {(data) => <PlayersForm key={data.tournamentId} data={data} />}
    </SetupPage>
  );
}

function PlayersForm({ data }: { data: SetupData }) {
  const { t } = useTranslation();
  const layout = useLayout();
  const navigate = useNavigate();
  const searchId = useId();
  const { leagueId, tournamentId, tournament, setup, ranking } = data;
  const format = setup.format;
  const [picked, setPicked] = useState(() => new Set(setup.player_ids));
  const [query, setQuery] = useState("");
  const save = useMutation(setupMutations.players(leagueId, tournamentId));

  const shown = ranking.filter((row) =>
    plain(row.name).includes(plain(query.trim())),
  );
  const count = picked.size;
  const type = tournament.type;
  const noGroup = format.group_phase === "none";
  const minimum = minimumPlayers(type, format.third_place_match, noGroup);
  const oddDoubles = type === "doubles" && count % 2 === 1;
  const enough = count >= minimum && !oddDoubles;

  const toggle = (playerId: string, checked: boolean) => {
    setPicked((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(playerId);
      } else {
        next.delete(playerId);
      }
      return next;
    });
  };
  // The ranking's order, whatever order the boxes were ticked in.
  const chosen = () =>
    ranking.filter((row) => picked.has(row.player_id)).map((r) => r.player_id);
  const goTo = (path: string) => {
    save.mutate(chosen(), {
      onSuccess: () => {
        void navigate(generatePath(path, { leagueId, tournamentId }));
      },
    });
  };

  const entries = entryCount(type, count);

  const list = (
    <ul className="md:columns-2 md:gap-x-6">
      {shown.map((row) => (
        <PickRow
          key={row.player_id}
          rank={row.rank}
          name={row.name}
          points={row.points}
          checked={picked.has(row.player_id)}
          onCheckedChange={(checked) => {
            toggle(row.player_id, checked);
          }}
        />
      ))}
    </ul>
  );

  const content = (
    <div className="grid gap-6">
      <div className="grid gap-2">
        <Label htmlFor={searchId}>
          {t("tournaments.setup.players.search")}
        </Label>
        <div className="relative">
          <SearchIcon className="pointer-events-none absolute top-1/2 left-3.5 size-5 -translate-y-1/2 text-muted-foreground" />
          <Input
            id={searchId}
            type="search"
            value={query}
            className="pl-11"
            onChange={(event) => {
              setQuery(event.target.value);
            }}
          />
        </div>
      </div>

      <div className="grid gap-1">
        <div className="flex items-center justify-between gap-3">
          <h2 className="font-display text-display-section" aria-live="polite">
            {t("tournaments.setup.players.picked", {
              picked: count,
              total: ranking.length,
            })}
          </h2>
          <div className="flex gap-1">
            <Button
              type="button"
              variant="ghost"

              onClick={() => {
                setPicked(new Set(ranking.map((row) => row.player_id)));
              }}
            >
              {t("tournaments.setup.players.pickAll")}
            </Button>
            <Button
              type="button"
              variant="ghost"

              onClick={() => {
                setPicked(new Set());
              }}
            >
              {t("tournaments.setup.players.clearAll")}
            </Button>
          </div>
        </div>
        <p className="text-body-sm text-muted-foreground">
          {type === "dyp"
            ? t("tournaments.setup.players.orderHintDyp")
            : t("tournaments.setup.players.orderHint")}
        </p>
      </div>

      {shown.length === 0 ? (
        <p className="text-body-md text-muted-foreground">
          {t("tournaments.setup.players.noMatch", { query: query.trim() })}
        </p>
      ) : (
        list
      )}

      <Link
        to={generatePath(paths.players, { leagueId })}
        className="inline-flex min-h-11 items-center gap-2 text-body-md font-bold text-primary underline-offset-4 hover:underline"
      >
        <PersonPlusIcon className="size-5" />
        {t("tournaments.setup.players.addPlayer")}
      </Link>

      <PlayersNotice
        type={type}
        players={count}
        entries={entries}
        enough={enough}
        minimum={minimum}
        oddDoubles={oddDoubles}
        legs={format.round_robin_legs}
        group={format.group_phase}
      />

      {save.isError && (
        <p role="alert" className="text-body-md text-destructive">
          {describeError(save.error, t)}
        </p>
      )}

      <div className="flex flex-col gap-3 md:flex-row md:justify-between">
        <Button
          type="button"
          variant="ghost"
          disabled={save.isPending}
          size="lg"
          onClick={() => {
            save.mutate(chosen(), {
              onSuccess: () => {
                void navigate({
                  pathname: generatePath(paths.newTournament, { leagueId }),
                  search: `?tournament=${tournamentId}`,
                });
              },
            });
          }}
        >
          {t("tournaments.setup.back")}
        </Button>
        <Button
          type="button"
          disabled={!enough || save.isPending}
          size="lg"
          className="md:min-w-60"
          onClick={() => {
            goTo(paths.setupDraw);
          }}
        >
          {t(`tournaments.setup.players.next.${type}`)}
        </Button>
      </div>
    </div>
  );

  return layout === "desktop" ? (
    <div className="grid grid-cols-[1fr_20rem] items-start gap-8">
      {content}
      <SoFarCard format={format} players={count} />
    </div>
  ) : (
    content
  );
}

interface PickRowProps {
  rank: number;
  name: string;
  points: number;
  checked: boolean;
  onCheckedChange: (checked: boolean) => void;
}

/** The design's Player pick row: rank, name, season points, checkbox. */
function PickRow({
  rank,
  name,
  points,
  checked,
  onCheckedChange,
}: PickRowProps) {
  const { t } = useTranslation();
  const id = useId();
  return (
    <li className="break-inside-avoid border-t border-border first:border-t-0">
      <div className="flex min-h-14 items-center gap-3 py-1.5">
        <span
          aria-hidden="true"
          className="w-7 shrink-0 text-center font-display text-score-m text-muted-foreground"
        >
          {rank}
        </span>
        <Label
          htmlFor={`${id}-box`}
          id={`${id}-name`}
          className="min-h-11 flex-1 cursor-pointer text-body-lg font-bold"
        >
          {name}
        </Label>
        <span
          id={`${id}-points`}
          className="text-body-sm text-muted-foreground"
        >
          {t("tournaments.setup.players.points", { points })}
        </span>
        <Checkbox
          id={`${id}-box`}
          checked={checked}
          aria-labelledby={`${id}-name`}
          aria-describedby={`${id}-points`}
          onCheckedChange={(next) => {
            onCheckedChange(next === true);
          }}
        />
      </div>
    </li>
  );
}

interface PlayersNoticeProps {
  type: SetupData["tournament"]["type"];
  players: number;
  entries: number;
  enough: boolean;
  minimum: number;
  oddDoubles: boolean;
  legs: 1 | 2;
  group: SetupData["setup"]["format"]["group_phase"];
}

/** What the picked number makes: pairs, matches, rounds; or why it is not enough. */
function PlayersNotice({
  type,
  players,
  entries,
  enough,
  minimum,
  oddDoubles,
  legs,
  group,
}: PlayersNoticeProps) {
  const { t } = useTranslation();
  if (oddDoubles) {
    return (
      <Notice
        variant="warning"
        title={t("tournaments.setup.players.oddDoubles.title")}
      >
        {t("tournaments.setup.players.oddDoubles.body")}
      </Notice>
    );
  }
  if (!enough) {
    return (
      <Notice
        variant="warning"
        title={t("tournaments.setup.players.tooFew.title", { count: minimum })}
      >
        {t("tournaments.setup.players.tooFew.body", { picked: players })}
      </Notice>
    );
  }
  const paired = type === "dyp" || type === "doubles";
  const title = paired
    ? t("tournaments.setup.players.pairsTitle", { count: entries, players })
    : t("tournaments.setup.players.playersTitle", { count: players });
  const odd = paired ? players % 2 === 1 : entries % 2 === 1;
  const body = (() => {
    switch (group) {
      case "round_robin": {
        const size = roundRobinSize(entries, legs);
        return t("tournaments.setup.players.roundRobin", {
          count: size.matches,
          rounds: size.rounds,
        });
      }
      case "swiss":
        return t("tournaments.setup.players.swiss");
      case "monster_dyp":
        return t("tournaments.setup.players.monsterDyp", {
          count: Math.floor(players / 4),
        });
      case "none":
        return t("tournaments.setup.players.knockout", { count: entries });
    }
  })();
  return (
    <Notice variant="info" title={title}>
      <p>{body}</p>
      {odd && group !== "none" && (
        <p>
          {paired
            ? t("tournaments.setup.players.oddLeftOut")
            : t("tournaments.setup.players.oddSitsOut")}
        </p>
      )}
    </Notice>
  );
}
