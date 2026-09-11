"""
Loads config.yaml once and exposes it as a simple object other modules import.

Why this exists: hardcoded thresholds/model names scattered across files are
a maintenance trap — changing the confidence floor from 0.6 to 0.7 shouldn't
require grepping through 5 files. Everything tunable lives in config.yaml,
this module just loads it.
"""

from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


CONFIG = load_config()

if __name__ == "__main__":
    import json

    print(json.dumps(CONFIG, indent=2))
