"""Regenerates backend/openapi.yaml from the running app's routes so the
published contract can never drift from the code (docs/19 Phase 8).

Usage (from backend/): python scripts/export_openapi.py [--check]
  --check  exit 1 if the committed file is out of date (use in CI).

Needs the usual env vars to import the app (values are never used; dummy
ones are fine for generation).
"""
import json
import os
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

for key, value in {
    "DATABASE_URL": "postgresql://x:x@localhost/x", "REDIS_URL": "redis://localhost", "PINECONE_API_KEY": "x",
    "PINECONE_HOST": "x", "GROQ_API_KEY": "x", "CLOUDFLARE_ACCOUNT_ID": "x", "CLOUDFLARE_API_TOKEN": "x",
}.items():
    os.environ.setdefault(key, value)

from app.main import app  # noqa: E402

TARGET = ROOT / "openapi.yaml"


def render() -> str:
    spec = json.loads(json.dumps(app.openapi()))  # normalise to plain JSON types
    spec["info"]["description"] = "Generated from the FastAPI app by scripts/export_openapi.py. Do not edit by hand."
    return yaml.safe_dump(spec, sort_keys=True, allow_unicode=True)


if __name__ == "__main__":
    text = render()
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != text:
            print("openapi.yaml is out of date; run: python scripts/export_openapi.py")
            sys.exit(1)
        print("openapi.yaml is up to date")
    else:
        TARGET.write_text(text, encoding="utf-8")
        print(f"wrote {TARGET} ({len(text.splitlines())} lines)")
