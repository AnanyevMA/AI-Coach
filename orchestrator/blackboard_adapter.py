"""
blackboard_adapter.py — AI Adaptive Coach v7.0 | Blackboard Abstraction Layer
Version: 2.0.0

Provides abstract BlackboardAdapter interface with FileSystemAdapter (default).
Switch to RedisAdapter or PostgreSQLAdapter by changing orchestration.adapter in agents_config.json.

Implements write-then-rename atomic writes to prevent corruption.
"""

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

import json
import shutil
import datetime
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Abstract Interface
# ---------------------------------------------------------------------------
class BlackboardAdapter(ABC):
    """Abstract Blackboard interface — swappable: FileSystem | Redis | PostgreSQL."""

    @abstractmethod
    def create_task(self, task: dict) -> str: ...

    @abstractmethod
    def update_task(self, task_id: str, patch: dict) -> None: ...

    @abstractmethod
    def get_task(self, task_id: str) -> Optional[dict]: ...

    @abstractmethod
    def list_by_status(self, status: str) -> list: ...

    @abstractmethod
    def archive_task(self, task_id: str) -> None: ...

    @abstractmethod
    def create_interrupt(self, task_id: str, data: dict) -> None: ...

    @abstractmethod
    def get_index(self) -> dict: ...


# ---------------------------------------------------------------------------
# FileSystem Adapter (default)
# ---------------------------------------------------------------------------
class FileSystemAdapter(BlackboardAdapter):
    """
    Stores tasks as JSON files in blackboard/tasks/.
    Atomic writes via write-to-temp-then-rename pattern.
    Zero infrastructure dependencies — git-trackable, human-readable.
    """

    def __init__(self,
                 tasks_path: Path,
                 interrupts_path: Path,
                 archive_path: Path):
        self.tasks_dir     = Path(tasks_path)
        self.interrupts_dir = Path(interrupts_path)
        self.archive_dir   = Path(archive_path)
        self.index_file    = self.tasks_dir.parent / "index.json"

        for d in [self.tasks_dir, self.interrupts_dir, self.archive_dir]:
            d.mkdir(parents=True, exist_ok=True)

        if not self.index_file.exists():
            self._write_json_atomic(self.index_file, {})

    # ---- CRUD ----

    def create_task(self, task: dict) -> str:
        task_id = task["task_id"]
        task_file = self.tasks_dir / f"{task_id}.json"
        if task_file.exists():
            raise FileExistsError(f"Task {task_id} already exists on Blackboard")
        self._write_json_atomic(task_file, task)
        self._update_index(task_id, task)
        return task_id

    def update_task(self, task_id: str, patch: dict) -> None:
        task_file = self.tasks_dir / f"{task_id}.json"
        if not task_file.exists():
            raise FileNotFoundError(f"Task {task_id} not found on Blackboard")
        patch["updated_at"] = datetime.datetime.now().isoformat()
        self._write_json_atomic(task_file, patch)
        self._update_index(task_id, patch)

    def get_task(self, task_id: str) -> Optional[dict]:
        task_file = self.tasks_dir / f"{task_id}.json"
        if not task_file.exists():
            return None
        return json.loads(task_file.read_text(encoding="utf-8"))

    def list_by_status(self, status: str) -> list:
        """Return all tasks matching status. Pass 'ALL' to return everything."""
        index = self.get_index()
        results = []
        for task_id, meta in index.items():
            if status == "ALL" or meta.get("status") == status:
                task = self.get_task(task_id)
                if task:
                    results.append(task)
        return results

    def archive_task(self, task_id: str) -> None:
        src = self.tasks_dir / f"{task_id}.json"
        dst = self.archive_dir / f"{task_id}.json"
        if src.exists():
            shutil.move(str(src), str(dst))
        index = self.get_index()
        if task_id in index:
            index[task_id]["status"] = "DONE"
            index[task_id]["archived_at"] = datetime.datetime.now().isoformat()
            self._write_json_atomic(self.index_file, index)

    def create_interrupt(self, task_id: str, data: dict) -> None:
        interrupt_file = self.interrupts_dir / f"INTERRUPT_REQ_{task_id}.json"
        self._write_json_atomic(interrupt_file, data)

    def get_index(self) -> dict:
        if not self.index_file.exists():
            return {}
        return json.loads(self.index_file.read_text(encoding="utf-8"))

    # ---- Atomic Write ----

    def _write_json_atomic(self, path: Path, data: dict) -> None:
        """Write JSON atomically: write to .tmp, then rename to target."""
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
        tmp.replace(path)

    def _update_index(self, task_id: str, task: dict) -> None:
        index = self.get_index()
        index[task_id] = {
            "status": task.get("status", "UNKNOWN"),
            "priority": task.get("priority", "NORMAL"),
            "title": task.get("title", ""),
            "domain": task.get("layer_routing", {}).get("domain", ""),
            "updated_at": task.get("updated_at", datetime.datetime.now().isoformat()),
        }
        self._write_json_atomic(self.index_file, index)


# ---------------------------------------------------------------------------
# Redis Adapter Stub (future)
# ---------------------------------------------------------------------------
class RedisAdapter(BlackboardAdapter):
    """Future adapter — swap in by setting orchestration.adapter='redis' in agents_config.json."""

    def __init__(self, host: str = "localhost", port: int = 6379, db: int = 0):
        raise NotImplementedError(
            "RedisAdapter not yet implemented. "
            "Set orchestration.adapter='filesystem' in agents_config.json."
        )

    def create_task(self, task): raise NotImplementedError
    def update_task(self, task_id, patch): raise NotImplementedError
    def get_task(self, task_id): raise NotImplementedError
    def list_by_status(self, status): raise NotImplementedError
    def archive_task(self, task_id): raise NotImplementedError
    def create_interrupt(self, task_id, data): raise NotImplementedError
    def get_index(self): raise NotImplementedError


# ---------------------------------------------------------------------------
# PostgreSQL Adapter Stub (future)
# ---------------------------------------------------------------------------
class PostgreSQLAdapter(BlackboardAdapter):
    """Future adapter — swap in by setting orchestration.adapter='postgresql' in agents_config.json."""

    def __init__(self, dsn: str):
        raise NotImplementedError(
            "PostgreSQLAdapter not yet implemented. "
            "Set orchestration.adapter='filesystem' in agents_config.json."
        )

    def create_task(self, task): raise NotImplementedError
    def update_task(self, task_id, patch): raise NotImplementedError
    def get_task(self, task_id): raise NotImplementedError
    def list_by_status(self, status): raise NotImplementedError
    def archive_task(self, task_id): raise NotImplementedError
    def create_interrupt(self, task_id, data): raise NotImplementedError
    def get_index(self): raise NotImplementedError
