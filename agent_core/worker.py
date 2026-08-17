"""Combined local worker for persisted jobs and scheduled AI tasks."""

from __future__ import annotations

import time
from datetime import UTC, datetime

from .background import BackgroundWorker
from .scheduler import build_worker
from .storage import BackgroundJobRepository


def main() -> None:
    schedule_worker = build_worker()
    jobs = BackgroundJobRepository(schedule_worker.services.chats.database)
    background_worker = BackgroundWorker(
        jobs,
        schedule_worker.services.knowledge,
        schedule_worker.services.memory,
        schedule_worker.services.chats,
    )
    while True:
        now = datetime.now(UTC)
        jobs.heartbeat(now)
        jobs.recover_stale(now)
        background_worker.run_once(now)
        schedule_worker.run_due(now)
        time.sleep(1)


if __name__ == "__main__":
    main()
