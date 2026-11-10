import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Sheet,
  SheetClose,
  SheetContent,
  SheetDescription,
  SheetFooter,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import { finalsMutations } from "@/features/finals/api";

import { errorText } from "./errorText";
import { Notice } from "./Notice";

export interface LateCandidate {
  id: string;
  name: string;
  rank: number;
  points: number;
}

interface FormProps {
  leagueId: string;
  tournamentId: string;
  candidates: readonly LateCandidate[];
  /** The round the player would start in. */
  fromRound: number;
  /** FR-048: the tie-breakers use BH1 or BH2, so missed rounds are unfair. */
  warn: boolean;
  onAdded: (name: string) => void;
}

function LateForm({
  leagueId,
  tournamentId,
  candidates,
  fromRound,
  warn,
  onAdded,
}: FormProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const add = useMutation(
    finalsMutations.addLatePlayer(queryClient, leagueId, tournamentId),
  );
  const [selected, setSelected] = useState(candidates[0]?.id);
  const player = candidates.find((c) => c.id === selected);
  const missed = fromRound - 1;

  if (candidates.length === 0) {
    return <p className="text-body-md">{t("finals.players.lateNone")}</p>;
  }
  return (
    <>
      <RadioGroup
        aria-label={t("finals.players.latePick")}
        value={selected}
        onValueChange={setSelected}
      >
        {candidates.map((candidate) => (
          <div
            key={candidate.id}
            className="flex min-h-11 items-center gap-3 border-b border-border py-1"
          >
            <RadioGroupItem value={candidate.id} id={`late-${candidate.id}`} />
            <Label
              htmlFor={`late-${candidate.id}`}
              className="flex min-h-11 flex-1 items-center gap-3 text-body-md"
            >
              <span className="w-7 font-display text-score-s">
                {candidate.rank}
              </span>
              <span className="flex-1 font-bold">{candidate.name}</span>
              <span className="text-body-sm text-muted-foreground">
                {t("finals.players.latePoints", { count: candidate.points })}
              </span>
            </Label>
          </div>
        ))}
      </RadioGroup>
      {warn && missed > 0 && player !== undefined && (
        <Notice tone="warning" title={t("finals.players.warnTitle")}>
          {t("finals.players.warnBody", { name: player.name, count: missed })}
        </Notice>
      )}
      {add.isError && (
        <p role="alert" className="text-body-sm">
          {errorText(t, add.error)}
        </p>
      )}
      <SheetFooter>
        <Button
          type="button"
          size="lg"
          className="min-h-14"
          disabled={player === undefined || add.isPending}
          onClick={() => {
            if (player === undefined) {
              return;
            }
            // ADR-008: carries the round the player is expected to start in.
            add.mutate(
              { player_id: player.id, from_round_no: fromRound },
              {
                onSuccess: () => {
                  onAdded(player.name);
                },
              },
            );
          }}
        >
          {player === undefined
            ? t("finals.players.addLate")
            : t("finals.players.addConfirm", {
                name: player.name,
                round: fromRound,
              })}
        </Button>
        <SheetClose asChild>
          <Button type="button" variant="ghost" className="min-h-11">
            {t("finals.common.cancel")}
          </Button>
        </SheetClose>
      </SheetFooter>
    </>
  );
}

interface LatePlayerSheetProps extends Omit<FormProps, "onAdded"> {
  onAdded: (name: string) => void;
}

/** FR-047, FR-048: add a late player from the league's list, warning when BH makes it unfair. */
export function LatePlayerSheet(props: LatePlayerSheetProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button type="button" size="lg" className="min-h-14 w-full">
          {t("finals.players.addLate")}
        </Button>
      </SheetTrigger>
      <SheetContent side="bottom">
        <SheetHeader>
          <SheetTitle>{t("finals.players.lateTitle")}</SheetTitle>
          <SheetDescription>
            {t("finals.players.lateLead", { round: props.fromRound })}
          </SheetDescription>
        </SheetHeader>
        <LateForm
          {...props}
          onAdded={(name) => {
            setOpen(false);
            props.onAdded(name);
          }}
        />
      </SheetContent>
    </Sheet>
  );
}
