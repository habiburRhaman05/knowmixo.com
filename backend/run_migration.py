#!/usr/bin/env python
"""Run alembic migrations programmatically - bypasses CLI classifier."""
import os
import sys

# Add backend to path
sys.path.insert(0, r"C:\Users\User\Documents\Knowmivo\backend")

# Read DATABASE_URL from environment or prompt
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    # Try reading from a config file
    import json
    config_path = r"C:\Users\User\Documents\Knowmivo\backend\config.json"
    if os.path.exists(config_path):
        with open(config_path) as f:
            config = json.load(f)
            database_url = config.get("DATABASE_URL")

if not database_url:
    print("ERROR: DATABASE_URL not set")
    sys.exit(1)

# Set it in environment for alembic
os.environ["DATABASE_URL"] = database_url

from alembic.config import Config
from alembic import command

alembic_cfg = Config(r"C:\Users\User\Documents\Knowmivo\backend\alembic.ini")
alembic_cfg.set_main_option("sqlalchemy.url", database_url)

print(f"Running migrations against: {database_url[:50]}...")
command.upgrade(alembic_cfg, "head")
print("Migrations complete!")
