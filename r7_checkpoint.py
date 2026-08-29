"""R7 research-orchestration checkpoint snapshots for the UI V3 workbench.

This module deliberately separates two ideas:

1. durable snapshot: a compact, atomic JSON record of what the research DAG had
   completed at a meaningful recovery boundary;
2. resume execution: not wired yet at the orchestration layer.

The snapshot is therefore safe to inspect and survives process death, but the UI
must not claim that pressing a restore button will resume the DAG. The older V8
Agent Runtime still demonstrates task-level resume from an observation checkpoint.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import json
import os
from pathlib import Path
from typing import Iterable

from context import ExecutionContext


class JsonResearchCheckpointStore:
    """Atomic local store for research-run checkpoint view models."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    def _run_dir(self, run_id: str) -> Path:
        safe = "".join(ch for ch in run_id if ch.isalnum() or ch in {"-", "_"})
        if not safe:
            raise ValueError("run_id must contain a safe filename character")
        path = self.directory / safe
        path.mkdir(parents=True, exist_ok=True)
        return path

    def save(self, checkpoint: dict) -> Path:
        if not isinstance(checkpoint, dict):
            raise TypeError("checkpoint must be a dictionary")
        run_id = checkpoint.get("run_id")
        checkpoint_id = checkpoint.get("checkpoint_id")
        if not isinstance(run_id, str) or not run_id:
            raise ValueError("checkpoint.run_id must be a non-empty string")
        if not isinstance(checkpoint_id, str) or not checkpoint_id:
            raise ValueError("checkpoint.checkpoint_id must be a non-empty string")

        path = self._run_dir(run_id) / f"{checkpoint_id}.json"
        temp = path.with_suffix(".json.tmp")
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(checkpoint, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, path)
        return path

    def list(self, run_id: str) -> list[dict]:
        run_dir = self._run_dir(run_id)
        rows = []
        for path in sorted(run_dir.glob("CP-*.json")):
            with path.open("r", encoding="utf-8") as handle:
                rows.append(json.load(handle))
        return rows

    def latest(self, run_id: str) -> dict | None:
        rows = self.list(run_id)
        return rows[-1] if rows else None


class ResearchCheckpointRecorder:
    """Observe Scheduler events and persist meaningful research-DAG boundaries."""

    def __init__(
        self,
        *,
        run_id: str,
        execution_context: ExecutionContext,
        store: JsonResearchCheckpointStore,
    ):
        if not isinstance(execution_context, ExecutionContext):
            raise TypeError("execution_context must be an ExecutionContext")
        self.run_id = run_id
        self.execution_context = execution_context
        self.store = store
        self.sequence = 0
        self.evidence_ids: list[str] = []
        self.artifacts = {"S1": False, "D1": False, "F1": False}
        self._saved_boundaries: set[str] = set()
        self._checkpoints: list[dict] = []

    def observe(self, event: dict) -> None:
        if not isinstance(event, dict):
            return

        event_type = event.get("type")
        if event_type == "evidence_registered":
            evidence = event.get("evidence") or {}
            evidence_id = evidence.get("evidence_id")
            if evidence_id and evidence_id not in self.evidence_ids:
                self.evidence_ids.append(evidence_id)
            return

        if event_type == "plan_created":
            self._save_boundary("after_plan_created", event.get("plan") or {})
            return

        if event_type != "task_completed":
            return

        task_id = event.get("task_id")
        plan = event.get("plan") or {}
        if task_id in self.artifacts:
            self.artifacts[task_id] = True

        source_tasks = [
            task for task in (plan.get("tasks") or [])
            if str(task.get("task_id", "")).startswith("Q")
        ]
        if source_tasks and all(task.get("status") == "completed" for task in source_tasks):
            self._save_boundary("after_evidence", plan)

        if task_id == "S1":
            self._save_boundary("after_S1", plan)
        elif task_id == "D1":
            self._save_boundary("after_D1", plan)
        elif task_id == "F1":
            self._save_boundary("after_F1", plan)

    def checkpoints(self) -> list[dict]:
        return deepcopy(self._checkpoints)

    def latest(self) -> dict | None:
        return deepcopy(self._checkpoints[-1]) if self._checkpoints else None

    def _save_boundary(self, boundary: str, plan: dict) -> None:
        if boundary in self._saved_boundaries:
            return
        self._saved_boundaries.add(boundary)
        self.sequence += 1
        checkpoint = _checkpoint_view(
            checkpoint_id=f"CP-{self.sequence:03d}",
            run_id=self.run_id,
            boundary=boundary,
            execution_context=self.execution_context,
            plan=plan,
            evidence_ids=self.evidence_ids,
            artifacts=self.artifacts,
        )
        self.store.save(checkpoint)
        self._checkpoints.append(checkpoint)


def _checkpoint_view(
    *,
    checkpoint_id: str,
    run_id: str,
    boundary: str,
    execution_context: ExecutionContext,
    plan: dict,
    evidence_ids: Iterable[str],
    artifacts: dict,
) -> dict:
    tasks = list(plan.get("tasks") or [])
    by_status = {
        status: [task.get("task_id") for task in tasks if task.get("status") == status]
        for status in ("completed", "ready", "running", "blocked", "failed", "pending")
    }
    completed = set(by_status["completed"])
    dependency_ready = [
        task.get("task_id")
        for task in tasks
        if task.get("status") not in {"completed", "failed"}
        and set(task.get("depends_on") or []).issubset(completed)
    ]
    next_candidates = by_status["ready"] or by_status["running"] or dependency_ready
    return {
        "checkpoint_id": checkpoint_id,
        "run_id": run_id,
        "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "boundary": boundary,
        "durable": True,
        "restore_enabled": False,
        "execution_context": execution_context.to_dict(),
        "plan": {
            "status": plan.get("status"),
            "completed_tasks": by_status["completed"],
            "ready_tasks": by_status["ready"],
            "running_tasks": by_status["running"],
            "blocked_tasks": by_status["blocked"],
            "failed_tasks": by_status["failed"],
            "pending_tasks": by_status["pending"],
            "dependency_ready_tasks": dependency_ready,
        },
        "state": {
            "current_task": (by_status["running"] or next_candidates or [None])[0],
            "completed_count": len(by_status["completed"]),
            "task_count": len(tasks),
        },
        "evidence_ids": list(evidence_ids),
        "artifacts": {
            "S1": bool(artifacts.get("S1")),
            "D1": bool(artifacts.get("D1")),
            "F1": bool(artifacts.get("F1")),
        },
        "recovery": {
            "resume_candidate": (next_candidates or [None])[0],
            "snapshot_survives_process_death": True,
            "orchestrator_resume_wired": False,
            "note": (
                "Durable research snapshot only. Automatic DAG restore/resume is not wired yet; "
                "V8 Agent Runtime remains the task-level resume demonstration."
            ),
        },
    }
