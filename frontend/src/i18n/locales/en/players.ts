// A league's player list (FR-012, BR-001, BR-002).
export const players = {
  list: {
    title: "Players",
    lead: "Everyone you can pick for a tournament. Names are unique, whatever the letter case.",
    count_one: "{{count}} player",
    count_other: "{{count}} players",
    empty: "No players yet.",
    emptyBody: "Add the people who play in your group.",
    loadFailed: "The players could not be loaded.",
  },
  add: {
    heading: "Add a player",
    name: "Name",
    submit: "Add",
    adding: "Adding…",
    added: "{{name}} is on the list.",
  },
  rename: {
    action: "Rename",
    label: "Rename {{name}}",
    name: "New name for {{name}}",
    save: "Save",
    cancel: "Cancel",
    saved: "Renamed to {{name}}.",
  },
  remove: {
    action: "Remove",
    label: "Remove {{name}}",
    title: "Remove {{name}}?",
    body: "{{name}} keeps their past results, places and points, but cannot be picked for new tournaments. You can restore them later.",
    confirm: "Remove",
    cancel: "Keep",
    removed: "{{name}} is removed.",
    inTournament:
      "{{name}} plays in a tournament that is not finished, so they cannot be removed yet.",
  },
  removed: {
    heading_one: "Removed player ({{count}})",
    heading_other: "Removed players ({{count}})",
    restore: "Restore",
    restoreLabel: "Restore {{name}}",
    restored: "{{name}} is back on the list.",
  },
  errors: {
    taken: "{{name}} is already on the list.",
    takenRemoved: "{{name}} is a removed player. Restore them instead.",
    takenUnknown: "This name was just taken. The list is reloaded.",
    limit: "A league holds at most 500 players, removed ones included.",
    generic: "That did not work. Check the connection and try again.",
  },
};
