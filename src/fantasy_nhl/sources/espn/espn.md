# sources/espn

Everything that talks to ESPN: the league load, the NHL schedule mapped
onto ESPN's fantasy calendar, rosters, saved lineups, free agents, player
ownership and the draft. It builds on
[cwendt94/espn-api](https://github.com/cwendt94/espn-api) and goes to the
raw API where that wrapper does not expose what is needed.

## Boundaries

- Returns plain dataclasses and the records of
  [analysis](../../analysis/analysis.md); does no analysis itself.
- Imports nothing of `views`, `cli`, `api`, `plots`, `rich`, `questionary`
  or `matplotlib`.
- The only place that imports `espn_api`. The front ends call the
  `fetch_*` functions and never touch `LeagueData.espn_league`.
- The public names are re-exported by [`__init__.py`](__init__.py); names
  with a leading underscore are internal.

## Layout

| File | Holds |
| --- | --- |
| [league.py](league.py) | `LeagueData` (the snapshot every tool works on), `ScheduleData`, `fetch_league_data`, `fetch_week_pairings` |
| [calendar.py](calendar.py) | Scoring periods as dates, ESPN's season calendar (also of archived seasons), `fetch_schedule_data`, `fetch_week_dates` |
| [players.py](players.py) | Lineup slots and add limit, rosters, IR, saved daily lineups, free agents, the raw player-info requests |
| [preview.py](preview.py) | `PreviewData` and `fetch_preview_data`: one matchup week with its real scores and games so far |
| [review.py](review.py) | `RosterReviewData` and `fetch_roster_review`: rosters, free agents and the draft with ownership |
| [calibration.py](calibration.py) | `fetch_calibration_data`: a past season's final rosters and schedule |

## What a fetch costs, and what is cached

`LeagueData` is a snapshot taken when the league is loaded: scores,
results and the rosters on `espn_league` do not change afterwards. Only
the schedule and the matchup dates are cached on it; every other fetch
asks ESPN again each time it is called. The terminal app therefore wraps
fetches in `Do` steps and the web backend caches them per session (see
[cli.md](../../cli/cli.md) and [api.md](../../api/api.md)).

| Function | Requests | Cached on `LeagueData` |
| --- | --- | --- |
| `fetch_league_data` | league load, plus one scoreboard per matchup so far | (it creates it) |
| `fetch_schedule_data` | NHL schedule, ESPN's public calendar page (two more for an archived season) | yes |
| `fetch_week_dates` | none beyond the schedule | yes |
| `fetch_week_pairings` | one scoreboard | no |
| `fetch_preview_data` | one scoreboard, settings, one per elapsed day of the week | no |
| `fetch_rosters_and_slots` | settings | no |
| `fetch_adds_used` | teams | no |
| `fetch_ir_roster` | none (reads the snapshot) | n/a |
| `fetch_daily_lineup_slots` | one per requested day | no |
| `fetch_free_agents` | one | no |
| `fetch_roster_review` | settings, teams, one per 200 players, one for free agents | no |
| `fetch_calibration_data` | a league load of the source season, settings, NHL schedule | no |

## The fantasy calendar

- A scoring period is one US/Eastern calendar day; period ids are
  consecutive, so their dates are extrapolated from the earliest scheduled
  NHL game.
- The league's `matchup_periods` do not hold scoring periods but ESPN's
  *base period* ids. A base period is usually a week, but longer around
  the season opener and breaks, and a playoff round can span several. The
  mapping from base period to days is only in the constants of ESPN's web
  app, so `calendar.py` reads them from the public schedule page.
- That page always embeds the current season. For an older season the
  constants are in a static chunk of the app, which is located through the
  app's main bundle; only its data literal is parsed, no code is run.
- Nothing is guessed: a calendar that is missing, of the wrong season or
  overlapping raises `ValueError`.
- These public requests carry no league cookies, go to two ESPN hosts over
  HTTPS only and time out after 30 seconds.

## ESPN quirks

- The wrapper keeps neither the lineup slot counts nor the weekly add
  limit; both come from the raw `mSettings` view. A negative add limit
  means none.
- Adds used per matchup are in the raw `mTeam` view; a week without a
  transaction is absent from the counter (0 adds), a missing counter is
  unknown (`None`).
- Saved lineups of a day need one `mRoster` request for that day. A
  response for another day, or without the player, leaves the assignment
  unknown; the current roster is never substituted.
- Lineups of elapsed days need one scoreboard request per day. Games
  played are stat id `34` for skaters and `0` (starts) for goalies, and
  only splits with `statSourceId` 0 are real.
- Today is partly real: games that have started are counted, the rest of
  the day is predicted.
- `league.free_agents(position="Util")` returns all skaters and no
  goalies. The raw `kona_player_info` view returns both.
- `kona_player_info` answers HTTP 400 to a `limit` without a sort key, so
  every request sorts by ownership; player ids are sent 200 per request.
- A player's `proTeam` is a team name; the schedule is matched by name.
- A finished season reports one placeholder ADP for every player.
- The playoff champion of a finished season gets ` *` appended to its team
  name.

## Gotchas

- `calendar.py` and `calibration.py` use private parts of `espn_api`
  (`_get_all_pro_schedule`, `_raw_schedule_settings`) and the raw
  `espn_request.league_get`. Check them after upgrading the library.
- The messages of `espn_api`'s exceptions can contain the `espn_s2` and
  `SWID` cookies. Do not log or display them; the web backend reports the
  exception type only.
- Roster moves on ESPN are not seen until the league is loaded again.

## Tests

The fetchers need ESPN and are not run by the tests. The calendar parsing
is tested offline with ESPN-shaped data in
[tests/test_espn_data.py](../../../../tests/test_espn_data.py); everything
above this layer runs on the synthetic league of
[tests/support.py](../../../../tests/support.py), whose methods are named
like the fetchers they replace (see [tests.md](../../../../tests/tests.md)).
