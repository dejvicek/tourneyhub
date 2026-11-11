// The fields of a running tournament (screens 6b–6d, FR-090–FR-094).
export const fields = {
  now: {
    title: "Fields: now playing and waiting",
    summary_one: "{{count}} field, {{playing}} playing",
    summary_other: "{{count}} fields, {{playing}} playing",
  },
  card: {
    free: "Free",
    freeHint: "Gets the next match that can be played.",
    putHere: "Put a match here",
    blocked: "Its players are on another field.",
    putOn: "Put on Field {{number}}",
    detail: "Round {{round}}, {{format}}",
    move: "Move",
  },
  waiting: {
    title: "Waiting for a field",
    rule: "Nobody plays on two fields at once. When a field frees up, it takes the first match whose players are all free.",
    none: "No match is waiting.",
    position: "Number {{position}}: ",
    put: "Put on a field",
    reasonFree:
      "Round {{round}}. Its players are free: it takes the next free field.",
    reasonBusy_one:
      "Round {{round}}. Waits for {{names}}, who is on Field {{field}}.",
    reasonBusy_other:
      "Round {{round}}. Waits for {{names}}, who are on Field {{field}}.",
    reasonBoth: "Round {{round}}. Both sides are still on a field.",
  },
  move: {
    title: "Move this match",
    putTitle: "Put this match on a field",
    nowOn: "{{match}}, now on Field {{number}}.",
    nowWaiting: "{{match}}, number {{position}} in line.",
    options: "Where it goes",
    here: "Where it is now.",
    busySwap: "Busy with {{match}}; choose it to swap the two matches.",
    busy: "Busy with {{match}}",
    blocked_one: "{{names}} is on Field {{field}}.",
    blocked_other: "{{names}} are on Field {{field}}.",
    free: "Free.",
    waitingTitle: "Back to waiting",
    waitingText:
      "Off the field. It waits for the next free field like any other match.",
    to: "Move to Field {{number}}",
    swap: "Swap with Field {{number}}",
    stay: "Keep it on Field {{number}}",
    toWaiting: "Move to waiting",
    choose: "Choose a field",
  },
  edit: {
    title: "Fields: add or remove",
    heading: "Fields",
    description:
      "Matches start only on a field. Add one when another field frees up at the venue.",
    removeField: "Remove Field {{number}}",
    remove: "Remove",
    lastField: "The last field can't be removed.",
    add: "Add a field",
    addHint:
      "It becomes Field {{number}} and takes the next match that can be played.",
    limit: "A tournament has at most {{max}} fields.",
    noticeTitle: "Removing a field with a match on it",
    noticeBody:
      "The match goes back to the front of the waiting list. The other fields keep their numbers. The last field can't be removed.",
    added: "Field {{number}} added.",
    removed: "Field {{number}} removed.",
    done: "Done",
    confirmTitle: "Remove Field {{number}}?",
    confirmBusy:
      "{{match}} goes back to the front of the waiting list. The other fields keep their numbers.",
    confirmFree: "The other fields keep their numbers.",
    cancel: "Cancel",
    confirmAction: "Remove Field {{number}}",
  },
  errors: {
    changed: "The fields changed elsewhere. They were reloaded.",
    placementChanged:
      "The fields changed in the meantime; the screen has been refreshed.",
    notInProgress:
      "The tournament is no longer in progress, for example because it was finished.",
    fieldRemoved: "That field was already removed. The fields were reloaded.",
    twoFields: "That would put a player on two fields at once.",
    lastField: "The last field can't be removed.",
    sidesUnknown: "This match can't be played yet: a side isn't known.",
    generic: "The fields could not be changed. Try again.",
  },
};
