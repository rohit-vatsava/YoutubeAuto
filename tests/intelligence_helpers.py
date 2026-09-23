import json
from pathlib import Path
from datetime import datetime, timezone
from tech_uncovered.intelligence.cli import seed_fixture

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT/'tests/fixtures/intelligence'
NOW = datetime(2026,9,20,12,tzinfo=timezone.utc)


def load(name):
    return json.loads((FIXTURES/name).read_text())


def config():
    return json.loads((ROOT/'config/intelligence.json').read_text())


def seed(db):
    seed_fixture(db,load('radar.json'))
