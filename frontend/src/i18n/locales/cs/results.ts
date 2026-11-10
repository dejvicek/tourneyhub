import type { Messages } from "../en";

// TODO(cs-plurals): add the _few (2–4) and _many forms once CsMessages
// allows them; until then 2–4 falls back to _other.
export const results: Messages["results"] = {
  enter: { title: "Zadat výsledek" },
  bestOf: {
    title: "Výsledky na více her: BO2, BO3, BO5",
    mode: "Jak zadat hry",
    goals: "Góly",
    winnersOnly: "Jen vítězové",
    scoresRequired: "Tato fáze potřebuje góly každé hry.",
    gameList: "Hry",
    game: "{{number}}. hra",
    now: "Teď",
    editing: "Upravujete {{number}}. hru. Jinou hru vyberete nahoře.",
    games: "{{a}} : {{b}} na hry",
    open: "Zatím {{a}}:{{b}} na hry.",
    win: "{{names}} vyhrávají {{score}} na hry.",
    draw_one: "Remíza 1:1 na hry. Každá dvojice dostane {{count}} bod.",
    draw_other: "Remíza 1:1 na hry. Každá dvojice dostane {{count}} bodů.",
    drawNotAllowed:
      "Remízy tu nejsou povolené: jedna strana musí vyhrát obě hry.",
    notNeeded_one: "Není potřeba: {{names}} už vyhráli {{count}} hru.",
    notNeeded_other: "Není potřeba: {{names}} už vyhráli {{count}} her.",
    winnerOf: "Vítěz {{number}}. hry",
  },
  documentTitle: "Výsledek: {{match}}",
  subtitle: {
    bo1: "{{tournament}}.",
    bo2: "Na 2 hry: vždy dvě hry. {{tournament}}.",
    bo3: "Na 3 hry. {{tournament}}.",
    bo5: "Na 5 her. {{tournament}}.",
  },
  titles: {
    final: "Finále",
    thirdPlace: "Zápas o 3. místo",
    semifinal: "{{number}}. semifinále",
    quarterfinal: "{{number}}. čtvrtfinále",
    knockoutRound: "{{round}}. kolo, {{number}}. zápas",
  },
  seed: "Nasazení {{seed}}",
  goalsFor: "Góly: {{names}}",
  noScore: "–",
  save: "Uložit výsledek",
  unknownSides: "Výsledek jde zadat, až budou známé obě strany.",
  beads: {
    legend: "Góly: {{names}}",
    bead_one: "{{count}} gól: {{names}}",
    bead_other: "{{count}} gólů: {{names}}",
  },
  simple: {
    hint: "Ťukněte na kuličku se skóre každé dvojice.",
    drawsAllowed:
      "V této lize jsou remízy povolené: dejte oběma dvojicím stejné skóre.",
    drawsNotAllowed: "V této lize nejsou remízy povolené.",
    empty:
      "Ťukněte na poslední kuličku vítěze, góly druhé dvojice můžete doplnit.",
    incomplete: "Doplňte i góly druhé dvojice.",
    needsScores: "Doplňte góly druhé dvojice: tato fáze potřebuje každé skóre.",
    winnerOnly:
      "{{names}} vyhrávají. Uložte hned, nebo doplňte góly druhé dvojice.",
    win: "{{names}} vyhrávají {{score}}.",
    winTop_one:
      "{{names}} vyhrávají {{score}} a jdou do čela s {{count}} bodem.",
    winTop_other:
      "{{names}} vyhrávají {{score}} a jdou do čela s {{count}} body.",
    draw_one: "Remíza {{score}}. Každá dvojice dostane {{count}} bod.",
    draw_other: "Remíza {{score}}. Každá dvojice dostane {{count}} bodů.",
    drawNotAllowed:
      "V této lize nejsou remízy povolené: jedna dvojice potřebuje víc gólů.",
  },
  walkover: {
    open: "Zapsat raději kontumaci",
    hint: "Kontumace se počítá jako běžná výhra a prohra, bez skóre.",
    legend: "Kdo vyhrává kontumačně",
    option: "{{names}} vyhrávají kontumačně",
    save: "Uložit kontumaci",
    cancel: "Zadat raději skóre",
  },
  clear: {
    open: "Smazat výsledek",
    title: "Smazat tento výsledek?",
    body: "{{match}} se vrátí mezi čekající. Na hřiště půjde, až se nějaké uvolní.",
    bodyFinished:
      "{{match}} se vrátí mezi čekající a ukončený turnaj se znovu otevře.",
    cancel: "Ponechat",
    confirm: "Smazat výsledek",
  },
  locked: {
    title: "Výsledky skupiny jsou zamčené",
    body: "Vyřazovací fáze je vylosovaná. Chcete-li výsledek změnit, nejdřív ji smažte.",
  },
  errors: {
    draw: "Remízy tu nejsou povolené.",
    scores: "Zadejte góly obou stran v každé hře.",
    locked: "Po vylosování vyřazovací fáze jsou výsledky skupiny zamčené.",
    changed: "Zápas se mezitím změnil. Byl znovu načten.",
    generic:
      "Výsledek se nepodařilo uložit. Zkontrolujte ho a zkuste to znovu.",
  },
};
