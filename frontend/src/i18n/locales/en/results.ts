// Result entry (screens 7 and 7b, FR-050–FR-053).
export const results = {
  enter: { title: "Enter a result" },
  bestOf: {
    title: "Best-of results: BO2, BO3, BO5",
    mode: "How to enter the games",
    goals: "Goals",
    winnersOnly: "Winners only",
    scoresRequired: "This phase needs every game's goals.",
    gameList: "Games",
    game: "Game {{number}}",
    now: "Now",
    editing: "Editing game {{number}}. Tap a game above to change it.",
    games: "{{a}} to {{b}} in games",
    open: "{{a}}:{{b}} in games so far.",
    win: "{{names}} win {{score}} in games.",
    draw_one: "Draw, 1:1 in games. Each pair gets {{count}} point.",
    draw_other: "Draw, 1:1 in games. Each pair gets {{count}} points.",
    drawNotAllowed: "Draws aren't allowed here: one side needs both games.",
    notNeeded_one: "Not needed: {{names}} already won {{count}} game.",
    notNeeded_other: "Not needed: {{names}} already won {{count}} games.",
    winnerOf: "Winner of game {{number}}",
  },
  documentTitle: "Result: {{match}}",
  subtitle: {
    bo1: "{{tournament}}.",
    bo2: "Best of 2: always two games. {{tournament}}.",
    bo3: "Best of 3. {{tournament}}.",
    bo5: "Best of 5. {{tournament}}.",
  },
  subtitleOnField: {
    bo1: "Field {{field}}. {{tournament}}.",
    bo2: "Field {{field}}. Best of 2: always two games. {{tournament}}.",
    bo3: "Field {{field}}. Best of 3. {{tournament}}.",
    bo5: "Field {{field}}. Best of 5. {{tournament}}.",
  },
  seed: "Seed {{seed}}",
  goalsFor: "Goals for {{names}}",
  noScore: "–",
  save: "Save result",
  unknownSides: "This match gets a result once both sides are known.",
  beads: {
    legend: "Goals for {{names}}",
    bead_one: "{{count}} goal for {{names}}",
    bead_other: "{{count}} goals for {{names}}",
  },
  simple: {
    hint: "Tap the bead for each pair's score.",
    drawsAllowed:
      "Draws are allowed in this league: give both pairs the same score.",
    drawsNotAllowed: "Draws aren't allowed in this league.",
    empty:
      "Tap the winner's last bead, then add the other pair's goals if you like.",
    incomplete: "Add the other pair's goals too.",
    needsScores: "Add the other pair's goals: this phase needs every score.",
    winnerOnly:
      "{{names}} win. Save now, or add the other pair's goals for the score.",
    win: "{{names}} win {{score}}.",
    winTop_one: "{{names}} win {{score}} and go top on {{count}} point.",
    winTop_other: "{{names}} win {{score}} and go top on {{count}} points.",
    draw_one: "Draw, {{score}}. Each pair gets {{count}} point.",
    draw_other: "Draw, {{score}}. Each pair gets {{count}} points.",
    drawNotAllowed:
      "Draws aren't allowed in this league: one pair needs more goals.",
  },
  walkover: {
    open: "Record a walkover instead",
    hint: "A walkover counts as a normal win and loss, with no score.",
    legend: "Who wins by walkover",
    option: "{{names}} win by walkover",
    save: "Save walkover",
    cancel: "Enter a score instead",
  },
  clear: {
    open: "Clear result",
    title: "Clear this result?",
    body: "{{match}} goes back to waiting. It takes a free field at once if its players are not on another field.",
    bodyFinished:
      "{{match}} goes back to waiting and takes a free field at once. The finished tournament is back in progress.",
    cancel: "Keep it",
    confirm: "Clear result",
  },
  locked: {
    group: {
      title: "Round robin results are locked",
      body: "The knockout is drawn. To change this result, delete the knockout first.",
    },
    knockout: {
      title: "This result is locked",
      body: "A later match already has a result. To change this one, clear that result first.",
    },
    winner: {
      title: "The winner is fixed",
      body: "A later knockout round is drawn. You can correct the score while the same pair wins. To change the winner, delete the knockout rounds after this one.",
    },
  },
  errors: {
    draw: "Draws aren't allowed here.",
    scores: "Enter both sides' goals for every game.",
    mismatch:
      "In game {{game}} the goals don't fit the winner: the winner scores more, a draw the same.",
    format: "These games don't make a result in this match format.",
    locked: "Round robin results are locked once the knockout is drawn.",
    lockedKnockout:
      "A later match already has a result. Clear that result first.",
    lockedRound:
      "This round is locked because round {{round}} is drawn. Delete the newer rounds to change it.",
    lockedWinner:
      "The winner is fixed because a later knockout round is drawn. Correct the score, or delete the knockout rounds after this one to change the winner.",
    sidesChanged:
      "The pairs in this match changed; the screen has been refreshed.",
    seasonClosed:
      "This season was closed meanwhile. Its results can no longer change.",
    changed: "The match changed elsewhere. It was reloaded.",
    generic: "The result could not be saved. Check it and try again.",
  },
};
