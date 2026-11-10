// Bez typu Messages["standings"]: čeština má plurální tvary navíc (viz finals.ts).
export const standings = {
  season: {
    title: "Pořadí sezóny",
    lead_one: "{{season}}, po {{count}} dohraném turnaji.",
    lead_few: "{{season}}, po {{count}} dohraných turnajích.",
    lead_many: "{{season}}, po {{count}} dohraného turnaje.",
    lead_other: "{{season}}, po {{count}} dohraných turnajích.",
    pick: "Sezóna",
    emptyTitle: "Zatím žádný dohraný turnaj",
    emptyBody:
      "Hráči se tu objeví, jakmile se dohraje první turnaj sezóny a rozdá body.",
    columns: {
      place: "Místo",
      player: "Hráč",
      played: "Odehráno",
      wins: "Výhry",
      points: "Body",
    },
    footnote:
      "Body za místa, 1. až {{last}}: {{points}}. Kdo sdílí místo, dělí se o body a zaokrouhluje se dolů. Hráče se stejným počtem bodů řadí počet vítězství v turnajích.",
    counted: "Započtené turnaje",
  },
};
