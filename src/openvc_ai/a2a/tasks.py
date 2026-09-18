"""In-memory A2A task lifecycle store.

This is intentionally replaceable. A production deployment can swap this for
Redis, Postgres, or an event bus without changing API models.
"""

from __future__ import annotations

from openvc_ai.domain.models import (
    A2ATask,
    A2ATaskEvent,
    A2ATaskRequest,
    TaskPlan,
    TaskStatus,
    utc_now,
)


class InMemoryTaskStore:
    def __init__(self) -> None:
        self._tasks: dict[str, A2ATask] = {}

    def create(self, request: A2ATaskRequest) -> A2ATask:
        task = A2ATask(
            task_type=request.task_type,
            input=request.input,
            required_capabilities=request.required_capabilities,
            preferred_agent=request.preferred_agent,
            session_id=request.session_id,
        )
        self._tasks[task.task_id] = task
        self.add_event(task.task_id, TaskStatus.QUEUED, "Task accepted and queued.")
        return self._tasks[task.task_id]

    def get(self, task_id: str) -> A2ATask | None:
        return self._tasks.get(task_id)

    def list(self, limit: int = 50) -> list[A2ATask]:
        tasks = sorted(self._tasks.values(), key=lambda t: t.created_at, reverse=True)
        return tasks[: max(1, limit)]

    def active_count(self) -> int:
        return sum(
            1 for task in self._tasks.values() if task.status in {TaskStatus.QUEUED, TaskStatus.PLANNED, TaskStatus.RUNNING}
        )

    def set_plan(self, task_id: str, plan: TaskPlan) -> A2ATask:
        task = self._require(task_id)
        task.plan = plan
        task.status = TaskStatus.PLANNED
        task.updated_at = utc_now()
        self.add_event(
            task_id,
            TaskStatus.PLANNED,
            "Task plan built from agent registry and tool capabilities.",
            payload=plan.model_dump(mode="json"),
        )
        return task

    def update_status(
        self,
        task_id: str,
        status: TaskStatus,
        message: str,
        *,
        agent: str | None = None,
        payload: dict | None = None,
        assigned_agent: str | None = None,
    ) -> A2ATask:
        task = self._require(task_id)
        task.status = status
        task.updated_at = utc_now()
        if assigned_agent is not None:
            task.assigned_agent = assigned_agent
        self.add_event(task_id, status, message, agent=agent, payload=payload or {})
        return task

    def add_event(
        self,
        task_id: str,
        status: TaskStatus,
        message: str,
        *,
        agent: str | None = None,
        payload: dict | None = None,
    ) -> A2ATaskEvent:
        task = self._require(task_id)
        event = A2ATaskEvent(
            task_id=task_id,
            status=status,
            message=message,
            agent=agent,
            payload=payload or {},
        )
        task.events.append(event)
        task.updated_at = event.timestamp
        return event

    def _require(self, task_id: str) -> A2ATask:
        task = self._tasks.get(task_id)
        if not task:
            raise KeyError(f"Unknown task id: {task_id}")
        return task
