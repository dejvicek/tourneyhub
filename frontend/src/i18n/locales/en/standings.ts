export const standings = {
  season: {
    title: "Season standings",
    lead_one: "{{season}}, after {{count}} finished tournament.",
    lead_other: "{{season}}, after {{count}} finished tournaments.",
    pick: "Season",
    emptyTitle: "No finished tournaments yet",
    emptyBody:
      "Players appear here once a tournament of the season has finished and given out its points.",
    columns: {
      place: "Place",
      player: "Player",
      played: "Played",
      wins: "Wins",
      points: "Pts",
    },
    footnote:
      "Points per place, 1st to {{last}}: {{points}}. Entries sharing a place split the points and round down. Players level on points are ranked by tournament wins.",
    counted: "Tournaments counted",
  },
};
