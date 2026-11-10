import type { TFunction } from "i18next";

import type { WaitingMatchRead } from "@/demo/contract";
import type { PlayModel } from "@/features/tournaments/play/model";
import { firstName } from "@/features/tournaments/play/model";

/**
 * Why a match waits (screen 6b, BR-131): "Waits for Jirka and Míša, who
 * are on Field 1", "Both pairs are still on a field", or nobody is busy and
 * it takes the next free field.
 */
export function waitingReason(
  t: TFunction,
  language: string | undefined,
  model: PlayModel,
  waiting: WaitingMatchRead,
): string {
  const list = new Intl.ListFormat(language, { type: "conjunction" });
  const info = model.matches.get(waiting.match_id);
  const busy = waiting.busy;
  const round = info?.round.round_no ?? 0;
  const [only] = busy;
  if (only === undefined || !info) {
    return t("fields.waiting.reasonFree", { round });
  }
  const sidesBusy = info.match.sides.filter((side) =>
    side.player_ids.some((id) => busy.some((b) => b.player_ids.includes(id))),
  ).length;
  if (busy.length === 1 && sidesBusy < 2) {
    const field = model.fields.find((f) => f.id === only.field_id);
    return t("fields.waiting.reasonBusy", {
      round,
      count: only.player_ids.length,
      names: list.format(
        only.player_ids.map((id) => firstName(model.players.get(id) ?? "?")),
      ),
      field: field?.number ?? 0,
    });
  }
  return t("fields.waiting.reasonBoth", { round });
}
