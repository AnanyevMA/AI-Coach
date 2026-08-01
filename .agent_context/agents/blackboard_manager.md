# Agent State: blackboard_manager

> **Layer:** Core
> **Role:** Task Artifact Manager & Blackboard Index
> **Status:** Active
> **Version:** 2.0.0

---

## Primary Responsibilities

- Управляет хранилищем Task JSON-артефактов (`blackboard/tasks/`, `blackboard/interrupts/`)
- Обеспечивает атомарную запись (write-then-rename pattern) во избежание race conditions
- Ведёт индекс задач: статус, приоритет, дата обновления
- Предоставляет API: `create_task()`, `update_status()`, `get_tasks_by_status()`, `archive_task()`

## Blackboard Structure

```
blackboard/
  tasks/
    TASK-20260801-0001.json    ← активные задачи
    TASK-20260801-0002.json
  interrupts/
    INTERRUPT_REQ_TASK-0001.json  ← Human Escalation запросы
  archive/
    TASK-20260731-*.json       ← завершённые задачи (DONE/CANCELLED)
  index.json                   ← индекс всех задач {task_id: {status, priority, updated}}
```

## Adapter Interface

```python
class BlackboardAdapter:
    def create_task(task: dict) -> str: ...        # returns task_id
    def update_task(task_id: str, patch: dict): ... # atomic update
    def get_task(task_id: str) -> dict: ...
    def list_by_status(status: str) -> list: ...
    def create_interrupt(task_id: str, data: dict): ...
```

Реализации: `FileSystemAdapter` (default), `RedisAdapter`, `PostgreSQLAdapter`

## Key Artifacts

- [`orchestrator/blackboard_adapter.py`](file:///D:/PyCharm_Projects/AI%20Sport/orchestrator/blackboard_adapter.py)
- [`blackboard/`](file:///D:/PyCharm_Projects/AI%20Sport/blackboard/)

## Last Significant Actions

- 2026-08-01: Создан в рамках ЭТАПА 2 (заменяет отсутствующий Blackboard механизм)
