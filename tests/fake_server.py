"""The web backend on the synthetic league, for frontend work without ESPN:

    .venv/bin/python tests/fake_server.py [scenario]

with a scenario of tests/support.py: midseason (default), finished,
opening_day, preseason, pre_draft or undrafted.
"""
import sys

import uvicorn
from pytest import MonkeyPatch

from fantasy_nhl.api import create_app
from fantasy_nhl.api.app import HOST, PORT
from support import SCENARIOS, FakeLeague, patch_everywhere


def main() -> None:
    league = SCENARIOS[sys.argv[1] if len(sys.argv) > 1 else "midseason"]()
    patches = MonkeyPatch()
    for name in FakeLeague.FETCHERS:
        patch_everywhere(patches, name, getattr(league, name))
    patch_everywhere(patches, "fetch_league_data", lambda config: league.data)
    patch_everywhere(patches, "save_calibration", lambda name, calibration: None)
    uvicorn.run(create_app(league.sources), host=HOST, port=PORT)


if __name__ == "__main__":
    main()
