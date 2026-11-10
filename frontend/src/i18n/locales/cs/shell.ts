import type { CsMessages, Messages } from "../en";

export const shell: CsMessages<Messages["shell"]> = {
  nav: {
    label: "Hlavní",
    tournaments: "Turnaje",
    standings: "Pořadí",
    seasonStandings: "Pořadí sezóny",
    players: "Hráči",
    league: "Liga",
    leagueSettings: "Nastavení ligy",
  },
  seasonName: "Sezóna {{number}}",
  leagueContext: "{{league}}, {{season}}",
  switchLeague: "Změnit ligu",
  copyShareLink: "Kopírovat odkaz ke sdílení",
  shareLinkCopied: "Odkaz ke sdílení je zkopírovaný",
  shareLinkFailed: "Odkaz se nepodařilo zkopírovat",
  signedInAs: "Přihlášen(a) jako {{name}}",
};
