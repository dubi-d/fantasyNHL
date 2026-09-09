"""Tests for YAML config loading and calibration persistence."""
import pytest
import yaml

from fantasy_nhl.config import (
    ScheduleCalibration,
    load_config,
    save_calibration,
)


@pytest.fixture
def config_files(tmp_path):
    config = tmp_path / "config.yaml"
    config.write_text(yaml.safe_dump({"leagues": [{
        "name": "Test League", "league_id": 42, "year": 2027,
        "categories": [{"name": "G"}, {"name": "GAA", "inverted": True}],
    }]}))
    secrets = tmp_path / "secrets.yaml"
    secrets.write_text(yaml.safe_dump(
        {"Test League": {"swid": "{S}", "espn_s2": "cookie"}}))
    return config, secrets, tmp_path / "calibration.yaml"


def test_load_config_merges_secrets_and_categories(config_files):
    config, secrets, calibration = config_files
    (league,) = load_config(config, secrets, calibration)
    assert (league.name, league.league_id, league.year) == (
        "Test League", 42, 2027)
    assert (league.swid, league.espn_s2) == ("{S}", "cookie")
    assert [(c.name, c.inverted) for c in league.categories] == [
        ("G", False), ("GAA", True)]
    assert league.calibration is None  # no calibration file yet


def test_missing_secrets_file_is_explained(config_files, tmp_path):
    config, _, calibration = config_files
    with pytest.raises(FileNotFoundError, match="secrets.example.yaml"):
        load_config(config, tmp_path / "nope.yaml", calibration)


def test_missing_league_credentials_raise(config_files):
    config, secrets, calibration = config_files
    secrets.write_text(yaml.safe_dump({"Other": {"swid": "x", "espn_s2": "y"}}))
    with pytest.raises(KeyError, match="Test League"):
        load_config(config, secrets, calibration)


def test_save_calibration_round_trips_and_keeps_other_leagues(config_files):
    config, secrets, calibration = config_files
    save_calibration("Other", ScheduleCalibration("src", "2026-01-01",
                                                  {10: 2.0}), calibration)
    save_calibration("Test League", ScheduleCalibration(
        "Source 2026", "2026-08-30", {16: 1.23456, 8: 2.5}), calibration)

    (league,) = load_config(config, secrets, calibration)
    assert league.calibration.source == "Source 2026"
    assert league.calibration.calibrated == "2026-08-30"
    assert league.calibration.curve == {8: 2.5, 16: 1.2346}  # rounded, int keys
    assert set(yaml.safe_load(calibration.read_text())) == {"Other", "Test League"}
