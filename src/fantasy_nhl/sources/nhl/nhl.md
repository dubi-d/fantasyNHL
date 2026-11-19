# sources/nhl

Historical player stats from the NHL's own stats API
(`api.nhle.com/stats/rest`): everything its season reports hold on every
skater and goalie of a finished regular season, stored as one CSV file
per season. It is the data basis for own projections; nothing reads the
files yet.

## Boundaries

- Imports only the standard library: nothing of ESPN, of `analysis` or of
  a front end.
- Knows no league and needs no credentials. It is used by the
  `fantasy-nhl-history` command in [cli](../../cli/cli.md) only.
- The public names are re-exported by [`__init__.py`](__init__.py).

## Layout

| File | Holds |
| --- | --- |
| [history.py](history.py) | `fetch_season_stats`, `fetch_season_ends`, `save_season_stats`, the season naming (`season_id`, `season_label`, `season_path`), `COLUMNS` and `NhlStatsError` |

## Key concepts

- **Seasons.** A season is the year it ends in, like `year` in
  `config.yaml`: 2026 is 2025-26, the NHL's `seasonId` 20252026.
- **Files.** `data/nhl/season_<seasonId>.csv`, relative to the working
  directory like `config.yaml`. The folder is gitignored.
- **Rows.** One per player and season, skaters first. A player traded
  during the season has one row with his totals and all his teams in
  `teams` (`VAN,TOR`).
- **Columns.** Every field of the three reports is kept. The file starts
  with `COLUMNS`, the same in every file: the identity and the stats
  that have an ESPN label, renamed to it.

  | Columns | Of |
  | --- | --- |
  | `season`, `player_id`, `name`, `position`, `teams` | everyone; `player_id` is the NHL's id, not ESPN's; `position` is `C`, `L`, `R`, `D` or `G` |
  | `GP`, `G`, `A` | everyone (a goalie's own goals and assists) |
  | `PPP`, `SHP`, `SOG`, `HIT`, `BLK` | skaters |
  | `GS`, `W`, `L`, `OTL`, `SA`, `SV`, `GA`, `GAA`, `SV%`, `SO` | goalies |

  All other fields follow under the NHL's own names, sorted by name:
  `penaltyMinutes`, `timeOnIcePerGame` (skaters, seconds), `timeOnIce`
  (goalies, seconds), `plusMinus`, `takeaways`, ... A column is blank
  where the report of the player's group does not have the field or the
  NHL has no value for it (`ties` always, some shot-attempt and
  missed-shot fields in the older seasons).
  These columns are whatever the NHL returns, so they can differ between
  seasons; 2021-22 to 2025-26 have the same 59 columns.
- **Raw stats.** Categories a league derives (`STP` = `PPP` + `SHP`,
  `DEF` = the points of a defenseman) are not stored, so the files serve
  any league.
- **Finished seasons only.** A stored season is never downloaded again
  unless asked to, so partial totals of a running season would stay. The
  command therefore refuses a season before the day after
  `fetch_season_ends` says its regular season ends.

## The API

- Three reports per season, each in one request with `limit=-1`:
  `skater/summary`, `skater/realtime` (hits, blocks) and
  `goalie/summary`, filtered to the regular season (`gameTypeId=2`).
  Another limit is capped at 100 rows.
- The two skater reports repeat some fields (`gamesPlayed`,
  `timeOnIcePerGame`, ...); the value of `skater/summary` is kept.
- Nothing is guessed: a report with fewer rows than its `total`, a player
  listed twice, skater reports that disagree on the players or a missing
  field behind one of `COLUMNS` raise `NhlStatsError`, and no file is
  written.

## Gotchas

- The API is the undocumented backend of nhl.com. It can change without
  notice; the unofficial reference is
  [Zmalski/NHL-API-Reference](https://github.com/Zmalski/NHL-API-Reference).
- The NHL publishes no licence for this API. Its terms of service limit
  use to personal, non-commercial purposes and forbid redistributing its
  content and unauthorized automated collection. Never commit the
  downloaded files, and keep the requests few: a finished season needs
  downloading once.

## Tests

[tests/test_nhl_history.py](../../../../tests/test_nhl_history.py) runs
the download and the command on stubbed API answers; no test asks the
NHL.
