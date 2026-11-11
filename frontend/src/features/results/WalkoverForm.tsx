import { type ReactNode, useState } from "react";
import { useTranslation } from "react-i18next";

import type { components } from "@/api/schema";
import { StickyActions } from "@/components/StickyActions";
import { Button } from "@/components/ui/button";
import { RadioGroup } from "@/components/ui/radio-group";
import type { Side } from "@/demo/contract";
import { OptionCard } from "@/features/tournaments/play/OptionCard";

type ResultWrite = components["schemas"]["ResultWrite"];

interface WalkoverFormProps {
  names: [string, string];
  initial: Side | null;
  pending: boolean;
  onSave: (body: ResultWrite) => void;
  onCancel: () => void;
  /** More actions under Cancel, such as clearing the result. */
  children?: ReactNode;
}

/**
 * The walkover the design only links to (FR-052, BR-093, BR-124): pick the
 * winner; it counts as a normal win, with no score.
 */
export function WalkoverForm({
  names,
  initial,
  pending,
  onSave,
  onCancel,
  children,
}: WalkoverFormProps) {
  const { t } = useTranslation();
  const [winner, setWinner] = useState<Side | null>(initial);

  return (
    <div className="space-y-4">
      <p className="text-body-md">{t("results.walkover.hint")}</p>
      <RadioGroup
        aria-label={t("results.walkover.legend")}
        value={winner ?? ""}
        onValueChange={(value) => {
          setWinner(value === "side_2" ? "side_2" : "side_1");
        }}
        className="gap-2"
      >
        <OptionCard
          value="side_1"
          title={t("results.walkover.option", { names: names[0] })}
        />
        <OptionCard
          value="side_2"
          title={t("results.walkover.option", { names: names[1] })}
        />
      </RadioGroup>
      <StickyActions>
        <Button
          type="button"
          onClick={() => {
            if (winner !== null) {
              onSave({ walkover_winner: winner, games: [] });
            }
          }}
          disabled={winner === null || pending}
          size="lg"
          className="w-full"
        >
          {t("results.walkover.save")}
        </Button>
        <Button
          type="button"
          variant="text"
          className="w-full"
          onClick={onCancel}
        >
          {t("results.walkover.cancel")}
        </Button>
        {children}
      </StickyActions>
    </div>
  );
}
