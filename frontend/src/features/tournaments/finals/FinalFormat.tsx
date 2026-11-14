import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";

import { type BracketData, finalsMutations } from "@/features/finals/api";

import { SegmentedControl } from "../setup/SegmentedControl";
import { errorText } from "./errorText";

type FinalFormat = NonNullable<BracketData["final_match_format"]>;
type FinalChoice = "same" | FinalFormat;

interface FinalFormatProps {
  leagueId: string;
  tournamentId: string;
  /** The final's own format; null lets it play the knockout's. */
  finalMatchFormat: BracketData["final_match_format"];
  /** Whether the final has a result; the control hides then (BR-096). */
  finalHasResult: boolean;
}

/**
 * The final's own format, changed while the final has no result (FR-054,
 * BR-096, BR-120): "same" lets it play the knockout's format. The choices
 * are the start's; BO1 shows only when the final already has it.
 */
export function FinalFormat({
  leagueId,
  tournamentId,
  finalMatchFormat,
  finalHasResult,
}: FinalFormatProps) {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const change = useMutation(
    finalsMutations.setFinalFormat(queryClient, leagueId, tournamentId),
  );

  const failure = change.isError && (
    <p role="alert" className="text-body-sm">
      {errorText(t, change.error)}
    </p>
  );
  // The control shows only while the final has no result (BR-096). A refused
  // change (409 `match_has_result` from a stale screen) reloads the knockout
  // with the result, so its message must outlive the control.
  if (finalHasResult) {
    return failure || null;
  }
  const shown = change.isPending
    ? change.variables.final_match_format
    : finalMatchFormat;
  const formats: readonly FinalFormat[] =
    finalMatchFormat === "bo1" ? ["bo1", "bo3", "bo5"] : ["bo3", "bo5"];

  return (
    <section className="space-y-2">
      <SegmentedControl<FinalChoice>
        label={t("finals.knockout.finalFormat")}
        hint={t("finals.knockout.finalFormatHint")}
        value={shown ?? "same"}
        options={[
          { value: "same", label: t("tournaments.setup.format.finalSame") },
          ...formats.map((format) => ({
            value: format,
            label: t(`tournaments.setup.matchFormat.${format}`),
          })),
        ]}
        onValueChange={(choice) => {
          change.mutate({
            final_match_format: choice === "same" ? null : choice,
          });
        }}
      />
      {failure}
    </section>
  );
}
