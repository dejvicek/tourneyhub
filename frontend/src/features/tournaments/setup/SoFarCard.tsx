import { useTranslation } from "react-i18next";

import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

import type { FormatForm } from "./format";
import {
  formatLabel,
  groupPhaseLabel,
  sitOutLabel,
  typeLabel,
} from "./summary";
import { SummaryRow } from "./SummaryRow";

interface SoFarCardProps {
  format: FormatForm;
  /** The picked players, once step 2 has them. */
  players?: number;
}

/** The desktop layout's "So far" summary beside the form (Figma: screen 2). */
export function SoFarCard({ format, players }: SoFarCardProps) {
  const { t } = useTranslation();
  const noGroup = format.group_phase === "none";

  return (
    <Card className="sticky top-6">
      <CardHeader>
        <CardTitle>
          <h2>{t("tournaments.setup.soFar.title")}</h2>
        </CardTitle>
      </CardHeader>
      <CardContent>
        <dl>
          <SummaryRow label={t("tournaments.setup.summary.type")}>
            {typeLabel(t, format.type)}
          </SummaryRow>
          <SummaryRow label={t("tournaments.setup.summary.groupPhase")}>
            {groupPhaseLabel(t, format)}
          </SummaryRow>
          <SummaryRow label={t("tournaments.setup.soFar.matches")}>
            {formatLabel(
              t,
              noGroup
                ? format.knockout_match_format
                : format.group_match_format,
            )}
          </SummaryRow>
          <SummaryRow label={t("tournaments.setup.summary.fields")}>
            {format.field_count}
          </SummaryRow>
          {!noGroup && (
            <SummaryRow label={t("tournaments.setup.summary.sitOut")}>
              {sitOutLabel(t, format.sit_out_points === 1)}
            </SummaryRow>
          )}
          <SummaryRow label={t("tournaments.setup.soFar.players")}>
            {players ?? t("tournaments.setup.soFar.none")}
          </SummaryRow>
        </dl>
      </CardContent>
    </Card>
  );
}
