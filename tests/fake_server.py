"""The web backend on the synthetic league, for frontend work without ESPN:

    .venv/bin/python tests/fake_server.py [--finished]
"""
import sys

import uvicorn
from pytest import MonkeyPatch

from fantasy_nhl.api import create_app
from fantasy_nhl.api.app import HOST, PORT
from support import FakeLeague, patch_everywhere


def main() -> None:
    league = FakeLeague()
    if "--finished" in sys.argv:  # the season is over
        league = FakeLeague(current_week=8, today=60, season_over=True,
                            constant_adp=True, blend_weight=1.0,
                            add_limit=None)
    patches = MonkeyPatch()
    for name in FakeLeague.FETCHERS:
        patch_everywhere(patches, name, getattr(league, name))
    patch_everywhere(patches, "fetch_league_data", lambda config: league.data)
    patch_everywhere(patches, "save_calibration", lambda name, calibration: None)
    uvicorn.run(create_app(league.sources), host=HOST, port=PORT)


if __name__ == "__main__":
    main()
