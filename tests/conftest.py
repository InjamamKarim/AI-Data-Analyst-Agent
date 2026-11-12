import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.db.seed import seed_database


@pytest.fixture(scope="session", autouse=True)
def seeded_database():
    seed_database(reset=True)
    yield
