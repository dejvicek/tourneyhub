import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import {
  defaultSitOutPoints,
  SIT_OUT_POINTS,
  type SitOutPoints,
} from "@/lib/sitOutPoints";

import type { MatchFormat } from "./format";
import { SegmentedControl } from "./SegmentedControl";
import { sitOutLabel } from "./summary";

interface SitOutPointsFieldProps {
  /** The points shown: the organizer's pick, or the default of the format. */
  points: SitOutPoints;
  /** Whether the organizer picked the value (BR-071). */
  setByHand: boolean;
  /** The group phase's match format, which decides the default. */
  matchFormat: MatchFormat;
  onPick: (points: SitOutPoints) => void;
  onUseDefault: () => void;
}

/**
 * FR-039, BR-071: the points of a sit-out, 0, 1 or 2. The default follows the
 * match format until a value is picked; the field says which of the two it is
 * and offers the way back to the default.
 */
export function SitOutPointsField({
  points,
  setByHand,
  matchFormat,
  onPick,
  onUseDefault,
}: SitOutPointsFieldProps) {
  const { t } = useTranslation();
  const fallback = defaultSitOutPoints(matchFormat);
  const like = t(
    fallback === 1
      ? "tournaments.setup.format.sitOutLikeDraw"
      : "tournaments.setup.format.sitOutLikeWin",
  );
  const values = {
    format: t(`tournaments.setup.matchFormat.${matchFormat}`),
    points: sitOutLabel(t, fallback),
    like,
  };

  return (
    <div className="grid gap-2">
      <SegmentedControl
        label={t("tournaments.setup.format.sitOut")}
        hint={`${t("tournaments.setup.format.sitOutHint")} ${t(
          setByHand
            ? "tournaments.setup.format.sitOutByHand"
            : "tournaments.setup.format.sitOutDefault",
          values,
        )}`}
        value={String(points)}
        options={SIT_OUT_POINTS.map((value) => ({
          value: String(value),
          label:
            value === fallback
              ? t("tournaments.setup.sitOut.pointsDefault", { count: value })
              : sitOutLabel(t, value),
        }))}
        onValueChange={(next) => {
          const picked = SIT_OUT_POINTS.find((value) => String(value) === next);
          if (picked !== undefined) {
            onPick(picked);
          }
        }}
        onReselect={(next) => {
          // Radix does not report a click on the checked option, so pinning a
          // value that equals the default is told here (BR-071).
          const picked = SIT_OUT_POINTS.find((value) => String(value) === next);
          if (picked !== undefined) {
            onPick(picked);
          }
        }}
      />
      {setByHand && (
        <Button
          type="button"
          variant="text"
          className="justify-self-start"
          onClick={onUseDefault}
        >
          {t("tournaments.setup.format.sitOutUseDefault", { value: fallback })}
        </Button>
      )}
    </div>
  );
}
