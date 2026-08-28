"""Loading of the YAML configuration file."""
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DEFAULT_CONFIG_PATH = Path("config.yaml")
DEFAULT_SECRETS_PATH = Path("secrets.yaml")


@dataclass
class Category:
    name: str
    inverted: bool = False


@dataclass
class LeagueConfig:
    name: str
    league_id: int
    year: int
    swid: str
    espn_s2: str
    categories: list[Category] = field(default_factory=list)


def _load_secrets(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(
            f"Secrets file '{path}' not found. Copy secrets.example.yaml to "
            f"'{path}' and fill in your ESPN cookies."
        )
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_config(path: Path = DEFAULT_CONFIG_PATH,
                secrets_path: Path = DEFAULT_SECRETS_PATH) -> list[LeagueConfig]:
    """Load league configurations from a YAML file, merging in credentials
    from the gitignored secrets file (keyed by league name)."""
    with open(path) as f:
        raw = yaml.safe_load(f)
    secrets = _load_secrets(secrets_path)

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
            )
        )
    return leagues
