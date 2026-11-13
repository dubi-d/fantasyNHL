# Methodology

The definitions behind the numbers the tools show (see
[tools.md](tools.md) for the tools themselves).

## Luck

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

## Player stats

Everything that rates a player — `Score` and percentiles, the per-game
rates of free-agent candidates, the predicted days of the matchup preview —
builds on his per-game rate per category (the ratio itself for GAA and
SV%). The **Player stats** setting in the main menu decides where that rate
comes from:

- **Blended (season + projection)**, the default: the current-season rate
  mixed with ESPN's preseason projection, weighted by how much of the
  season has elapsed (see [Stat blending](#stat-blending)). Early on it
  mostly shows
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

## Stat blending

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

## Contestedness

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

## Schedule scoring

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

## Player value

The review pools every rostered player, the 200 most-owned free agents and
every drafted player, and attaches these metrics to each of them:

- **`Score`** — the player's stat-based value: for each category, his
  per-game rate on the chosen stats (see [Player stats](#player-stats)) is
  ranked within the pool and
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

## Player category profiles

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

## Category outlook

Each roster's full-season pace per category, its z-score across the league,
and how that profile would turn into matchup results.

**Pace.** The whole roster counts, Bench and IR included — with daily
lineups the bench plays nearly every night, so lineup seats are not the
constraint. *As drafted* sums ESPN's season projections for the draft-day
rosters. *Current* uses each player's blended per-game rate (see
[Stat blending](#stat-blending); always blended, whatever the *Player stats*
setting) times his
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

