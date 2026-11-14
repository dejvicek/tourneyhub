import { useTranslation } from "react-i18next";

/** A place row as far as the pairing needs it. */
interface PairableRow {
  entry_id: string;
  place: number;
  reason: { partner_entry_id: string | null };
}

/** One line of a places list: a player, or two partners who share a place. */
export interface PlaceGroup<R extends PairableRow> {
  place: number;
  entryIds: string[];
  /** The first row of the group; its reason and points stand for all of it. */
  first: R;
}

/**
 * Joins each row with its partner's row of the same place (BR-145), keeping
 * the order. A row without a partner row passes through on its own.
 */
export function pairPlaces<R extends PairableRow>(
  rows: readonly R[],
): PlaceGroup<R>[] {
  const taken = new Set<string>();
  const groups: PlaceGroup<R>[] = [];
  for (const row of rows) {
    if (taken.has(row.entry_id)) {
      continue;
    }
    taken.add(row.entry_id);
    const partner = rows.find(
      (other) =>
        other.place === row.place &&
        other.entry_id === row.reason.partner_entry_id &&
        !taken.has(other.entry_id),
    );
    if (partner !== undefined) {
      taken.add(partner.entry_id);
    }
    groups.push({
      place: row.place,
      entryIds:
        partner === undefined
          ? [row.entry_id]
          : [row.entry_id, partner.entry_id],
      first: row,
    });
  }
  return groups;
}

/** The name of a group: one entry's name, or the two partners as a team. */
export function useGroupName(
  entryName: (entryId: string) => string,
): (entryIds: readonly string[]) => string {
  const { t } = useTranslation();
  return (entryIds) => {
    const [first, second] = entryIds;
    if (first === undefined) {
      return "";
    }
    return second === undefined
      ? entryName(first)
      : t("finals.common.names.team", {
          first: entryName(first),
          second: entryName(second),
        });
  };
}
