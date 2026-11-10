import type { CsMessages, Messages } from "../en";

export const fields: CsMessages<Messages["fields"]> = {
  now: {
    title: "Hřiště: hraje se a čeká",
    summary_one: "{{count}} hřiště, hraje se na {{playing}}",
    summary_other: "{{count}} hřišť, hraje se na {{playing}}",
    summary_few: "{{count}} hřiště, hraje se na {{playing}}",
    summary_many: "{{count}} hřišť, hraje se na {{playing}}",
  },
  card: {
    free: "Volné",
    freeHint: "Dostane další zápas, který jde hrát.",
    putHere: "Dát sem zápas",
    blocked: "Jeho hráči jsou na jiném hřišti.",
    putOn: "Dát na hřiště {{number}}",
    detail: "{{round}}. kolo, {{format}}",
    move: "Přesunout",
  },
  waiting: {
    title: "Čeká na hřiště",
    rule: "Nikdo nehraje na dvou hřištích najednou. Uvolněné hřiště dostane první zápas, jehož hráči jsou všichni volní.",
    none: "Žádný zápas nečeká.",
    position: "{{position}}. v pořadí: ",
    put: "Dát na hřiště",
    reasonFree:
      "{{round}}. kolo. Hráči jsou volní: dostane další volné hřiště.",
    reasonBusy_one:
      "{{round}}. kolo. Čeká na {{names}}, který hraje na hřišti {{field}}.",
    reasonBusy_other:
      "{{round}}. kolo. Čeká na {{names}}, kteří hrají na hřišti {{field}}.",
    reasonBusy_few:
      "{{round}}. kolo. Čeká na {{names}}, kteří hrají na hřišti {{field}}.",
    reasonBusy_many:
      "{{round}}. kolo. Čeká na {{names}}, kteří hrají na hřišti {{field}}.",
    reasonBoth: "{{round}}. kolo. Obě strany ještě hrají na hřišti.",
  },
  move: {
    title: "Přesunout zápas",
    putTitle: "Dát zápas na hřiště",
    nowOn: "{{match}}, teď na hřišti {{number}}.",
    nowWaiting: "{{match}}, {{position}}. v pořadí.",
    options: "Kam zápas půjde",
    here: "Tady se hraje teď.",
    busySwap: "Hraje se tu {{match}}. Vyberte ho a zápasy se prohodí.",
    busy: "Hraje se tu {{match}}.",
    blocked_one: "{{names}} hraje na hřišti {{field}}.",
    blocked_other: "{{names}} hrají na hřišti {{field}}.",
    blocked_few: "{{names}} hrají na hřišti {{field}}.",
    blocked_many: "{{names}} hrají na hřišti {{field}}.",
    free: "Volné.",
    waitingTitle: "Zpět mezi čekající",
    waitingText:
      "Pryč z hřiště. Počká na další volné hřiště jako každý jiný zápas.",
    to: "Přesunout na hřiště {{number}}",
    swap: "Prohodit s hřištěm {{number}}",
    stay: "Nechat na hřišti {{number}}",
    toWaiting: "Vrátit mezi čekající",
    choose: "Vyberte hřiště",
  },
  edit: {
    title: "Hřiště: přidat nebo odebrat",
    heading: "Hřiště",
    description:
      "Zápasy začínají jen na hřišti. Přidejte ho, když se v herně uvolní další stůl.",
    removeField: "Odebrat hřiště {{number}}",
    remove: "Odebrat",
    lastField: "Poslední hřiště nejde odebrat.",
    add: "Přidat hřiště",
    addHint: "Bude to hřiště {{number}} a dostane další zápas, který jde hrát.",
    noticeTitle: "Odebrání hřiště, na kterém se hraje",
    noticeBody:
      "Zápas se vrátí na začátek čekajících. Ostatní hřiště si nechají svá čísla. Poslední hřiště nejde odebrat.",
    added: "Hřiště {{number}} přidáno.",
    removed: "Hřiště {{number}} odebráno.",
    done: "Hotovo",
    confirmTitle: "Odebrat hřiště {{number}}?",
    confirmBusy:
      "{{match}} se vrátí na začátek čekajících. Ostatní hřiště si nechají svá čísla.",
    confirmFree: "Ostatní hřiště si nechají svá čísla.",
    cancel: "Zrušit",
    confirmAction: "Odebrat hřiště {{number}}",
  },
  errors: {
    changed: "Hřiště se mezitím změnila. Byla znovu načtena.",
    twoFields: "Tím by hráč hrál na dvou hřištích najednou.",
    lastField: "Poslední hřiště nejde odebrat.",
    generic: "Hřiště se nepodařilo změnit. Zkuste to znovu.",
  },
};
