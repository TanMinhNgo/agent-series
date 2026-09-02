"""Combined local worker for persisted jobs and scheduled AI tasks."""

from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from threading import Event, Thread

from .background import BackgroundWorker
from .scheduler import build_worker
from ..persistence.store import BackgroundJobRepository

logger = logging.getLogger(__name__)


def run_cycle(schedule_worker, jobs: BackgroundJobRepository, now: datetime | None = None) -> None:
    """Process one persisted background job and any schedules currently due."""
    now = now or datetime.now(UTC)
    jobs.heartbeat(now)
    jobs.recover_stale(now)
    background_worker = BackgroundWorker(
        jobs,
        schedule_worker.services.knowledge,
        schedule_worker.services.memory,
        schedule_worker.services.chats,
        schedule_worker.services.settings.media_dir,
        schedule_worker.services.artifacts,
        schedule_worker.services.media.storage,
    )
    stop_heartbeat = Event()

    def heartbeat_while_busy() -> None:
        while not stop_heartbeat.wait(5):
            jobs.heartbeat(datetime.now(UTC), current_job_type="processing")

    heartbeat_thread = Thread(target=heartbeat_while_busy, daemon=True)
    heartbeat_thread.start()
    try:
        background_worker.run_once(now)
        schedule_worker.run_due(now)
    finally:
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=1)


def build_runtime():
    schedule_worker = build_worker()
    jobs = BackgroundJobRepository(schedule_worker.services.chats.database)
    while True:
        try:
            run_cycle(schedule_worker, jobs)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Worker cycle failed; retrying in 5 seconds")
            jobs.heartbeat(datetime.now(UTC), last_error=str(exc))
            time.sleep(5)
            continue
        time.sleep(1)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    while True:
        try:
            build_runtime()
        except Exception:  # noqa: BLE001
            # Failures before a database connection exists cannot be recorded
            # in worker_status, so keep the process alive and expose them in
            # the supervising PowerShell log.
            logger.exception("Worker could not start; retrying in 5 seconds")
            time.sleep(5)


if __name__ == "__main__":
    main()
