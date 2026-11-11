import type { CsMessages, Messages } from "../en";

export const players: CsMessages<Messages["players"]> = {
  list: {
    title: "Hráči",
    lead: "Všichni, koho můžete vybrat do turnaje. Jména jsou jedinečná bez ohledu na velikost písmen.",
    count_one: "{{count}} hráč",
    count_few: "{{count}} hráči",
    count_many: "{{count}} hráče",
    count_other: "{{count}} hráčů",
    empty: "Zatím žádní hráči.",
    emptyBody: "Přidejte lidi, kteří ve vaší skupině hrají.",
    loadFailed: "Hráče se nepodařilo načíst.",
  },
  add: {
    heading: "Přidat hráče",
    name: "Jméno",
    submit: "Přidat",
    adding: "Přidávání…",
    added: "{{name}} je na seznamu.",
  },
  rename: {
    action: "Přejmenovat",
    label: "Přejmenovat: {{name}}",
    name: "Nové jméno pro: {{name}}",
    save: "Uložit",
    cancel: "Zrušit",
    saved: "Přejmenováno na {{name}}.",
  },
  remove: {
    action: "Odebrat",
    label: "Odebrat: {{name}}",
    title: "Odebrat: {{name}}?",
    body: "Hráč {{name}} si ponechá dosavadní výsledky, umístění a body, ale nepůjde vybrat do nových turnajů. Později ho můžete vrátit.",
    confirm: "Odebrat",
    cancel: "Ponechat",
    removed: "Hráč {{name}} je odebraný.",
    blocked:
      "Hráče {{name}} zatím nejde odebrat. Tyto turnaje nejsou dokončené a hrají v nich: {{tournaments}}. Nejdřív je dokončete nebo smažte.",
    inTournament:
      "Hráč {{name}} hraje v nedokončeném turnaji, takže zatím nejde odebrat.",
  },
  removed: {
    heading_one: "Odebraný hráč ({{count}})",
    heading_few: "Odebraní hráči ({{count}})",
    heading_many: "Odebraní hráči ({{count}})",
    heading_other: "Odebraní hráči ({{count}})",
    restore: "Vrátit",
    restoreLabel: "Vrátit: {{name}}",
    restored: "Hráč {{name}} je zpět na seznamu.",
  },
  errors: {
    taken: "{{name}} už na seznamu je.",
    takenRemoved: "{{name}} je odebraný hráč. Vraťte ho na seznam.",
    takenUnknown: "Toto jméno právě někdo použil. Seznam se znovu načetl.",
    limit: "Liga může mít nejvýš 500 hráčů včetně odebraných.",
    generic: "Nepovedlo se. Zkontrolujte připojení a zkuste to znovu.",
  },
};
