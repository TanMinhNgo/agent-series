from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select

from agent_core.persistence.database import Database
from agent_core.persistence.models import Schedule, ScheduleRun, utc_now


class ScheduleRepository:
    """Coordinate persisted schedule runs so multiple workers cannot run one job twice."""

    def __init__(self, database: Database):
        self.database = database

    @staticmethod
    def next_run_after(schedule: Schedule, now: datetime) -> datetime | None:
        if schedule.recurrence == "once":
            return None
        interval = timedelta(days=1 if schedule.recurrence == "daily" else 7)
        candidate = schedule.next_run_at or now
        if schedule.workflow_id:
            from zoneinfo import ZoneInfo
            if candidate.tzinfo is None:
                candidate = candidate.replace(tzinfo=UTC)
            candidate = candidate.astimezone(ZoneInfo(schedule.timezone))
        while candidate <= now:
            candidate += interval
        return candidate.astimezone(UTC) if schedule.workflow_id else candidate

    @staticmethod
    def _scheduled_slot(schedule: Schedule, now: datetime) -> datetime | None:
        scheduled_for = schedule.next_run_at
        if scheduled_for is None or not schedule.workflow_id:
            return scheduled_for
        from zoneinfo import ZoneInfo
        if scheduled_for.tzinfo is None:
            scheduled_for = scheduled_for.replace(tzinfo=UTC)
        interval = timedelta(days=1 if schedule.recurrence == "daily" else 7)
        local = scheduled_for.astimezone(ZoneInfo(schedule.timezone))
        while local + interval <= now:
            local += interval
        return local.astimezone(UTC)

    @classmethod
    def _advance_schedule(cls, schedule: Schedule, now: datetime) -> None:
        schedule.next_run_at = cls.next_run_after(schedule, now)
        if schedule.next_run_at is None:
            schedule.status = "completed"
        schedule.updated_at = now

    def claim_due(self, now: datetime) -> list[tuple[Schedule, ScheduleRun]]:
        claimed: list[tuple[Schedule, ScheduleRun]] = []
        with self.database.session() as session:
            schedules = session.scalars(
                select(Schedule)
                .where(Schedule.status == "active", Schedule.next_run_at.is_not(None), Schedule.next_run_at <= now)
                .with_for_update(skip_locked=True)
            ).all()
            for schedule in schedules:
                scheduled_for = self._scheduled_slot(schedule, now)
                if scheduled_for is None:
                    continue
                already_ran = session.scalar(
                    select(ScheduleRun.id)
                    .where(ScheduleRun.schedule_id == schedule.id, ScheduleRun.scheduled_for == scheduled_for)
                    .limit(1)
                )
                if already_ran is not None:
                    # This slot already has a run: editing a schedule rewinds
                    # `next_run_at` to `starts_at`, which can land on a past slot.
                    # Roll forward instead of inserting a duplicate, whose unique
                    # violation would abort the whole batch and stall the worker.
                    self._advance_schedule(schedule, now)
                    continue
                run = ScheduleRun(
                    schedule_id=schedule.id,
                    scheduled_for=scheduled_for,
                    status="running",
                    started_at=now,
                    heartbeat_at=now,
                    user_id=schedule.user_id,
                    workspace_id=schedule.workspace_id,
                )
                session.add(run)
                if schedule.workflow_id:
                    from agent_core.workflows.repository import WorkflowRepository
                    workflow_run = WorkflowRepository.enqueue_schedule(session, schedule, scheduled_for)
                    run.status, run.finished_at = "succeeded", now
                    run.summary = f"Workflow run: {workflow_run.id}"
                schedule.last_run_at = now
                self._advance_schedule(schedule, now)
                if not schedule.workflow_id:
                    claimed.append((schedule, run))
            session.commit()
            return claimed

    def claim_due_retries(self, now: datetime) -> list[tuple[Schedule, ScheduleRun]]:
        """Claim delayed provider retries without creating another schedule run."""
        with self.database.session() as session:
            rows = session.execute(
                select(Schedule, ScheduleRun)
                .join(ScheduleRun, ScheduleRun.schedule_id == Schedule.id)
                .where(ScheduleRun.status == "retrying", ScheduleRun.retry_at.is_not(None), ScheduleRun.retry_at <= now)
                .with_for_update(skip_locked=True)
            ).all()
            claimed: list[tuple[Schedule, ScheduleRun]] = []
            for schedule, run in rows:
                # `started_at` still points at the first attempt, so the heartbeat
                # must be refreshed or recovery would reclaim this retry at once.
                run.status, run.retry_at, run.heartbeat_at = "running", None, now
                claimed.append((schedule, run))
            session.commit()
            return claimed

    def claim_manual(self, schedule_id: str, now: datetime) -> tuple[Schedule, ScheduleRun] | None:
        with self.database.session() as session:
            schedule = session.get(Schedule, schedule_id, with_for_update=True)
            if schedule is None:
                return None
            if schedule.workflow_id:
                raise ValueError("Hãy chạy workflow từ Project; lịch này không tạo chat.")
            running = session.scalar(
                select(ScheduleRun.id)
                .where(ScheduleRun.schedule_id == schedule_id, ScheduleRun.status == "running")
                .limit(1)
            )
            if running is not None:
                raise ValueError("Lịch trình đang chạy. Hãy chờ lần chạy hiện tại hoàn tất.")
            pending_retries = session.scalars(
                select(ScheduleRun)
                .where(ScheduleRun.schedule_id == schedule_id, ScheduleRun.status == "retrying")
                .with_for_update()
            ).all()
            for pending in pending_retries:
                pending.status = "cancelled"
                pending.retry_at = None
                pending.error = "Đã thay bằng lần chạy thủ công."
                pending.finished_at = now
            run = ScheduleRun(
                schedule_id=schedule.id,
                scheduled_for=now,
                status="running",
                started_at=now,
                heartbeat_at=now,
                user_id=schedule.user_id,
            )
            session.add(run)
            schedule.last_run_at, schedule.updated_at = now, now
            session.commit()
            return schedule, run

    def enqueue_workflow_manual(self, schedule_id: str, now: datetime):
        from agent_core.workflows.repository import WorkflowRepository
        with self.database.session() as session:
            schedule = session.get(Schedule, schedule_id, with_for_update=True)
            if schedule is None or not schedule.workflow_id:
                raise ValueError("Không tìm thấy lịch workflow.")
            run = WorkflowRepository.enqueue_schedule(session, schedule, now)
            previous = session.scalar(select(ScheduleRun).where(ScheduleRun.schedule_id == schedule_id, ScheduleRun.scheduled_for == now))
            if previous is None:
                session.add(ScheduleRun(schedule_id=schedule.id, scheduled_for=now, status="succeeded",
                    started_at=now, finished_at=now, summary=f"Workflow run: {run.id}",
                    user_id=schedule.user_id, workspace_id=schedule.workspace_id))
            schedule.last_run_at = now
            session.commit()
            return run

    def schedule_retry(self, run_id: str, error: str, delays: tuple[int, ...], now: datetime | None = None) -> tuple[datetime, int] | None:
        """Queue one durable retry, returning its due time and retry number."""
        current_time = now or utc_now()
        with self.database.session() as session:
            run = session.get(ScheduleRun, run_id, with_for_update=True)
            if run is None or run.retry_count >= len(delays):
                return None
            retry_at = current_time + timedelta(minutes=delays[run.retry_count])
            run.retry_count += 1
            run.status, run.retry_at, run.error, run.finished_at = "retrying", retry_at, error, None
            session.commit()
            return retry_at, run.retry_count

    def finish(self, run_id: str, *, summary: str | None = None, error: str | None = None) -> ScheduleRun | None:
        with self.database.session() as session:
            run = session.get(ScheduleRun, run_id)
            if run is None:
                return None
            run.status = "failed" if error else "succeeded"
            run.summary, run.error, run.retry_at, run.finished_at = summary, error, None, utc_now()
            session.commit()
            return run

    def get_run(self, schedule_id: str, run_id: str) -> ScheduleRun | None:
        with self.database.session() as session:
            return session.scalar(select(ScheduleRun).where(ScheduleRun.id == run_id, ScheduleRun.schedule_id == schedule_id))

    def record_email(self, run_id: str, *, status: str, error: str | None = None) -> ScheduleRun | None:
        """Track notification delivery without touching the AI run outcome."""
        with self.database.session() as session:
            run = session.get(ScheduleRun, run_id)
            if run is None:
                return None
            run.email_status, run.email_error = status, error
            run.email_sent_at = utc_now() if status == "sent" else None
            session.commit()
            return run

    def recover_stale_runs(self, now: datetime, timeout: timedelta = timedelta(minutes=20)) -> int:
        with self.database.session() as session:
            stale = session.scalars(
                select(ScheduleRun).where(
                    ScheduleRun.status == "running",
                    # A slow run still reporting a heartbeat is alive, not stale.
                    # Only silence since the last beat (or the start, for runs
                    # predating heartbeats) means the worker really died.
                    func.coalesce(ScheduleRun.heartbeat_at, ScheduleRun.started_at) < now - timeout,
                )
            ).all()
            for run in stale:
                run.status, run.error, run.finished_at = "failed", "Worker timeout; hãy chạy lại thủ công.", now
            session.commit()
            return len(stale)

    def touch_run(self, run_id: str, now: datetime | None = None) -> bool:
        """Report that this run's worker is still alive; False once it is not ours."""
        with self.database.session() as session:
            run = session.get(ScheduleRun, run_id)
            if run is None or run.status != "running":
                return False
            run.heartbeat_at = now or utc_now()
            session.commit()
            return True

    def list_runs(self, schedule_id: str, limit: int = 30) -> list[ScheduleRun]:
        with self.database.session() as session:
            return list(session.scalars(select(ScheduleRun).where(ScheduleRun.schedule_id == schedule_id).order_by(ScheduleRun.started_at.desc()).limit(limit)))

    def attach_chat(self, schedule_id: str, chat_id: str) -> None:
        with self.database.session() as session:
            schedule = session.get(Schedule, schedule_id)
            if schedule is not None:
                schedule.chat_id, schedule.updated_at = chat_id, utc_now()
                session.commit()
