# fantasyNHL

My repo for playing around with stats in my fantasy hockey league.
Uses [cwendt94/espn-api](https://github.com/cwendt94/espn-api).

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
```

The `[dev]` extra adds the development dependencies (pytest and the web
backend) so the test suite runs out of the box; for just using the CLI,
`pip install -e .` is enough, for the web app without tests
`pip install -e ".[web]"`.

## Configuration

Leagues and their scoring categories live in [config.yaml](config.yaml)
(committed). ESPN credentials (SWID / espn_s2 cookies) live in `secrets.yaml`
(gitignored), keyed by league name — copy
[secrets.example.yaml](secrets.example.yaml) to `secrets.yaml` and fill in
your cookies. Add or replace leagues as entries under `leagues:` plus a matching
entry in `secrets.yaml`. The optional `default_league:` names the league to
start on: the web app opens on it and the terminal menu preselects it.
Schedule-scoring calibrations are stored in
`calibration.yaml`, written by the calibrate option of the schedule outlook
tool — don't edit it by hand.

## Usage

```bash
.venv/bin/fantasy-nhl
```

Starts an interactive session: pick a league and tools from arrow-key menus.
League data is fetched once per session and reused.

```
Select tool
├── Weekly
│   ├── Show weekly scores
│   └── Generate weekly awards
├── Season standings
│   ├── Show accumulated scores
│   ├── Show luck ranking
│   ├── Show power rankings over time
│   └── Show category strength profile
├── Roster planning
│   ├── Show matchup preview
│   ├── Plan streaming week
│   └── Show NHL schedule outlook
├── Players, rosters & draft
├── Player stats: Blended (season + projection)
└── Quit
```

**Player stats** is a setting, not a tool: it decides which player stats
every `Score`, per-game rate and prediction is built from — *Blended*
(season stats mixed with ESPN's preseason projection, the default) or *This
season only* (no projection anywhere). The menu entry shows the current
value; it applies to all tools for the rest of the session and every
affected table names it in its title. See *Player stats* below.

After a tool finishes it returns to its own first prompt, so you can re-run
it with different inputs right away. **ESC** goes back one step — the
previous prompt within a tool, or up one menu level (ESC at the top menu
quits); **Ctrl-C** quits immediately from anywhere. Stepping back doesn't
repeat fetches or tables already shown; only the steps after the changed
answer re-run.

## Web app

The same tools in the browser: a local FastAPI backend serving every view
as JSON and a React/TypeScript frontend rendering them, with the terminal's
prompts as form controls. It needs Node.js for the frontend.

```bash
cd web && npm install && npm run build && cd ..   # once, and after frontend changes
.venv/bin/fantasy-nhl-web                         # http://127.0.0.1:8000
```

Run it from the repository root (it reads `config.yaml` and `secrets.yaml`
there). The sidebar mirrors the menu above; the league, the **Player stats**
setting and *Reload from ESPN* sit on top. What was fetched from ESPN is
kept for five minutes, so changing a form does not refetch; reload after
roster moves. The server listens on `127.0.0.1` only, answers no other
host name, and never sends the ESPN cookies to the browser.

For working on the frontend, run the two parts separately:

```bash
.venv/bin/fantasy-nhl-web            # backend with your leagues, or:
.venv/bin/python tests/fake_server.py  # backend on the synthetic test league
cd web && npm run dev                # frontend with hot reload, http://127.0.0.1:5173
```

The API is described at `http://127.0.0.1:8000/api/docs`; after changing
it, `npm run types` (backend running) regenerates the frontend's types in
`web/src/schema.d.ts`. `npm test` runs the frontend's unit tests.

## Tools

- **Show weekly scores** — For each matchup week (including the ongoing one),
  prints a round-robin table: every team is matched against every other team
  using their category totals of that week, yielding W/L/T, categories won,
  and points (2 per win, 1 per tie). A `Result` column shows the team's actual
  ESPN matchup outcome that week (`NA` while undecided), and a `Luck` column
  quantifies that week's schedule luck (see below; empty while the matchup is
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
  (`rrW/rrL/rrT`) and the expected points (`xPts`, see below). Useful as
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
  league-wide (see below).
- **Show matchup preview** — Predicted category scores for every head-to-head
  pairing of a selected matchup. Elapsed days use real data (live scores and
  games actually played), remaining days use per-game rates on the chosen
  player stats (see *Player stats* below) with the current roster filling
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
  category rates on the chosen player stats (see *Player stats* below)
  alongside (injured players are flagged
  DTD/OUT/IR). The roster's **Games** column counts scheduled games in each
  player's **saved active ESPN lineup**, from today through the end of the
  matchup (or simulated today onward); Bench/IR and next-matchup lookahead
  don't count. Orange dots mark games assigned to Bench on that date, red
  dots mark IR assignments. Players currently in your fantasy IR slot appear
  last, with red team-schedule dots and **Games 0**, regardless of future
  assignments; they remain excluded from all seat/streaming calculations.
  **Inj** shows reported injury status separately from IR-slot placement
  (DTD/SUS yellow, OUT/IR red, healthy blank). Dots show team games, not
  guaranteed appearances or goalie starts.

  Saved assignments are fetched using one date-specific ESPN roster request
  per actionable day. `?` marks unavailable assignments and incomplete Games
  totals; missing data is never replaced with today's lineup or a predicted
  bench. Open-seat/coverage/FA tables still model maximum usable capacity, so
  an orange bench dot can coexist with an open seat. Simulations use today's
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
  (see *Schedule scoring* below for the definitions and which column leads
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
  freely. Every player is valued by a stat-based `Score` (see *Player
  value* below); ESPN's roster% is shown alongside for context only — it
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
    radar PNG. See *Player category profiles* below.
  - *League* — **Roster origins**: per team, how many players were
    drafted, added or traded in, how many sit on IR, average roster% and
    Score, and the season's add/drop/trade counters. **Category outlook**:
    each roster's projected full-season category totals — as drafted or
    current — ranked by the round-robin points they would earn against the
    rest of the league, with balance indicators (see *Category outlook*
    below).
  - *Draft* — **Draft grades vs ADP**: each pick's *value* is
    `overall pick − ADP` — positive means the player went later than the
    ESPN crowd takes him (a steal), negative a reach; players without an
    ESPN ADP count as one pick after the last one. Per-team summary
    (average and total value, best steal, biggest reach, goalies and
    defensemen drafted, round of the first goalie, own picks still on the
    roster), a teams × rounds value grid and the league-wide top-10 steals
    and reaches. ESPN archives ADP to a placeholder once a season is over,
    which the view flags. **Draft hits & busts**: every pick's `Return`
    (see below), the league-wide top-15 hits and busts (games played,
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
    roster%, 7-day change, the crowd-vs-stats `Gap` (see below) and
    injury status.

### Luck

The round-robin table tells you how strong a team really was; the actual
record also depends on who the schedule happened to serve up. `Luck` is the
difference between actual and expected matchup points:

```
xPts = rr points / (teams − 1)
Luck = Pts − xPts
```

Each week a team earns actual points from its real matchup (2 for a win,
1 for a tie) and round-robin points from its `teams − 1` hypothetical
matchups; dividing the latter by `teams − 1` gives `xPts`, the points an
average schedule would have produced. Positive luck means the team got easier
opponents than average (its record flatters its strength), negative means
it ran into a tough schedule. Luck sums to zero across the league each week.

### Player stats

Everything that rates a player — `Score` and percentiles, the per-game
rates of free-agent candidates, the predicted days of the matchup preview —
builds on his per-game rate per category (the ratio itself for GAA and
SV%). The **Player stats** setting in the main menu decides where that rate
comes from:

- **Blended (season + projection)**, the default: the current-season rate
  mixed with ESPN's preseason projection, weighted by how much of the
  season has elapsed (see *Stat blending* below). Early on it mostly shows
  what ESPN expected of a player; his real production takes over as the
  season goes. A player ESPN has no projection for is rated on his season
  stats alone; such players are marked `†` in player tables, and the
  matchup preview states how many rostered players are affected.
- **This season only**: the season stats alone. No projection is used and
  nothing falls back to one: a player without games this season has no rate
  (blank `Score`, 0 in predictions).

The two are never mixed in one table: season totals are shown only next to
*This season only* rates, and every affected table states the stats it is
built on in its title. The setting lasts for the session. The one exception
is the **Category outlook**: a full-season pace needs projected games, so
it always uses blended stats (and says so).

### Stat blending

Blended player stats build on per-game rates. For each player and category, the
current-season rate is blended linearly with ESPN's preseason projection,
weighted by how much of the season has elapsed:

```
rate = w · season per-game rate + (1 − w) · projected per-game rate
w    = elapsed scoring periods / season length
```

Early in the season the projection dominates (little evidence yet); as the
season progresses, the actual production takes over — at `w = 1` the
projection is ignored entirely. If one side is missing (e.g. a player with no
games yet, or no preseason projection), the other is used alone. Games played
come from `GP` for skaters and `GS` for goalies. Ratio categories (GAA, SV%)
are blended the same way but as ratios rather than per-game counts, and when
aggregated over a week they are averaged weighted by goalie games instead of
summed.

### Contestedness

The `(contested)` footer row of the category strength profile measures how
up-for-grabs a category is league-wide:

```
contested = 1 − std(win rates) / 0.5
```

Each category's win-rate column averages 0.5 by construction, so its standard
deviation says how spread out the teams are: everyone near 0.5 (std ≈ 0,
contested ≈ 1) means full parity — small roster moves can swing the category;
a wide spread (std → 0.5, contested → 0) means a few teams structurally own
it and chasing it is expensive.

### Schedule scoring

The schedule outlook ranks NHL teams by *effective games per matchup*: not
every game is worth the same to a fantasy roster. A game on a quiet night is
extra valuable — you likely have an open active seat, so a player from that
team gets you production you'd otherwise not have. A game on a busy night is
just a game: your lineup is full either way. Each game therefore counts

```
value = 1 + α · min(seats, 3) / 3        (α = 1)
```

where `seats` is the number of open lineup seats a fantasy roster has on that
night. A game on a night with 3+ open seats is worth two regular games; a
game on a night with a full lineup is worth one. Seats are capped at 3
because weekly add limits make more open seats unusable anyway. The values
are summed per NHL team over the scope's nights and divided by its number of
matchups, so scores read as "games per matchup, adjusted for streamability".

The general and team-specific flavors differ only in where `seats` comes
from; `Combined` blends the two general scores:

- **`Reg Score`/`PO Score` (general)** — how league-average rosters
  experience each night. For an NHL team playing on nights `d` of a scope
  with `M` matchups:

  ```
  Score = (1/M) · Σ_d [ 1 + min(ŵ(n_d), 3) / 3 ]
  ```

  where `n_d` is the number of NHL teams playing on night `d` and `ŵ(n)` is
  the night-value curve: the *expected* open skater seats of a roster on a
  night with `n` teams playing. The curve is calibrated on demand (scope
  menu → **Calibrate scoring**) from a real season: for every roster in the
  source league and every night, the actual open skater seats are computed
  against that season's NHL schedule, capped at 3, and averaged per
  teams-playing count `n` (interpolated between observed `n`). Uncalibrated,
  the linear proxy `ŵ(n) = 3 · (1 − n/32)` is used. `Reg Score` covers only
  regular-season weeks and `PO Score` only playoff weeks (shown side by side
  in the full-season and remaining scopes whenever playoff weeks are in
  scope; the playoffs-only scope just calls its single column `Score`, since
  it's already playoff-only). Use these for roster-independent questions:
  draft prep, comparing schedules in a vacuum, or advising trades.
- **`Fit` (team-specific)** — how *your* roster experiences each night
  (optional in the remaining and playoffs scopes, for a fantasy roster you
  pick):

  ```
  Fit = (1/M) · Σ_d [ 1 + min(s_d, 3) / 3 ]
  ```

  where `s_d` is your roster's *actual* open skater seats on night `d`,
  computed from your current roster against the NHL schedule (maximum
  lineup matching, goalie slots excluded). Two NHL teams with an identical
  `Reg Score` can have very different `Fit`: the one playing on the nights
  your lineup happens to have holes fills them; the one playing when you're
  full adds bench-warmers. Use `Fit` for pickup decisions with your real
  roster — but note it reflects today's roster, so it shifts as you make
  moves.
- **`Combined`** — a blend of `Reg Score` and `PO Score`,
  `Combined = (1 − p) · Reg Score + p · PO Score`, for drafting with an eye
  on both making the playoffs and performing once there; `p` (the playoff
  weight, default 0.4) is prompted whenever playoff weeks are in scope. In
  the remaining scope the column is called `Combined rest of season` and
  its `Reg Score` part covers the whole remaining regular season; the
  near-term `Reg Score next N` and `Reg Score rest` columns shown there
  are informational splits of it.

The full-season scope sorts by `Combined` when playoffs are in scope,
otherwise by `Reg Score`. The remaining scope prompts you to choose which of
`Fit next N`, `Combined rest of season` or `Reg Score next N` leads the sort
(skipped when only one applies). The playoffs-only scope sorts by `Fit` when
chosen, otherwise `Score`.

### Player value (Players, rosters & draft)

The review pools every rostered player, the 200 most-owned free agents and
every drafted player, and attaches these metrics to each of them:

- **`Score`** — the player's stat-based value: for each category, his
  per-game rate on the chosen stats (see *Player stats*) is ranked within the pool and
  his position group, the percentile rank is mapped to a normal quantile
  (median 0, 84th percentile +1, 98th +2), and `Score` is the mean over the
  categories, with inverted categories flipped so higher is always better.
  - *Rank-based, not z-scored:* a runaway leader in one category is
    credited for his rank, not for the size of his lead — in a head-to-head
    category league a category is won once, however large the margin.
  - *Per position group:* forwards, defensemen and goalies are ranked
    separately (skater categories for F and D, goalie categories for G), so
    defense-only categories (DEF, BLK) don't hand every defenseman a bonus
    over forwards. Scores compare strictly within a group; across groups
    they are indicative (defensemen spread wider than forwards because
    their categories move together).
  - *Minimum games:* a player needs 20 season games over a full season,
    scaled by the fraction of the season elapsed (none before the season
    starts, 5 a quarter in, 20 at the end; with *This season only* stats
    always at least one); below that his Score is blank —
    a rate over a handful of games is noise, and falling back to the
    projection would credit him for games he did not play. Rates otherwise
    ignore availability; the `GP` column and the injury flag carry that.
- **`Gap`** — the player's roster% percentile minus his Score percentile,
  both within his position group in the pool, in percentage points.
  Positive: the crowd rosters him more than his stats justify; negative: he
  is under-owned for what he produces (a pickup candidate if he is a free
  agent).
- **`Return`** (draft hits & busts) — the player's Score percentile
  (within his position group) minus the percentile of his draft slot
  (pick 1 = 100), in percentage points. A late pick who is now productive
  scores high; an early pick who has fallen off scores negative; a pick
  with too few games for a Score counts as the 0th percentile — he
  delivered nothing for the slot. Roster% is shown alongside for
  information only; it does not enter the metric.

ESPN's roster% and 7-day change are the values as of today, not as of the
transaction.

### Player category profiles (Players, rosters & draft)

`Score` collapses a player into one number; the profile keeps the
per-category picture. Each category's **percentile** is the player's rank
in his per-game rate (on the chosen *Player stats*) within his position
group of the pool — the
same ranking `Score` is built on (midpoint percentile, 100 = best,
inverted categories flipped; blank under the minimum games). The profile
separates *how good* a player is from *what shape* his production has:

- **`Level`** — his `Score` percentile within the position group (how
  good).
- **`Peak`** / **`Breadth`** — mean percentile of his best two categories /
  of the remaining ones.
- **`Spec`** — `Peak − Breadth` in percentile points (what shape): high =
  carries a couple of categories and gives little elsewhere, low = evenly
  spread. Blank when the group has only two categories (goalies in a SV/GAA
  league). Nearly independent of `Level` (correlation −0.3 for forwards,
  −0.55 for defensemen in 2025-26), unlike `Breadth`, which tracks `Score`
  almost one to one (0.96).
- **`Elite`** / **`Holes`** — number of categories at or above the 90th /
  at or below the 25th percentile.
- **`Best`** — his top two categories.
- **`Type`** — tier by `Level`: Elite (≥ 90), Solid (≥ 60), Depth; plus
  *specialist* when `Spec` ≥ 40 or *all-rounder* when `Spec` ≤ 25 (the
  2025-26 quartiles are about 27 / 35 / 45). Examples: Kucherov and
  Draisaitl are elite specialists (offense, no hits/blocks), Seider an
  elite all-rounder, McNabb a depth specialist (BLK/HIT).

The map PNG plots `Level` against `Spec` for the whole group (grey) with
the listed players highlighted. A specialist helps most on a roster that is
weak in his categories; an all-rounder fits anywhere. The profile describes
the player's shape — it is not an extra value bonus on top of `Score`.

### Category outlook (Players, rosters & draft)

Each roster's full-season pace per category, its z-score across the league,
and how that profile would turn into matchup results.

**Pace.** The whole roster counts, Bench and IR included — with daily
lineups the bench plays nearly every night, so lineup seats are not the
constraint. *As drafted* sums ESPN's season projections for the draft-day
rosters. *Current* uses each player's blended per-game rate (see *Stat
blending*; always blended, whatever the *Player stats* setting) times his
projected games, so it reflects actual production on a
full-season scale; players below the `Score` games threshold stay on
projections so a fluke week cannot swing a team. Ratio categories (GAA,
SV%) are goalie-start-weighted means; inverted categories are flipped so a
positive z-score is always good.

**Replacement fill.** Games a player is *not* projected to play — up to
82 GP for skaters, 60 GS for goalies — are filled at replacement level: the
median free agent of his position group in each category (a roster without
a goalie counts one replacement goalie). A roster spot is never empty, it is
filled from the waiver wire, so an injured or unprojected pick is worth a
replacement player rather than nothing, and a team is not penalised for a
low projected games count.

**Ranking.** Teams are ranked by `RR Pts`, the round-robin points (2 per
win, 1 per tie) they would take from one week against every other team at
these totals — the same scale as the weekly scores table. Winning one
category by a mile is still one win and conceding several is several
losses — a plain average of the z-scores hides that.
`Cats/M` is the categories won per matchup, `Spread` the standard deviation
of the team's category z-scores (0 = evenly built) and `Punts` the number of
categories at z ≤ −1. A footer row shows the league-average totals.

**A snapshot, not a forecast.** In a league with heavy waiver activity the
drafted roster has little bearing on the standings: in 2025-26 the
draft-day outlook was uncorrelated with the final round-robin points, and
even valuing the drafted players by how they actually played barely helped —
most rosters were rebuilt on the wire. ESPN's projections also regress young
players toward the mean, so a draft built on breakouts looks weak on paper.
*Draft hits & busts* and *Waiver pickups* show what actually happened.

## Tests

```bash
.venv/bin/pytest
```

`tests/test_golden.py` runs every tool through the real menu on a synthetic
league and compares the whole terminal session (output with colors, prompts,
fetch calls, figure inputs) with the transcripts in `tests/golden/`. After an
intended change to what a tool shows, regenerate them with
`UPDATE_GOLDEN=1 .venv/bin/pytest tests/test_golden.py` and review the diff.

## Repo overview

```
config.yaml                  # leagues and scoring categories (committed)
secrets.example.yaml         # template for secrets.yaml (ESPN cookies, gitignored)
calibration.yaml             # stored schedule-scoring calibrations (auto-managed)
pyproject.toml               # package metadata, dependencies, CLI entrypoint
src/fantasy_nhl/
  config.py                  # YAML loading into LeagueConfig/Category dataclasses
  sources/espn/              # ESPN API access (public names re-exported by the package)
    league.py                #   the league session: weekly scores, results, fetch caches
    calendar.py              #   NHL schedule mapped onto ESPN's fantasy calendar
    players.py               #   rosters, saved lineups, free agents, player info
    preview.py, review.py, calibration.py   # the fetches behind those tools
  analysis/                  # pure logic (all names re-exported by the package)
    models.py                #   player/draft records, position groups
    rates.py, ranking.py     #   per-game rates and their blend; rank statistics
    standings.py, seats.py, schedule.py, preview.py
    draft.py, outlook.py, values.py, review.py
  plots.py                   # matplotlib figures (power rankings, schedule grids, player profiles)
  views/                     # what each tool shows, independent of the frontend
    model.py                 #   View = ordered blocks: tables with cell tones, notes, text, figures
    common.py                #   shared formatting: player tables, abbreviations, stat-basis labels
    weekly.py, standings.py, preview.py, streaming.py, schedule.py
    review.py                #   the valued player pool behind players.py, rosters.py, draft.py
  cli/                       # the terminal frontend
    app.py                   #   interactive session: league picker, menu tree, wizard runner
    prompts.py               #   prompt primitives: Ask/Do steps, ESC = back, Ctrl-C = quit
    display.py               #   rich rendering: tables, tone -> color mapping
    tools.py                 #   the tools (prompts, fetches, rendering of views) and the TOOLS menu tree
  api/                       # the web backend (FastAPI)
    state.py                 #   one session per league: lazy load, lock, short-lived fetch cache
    serialize.py             #   View -> JSON models
    routes.py                #   one endpoint per view, prompts as query parameters
    app.py                   #   the app: local-only middleware, static frontend, entrypoint
web/                         # the web frontend (Vite, React, TypeScript)
  src/components/View.tsx    #   generic renderer of a served view (tables, notes, text, figures)
  src/pages/                 #   one page per tool: its form controls around the view
tests/                       # pytest suite; support.py = synthetic league, golden/ = transcripts
```

Imports point one way, checked by `tests/test_layering.py`: `analysis` knows
nothing of ESPN, views or the terminal; `views` build on `analysis` and import
neither `rich`, `questionary`, `matplotlib` nor the ESPN layer; `cli` and
`api` are the two frontends that fetch and render, and know nothing of each
other.

## Contributing

- Install with dev dependencies: `pip install -e ".[dev]"` (see Setup).
- **Adding a tool:** write a builder in `views/` that takes the
  `LeagueData`, anything already fetched and the user's choices, and returns
  a `View` (see `views/model.py`): tables as DataFrames with per-cell
  *tones* (`diverging`/`heat` intensities or tags like `GOOD`, `WARN`)
  instead of terminal styles, notes, verbatim text and figures. A builder
  never fetches, prompts or prints. Then write the tool in `cli/tools.py`,
  a function taking a `LeagueData`, and register it in the `TOOLS` tree (a
  nested list of `(label, tool)` or `(label, [children])` pairs — nest a
  list to add a submenu; a label can be a function of the `LeagueData` to
  show a current value). A tool without prompts is a plain function:
  `_show(data, build_x(data))`. A tool with prompts is a generator:
  `answer = yield Ask(lambda: ask(questionary.select(...)))` for each
  prompt and `result = yield Do(thunk)` for every side effect (fetch,
  render, save). The runner in `cli/app.py` memoizes `Do` results and
  replays answers when the user steps back with ESC, so keep the code
  between yields free of side effects and never call `.ask()` directly —
  `prompts.ask` is what makes ESC/Ctrl-C work. Keep computation in
  `analysis/` (pure functions, no API calls) and data fetching in
  `sources/espn/`. Anything that rates a player takes a `StatBasis` (the
  tool builds it with `_stat_basis` from the *Player stats* setting) and
  gets rates from `analysis.player_rate`. For the web app, add an endpoint
  in `api/routes.py` (a function decorated with `@view(path)` that fetches
  through the league session and returns the same `View`), a case in
  `tests/test_api.py`, and a page in `web/src/pages/`.
- **Adding a league:** append an entry under `leagues:` in `config.yaml` and
  a matching credentials entry in `secrets.yaml`.
  The category list must match what the league actually scores on ESPN;
  mark lower-is-better categories with `inverted: true`.
- Run `pytest` before committing. New analysis logic should come with tests
  (`tests/test_analysis.py`), a new tool with a scripted case in
  `tests/test_golden.py`; the wizard runner and menu are covered by
  `tests/test_cli.py` with scripted fake prompts, the ESC/Ctrl-C prompt
  behavior by `tests/test_prompts.py` (real questionary prompts driven
  through a pipe), and config/calibration persistence by
  `tests/test_config.py`. Requests to ESPN are never made in tests: the
  parsing of its payloads is covered offline by `tests/test_espn_data.py`,
  the tools run on the fake fetchers of `tests/support.py`.
