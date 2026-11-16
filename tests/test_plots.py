"""Smoke tests: the player profile figures render to PNG."""
import numpy as np
import pandas as pd

from fantasy_nhl import plots


def test_category_radar_figure(tmp_path):
    pcts = pd.DataFrame({"G": [90.0, 20.0, np.nan], "A": [50.0, 80.0, 10.0],
                         "HIT": [10.0, 95.0, 40.0]},
                        index=["Ann", "Bob", "Cy"])
    path = tmp_path / "radar.png"
    plots.save_figure(plots.category_radar_figure(pcts, "Radar"), path)
    assert path.stat().st_size > 0


def test_level_spec_figure(tmp_path):
    summary = pd.DataFrame({"Group": ["F", "D", "F", "F"],
                            "Level": [90.0, 70.0, 50.0, np.nan],
                            "Spec": [40.0, 15.0, 80.0, np.nan]},
                           index=[1, 2, 3, 4])
    path = tmp_path / "map.png"
    # highlights without a profile (4) and outside the pool (9) are skipped
    plots.save_figure(plots.level_spec_figure(
        summary, pd.Series({1: "Ann", 2: "Bob", 4: "Cy", 9: "Zed"}), "Map"),
        path)
    assert path.stat().st_size > 0
