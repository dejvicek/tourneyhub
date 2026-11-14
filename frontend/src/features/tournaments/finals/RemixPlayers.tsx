import { useId, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import type { RemixKnockoutData, RemixPlayerData } from "@/features/finals/api";
import { cn } from "@/lib/utils";

import { ChevronDownIcon } from "./icons";

interface RemixPlayersProps {
  knockout: RemixKnockoutData;
  playerName: (playerId: string) => string;
  /** The entry whose change is being saved, or null. */
  pendingEntryId: string | null;
  onChange: (player: RemixPlayerData, disabled: boolean) => void;
}

/**
 * The knockout's players with a disable button each (FR-044, BR-147): a
 * player still in who is disabled has left and is replaced at the next draw
 * (BR-148) or stays in it (BR-149); a knocked-out player who is disabled is
 * skipped as a replacement; a replaced player cannot come back unless the
 * round is deleted (BR-153, BR-154). Collapsed by default: the list holds
 * every player of the knockout, up to 32 or more on a phone.
 */
export function RemixPlayers({
  knockout,
  playerName,
  pendingEntryId,
  onChange,
}: RemixPlayersProps) {
  const { t, i18n } = useTranslation();
  const [open, setOpen] = useState(false);
  const listId = useId();

  // BR-155: who replaced whom, and in which round.
  const replacedBy = new Map(
    knockout.rounds.flatMap((round) =>
      round.matches.flatMap((match) =>
        match.sides.flatMap((side) =>
          side.replacements.map(
            (r) =>
              [
                r.replaced_player_id,
                { playerId: r.player_id, round: round.name },
              ] as const,
          ),
        ),
      ),
    ),
  );
  // The players of the newest round's matches still to be played.
  const playing = new Set(
    (knockout.rounds.at(-1)?.matches ?? [])
      .filter((match) => match.state === "ready" || match.state === "on_field")
      .flatMap((match) => match.sides.flatMap((side) => side.player_ids)),
  );

  const statusLine = (player: RemixPlayerData): string => {
    if (player.status === "replaced") {
      const by = replacedBy.get(player.player_id);
      return t("finals.remix.players.replaced", {
        name: by === undefined ? "" : playerName(by.playerId),
        round:
          by === undefined
            ? ""
            : t(`finals.roundName.${by.round}`).toLocaleLowerCase(
                i18n.resolvedLanguage,
              ),
      });
    }
    if (player.status === "still_in") {
      if (!player.is_disabled) {
        return t("finals.remix.players.stillIn");
      }
      return playing.has(player.player_id)
        ? t("finals.remix.players.leftOpen")
        : t("finals.remix.players.leftNext");
    }
    return player.is_disabled
      ? t("finals.remix.players.notHere")
      : t("finals.remix.players.knockedOut");
  };

  return (
    <section aria-labelledby={`${listId}-heading`} className="space-y-2">
      <h2 id={`${listId}-heading`}>
        <Button
          type="button"
          variant="ghost"
          aria-expanded={open}
          aria-controls={listId}
          className="h-auto min-h-11 w-full justify-between px-0 font-display text-display-section whitespace-normal hover:bg-transparent"
          onClick={() => {
            setOpen(!open);
          }}
        >
          <span className="text-left">{t("finals.remix.players.title")}</span>
          <ChevronDownIcon
            className={cn("transition-transform", open && "rotate-180")}
          />
        </Button>
      </h2>
      <div id={listId} hidden={!open} className="space-y-2">
        <p className="text-body-sm text-muted-foreground">
          {t("finals.remix.players.help")}
        </p>
        <ul className="border-t border-border">
          {knockout.players.map((player) => {
            const name = playerName(player.player_id);
            const disabled = player.is_disabled;
            return (
              <li
                key={player.player_id}
                className="flex items-center gap-3 border-b border-border py-2.5"
              >
                <div className="min-w-0 flex-1">
                  <p className="text-body-md font-bold break-words">{name}</p>
                  <p
                    className={
                      disabled
                        ? "text-body-sm text-notice-warning-foreground"
                        : "text-body-sm text-muted-foreground"
                    }
                  >
                    {statusLine(player)}
                  </p>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  disabled={pendingEntryId === player.entry_id}
                  aria-label={
                    disabled
                      ? t("finals.players.enableFor", { name })
                      : t("finals.players.disableFor", { name })
                  }
                  onClick={() => {
                    // The target state (ADR-008): disabled or not, never a toggle.
                    onChange(player, !disabled);
                  }}
                >
                  {disabled
                    ? t("finals.players.enable")
                    : t("finals.players.disable")}
                </Button>
              </li>
            );
          })}
        </ul>
      </div>
    </section>
  );
}
