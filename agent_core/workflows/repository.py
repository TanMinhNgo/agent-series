"""PostgreSQL queue with fenced checkpoints and resumable side effects."""
from copy import deepcopy
from datetime import UTC, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo
from uuid import NAMESPACE_URL, uuid4, uuid5

from sqlalchemy import or_, select

from agent_core.persistence.store import (
    LibraryAsset, Workflow, WorkflowRun, WorkflowStepRun, utc_now,
    current_user_id, current_workspace_id,
)
from .contracts import STEP_IDS

RETRY_MINUTES = (1, 5, 15)


class LeaseLost(RuntimeError):
    pass


class RunCancelled(RuntimeError):
    pass


class WorkflowConflict(ValueError):
    pass


def aware(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def completed(step):
    # Old failed runs marked unstarted steps skipped without output.
    return step.status == "succeeded" or (step.status == "skipped" and bool(step.output)
        and ((step.step_id == "agent" and "markdown" in step.output)
             or (step.step_id == "notification" and "reason" in step.output)))


class WorkflowRepository:
    def __init__(self, database):
        self.database = database

    def list(self, project_id):
        with self.database.session() as session:
            return list(session.scalars(select(Workflow).where(Workflow.project_id == project_id).order_by(Workflow.updated_at.desc())))

    def get(self, project_id, workflow_id):
        with self.database.session() as session:
            item = session.scalar(select(Workflow).where(Workflow.id == workflow_id, Workflow.project_id == project_id))
            if item is None:
                raise LookupError("Không tìm thấy workflow.")
            return item

    def save(self, project_id, config, workflow_id=None):
        with self.database.session() as session:
            if workflow_id:
                item = session.scalar(select(Workflow).where(Workflow.id == workflow_id, Workflow.project_id == project_id).with_for_update())
                if item is None:
                    raise LookupError("Không tìm thấy workflow.")
                item.revision += 1
            else:
                item = Workflow(project_id=project_id)
                session.add(item)
            item.name, item.config = config.name, config.model_dump()
            session.commit()
            return item

    @staticmethod
    def enqueue_in_session(session, workflow, period, key, user_id, workspace_id):
        # Serialize requests for this workflow; DB uniqueness is the final guard.
        session.scalar(select(Workflow.id).where(Workflow.id == workflow.id).with_for_update())
        if key:
            existing = session.scalar(select(WorkflowRun).where(
                WorkflowRun.workflow_id == workflow.id, WorkflowRun.user_id == user_id,
                WorkflowRun.idempotency_key == key,
            ))
            if existing:
                if (aware(existing.starts_at), aware(existing.ends_at)) != (aware(period.startsAt), aware(period.endsAt)):
                    raise WorkflowConflict("Idempotency-Key đã được dùng với khoảng dữ liệu khác.")
                return existing
        run = WorkflowRun(workflow_id=workflow.id, project_id=workflow.project_id,
            snapshot={**deepcopy(workflow.config), "revision": workflow.revision},
            starts_at=period.startsAt, ends_at=period.endsAt, user_id=user_id,
            workspace_id=workspace_id, idempotency_key=key)
        session.add(run)
        session.flush()
        session.add_all([WorkflowStepRun(run_id=run.id, step_id=step, position=index,
            user_id=user_id, workspace_id=workspace_id) for index, step in enumerate(STEP_IDS)])
        return run

    def enqueue(self, workflow, period, idempotency_key=None):
        with self.database.session() as session:
            run = self.enqueue_in_session(session, workflow, period, idempotency_key,
                current_user_id.get(), current_workspace_id.get())
            session.commit()
            return run

    @classmethod
    def enqueue_schedule(cls, session, schedule, scheduled_for):
        workflow = session.scalar(select(Workflow).where(Workflow.id == schedule.workflow_id,
            Workflow.project_id == schedule.project_id, Workflow.workspace_id == schedule.workspace_id).with_for_update())
        if workflow is None:
            raise LookupError("Workflow của lịch không còn tồn tại.")
        local = aware(scheduled_for).astimezone(ZoneInfo(schedule.timezone))
        end = local.replace(hour=0, minute=0, second=0, microsecond=0)
        if workflow.config.get("template") == "daily-ai-digest":
            start = end - timedelta(days=1)
        else:
            end -= timedelta(days=end.weekday())
            start = end - timedelta(days=7)
        period = SimpleNamespace(startsAt=start.astimezone(UTC), endsAt=end.astimezone(UTC))
        return cls.enqueue_in_session(session, workflow, period,
            f"schedule:{schedule.id}:{aware(scheduled_for).isoformat()}", schedule.user_id, schedule.workspace_id)

    def runs(self, project_id, workflow_id, status=None, limit=50):
        self.get(project_id, workflow_id)
        with self.database.session() as session:
            statement = select(WorkflowRun).where(WorkflowRun.workflow_id == workflow_id, WorkflowRun.project_id == project_id)
            if status:
                statement = statement.where(WorkflowRun.status == status)
            return list(session.scalars(statement.order_by(WorkflowRun.created_at.desc()).limit(min(limit, 100))))

    @staticmethod
    def _steps(session, run_id):
        return list(session.scalars(select(WorkflowStepRun).where(WorkflowStepRun.run_id == run_id).order_by(WorkflowStepRun.position)))

    def detail(self, project_id, run_id):
        with self.database.session() as session:
            run = session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id, WorkflowRun.project_id == project_id))
            if run is None:
                raise LookupError("Không tìm thấy lần chạy.")
            return run, self._steps(session, run.id)

    @staticmethod
    def _owned(session, run_id, token, now=None):
        now = now or utc_now()
        run = session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id).with_for_update())
        if (run is None or not token or run.lease_token != token or run.status != "running"
                or run.lease_until is None or aware(run.lease_until) <= aware(now)):
            raise LeaseLost("Worker không còn giữ lease của lần chạy.")
        return run

    def check(self, run_id, token):
        with self.database.session() as session:
            run = self._owned(session, run_id, token)
            if run.cancel_requested:
                raise RunCancelled("Lượt chạy đã bị hủy.")

    def claim(self, now=None, lease_seconds=120):
        now = now or utc_now()
        with self.database.session() as session:
            ready = select(WorkflowStepRun.run_id).where(WorkflowStepRun.run_id == WorkflowRun.id,
                WorkflowStepRun.status == "retrying", WorkflowStepRun.retry_at <= now).exists()
            run = session.scalar(select(WorkflowRun).where(or_(WorkflowRun.status == "queued",
                (WorkflowRun.status == "retrying") & ready,
                (WorkflowRun.status == "running") & or_(WorkflowRun.lease_until <= now, WorkflowRun.lease_until.is_(None))
            )).order_by(WorkflowRun.created_at).with_for_update(skip_locked=True).limit(1).execution_options(skip_user_scope=True))
            if run:
                run.status, run.started_at = "running", run.started_at or now
                run.lease_token, run.lease_until, run.heartbeat_at = str(uuid4()), now + timedelta(seconds=lease_seconds), now
                steps = session.scalars(select(WorkflowStepRun).where(WorkflowStepRun.run_id == run.id).execution_options(skip_user_scope=True))
                for step in steps:
                    if step.step_id == "notification" and step.status in {"running", "sending"}:
                        step.status, step.finished_at = "unknown", now
                        step.error = "Không xác định email đã được gửi hay chưa. Không tự gửi lại."
                    elif step.status in {"running", "retrying"}:
                        step.status, step.retry_at = "pending", None
                session.commit()
            return run

    def heartbeat(self, run_id, lease_token, now=None, lease_seconds=120):
        now = now or utc_now()
        with self.database.session() as session:
            try:
                run = self._owned(session, run_id, lease_token, now)
            except LeaseLost:
                return False
            run.heartbeat_at, run.lease_until = now, now + timedelta(seconds=lease_seconds)
            session.commit()
            return True

    def step(self, run_id, step_id, status, output=None, error=None, lease_token=None):
        with self.database.session() as session:
            run = self._owned(session, run_id, lease_token)
            if run.cancel_requested and status in {"running", "sending"}:
                raise RunCancelled("Lượt chạy đã bị hủy.")
            step = next(item for item in self._steps(session, run_id) if item.step_id == step_id)
            step.status, step.error, step.retry_at = status, error, None
            if output is not None:
                step.output = output
            if status in {"running", "sending"}:
                step.attempt += 1
                step.started_at, step.finished_at = utc_now(), None
            else:
                step.finished_at = utc_now()
            session.commit()

    def artifact_intent(self, run_id, token, content, storage):
        with self.database.session() as session:
            run = self._owned(session, run_id, token)
            if run.cancel_requested:
                raise RunCancelled("Lượt chạy đã bị hủy.")
            step = next(item for item in self._steps(session, run_id) if item.step_id == "artifact")
            if not step.output:
                step.output = {"assetId": str(uuid5(NAMESPACE_URL, f"workflow:{run_id}:artifact")),
                    "content": content, "provider": "imagekit" if storage.imagekit_enabled else "local"}
            session.commit()
            return step.output

    def publish_artifact(self, run_id, token, intent, stored):
        with self.database.session() as session:
            run = self._owned(session, run_id, token)
            step = next(item for item in self._steps(session, run_id) if item.step_id == "artifact")
            asset = session.get(LibraryAsset, intent["assetId"])
            if asset is None:
                asset = LibraryAsset(id=intent["assetId"], artifact_id=intent["assetId"],
                    name=f"workflow-report-{run_id}.md", stored_name=stored.stored_name,
                    storage_provider=stored.provider, storage_file_id=stored.file_id,
                    mime_type="text/markdown", size_bytes=len(intent["content"].encode("utf-8")),
                    source="generated", project_id=run.project_id, user_id=run.user_id,
                    workspace_id=run.workspace_id, is_project_source=True, index_status="queued")
                session.add(asset)
                session.flush()
            run.artifact_id = asset.id
            step.status, step.output, step.finished_at = "succeeded", {"artifactId": asset.id}, utc_now()
            session.commit()
            return asset.id

    def retry(self, run_id, step_id, error, lease_token, now=None):
        now = now or utc_now()
        with self.database.session() as session:
            run = self._owned(session, run_id, lease_token, now)
            if run.cancel_requested:
                raise RunCancelled("Lượt chạy đã bị hủy.")
            step = next(item for item in self._steps(session, run_id) if item.step_id == step_id)
            if not 1 <= step.attempt <= len(RETRY_MINUTES):
                return False
            step.status, step.error = "retrying", error
            step.retry_at = now + timedelta(minutes=RETRY_MINUTES[step.attempt - 1])
            step.finished_at = now
            run.status, run.lease_token, run.lease_until = "retrying", None, None
            session.commit()
            return True

    def finish(self, run_id, error=None, artifact_id=None, lease_token=None):
        with self.database.session() as session:
            run = self._owned(session, run_id, lease_token)
            run.status = "cancelled" if run.cancel_requested else ("failed" if error else "succeeded")
            run.error = "Lượt chạy đã bị hủy." if run.cancel_requested else error
            run.finished_at, run.lease_token, run.lease_until = utc_now(), None, None
            if artifact_id:
                run.artifact_id = artifact_id
            for step in self._steps(session, run_id):
                if step.status in {"pending", "running", "retrying"}:
                    step.status, step.finished_at = "skipped", utc_now()
            session.commit()

    def cancel(self, project_id, run_id):
        with self.database.session() as session:
            run = session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id, WorkflowRun.project_id == project_id).with_for_update())
            if not run:
                raise LookupError("Không tìm thấy lần chạy.")
            if run.status not in {"succeeded", "failed", "cancelled"}:
                run.cancel_requested = True
                if run.status in {"queued", "retrying"}:
                    run.status, run.finished_at, run.error = "cancelled", utc_now(), "Lượt chạy đã bị hủy."
                    for step in self._steps(session, run_id):
                        if step.status in {"pending", "retrying"}:
                            step.status, step.retry_at, step.finished_at = "skipped", None, utc_now()
                session.commit()
            return run

    def retry_run(self, project_id, run_id, step_id=None, confirm_resend=False):
        with self.database.session() as session:
            run = session.scalar(select(WorkflowRun).where(WorkflowRun.id == run_id, WorkflowRun.project_id == project_id).with_for_update())
            if not run:
                raise LookupError("Không tìm thấy lần chạy.")
            if run.status not in {"failed", "cancelled", "succeeded"}:
                raise WorkflowConflict("Lượt chạy chưa kết thúc.")
            steps = self._steps(session, run_id)
            target = next((item for item in steps if not completed(item)), None)
            if target is None or (step_id and target.step_id != step_id):
                raise WorkflowConflict("Chỉ retry bước chưa hoàn tất đầu tiên; hãy tạo run mới để chạy lại toàn bộ.")
            if target.status == "unknown" and not confirm_resend:
                raise WorkflowConflict("Cần xác nhận gửi lại email vì lần gửi trước không xác định.")
            if run.status == "succeeded" and target.step_id != "notification":
                raise WorkflowConflict("Lượt chạy đã hoàn tất.")
            for item in steps:
                if item.position >= target.position and not completed(item):
                    item.status, item.error, item.retry_at, item.finished_at = "pending", None, None, None
                    item.attempt = 0
            run.status, run.error, run.finished_at, run.cancel_requested = "queued", None, None, False
            run.lease_token, run.lease_until = None, None
            session.commit()
            return run
