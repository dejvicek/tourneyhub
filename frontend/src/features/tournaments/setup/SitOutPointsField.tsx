import { useTranslation } from "react-i18next";

import {
  DEFAULT_SIT_OUT_POINTS,
  SIT_OUT_POINTS,
  type SitOutPoints,
} from "@/lib/sitOutPoints";

import { SegmentedControl } from "./SegmentedControl";
import { sitOutLabel } from "./summary";

interface SitOutPointsFieldProps {
  points: SitOutPoints;
  onPick: (points: SitOutPoints) => void;
}

/**
 * FR-039, BR-075: the points for sitting out in Swiss and Monster DYP, 0, 1 or
 * 2, picked in setup. 0 is the default.
 */
export function SitOutPointsField({ points, onPick }: SitOutPointsFieldProps) {
  const { t } = useTranslation();

  return (
    <SegmentedControl
      label={t("tournaments.setup.format.sitOut")}
      hint={`${t("tournaments.setup.format.sitOutHint")} ${t(
        "tournaments.setup.format.sitOutScale",
      )}`}
      value={String(points)}
      options={SIT_OUT_POINTS.map((value) => ({
        value: String(value),
        label:
          value === DEFAULT_SIT_OUT_POINTS
            ? t("tournaments.setup.sitOut.pointsDefault", { count: value })
            : sitOutLabel(t, value),
      }))}
      onValueChange={(next) => {
        const picked = SIT_OUT_POINTS.find((value) => String(value) === next);
        if (picked !== undefined) {
          onPick(picked);
        }
      }}
    />
  );
}
