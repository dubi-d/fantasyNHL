# Tools

What each tool shows, in the order of the menu. The terminal and the web
app show the same tables and figures; the definitions behind the numbers
are in [methodology.md](methodology.md).

- **Show weekly scores** — For each matchup week (including the ongoing one),
  prints a round-robin table: every team is matched against every other team
  using their category totals of that week, yielding W/L/T, categories won,
  and points (2 per win, 1 per tie). A `Result` column shows the team's actual
  ESPN matchup outcome that week (`NA` while undecided), and a `Luck` column
  quantifies that week's schedule luck (see [Luck](methodology.md#luck);
  empty while the matchup is
  undecided). Sorted by points, indexed by rank.
- **Generate weekly awards** — Picks a completed matchup (default: the
  latest) and prints its round-robin table plus a plain-text awards block
  ready to paste into the league chat: team and dud of the matchup (best and
  worst round-robin points, with their head-to-head scoreline), the luckiest
  win (the winner with the weakest stats) and the biggest choke (the loser
  with the strongest stats); the last two are omitted when they coincide
  with the best/worst team.
- **Show accumulated scores** — Sums the weekly round-robin results over all
  completed weeks into overall standings, sorted by round-robin strength and
  indexed by rank. The actual matchup record (W/L/T) and points (`Pts`) are
  shown next to the team name, separated from the round-robin stats
  (`rrW/rrL/rrT`) and the expected points (`xPts`, see
  [Luck](methodology.md#luck)). Useful as
  a schedule-independent measure of season-long team strength. A `Luck`
  column shows the accumulated schedule luck.
- **Show luck ranking** — Ranks teams by accumulated schedule luck over all
  completed weeks, luckiest first, alongside their actual record, actual
  points and expected points.
- **Show power rankings over time** — Round-robin points per completed
  matchup as a terminal heatmap, plus a shareable two-panel PNG saved to
  `plots/`: a "who's hot" bump chart ranking teams by their round-robin
  points over a trailing window of matchups (window prompted, default 4),
  and a "season strength" line chart of expected points per matchup
  (accumulated `xPts` divided by matchups played, so 2 = would beat
  everyone, 1 = league average).
- **Show category strength profile** — For each team, the win rate per
  category across all completed weeks' round-robin comparisons (ties count as
  half a win, so each column averages 0.5 across the league). Values near 1
  are structural strengths, values near 0 are weaknesses. An
  `Overall` column averages across categories and sorts the table; a
  `(contested)` footer row shows how up-for-grabs each category is
  league-wide (see [Contestedness](methodology.md#contestedness)).
- **Show matchup preview** — Predicted category scores for every head-to-head
  pairing of a selected matchup. Elapsed days use real data (live scores and
  games actually played), remaining days use per-game rates on the chosen
  player stats (see [Player stats](methodology.md#player-stats)) with the
  current roster filling
  all active lineup slots against the
  NHL schedule. Shows games played/playable, per-category winners, and a
  projected result.
- **Plan streaming week** — Helps plan streamer pickups for a selected
  matchup: a per-day roster grid with game markers and open active seats
  (optionally with your designated streamers dropped), a per-lineup-slot
  breakdown of the open seats, and NHL teams ranked by how many of the open
  days their schedule covers. Shows your used/allowed weekly adds. The first
  two days of the next matchup appear as informational columns. Elapsed
  days are excluded (dimmed); for finished weeks the tool offers to simulate
  the week as ongoing. Optionally ranks skater free agents by how many of
  the open days they would actually fill a lineup seat, with per-game
  category rates on the chosen player stats (see
  [Player stats](methodology.md#player-stats))
  alongside (injured players are flagged
  DTD/OUT/IR). The roster's **Games** column counts scheduled games in each
  player's **saved active ESPN lineup**, from today through the end of the
  matchup (or simulated today onward); Bench/IR and next-matchup lookahead
  don't count. An orange `○` marks a game assigned to Bench on that date, a
  red `×` an IR assignment. Players currently in your fantasy IR slot appear
  last, with red `×` on their team's game days and **Games 0**, regardless of future
  assignments; they remain excluded from all seat/streaming calculations.
  **Inj** shows reported injury status separately from IR-slot placement
  (DTD/SUS yellow, OUT/IR red, healthy blank). Dots show team games, not
  guaranteed appearances or goalie starts.

  Saved assignments are fetched using one date-specific ESPN roster request
  per actionable day. `?` marks unavailable assignments and incomplete Games
  totals; missing data is never replaced with today's lineup or a predicted
  bench. Open-seat/coverage/FA tables still model maximum usable capacity, so
  an orange bench mark can coexist with an open seat. Simulations use today's
  loaded roster/IR group with the selected dates' saved assignments, not a
  reconstructed historical roster. Roster membership and injuries are the
  loaded league snapshot (reload the league after roster/IR changes); daily
  assignments are freshly fetched when entering the planner, and reused
  when stepping back to change streamer choices.
- **Show NHL schedule outlook** — Per-NHL-team games and off-night games
  (≤16 teams playing) per fantasy matchup, for the full season, the
  remaining matchups, or the playoffs only, with *effective-games* scores
  that value games on quiet nights higher: `Reg Score` (regular season),
  `PO Score` (playoffs), their `Combined` blend and a roster-specific `Fit`
  (see [Schedule scoring](methodology.md#schedule-scoring) for the
  definitions and which column leads
  the sort). A shareable PNG saved to `plots/` shows the full teams ×
  matchups grid as `games (off-nights)` cells with the score columns
  alongside; playoff matchups are marked. The scope menu also offers
  **Calibrate scoring**, which fits the night-value curve behind the scores
  from a chosen (past) league season and stores it in `calibration.yaml`;
  until then a linear proxy is used.
- **Matchup dates** — Schedule outlook, matchup preview, and streaming planning
  use ESPN's season calendar combined with the league's matchup settings, not
  an assumption that every matchup is one calendar week. This includes extended
  matchups around breaks and multi-period playoff rounds. The calendar is read
  from the public ESPN app and cached for the session; if unavailable or for the
  wrong season, the tool reports an error rather than guessing dates.
- **Players, rosters & draft** — One fetch (all rosters including Bench and
  IR, the 200 most-owned free agents, the draft, ESPN ownership and the
  transaction counters), then a menu of views you can switch between
  freely. Every player is valued by a stat-based `Score` (see
  [Player value](methodology.md#player-value)); ESPN's roster% is shown
  alongside for context only — it
  reflects ESPN's default settings, not this league's categories.
  - *Players* — **Category leaderboard**: the whole pool, the free agents
    or one team's roster, for forwards, defensemen, all skaters or
    goalies, sorted by `Score`, `Spec`, `Elite` or any single
    category, with one column per category showing percentiles or per-game
    rates — and, with *This season only* stats, season totals — always
    colored by percentile. Also saves a
    level-vs-specialization map PNG to `plots/`. **Compare players**: pick 2–4
    skaters or 2–4 goalies by name (autocomplete) for a per-category table
    (per game · percentile; with *This season only* stats also the season
    total), their profile metrics and a
    radar PNG. See
    [Player category profiles](methodology.md#player-category-profiles).
  - *League* — **Roster origins**: per team, how many players were
    drafted, added or traded in, how many sit on IR, average roster% and
    Score, and the season's add/drop/trade counters. **Category outlook**:
    each roster's projected full-season category totals — as drafted or
    current — ranked by the round-robin points they would earn against the
    rest of the league, with balance indicators (see
    [Category outlook](methodology.md#category-outlook)).
  - *Draft* — **Draft grades vs ADP**: each pick's *value* is
    `overall pick − ADP` — positive means the player went later than the
    ESPN crowd takes him (a steal), negative a reach; players without an
    ESPN ADP count as one pick after the last one. Per-team summary
    (average and total value, best steal, biggest reach, goalies and
    defensemen drafted, round of the first goalie, own picks still on the
    roster), a teams × rounds value grid and the league-wide top-10 steals
    and reaches. ESPN archives ADP to a placeholder once a season is over,
    which the view flags. **Draft hits & busts**: every pick's `Return`
    (see [Player value](methodology.md#player-value)), the league-wide
    top-15 hits and busts (games played,
    roster%, Score, who owns the player now) and the average/total Return
    per drafting team.
  - *Transactions* — **Waiver pickups**: free-agent/waiver pickups still on
    rosters, ranked by Score, with a per-team summary (count still
    rostered, average roster%/Score, best pickup, season add counter).
    **Trade haul**: the same for players acquired by trade.
  - *One team* — **Team roster**: a chosen team's full roster, as drafted
    (in draft order: round.pick, overall, ADP, value in picks and rounds,
    ESPN rank, games, roster%, Score, Return, who owns the player now) or
    current (sorted by Score: lineup slot, how acquired, overall draft
    position if drafted by anyone, games, roster%, 7-day change, Score,
    Gap, injury). **Drop candidates & free agents**: the team's ten
    lowest-scoring players next to the ten highest-scoring free-agent
    skaters and the five highest-scoring free-agent goalies (listed
    separately, since Scores compare within a position group), each with
    roster%, 7-day change, the crowd-vs-stats `Gap` (see
    [Player value](methodology.md#player-value)) and
    injury status.

