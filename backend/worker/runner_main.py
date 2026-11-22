"""Worker process entry point: `python -m worker.runner_main`

Separate OS process from the FastAPI app, per docs/03-TRD.md: "A separate
Python worker runs ingestion jobs." Shares the same Postgres pool code
(app/db.py) and job runner (app/jobs/*) as the API, but never serves HTTP.
"""
import logging

from app.config import settings
from app.jobs.loop import run_forever

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

if __name__ == "__main__":
    run_forever(lease_seconds=settings().job_lease_seconds)
