from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from agent_core.persistence.database import Database
from agent_core.persistence.models import BackgroundJob, WorkerStatus


class BackgroundJobRepository:
    def __init__(self, database: Database):
        self.database = database

    def enqueue(self, type: str, payload: dict, max_attempts: int = 3, dedupe_key: str | None = None) -> BackgroundJob:
        with self.database.session() as session:
            job = BackgroundJob(type=type, payload=payload, max_attempts=max_attempts, dedupe_key=dedupe_key)
            session.add(job)
            session.commit()
            return job

    def enqueue_unique(self, type: str, payload: dict, dedupe_key: str, max_attempts: int = 3) -> tuple[BackgroundJob, bool]:
        """Return an active equivalent job, or atomically create one."""
        with self.database.session() as session:
            active = session.scalar(
                select(BackgroundJob)
                .where(BackgroundJob.type == type, BackgroundJob.dedupe_key == dedupe_key, BackgroundJob.status.in_(("queued", "running")))
                .order_by(BackgroundJob.created_at.desc())
                .limit(1)
            )
            if active is not None:
                return active, False
            job = BackgroundJob(type=type, payload=payload, max_attempts=max_attempts, dedupe_key=dedupe_key)
            session.add(job)
            try:
                session.commit()
                return job, True
            except IntegrityError:
                session.rollback()
                active = session.scalar(
                    select(BackgroundJob)
                    .where(BackgroundJob.type == type, BackgroundJob.dedupe_key == dedupe_key, BackgroundJob.status.in_(("queued", "running")))
                    .order_by(BackgroundJob.created_at.desc())
                    .limit(1)
                )
                if active is None:
                    raise
                return active, False

    def latest_for_document(self, document_id: str) -> BackgroundJob | None:
        with self.database.session() as session:
            return session.scalar(
                select(BackgroundJob)
                .where(BackgroundJob.type == "document_index", BackgroundJob.dedupe_key == f"document:{document_id}")
                .order_by(BackgroundJob.created_at.desc())
                .limit(1)
            )

    def claim(self, now: datetime) -> BackgroundJob | None:
        with self.database.session() as session:
            job = session.scalar(
                select(BackgroundJob)
                .where(BackgroundJob.status == "queued", BackgroundJob.run_after <= now)
                .order_by(BackgroundJob.run_after, BackgroundJob.created_at)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if job is None:
                return None
            job.status, job.locked_at, job.attempts = "running", now, job.attempts + 1
            session.commit()
            return job

    def succeed(self, job_id: str) -> None:
        with self.database.session() as session:
            job = session.get(BackgroundJob, job_id)
            if job and job.status == "running":
                job.status, job.locked_at, job.last_error = "succeeded", None, None
                session.commit()

    def fail(self, job_id: str, error: str, now: datetime) -> None:
        with self.database.session() as session:
            job = session.get(BackgroundJob, job_id)
            if job is None or job.status != "running":
                return
            job.last_error, job.locked_at = error[:10_000], None
            if job.attempts >= job.max_attempts:
                job.status = "failed"
            else:
                job.status, job.run_after = "queued", now + timedelta(seconds=2 ** job.attempts)
            session.commit()

    def cancel_document_jobs(self, document_ids: list[str]) -> int:
        """Stop queued/running index jobs for documents removed by a Project deletion."""
        if not document_ids:
            return 0
        keys = [f"document:{document_id}" for document_id in document_ids]
        with self.database.session() as session:
            jobs = session.scalars(
                select(BackgroundJob).where(
                    BackgroundJob.type == "document_index",
                    BackgroundJob.dedupe_key.in_(keys),
                    BackgroundJob.status.in_(("queued", "running")),
                )
            ).all()
            for job in jobs:
                job.status, job.locked_at, job.last_error = "cancelled", None, "Tài liệu đã bị xóa."
            session.commit()
            return len(jobs)

    def recover_stale(self, now: datetime, timeout: timedelta = timedelta(minutes=20)) -> int:
        with self.database.session() as session:
            jobs = session.scalars(
                select(BackgroundJob).where(BackgroundJob.status == "running", BackgroundJob.locked_at < now - timeout)
            ).all()
            for job in jobs:
                job.status, job.locked_at, job.run_after = "queued", None, now
                job.last_error = "Worker stopped before finishing; queued again."
            session.commit()
            return len(jobs)

    def heartbeat(self, now: datetime, current_job_type: str | None = None, last_error: str | None = None) -> None:
        with self.database.session() as session:
            state = session.get(WorkerStatus, "default")
            if state is None:
                state = WorkerStatus(worker_id="default")
                session.add(state)
            state.last_heartbeat_at = now
            state.current_job_type = current_job_type
            if last_error:
                state.last_error = last_error[:10_000]
            session.commit()

    def worker_status(self, now: datetime) -> dict:
        with self.database.session() as session:
            state = session.get(WorkerStatus, "default")
            counts = dict(session.execute(select(BackgroundJob.status, func.count()).group_by(BackgroundJob.status)).all())
            last_failed = session.scalar(
                select(BackgroundJob).where(BackgroundJob.status == "failed").order_by(BackgroundJob.updated_at.desc()).limit(1)
            )
            heartbeat = state.last_heartbeat_at if state else None
            if heartbeat is not None and heartbeat.tzinfo is None:
                heartbeat = heartbeat.replace(tzinfo=now.tzinfo)
            last_error = state.last_error if state and state.last_error else None
            if last_error is None and last_failed:
                last_error = last_failed.last_error
            return {
                "online": bool(heartbeat and heartbeat >= now - timedelta(seconds=15)),
                "lastHeartbeatAt": heartbeat.isoformat() if heartbeat else None,
                "currentJobType": state.current_job_type if state else None,
                "queued": counts.get("queued", 0),
                "running": counts.get("running", 0),
                "failed": counts.get("failed", 0),
                "lastError": last_error,
            }
