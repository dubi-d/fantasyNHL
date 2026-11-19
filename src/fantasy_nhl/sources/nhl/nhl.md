# sources/nhl

Historical player stats from the NHL's own stats API
(`api.nhle.com/stats/rest`): everything its season reports hold on every
skater and goalie of a regular season, stored as one CSV file per
season, and the reading of those files. A finished season is stored
once; the season being played has a file of its own that is downloaded
again. They are the data basis for own projections; so far the web app's
*Player history* shows them.

## Boundaries

- Imports the standard library and `pandas`: nothing of ESPN, of
  `analysis` or of a front end.
- Knows no league and needs no credentials. The
  `fantasy-nhl-history` command in [cli](../../cli/cli.md) downloads
  finished seasons; the web backend ([api](../../api/api.md)) reads the
  files and downloads the current season.
- Only the downloads ask the NHL; reading works offline.
- The public names are re-exported by [`__init__.py`](__init__.py).

## Layout

| File | Holds |
| --- | --- |
| [history.py](history.py) | The download (`fetch_season_stats`, `fetch_season_ends`, `save_season_stats`), the reading (`stored_seasons`, `read_history`), the current season (`fetch_current_season`, `refresh_current_season`, `current_file`, `read_current_season`, `CurrentSeason`), the naming (`season_id`, `season_label`, `season_path`, `current_path`), `COLUMNS` and `NhlStatsError` |

## Key concepts

- **Seasons.** A season is the year it ends in, like `year` in
  `config.yaml`: 2026 is 2025-26, the NHL's `seasonId` 20252026.
- **Files.** `data/nhl/season_<seasonId>.csv` for a finished season and
  `data/nhl/current_<seasonId>.csv` for the one being played, relative
  to the working directory like `config.yaml`. The folder is gitignored.
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
- **Finished seasons only** in a `season_*.csv`. A stored season is
  never downloaded again unless asked to, so partial totals of a running
  season would stay. The command therefore refuses a season before the
  day after `fetch_season_ends` says its regular season ends.
- **The current season** is the newest one that has started
  (`fetch_current_season`); it stays the current one after its last
  game, until the next season starts. `refresh_current_season` downloads
  it into its `current_*.csv`, in the format of a finished season,
  replacing the earlier download. When it was downloaded is the file's
  modification time; who refreshes it and when is the caller's rule (the
  web backend: once a day). The file is no stored season: `stored_seasons`,
  `read_history` and the command do not see it, so its partial totals
  never count as a season and never keep the finished one from being
  downloaded. `current_file` is the file of the newest such season, and
  none once that season is stored as finished; `save_season_stats`
  removes the file it supersedes. `read_current_season` gives it as a
  `CurrentSeason`: the table, the season and the time of the download.
- **Reading.** `read_history` gives every stored season as one table, a
  row per player and season with the columns of all files; a blank cell
  is missing, and only a blank cell (a name may be `NA`). No stored
  season is an empty table with `COLUMNS`. A `season_*.csv` or
  `current_*.csv` that does not start with `COLUMNS` raises
  `NhlStatsError` instead of being skipped.

## The API

- Three reports per season, each in one request with `limit=-1`:
  `skater/summary`, `skater/realtime` (hits, blocks) and
  `goalie/summary`, filtered to the regular season (`gameTypeId=2`).
  Another limit is capped at 100 rows.
- The `season` list gives every season's dates: `regularSeasonEndDate`
  for the command, `startDate` for the current season.
- A request waits 30 seconds for the NHL, those of
  `refresh_current_season` 10: a page is waiting for them.
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
  downloading once, the current one not more than its games change it.
- A `current_*.csv` of a season that was never stored as finished stays
  in the folder when the next season starts. It is ignored from then on;
  store that season with the command.

## Tests

[tests/test_nhl_history.py](../../../../tests/test_nhl_history.py) runs
the downloads and the command on stubbed API answers and the reading on
files it writes; no test asks the NHL. The synthetic history and current
season the other layers are tested on are in
[tests/support.py](../../../../tests/support.py).
