import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { Switch } from "@/components/ui/switch";
import { finalsMutations } from "@/features/finals/api";
import { rules, type SwissTiebreaker } from "@/lib/rules";

import { errorText } from "./errorText";

interface Draft {
  key: SwissTiebreaker;
  on: boolean;
}

function initialDraft(active: readonly SwissTiebreaker[]): Draft[] {
  // The rules list every tie-breaker there is (FR-043); the enabled ones come first, in order.
  const rest = rules.swissTiebreakers.filter((key) => !active.includes(key));
  return [...active, ...rest].map((key) => ({ key, on: active.includes(key) }));
}

interface FormProps {
  leagueId: string;
  tournamentId: string;
  active: readonly SwissTiebreaker[];
  onSaved: () => void;
}

function TiebreakerForm({
  leagueId,
  tournamentId,
  active,
  onSaved,
}: FormProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const save = useMutation(
    finalsMutations.setTiebreakers(queryClient, leagueId, tournamentId),
  );
  const [draft, setDraft] = useState(() => initialDraft(active));

  // Moving by a tap, not only by dragging (guide §6).
  const move = (index: number, by: -1 | 1) => {
    setDraft((items) => {
      const target = index + by;
      const moved = items[index];
      const other = items[target];
      if (moved === undefined || other === undefined) {
        return items;
      }
      return items.map((item, i) =>
        i === index ? other : i === target ? moved : item,
      );
    });
  };

  return (
    <>
      <ol className="space-y-2">
        {draft.map((item, index) => {
          const name = t(`finals.tiebreakers.names.${item.key}`);
          return (
            <li
              key={item.key}
              className="flex items-center gap-2 rounded-lg border border-border-surface bg-card px-3 py-2"
            >
              <Switch
                checked={item.on}
                aria-label={t("finals.tiebreakers.on", { name })}
                onCheckedChange={(on) => {
                  setDraft((items) =>
                    items.map((i) => (i.key === item.key ? { ...i, on } : i)),
                  );
                }}
              />
              <span className="min-w-0 flex-1 text-body-md font-bold">
                {name}
              </span>
              <Button
                type="button"
                variant="outline"
                size="icon"
                disabled={index === 0}
                aria-label={t("finals.tiebreakers.moveUp", { name })}
                onClick={() => {
                  move(index, -1);
                }}
              >
                <span aria-hidden="true">↑</span>
              </Button>
              <Button
                type="button"
                variant="outline"
                size="icon"
                disabled={index === draft.length - 1}
                aria-label={t("finals.tiebreakers.moveDown", { name })}
                onClick={() => {
                  move(index, 1);
                }}
              >
                <span aria-hidden="true">↓</span>
              </Button>
            </li>
          );
        })}
      </ol>
      {save.isError && (
        <p role="alert" className="text-body-sm">
          {errorText(t, save.error)}
        </p>
      )}
      <SheetFooter>
        <Button
          type="button"
          disabled={save.isPending}
          onClick={() => {
            save.mutate(
              { tiebreakers: draft.filter((i) => i.on).map((i) => i.key) },
              { onSuccess: onSaved },
            );
          }}
        >
          {t("finals.tiebreakers.save")}
        </Button>
      </SheetFooter>
    </>
  );
}

interface TiebreakerSheetProps {
  leagueId: string;
  tournamentId: string;
  /** The group phase's enabled tie-breakers, in order. */
  tiebreakers: readonly SwissTiebreaker[];
}

/** FR-043: switch each tie-breaker on or off and put them in order. */
export function TiebreakerSheet({
  leagueId,
  tournamentId,
  tiebreakers,
}: TiebreakerSheetProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button type="button" variant="outline">
          {t("finals.tiebreakers.change")}
        </Button>
      </SheetTrigger>
      <SheetContent side="bottom">
        <SheetHeader>
          <SheetTitle>{t("finals.tiebreakers.title")}</SheetTitle>
          <SheetDescription>{t("finals.tiebreakers.lead")}</SheetDescription>
        </SheetHeader>
        <TiebreakerForm
          leagueId={leagueId}
          tournamentId={tournamentId}
          active={tiebreakers}
          onSaved={() => {
            setOpen(false);
          }}
        />
      </SheetContent>
    </Sheet>
  );
}
