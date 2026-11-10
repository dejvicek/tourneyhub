import { useTranslation } from "react-i18next";

import type { PlaceData as PlaceDetail } from "@/features/finals/api";

import { usePlaceLabel } from "./usePlaceLabel";

interface PlacesSoFarProps {
  rows: readonly PlaceDetail[];
  entryName: (entryId: string) => string;
}

/** The places already decided (screen 9): "3rd, shared: A and B, C and D". */
export function PlacesSoFar({ rows, entryName }: PlacesSoFarProps) {
  const { t, i18n } = useTranslation();
  const placeLabel = usePlaceLabel();
  const list = new Intl.ListFormat(i18n.resolvedLanguage, {
    style: "short",
    type: "unit",
  });
  const places = [...new Set(rows.map((row) => row.place))];
  return (
    <section aria-labelledby="places-so-far" className="space-y-2">
      <h2 id="places-so-far" className="font-display text-display-section">
        {t("finals.knockout.placesSoFar")}
      </h2>
      {places.length === 0 ? (
        <p className="text-body-sm text-muted-foreground">
          {t("finals.knockout.placesNone")}
        </p>
      ) : (
        <ul className="space-y-1 text-body-md">
          {places.map((place) => {
            const names = rows
              .filter((row) => row.place === place)
              .map((row) => entryName(row.entry_id));
            return (
              <li key={place}>
                {t(
                  names.length > 1
                    ? "finals.knockout.placesLineShared"
                    : "finals.knockout.placesLine",
                  { place: placeLabel(place), names: list.format(names) },
                )}
              </li>
            );
          })}
        </ul>
      )}
      {!places.includes(1) && (
        <p className="text-caption text-muted-foreground">
          {t("finals.knockout.placesFinal")}
        </p>
      )}
    </section>
  );
}
