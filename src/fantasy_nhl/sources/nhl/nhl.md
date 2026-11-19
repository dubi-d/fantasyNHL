# sources/nhl

Player stats from the NHL's own stats API (`api.nhle.com/stats/rest`):
everything its season reports hold on every skater and goalie of a
regular season, stored as one CSV file per season, and the reading of
those files. They are the data basis for own projections; so far the
web app's *Player history* shows them.

## Boundaries

- Imports the standard library and `pandas`: nothing of ESPN, of
  `analysis` or of a front end.
- Knows no league and needs no credentials.
- Only the downloads ask the NHL; reading works offline. The
  `fantasy-nhl-history` command in [cli](../../cli/cli.md) downloads
  the seasons it is given; the web backend ([api](../../api/api.md))
  reads the files and keeps the current season up to date.
- The public names are re-exported by [`__init__.py`](__init__.py).

## Layout

| File | Holds |
| --- | --- |
| [history.py](history.py) | The download (`fetch_season_stats`, `fetch_season_dates`, `final_day`, `save_season_stats`), the reading (`stored_seasons`, `read_history`), the current season (`refresh_current_season`, `current_file`, `read_current_season`, `CurrentSeason`), the naming (`season_id`, `season_label`, `season_path`, `current_path`), `COLUMNS` and `NhlStatsError` |

## Key concepts

- **Seasons.** A season is the year it ends in, like `year` in
  `config.yaml`: 2026 is 2025-26, the NHL's `seasonId` 20252026.
- **Files.** `data/nhl/season_<seasonId>.csv` holds a finished season,
  `data/nhl/current_<seasonId>.csv` the one being played, in the same
  format. The folder is relative to the working directory like
  `config.yaml`, and gitignored.
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
- **Finished seasons.** A `season_*.csv` is downloaded once and not
  again unless asked to, so it must never hold partial totals. A season
  is finished from its `final_day`: two days after its regular season
  ends, because the last games end on the following day east of North
  America. The command refuses a season before that day.
- **The current season** is the newest one that has started; it stays
  the current one after its last game, until the next season starts.
  `refresh_current_season` downloads it into its `current_*.csv`,
  replacing the earlier download; the file's modification time says
  when that was. `stored_seasons`, `read_history` and the command do not
  see this file, so partial totals never pass for a season.
- **From current to finished.** From its `final_day` on,
  `refresh_current_season` stores the current season as a `season_*.csv`
  instead, and `save_season_stats` removes its `current_*.csv`. The
  same happens to an older season that still has a `current_*.csv`.
  `current_file` is then nothing until the next season starts.
- **Reading.** `read_history` gives every finished season as one table,
  a row per player and season with the columns of all files;
  `read_current_season` gives a current file as a `CurrentSeason` (the
  table, the season, when it was downloaded). Only a blank cell is
  missing: a name may be `NA`. With no finished season stored the table
  is empty and has `COLUMNS`. A file that does not start with `COLUMNS`
  raises `NhlStatsError` instead of being skipped.

## The API

- Three reports per season, each in one request with `limit=-1`:
  `skater/summary`, `skater/realtime` (hits, blocks) and
  `goalie/summary`, filtered to the regular season (`gameTypeId=2`).
  Another limit is capped at 100 rows.
- The two skater reports repeat some fields (`gamesPlayed`,
  `timeOnIcePerGame`, ...); the value of `skater/summary` is kept.
- The `season` list gives every season's first day and the last day of
  its regular season (`fetch_season_dates`).
- Nothing is guessed: a report with fewer rows than its `total`, a player
  listed twice, skater reports that disagree on the players or a missing
  field behind one of `COLUMNS` raise `NhlStatsError`, and no file is
  written.
- A request waits 30 seconds for the NHL, those of
  `refresh_current_season` 10: a page is waiting for them.

## Gotchas

- The API is the undocumented backend of nhl.com. It can change without
  notice; the unofficial reference is
  [Zmalski/NHL-API-Reference](https://github.com/Zmalski/NHL-API-Reference).
- The NHL publishes no licence for this API. Its terms of service limit
  use to personal, non-commercial purposes and forbid redistributing its
  content and unauthorized automated collection. Never commit the
  downloaded files, and keep the requests few: a finished season is
  downloaded once, the current one once a day unless the user asks.

## Tests

[tests/test_nhl_history.py](../../../../tests/test_nhl_history.py) runs
the downloads and the command on stubbed API answers and the reading on
files it writes; no test asks the NHL. The synthetic history and current
season the other layers are tested on are in
[tests/support.py](../../../../tests/support.py).
