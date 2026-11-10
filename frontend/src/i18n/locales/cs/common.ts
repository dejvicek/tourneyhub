import type { common as reference } from "../en/common";

export const common: typeof reference = {
  app: {
    name: "TourneyHub",
    title: "{{screen}} · TourneyHub",
  },
  language: {
    switchLabel: "Jazyk",
    en: { short: "EN", name: "English" },
    cs: { short: "CS", name: "Čeština" },
  },
  home: {
    title: "Vítejte v aplikaci TourneyHub",
    lead: "Turnaje a sezóny vaší skupiny přímo z telefonu.",
    myLeagues: "Přejít na moje ligy",
  },
  notFound: {
    title: "Stránka nenalezena",
    body: "Hledaná stránka neexistuje.",
    home: "Zpět na úvodní stránku",
  },
  placeholder: {
    screen: "Obrazovka návrhu {{screen}}",
    body: "Tahle obrazovka je zatím jen zástupná, dokud ji někdo nepostaví.",
  },
  routeError: {
    title: "Něco se pokazilo",
    body: "Stránku se nepodařilo zobrazit. Zkuste ji načíst znovu.",
    notFound: "Tahle stránka neexistuje, nebo byla smazána.",
    reload: "Načíst stránku znovu",
  },
  loading: "Načítání…",
  demo: {
    notice:
      "Ukázkový režim: data jsou smyšlená a po novém načtení začínají znovu.",
  },
};
