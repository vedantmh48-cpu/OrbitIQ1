"""Seed demo datasets + admin account: python seed.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.storage import get_db  # noqa: E402
from app.seed_data import seed_demo_data  # noqa: E402

if __name__ == "__main__":
    db = get_db()
    count = seed_demo_data(db)
    print(f"Seeded {count} demo datasets.")
    print("Admin account: admin@satquery.ai / Admin@123")