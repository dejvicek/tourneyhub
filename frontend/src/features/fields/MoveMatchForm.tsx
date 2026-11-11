import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import type { components } from "@/api/schema";
import { Button } from "@/components/ui/button";
import { RadioGroup } from "@/components/ui/radio-group";
import { fieldMutations } from "@/features/fields/api";
import type { PlayModel } from "@/features/tournaments/play/model";
import { firstName } from "@/features/tournaments/play/model";
import { OptionCard } from "@/features/tournaments/play/OptionCard";
import { useNames } from "@/features/tournaments/play/useNames";

import { useFieldError } from "./useFieldError";

type PlacementsWrite = components["schemas"]["PlacementsWrite"];

const WAITING = "waiting";

interface MoveMatchFormProps {
  leagueId: string;
  model: PlayModel;
  matchId: string;
  onDone: () => void;
}

/**
 * Screen 6c: move a match to another field, swap it with a busy one, send
 * it back to waiting, or put a waiting match on a free field (FR-093). A
 * choice that would put a player on two fields is not offered (BR-131).
 */
export function MoveMatchForm({
  leagueId,
  model,
  matchId,
  onDone,
}: MoveMatchFormProps) {
  const { t, i18n } = useTranslation();
  const names = useNames(model);
  const list = new Intl.ListFormat(i18n.resolvedLanguage, {
    type: "conjunction",
  });
  const place = useMutation(
    fieldMutations.place(leagueId, model.tournament.id),
  );
  const errorText = useFieldError(place.error);
  const info = model.matches.get(matchId);
  const current = info?.field;
  const myPlayers = new Set(
    info?.match.sides.flatMap((s) => s.player_ids) ?? [],
  );

  const options = model.fields.map((field) => {
    const other =
      field.match_id === null || field.match_id === matchId
        ? undefined
        : model.matches.get(field.match_id);
    const clash = other?.match.sides
      .flatMap((s) => s.player_ids)
      .filter((id) => myPlayers.has(id));
    if (field.id === current?.id) {
      return { field, other, disabled: false, text: t("fields.move.here") };
    }
    if (other) {
      // Only two matches on fields can swap (FR-093).
      return current
        ? {
            field,
            other,
            disabled: false,
            text: t("fields.move.busySwap", {
              match: names.match(other.match.sides),
            }),
          }
        : {
            field,
            other,
            disabled: true,
            text: t("fields.move.busy", {
              match: names.match(other.match.sides),
            }),
          };
    }
    // A waiting match whose players are on another field cannot start (BR-131).
    const busyElsewhere = current
      ? []
      : model.fields.flatMap((f) => {
          const m =
            f.match_id === null ? undefined : model.matches.get(f.match_id);
          const ids =
            m?.match.sides
              .flatMap((s) => s.player_ids)
              .filter((id) => myPlayers.has(id)) ?? [];
          return ids.length > 0 ? [{ number: f.number, ids }] : [];
        });
    const [blocker] = busyElsewhere;
    return blocker
      ? {
          field,
          other,
          disabled: true,
          text: t("fields.move.blocked", {
            count: blocker.ids.length,
            names: list.format(
              blocker.ids.map((id) => firstName(model.players.get(id) ?? "?")),
            ),
            field: blocker.number,
          }),
        }
      : {
          field,
          other,
          disabled: clash !== undefined && clash.length > 0,
          text: t("fields.move.free"),
        };
  });
  const firstFree = options.find(
    (o) => !o.disabled && !o.other && o.field.id !== current?.id,
  );
  const [choice, setChoice] = useState<string>(
    firstFree?.field.id ?? current?.id ?? WAITING,
  );

  if (!info) {
    return <p role="alert">{t("fields.errors.changed")}</p>;
  }
  const chosen = options.find((o) => o.field.id === choice);
  const label =
    choice === WAITING
      ? t("fields.move.toWaiting")
      : chosen === undefined
        ? t("fields.move.choose")
        : chosen.field.id === current?.id
          ? t("fields.move.stay", { number: chosen.field.number })
          : chosen.other
            ? t("fields.move.swap", { number: chosen.field.number })
            : t("fields.move.to", { number: chosen.field.number });

  // The field this screen shows the match on; the API refuses a changed one.
  const from = current?.id ?? null;
  const submit = () => {
    if (choice === current?.id || (choice === WAITING && !current)) {
      onDone();
      return;
    }
    let body: PlacementsWrite;
    if (choice === WAITING) {
      body = {
        placements: [
          { match_id: matchId, field_id: null, from_field_id: from },
        ],
      };
    } else if (chosen?.other && current) {
      // A swap names both matches with their new fields (ADR-008).
      body = {
        placements: [
          {
            match_id: matchId,
            field_id: chosen.field.id,
            from_field_id: current.id,
          },
          {
            match_id: chosen.other.match.id,
            field_id: current.id,
            from_field_id: chosen.field.id,
          },
        ],
      };
    } else {
      body = {
        placements: [
          { match_id: matchId, field_id: choice, from_field_id: from },
        ],
      };
    }
    place.mutate(body, { onSuccess: onDone });
  };

  return (
    <div className="space-y-4">
      <RadioGroup
        aria-label={t("fields.move.options")}
        value={choice}
        onValueChange={setChoice}
        className="gap-2"
      >
        {options.map((option) => (
          <OptionCard
            key={option.field.id}
            value={option.field.id}
            title={t("roundRobin.field", { number: option.field.number })}
            description={option.text}
            disabled={option.disabled}
          />
        ))}
        {current && (
          <OptionCard
            value={WAITING}
            title={t("fields.move.waitingTitle")}
            description={t("fields.move.waitingText")}
          />
        )}
      </RadioGroup>
      {errorText !== null && (
        <p role="alert" className="text-body-sm font-bold text-destructive">
          {errorText}
        </p>
      )}
      <Button
        type="button"
        onClick={submit}
        disabled={place.isPending || chosen?.disabled === true}
        size="lg"
        className="w-full"
      >
        {label}
      </Button>
    </div>
  );
}
