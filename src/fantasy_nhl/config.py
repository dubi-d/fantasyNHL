"""Loading of the YAML configuration file."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_SECRETS_PATH = Path("secrets.yaml")
# auto-managed by the calibration tool; config.yaml stays hand-edited
DEFAULT_CALIBRATION_PATH = Path("calibration.yaml")


@dataclass
class Category:
    name: str
    inverted: bool = False


@dataclass
class ScheduleCalibration:
    """Night-value curve for schedule scoring, calibrated from a past season."""
    source: str  # league entry the curve was calibrated on
    calibrated: str  # ISO date of the calibration run
    curve: dict[int, float]  # NHL teams playing -> mean capped open seats


@dataclass
class LeagueConfig:
    name: str
    league_id: int
    year: int
    swid: str
    espn_s2: str
    categories: list[Category] = field(default_factory=list)
    calibration: ScheduleCalibration | None = None


def _load_secrets(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Secrets file '{path}' not found. Copy secrets.example.yaml to "
            f"'{path}' and fill in your ESPN cookies."
        )
    with open(path) as f:
        return yaml.safe_load(f) or {}


def _load_calibrations(path: Path) -> dict[str, ScheduleCalibration]:
    if not path.exists():
        return {}
    with open(path) as f:
        raw = yaml.safe_load(f) or {}
    return {name: ScheduleCalibration(
                source=entry["source"],
                calibrated=str(entry["calibrated"]),
                curve={int(n): float(v) for n, v in entry["curve"].items()})
            for name, entry in raw.items()}


def save_calibration(league_name: str, calibration: ScheduleCalibration,
                     path: Path = DEFAULT_CALIBRATION_PATH) -> None:
    """Store a league's night-value curve, keeping other leagues' entries."""
    raw = {}
    if path.exists():
        with open(path) as f:
            raw = yaml.safe_load(f) or {}
    raw[league_name] = {
        "source": calibration.source,
        "calibrated": calibration.calibrated,
        "curve": {int(n): round(float(v), 4)
                  for n, v in sorted(calibration.curve.items())},
    }
    with open(path, "w") as f:
        yaml.safe_dump(raw, f, sort_keys=True)


def load_config(path: Path = DEFAULT_CONFIG_PATH,
                secrets_path: Path = DEFAULT_SECRETS_PATH,
                calibration_path: Path = DEFAULT_CALIBRATION_PATH,
                ) -> list[LeagueConfig]:
    """Load league configurations from a YAML file, merging in credentials
    from the gitignored secrets file (keyed by league name) and any stored
    schedule-scoring calibrations."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    secrets = _load_secrets(secrets_path)
    calibrations = _load_calibrations(calibration_path)

    leagues = []
    for entry in raw["leagues"]:
        name = entry["name"]
        credentials = secrets.get(name)
        if not credentials:
            raise KeyError(
                f"No credentials for league '{name}' in '{secrets_path}'. "
                f"Add an entry with 'swid' and 'espn_s2'."
            )
        categories = [
            Category(name=cat["name"], inverted=cat.get("inverted", False))
            for cat in entry["categories"]
        ]
        leagues.append(
            LeagueConfig(
                name=name,
                league_id=entry["league_id"],
                year=entry["year"],
                swid=credentials["swid"],
                espn_s2=credentials["espn_s2"],
                categories=categories,
                calibration=calibrations.get(name),
            )
        )
    return leagues
